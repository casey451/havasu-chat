"""Auto-publish engine for scraped class schedules (the schedule-hunt loop).

A scraped finding is a ``Contribution`` (source ``facebook_scrape``) carrying a
``confidence``, a ``target_entity_id``, and a ``proposed_record`` shaped like
:class:`~app.schemas.contribution.ProgramApprovalFields`. Publishing it ATTACHES
a recurring ``Schedule`` + ``Offering`` (+ optional ``ContactPoint``) to the
**existing** venue ``Entity`` — it never mints a duplicate venue.

This is deliberately narrower and safer than the manual approval path
(``app/contrib/approval_service.py``), which creates brand-new Program/Event/
Provider entities. Auto-publish only does the idempotent attach-to-existing-venue
case; anything that doesn't cleanly resolve to an existing entity, or whose
payload doesn't validate, returns ``skipped`` and the contribution stays
``pending`` for manual review in ``/admin/contributions``.

Reused: ``reconcile_hit`` (strong-signal entity match), the Schedule/Offering/
SourceEvidence construction shapes from ``app/db/entity_dual_write.py``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import reconcile_hit
from app.db.models import (
    ContactPoint,
    Contribution,
    Entity,
    Offering,
    Schedule,
    SourceEvidence,
)
from app.schemas.contribution import ProgramApprovalFields

logger = logging.getLogger(__name__)


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_hhmm(value: str | None) -> time | None:
    """Parse an ``HH:MM`` string to ``time``; ``None`` on empty/malformed."""
    if not value:
        return None
    try:
        h, m = value.strip().split(":", 1)
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return None


def parse_proposed_program(contribution: Contribution) -> ProgramApprovalFields | None:
    """Validate ``proposed_record`` into ProgramApprovalFields; ``None`` if absent/invalid."""
    raw = contribution.proposed_record
    if not isinstance(raw, dict):
        return None
    try:
        return ProgramApprovalFields(**raw)
    except (ValidationError, TypeError):
        return None


def resolve_target_entity(db: Session, contribution: Contribution) -> str | None:
    """The existing Entity id this contribution targets, or ``None``.

    1. Explicit ``target_entity_id`` (worker-supplied) when it names a real Entity
       — the precise, primary path for the schedule-hunt loop.
    2. Else reconcile by name/website/geo via :func:`reconcile_hit`, accepting
       ONLY a strong ``action == "update"`` match (google_place_id / geo+name /
       contact-tier). Name-only matches are ``ambiguous`` → ``None`` → the
       contribution stays for manual review (never auto-link on a weak signal).
    """
    tid = (contribution.target_entity_id or "").strip()
    if tid and db.get(Entity, tid) is not None:
        return tid
    payload = EntityPayload(
        name=contribution.submission_name,
        entity_type=contribution.entity_type,
        website=str(contribution.submission_url) if contribution.submission_url else None,
        source="facebook_scrape",
    )
    result = reconcile_hit(db, payload)
    if result.action == "update" and result.existing_id:
        return result.existing_id
    return None


def attach_schedule_to_entity(
    db: Session, entity_id: str, fields: ProgramApprovalFields, *, source: str, source_url: str | None
) -> None:
    """Write a recurring Schedule + Offering (+ contacts + evidence) onto an
    existing entity. No new Entity, no Program row (audit lives on the
    contribution's ``created_entity_id``)."""
    db.add(
        Offering(
            entity_id=entity_id,
            name=fields.title[:255],
            description=fields.description,
            price_text=(fields.cost or "")[:64] if fields.cost else None,
            price_min_cents=None,
            price_max_cents=None,
            duration_minutes=None,
            url=None,
            display_order=0,
            created_at=_utc_now_naive(),
            updated_at=_utc_now_naive(),
        )
    )
    db.add(
        Schedule(
            entity_id=entity_id,
            schedule_type="recurring",
            start_date=None,
            end_date=None,
            start_time=_parse_hhmm(fields.schedule_start_time),
            end_time=_parse_hhmm(fields.schedule_end_time),
            recurrence_rule=None,
            days_of_week=list(fields.schedule_days or []),
            capacity=None,
            capacity_label=None,
            notes=None,
            created_at=_utc_now_naive(),
            updated_at=_utc_now_naive(),
        )
    )
    for kind, value in (
        ("phone", fields.contact_phone),
        ("email", fields.contact_email),
        ("website", fields.contact_url),
    ):
        if value and str(value).strip():
            db.add(
                ContactPoint(
                    entity_id=entity_id,
                    kind=kind,
                    value=str(value).strip()[:512],
                    label=None,
                    display_order=0,
                    is_primary=False,
                    created_at=_utc_now_naive(),
                )
            )
    db.add(
        SourceEvidence(
            entity_id=entity_id,
            field_path="(schedule_hunt)",
            source_type=(source or "facebook_scrape")[:64],
            source_url=source_url,
            verified_at=None,
            verification_method=None,
            notes=None,
            created_at=_utc_now_naive(),
        )
    )


def _already_published(contribution: Contribution) -> bool:
    return bool(
        contribution.created_entity_id
        or contribution.created_program_id
        or contribution.created_event_id
        or contribution.created_provider_id
    )


def publish_contribution(db: Session, contribution: Contribution) -> dict:
    """Attach a scraped class schedule to its existing venue. Idempotent.

    Returns ``{"status": "published", "entity_id": ...}`` on success, else
    ``{"status": "skipped", "reason": ...}`` leaving the contribution pending.
    Skips (safe, no write) when: not pending, already published, the
    proposed_record is missing/invalid, or no existing entity resolves.
    """
    if contribution.status != "pending":
        return {"status": "skipped", "reason": "not_pending"}
    if _already_published(contribution):
        return {"status": "skipped", "reason": "already_published"}

    fields = parse_proposed_program(contribution)
    if fields is None:
        return {"status": "skipped", "reason": "invalid_proposed_record"}

    entity_id = resolve_target_entity(db, contribution)
    if entity_id is None:
        return {"status": "skipped", "reason": "no_entity_match"}

    attach_schedule_to_entity(
        db,
        entity_id,
        fields,
        source=contribution.source,
        source_url=contribution.source_url or (
            str(contribution.submission_url) if contribution.submission_url else None
        ),
    )
    contribution.created_entity_id = entity_id
    contribution.status = "approved"
    contribution.reviewed_at = _utc_now_naive()
    db.commit()
    db.refresh(contribution)
    logger.info(
        "schedule_hunt auto-published contribution %s -> entity %s",
        contribution.id,
        entity_id,
    )
    return {"status": "published", "entity_id": entity_id}
