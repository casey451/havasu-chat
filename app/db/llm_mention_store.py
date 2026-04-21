"""CRUD helpers for ``llm_mentioned_entities`` (Phase 5.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import LlmMentionedEntity


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_mention(
    db: Session,
    chat_log_id: str,
    mentioned_name: str,
    context_snippet: str | None,
) -> LlmMentionedEntity | None:
    """Insert a mention. Returns None if unique constraint violated (duplicate)."""
    row = LlmMentionedEntity(
        chat_log_id=chat_log_id,
        mentioned_name=mentioned_name[:300],
        context_snippet=(context_snippet or "")[:500] or None,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        return None


def get_mention(db: Session, mention_id: int) -> LlmMentionedEntity | None:
    return db.get(LlmMentionedEntity, mention_id)


def list_mentions(
    db: Session,
    status: str | None = None,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[LlmMentionedEntity]:
    stmt = select(LlmMentionedEntity).order_by(desc(LlmMentionedEntity.detected_at))
    if status is not None:
        stmt = stmt.where(LlmMentionedEntity.status == status)
    if detected_from is not None:
        stmt = stmt.where(LlmMentionedEntity.detected_at >= detected_from)
    if detected_to is not None:
        stmt = stmt.where(LlmMentionedEntity.detected_at <= detected_to)
    stmt = stmt.offset(offset).limit(limit)
    return db.execute(stmt).scalars().all()


def count_mentions(
    db: Session,
    status: str | None = None,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
) -> int:
    stmt = select(func.count()).select_from(LlmMentionedEntity)
    if status is not None:
        stmt = stmt.where(LlmMentionedEntity.status == status)
    if detected_from is not None:
        stmt = stmt.where(LlmMentionedEntity.detected_at >= detected_from)
    if detected_to is not None:
        stmt = stmt.where(LlmMentionedEntity.detected_at <= detected_to)
    return int(db.execute(stmt).scalar_one() or 0)


def dismiss_mention(
    db: Session,
    mention_id: int,
    dismissal_reason: str,
) -> LlmMentionedEntity | None:
    row = db.get(LlmMentionedEntity, mention_id)
    if row is None:
        return None
    row.status = "dismissed"
    row.dismissal_reason = dismissal_reason[:128]
    row.reviewed_at = _naive_utc_now()
    db.commit()
    db.refresh(row)
    return row


def promote_mention(
    db: Session,
    mention_id: int,
    contribution_id: int,
) -> LlmMentionedEntity | None:
    row = db.get(LlmMentionedEntity, mention_id)
    if row is None:
        return None
    row.status = "promoted"
    row.promoted_to_contribution_id = contribution_id
    row.reviewed_at = _naive_utc_now()
    row.dismissal_reason = None
    db.commit()
    db.refresh(row)
    return row
