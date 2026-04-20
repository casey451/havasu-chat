"""CRUD helpers for ``contributions`` (Phase 5.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import Contribution
from app.schemas.contribution import ContributionCreate

_VALID_STATUSES = frozenset({"pending", "approved", "rejected", "needs_info"})


def normalize_submission_url(url: str | None) -> str | None:
    """Normalize URL for duplicate detection (strip, lowercase, drop trailing slash)."""
    if url is None:
        return None
    s = str(url).strip()
    if not s:
        return None
    return s.lower().rstrip("/")


def has_pending_or_approved_duplicate_url(db: Session, normalized_url: str | None) -> bool:
    """True if another contribution already has this URL while pending or approved."""
    if not normalized_url:
        return False
    stmt = select(Contribution.submission_url).where(
        Contribution.status.in_(("pending", "approved")),
        Contribution.submission_url.isnot(None),
    )
    for u in db.execute(stmt).scalars().all():
        if normalize_submission_url(u) == normalized_url:
            return True
    return False


def count_submissions_since_by_ip_hash(db: Session, ip_hash: str, since: datetime) -> int:
    """Count contributions from this IP hash with submitted_at >= since (naive UTC)."""
    n = db.scalar(
        select(func.count())
        .select_from(Contribution)
        .where(
            Contribution.submitter_ip_hash == ip_hash,
            Contribution.submitted_at >= since,
        )
    )
    return int(n or 0)


def create_contribution(
    db: Session,
    data: ContributionCreate,
    submitter_ip_hash: str | None = None,
) -> Contribution:
    """Insert a new contribution. Returns the created row."""
    url_str = str(data.submission_url) if data.submission_url is not None else None
    row = Contribution(
        entity_type=data.entity_type,
        submission_name=data.submission_name.strip(),
        submission_url=url_str,
        submission_category_hint=data.submission_category_hint,
        submission_notes=data.submission_notes,
        event_date=data.event_date,
        event_time_start=data.event_time_start,
        event_time_end=data.event_time_end,
        submitter_email=str(data.submitter_email) if data.submitter_email is not None else None,
        submitter_ip_hash=submitter_ip_hash,
        source=data.source,
        llm_source_chat_log_id=data.llm_source_chat_log_id,
        unverified=data.unverified,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_contribution(db: Session, contribution_id: int) -> Contribution | None:
    """Fetch by ID. Returns None if not found."""
    return db.get(Contribution, contribution_id)


def list_contributions(
    db: Session,
    status: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Contribution]:
    """List contributions with optional filters. Sorted by submitted_at DESC."""
    stmt = select(Contribution).order_by(desc(Contribution.submitted_at))
    if status is not None:
        stmt = stmt.where(Contribution.status == status)
    if entity_type is not None:
        stmt = stmt.where(Contribution.entity_type == entity_type)
    if source is not None:
        stmt = stmt.where(Contribution.source == source)
    stmt = stmt.offset(offset).limit(limit)
    return db.execute(stmt).scalars().all()


def count_contributions(
    db: Session,
    status: str | None = None,
    entity_type: str | None = None,
    source: str | None = None,
) -> int:
    """Count rows matching the same filters as ``list_contributions``."""
    stmt = select(func.count()).select_from(Contribution)
    if status is not None:
        stmt = stmt.where(Contribution.status == status)
    if entity_type is not None:
        stmt = stmt.where(Contribution.entity_type == entity_type)
    if source is not None:
        stmt = stmt.where(Contribution.source == source)
    n = db.execute(stmt).scalar_one()
    return int(n)


def update_contribution_status(
    db: Session,
    contribution_id: int,
    status: str,
    review_notes: str | None = None,
    rejection_reason: str | None = None,
) -> Contribution | None:
    """Update status. Sets reviewed_at = now (UTC, naive) on each update. Returns updated row or None."""
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    row = db.get(Contribution, contribution_id)
    if row is None:
        return None
    row.status = status
    if review_notes is not None:
        row.review_notes = review_notes
    if status == "rejected":
        row.rejection_reason = rejection_reason
    else:
        row.rejection_reason = None
    row.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.refresh(row)
    return row
