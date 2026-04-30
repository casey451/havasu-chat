"""Create catalog rows from approved contributions (Phase 5.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy.orm import Session

from app.contrib.hours_helper import places_hours_to_structured
from app.core.event_recurrence import event_text_blob, is_recurring_heuristic
from app.db.contribution_store import normalize_submission_url
from app.db.models import Contribution, Event, Program, Provider
from app.schemas.contribution import EventApprovalFields, ProgramApprovalFields, ProviderApprovalFields
from app.schemas.event import EventCreate
from app.schemas.program import ProgramCreate


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def enrichment_suggests_verified(contribution: Contribution) -> bool:
    """True when URL fetch or Places lookup gave usable signal (Phase 5.3 acceptance)."""
    if (contribution.url_fetch_status or "").strip().lower() == "success":
        return True
    ged = contribution.google_enriched_data
    if isinstance(ged, dict):
        ls = ged.get("lookup_status")
        if ls in ("success", "low_confidence"):
            return True
    return False


def _load_pending_contribution(db: Session, contribution_id: int, entity_type: str) -> Contribution:
    row = db.get(Contribution, contribution_id)
    if row is None:
        raise ValueError("contribution not found")
    if row.status != "pending":
        raise ValueError("contribution is not pending")
    if row.entity_type != entity_type:
        raise ValueError("entity type mismatch")
    return row


def approve_contribution_as_provider(
    db: Session,
    contribution_id: int,
    edited_fields: ProviderApprovalFields,
    category: str,
    reviewed_by: str | None = None,
) -> Provider:
    """Create a Provider row from contribution + edits. Update contribution."""
    _ = reviewed_by
    cat = (category or "").strip()
    if not cat:
        raise ValueError("category is required")

    c = _load_pending_contribution(db, contribution_id, "provider")
    verified = enrichment_suggests_verified(c)
    src = "user" if c.source == "user_submission" else "admin"
    website = (edited_fields.website or "").strip() or None
    hours_structured: dict | None = None
    ged = c.google_enriched_data
    if isinstance(ged, dict):
        roh = ged.get("regular_opening_hours")
        if isinstance(roh, dict):
            conv = places_hours_to_structured(roh)
            if conv:
                hours_structured = conv
    prov = Provider(
        provider_name=edited_fields.name.strip(),
        category=cat,
        address=(edited_fields.address or "").strip() or None,
        phone=(edited_fields.phone or "").strip() or None,
        hours=(edited_fields.hours or "").strip() or None,
        hours_structured=hours_structured,
        description=(edited_fields.description or "").strip() or None,
        website=website,
        draft=False,
        is_active=True,
        verified=verified,
        pending_review=False,
        source=src,
    )
    try:
        db.add(prov)
        db.flush()
        c.status = "approved"
        c.reviewed_at = _naive_utc_now()
        c.created_provider_id = prov.id
        c.rejection_reason = None
        c.review_notes = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(prov)
    return prov


def approve_contribution_as_program(
    db: Session,
    contribution_id: int,
    edited_fields: ProgramApprovalFields,
    category: str,
    reviewed_by: str | None = None,
) -> Program:
    """Create a Program row. Update contribution."""
    _ = reviewed_by
    act = (category or "").strip()
    if not act:
        raise ValueError("activity_category is required")

    c = _load_pending_contribution(db, contribution_id, "program")
    verified = enrichment_suggests_verified(c)
    payload = ProgramCreate(
        title=edited_fields.title.strip(),
        description=edited_fields.description.strip(),
        activity_category=act,
        age_min=edited_fields.age_min,
        age_max=edited_fields.age_max,
        schedule_days=list(edited_fields.schedule_days or []),
        schedule_start_time=edited_fields.schedule_start_time.strip(),
        schedule_end_time=edited_fields.schedule_end_time.strip(),
        location_name=edited_fields.location_name.strip(),
        location_address=(edited_fields.location_address or "").strip() or None,
        cost=(edited_fields.cost or "").strip() or None,
        provider_name=edited_fields.provider_name.strip(),
        contact_phone=(edited_fields.contact_phone or "").strip() or None,
        contact_email=(edited_fields.contact_email or "").strip() or None,
        contact_url=(edited_fields.contact_url or "").strip() or None,
        source="admin",
        is_active=True,
        tags=list(edited_fields.tags or []),
    )
    prog = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=payload.schedule_days,
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        verified=verified,
        is_active=True,
        tags=list(payload.tags),
        draft=False,
        pending_review=False,
    )
    try:
        db.add(prog)
        db.flush()
        c.status = "approved"
        c.reviewed_at = _naive_utc_now()
        c.created_program_id = prog.id
        c.rejection_reason = None
        c.review_notes = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(prog)
    return prog


def approve_contribution_as_event(
    db: Session,
    contribution_id: int,
    edited_fields: EventApprovalFields,
    tags: list[str],
    reviewed_by: str | None = None,
) -> Event:
    """Create an Event row. Update contribution."""
    _ = reviewed_by
    c = _load_pending_contribution(db, contribution_id, "event")
    verified = enrichment_suggests_verified(c)
    created_by = "user" if c.source == "user_submission" else "admin"
    blob = event_text_blob(
        edited_fields.title.strip(),
        edited_fields.description.strip(),
        list(tags or []),
    )
    is_rec = is_recurring_heuristic(blob)
    event_source: str | None = "river_scene_import" if c.source == "river_scene_import" else None
    event_source_url = (
        normalize_submission_url(c.source_url) if c.source_url else None
    )
    end_date = edited_fields.end_date if edited_fields.end_date is not None else c.event_end_date
    ec = EventCreate(
        title=edited_fields.title.strip(),
        date=edited_fields.date,
        end_date=end_date,
        start_time=edited_fields.start_time,
        end_time=edited_fields.end_time,
        location_name=edited_fields.location_name.strip(),
        description=edited_fields.description.strip(),
        event_url=edited_fields.event_url.strip(),
        source_url=event_source_url,
        contact_name=None,
        contact_phone=None,
        tags=list(tags or []),
        is_recurring=is_rec,
        source=event_source,
        status="live",
        created_by=created_by,
    )
    ev = Event.from_create(ec)
    ev.verified = verified
    try:
        db.add(ev)
        db.flush()
        c.status = "approved"
        c.reviewed_at = _naive_utc_now()
        c.created_event_id = ev.id
        c.rejection_reason = None
        c.review_notes = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(ev)
    return ev


def parse_comma_tags(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def parse_schedule_days_field(raw: str | None) -> list[str]:
    """Split comma-separated day names into stripped lowercase tokens (validated by ProgramCreate)."""
    if not raw or not str(raw).strip():
        return []
    return [p.strip().lower() for p in str(raw).split(",") if p.strip()]
