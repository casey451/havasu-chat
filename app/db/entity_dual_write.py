"""Phase 1D — dual-write Provider/Event/Program rows into ENTITY + extensions.

Each helper persists the legacy row and matching ``entities`` row (+ extensions)
in the same SQLAlchemy session and wires ``legacy.entity_id = entity.id``.

Idempotency: calling a helper again on an object that already has ``entity_id``
(or reusing the same slug-backed Provider row that was fully written) returns
the existing pair without inserting duplicate ENTITY graphs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.entity_backfill import _WEEKDAY_KEYS, _parse_hours_time
from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PROGRAM,
)
from app.db.models import (
    ContactPoint,
    Entity,
    EntityCategory,
    Event,
    Hours,
    Location,
    Offering,
    Program,
    Provider,
    Schedule,
    SourceEvidence,
)
from app.db.seed_helpers import derive_provider_slug
from app.utils.slug import make_unique_slug, slugify

_DEFAULT_CITY = "Lake Havasu City"
_DEFAULT_STATE = "AZ"


def _location_address_fields(raw: str | None) -> tuple[str | None, str | None]:
    """Truncate to locations.address / address_normalized VARCHAR(255) limits."""
    addr = (raw or "").strip() or None
    if addr is None:
        return None, None
    addr = addr[:255]
    return addr, addr.lower()[:255]


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _entity_slug_pool(db: Session) -> set[str]:
    return set(db.scalars(select(Entity.slug)).all())


def _allocate_entity_slug(db: Session, title_or_name: str, *, max_len: int = 96) -> str:
    base = slugify(title_or_name)[:max_len]
    used = _entity_slug_pool(db)
    for obj in db.new:
        if isinstance(obj, Entity) and obj.slug:
            used.add(obj.slug)
    return make_unique_slug(base, used, max_length=max_len)


def _get_entity_maybe_pending(db: Session, entity_id: str) -> Entity | None:
    inst = db.get(Entity, entity_id)
    if inst is not None:
        return inst
    for obj in db.new:
        if isinstance(obj, Entity) and obj.id == entity_id:
            return obj
    return None


def create_provider_and_entity(db: Session, provider: Provider) -> tuple[Provider, Entity]:
    """Insert ENTITY graph for a Provider row; set ``provider.entity_id``."""
    if provider.entity_id:
        existing = _get_entity_maybe_pending(db, provider.entity_id)
        if existing is not None:
            return provider, existing

    if not provider.slug:
        provider.slug = derive_provider_slug(db, provider.provider_name)

    ent = Entity(
        id=str(uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=provider.slug,
        name=provider.provider_name,
        description=provider.description,
        last_verified_at=provider.last_verified_at,
        source=(provider.source or "seed")[:64],
        is_active=bool(provider.is_active),
        liveness_score=provider.liveness_score,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )
    db.add(ent)
    _attach_provider_extensions(db, ent.id, provider)
    provider.entity_id = ent.id
    return provider, ent


def _attach_provider_extensions(db: Session, entity_id: str, provider: Provider) -> None:
    if provider.category_id is not None:
        db.add(
            EntityCategory(
                entity_id=entity_id,
                category_id=provider.category_id,
                is_primary=True,
                created_at=_utc_now_naive(),
            )
        )

    addr, addr_norm = _location_address_fields(provider.address)
    db.add(
        Location(
            entity_id=entity_id,
            address=addr,
            address_normalized=addr_norm,
            city=_DEFAULT_CITY,
            state=_DEFAULT_STATE,
            zip=provider.zip,
            lat=provider.lat,
            lng=provider.lng,
            google_place_id=provider.google_place_id,
            district=(provider.district or "")[:64] or None,
            created_at=_utc_now_naive(),
            updated_at=_utc_now_naive(),
        )
    )

    hs = provider.hours_structured
    if isinstance(hs, str):
        try:
            hs = json.loads(hs)
        except json.JSONDecodeError:
            hs = None
    if isinstance(hs, dict):
        for di, day_key in enumerate(_WEEKDAY_KEYS):
            spans = hs.get(day_key)
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                open_raw = span.get("open") or span.get("opens")
                close_raw = span.get("close") or span.get("closes") or span.get("closes_at")
                ot = _parse_hours_time(str(open_raw) if open_raw is not None else None)
                ct = _parse_hours_time(str(close_raw) if close_raw is not None else None)
                if ot is None and ct is None:
                    continue
                db.add(
                    Hours(
                        entity_id=entity_id,
                        day_of_week=di,
                        opens_at=ot,
                        closes_at=ct,
                        is_24h=False,
                        notes=None,
                        created_at=_utc_now_naive(),
                    )
                )

    _add_contact(db, entity_id, "phone", provider.phone, is_primary=True)
    _add_contact(db, entity_id, "email", provider.email, is_primary=False)
    _add_contact(db, entity_id, "website", provider.website, is_primary=False)
    _add_contact(db, entity_id, "facebook", provider.facebook, is_primary=False)

    db.add(
        SourceEvidence(
            entity_id=entity_id,
            field_path="(provider_record)",
            source_type=(provider.source or "seed")[:64],
            source_url=None,
            verified_at=provider.last_verified_at,
            verification_method=provider.verification_method,
            notes=None,
            created_at=_utc_now_naive(),
        )
    )


def _add_contact(
    db: Session,
    entity_id: str,
    kind: str,
    value: str | None,
    *,
    is_primary: bool,
    label: str | None = None,
) -> None:
    if not value or not str(value).strip():
        return
    db.add(
        ContactPoint(
            entity_id=entity_id,
            kind=kind,
            value=str(value).strip()[:512],
            label=label,
            display_order=0,
            is_primary=is_primary,
            created_at=_utc_now_naive(),
        )
    )


def create_event_and_entity(db: Session, event: Event) -> tuple[Event, Entity]:
    if event.entity_id:
        existing = _get_entity_maybe_pending(db, event.entity_id)
        if existing is not None:
            return event, existing

    slug = _allocate_entity_slug(db, event.title)
    is_live = (event.status or "").lower() == "live"
    created_at = event.created_at or _utc_now_naive()
    ent = Entity(
        id=str(uuid4()),
        entity_type=ENTITY_TYPE_EVENT,
        slug=slug,
        name=event.title,
        description=event.description,
        last_verified_at=event.last_verified_at,
        source=(event.source or "admin")[:64],
        is_active=is_live,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(ent)

    loc = (event.location_name or "").strip()
    if loc:
        addr, addr_norm = _location_address_fields(loc)
        db.add(
            Location(
                entity_id=ent.id,
                address=addr,
                address_normalized=addr_norm,
                city=None,
                state=None,
                zip=None,
                lat=None,
                lng=None,
                google_place_id=None,
                district=None,
                created_at=_utc_now_naive(),
                updated_at=_utc_now_naive(),
            )
        )

    db.add(
        Schedule(
            entity_id=ent.id,
            schedule_type="one_off",
            start_date=event.date,
            end_date=event.end_date,
            start_time=event.start_time,
            end_time=event.end_time,
            recurrence_rule=None,
            days_of_week=None,
            capacity=None,
            capacity_label=None,
            notes=None,
            created_at=_utc_now_naive(),
            updated_at=_utc_now_naive(),
        )
    )

    label = (event.contact_name or "").strip() or None
    if event.contact_phone and str(event.contact_phone).strip():
        _add_contact(db, ent.id, "phone", event.contact_phone, is_primary=True, label=label)
    elif label:
        _add_contact(db, ent.id, "other", label, is_primary=False)

    eu = (event.event_url or "").strip()
    if eu:
        _add_contact(db, ent.id, "website", eu, is_primary=False)

    db.add(
        SourceEvidence(
            entity_id=ent.id,
            field_path="(event_record)",
            source_type=(event.source or "admin")[:64],
            source_url=None,
            verified_at=event.last_verified_at,
            verification_method=None,
            notes=None,
            created_at=_utc_now_naive(),
        )
    )

    event.entity_id = ent.id
    return event, ent


def create_program_and_entity(db: Session, program: Program) -> tuple[Program, Entity]:
    if program.entity_id:
        existing = _get_entity_maybe_pending(db, program.entity_id)
        if existing is not None:
            return program, existing

    slug = _allocate_entity_slug(db, program.title)
    ent = Entity(
        id=str(uuid4()),
        entity_type=ENTITY_TYPE_PROGRAM,
        slug=slug,
        name=program.title,
        description=program.description,
        last_verified_at=None,
        source=(program.source or "admin")[:64],
        is_active=bool(program.is_active),
        created_at=program.created_at,
        updated_at=program.updated_at,
    )
    db.add(ent)

    if program.category_id is not None:
        db.add(
            EntityCategory(
                entity_id=ent.id,
                category_id=program.category_id,
                is_primary=True,
                created_at=_utc_now_naive(),
            )
        )

    la = (program.location_address or "").strip()
    if la:
        db.add(
            Location(
                entity_id=ent.id,
                address=la[:255],
                address_normalized=la.lower(),
                city=None,
                state=None,
                zip=None,
                lat=None,
                lng=None,
                google_place_id=None,
                district=None,
                created_at=_utc_now_naive(),
                updated_at=_utc_now_naive(),
            )
        )

    _add_contact(db, ent.id, "phone", program.contact_phone, is_primary=True)
    _add_contact(db, ent.id, "email", program.contact_email, is_primary=False)
    _add_contact(db, ent.id, "website", program.contact_url, is_primary=False)

    db.add(
        Schedule(
            entity_id=ent.id,
            schedule_type="recurring",
            start_date=None,
            end_date=None,
            start_time=program.schedule_start_time,
            end_time=program.schedule_end_time,
            recurrence_rule=None,
            days_of_week=list(program.schedule_days or []),
            capacity=None,
            capacity_label=None,
            notes=(program.schedule_note or "")[:255] if program.schedule_note else None,
            created_at=_utc_now_naive(),
            updated_at=_utc_now_naive(),
        )
    )

    db.add(
        Offering(
            entity_id=ent.id,
            name=program.title[:255],
            description=program.description,
            price_text=(program.cost or "")[:64] if program.cost else None,
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
        SourceEvidence(
            entity_id=ent.id,
            field_path="(program_record)",
            source_type=(program.source or "admin")[:64],
            source_url=None,
            verified_at=None,
            verification_method=None,
            notes=None,
            created_at=_utc_now_naive(),
        )
    )

    program.entity_id = ent.id
    return program, ent


_CATALOG_DUAL_WRITE_HOOKS_REGISTERED = False


def register_catalog_dual_write_hooks() -> None:
    """Ensure new Provider/Event/Program rows get ENTITY rows before INSERT.

    Idempotent with explicit :func:`create_*_and_entity` calls (those set
    ``entity_id`` first). Registered from ``app.db.models`` import side-effects.
    """
    global _CATALOG_DUAL_WRITE_HOOKS_REGISTERED
    if _CATALOG_DUAL_WRITE_HOOKS_REGISTERED:
        return
    _CATALOG_DUAL_WRITE_HOOKS_REGISTERED = True

    from sqlalchemy import event
    from sqlalchemy.orm import Session as OrmSession

    @event.listens_for(OrmSession, "before_flush")
    def _catalog_dual_write_before_flush(
        session: Session, flush_context: Any, instances: Any
    ) -> None:
        for obj in list(session.new):
            if isinstance(obj, Provider) and not obj.entity_id:
                create_provider_and_entity(session, obj)
            elif isinstance(obj, Event) and not obj.entity_id:
                create_event_and_entity(session, obj)
            elif isinstance(obj, Program) and not obj.entity_id:
                create_program_and_entity(session, obj)


def sync_provider_entity_from_legacy(db: Session, provider: Provider) -> None:
    """Keep ENTITY extensions aligned after legacy Provider fields change (upsert/update)."""
    if not provider.entity_id:
        return
    ent = db.get(Entity, provider.entity_id)
    if ent is None:
        return

    ent.name = provider.provider_name
    ent.description = provider.description
    ent.last_verified_at = provider.last_verified_at
    ent.source = (provider.source or "seed")[:64]
    ent.is_active = bool(provider.is_active)
    ent.liveness_score = provider.liveness_score
    ent.updated_at = provider.updated_at

    loc = db.scalar(select(Location).where(Location.entity_id == ent.id))
    addr, addr_norm = _location_address_fields(provider.address)
    district = (provider.district or "")[:64] or None
    if loc is None:
        db.add(
            Location(
                entity_id=ent.id,
                address=addr,
                address_normalized=addr_norm,
                city=_DEFAULT_CITY,
                state=_DEFAULT_STATE,
                zip=provider.zip,
                lat=provider.lat,
                lng=provider.lng,
                google_place_id=provider.google_place_id,
                district=district,
                created_at=_utc_now_naive(),
                updated_at=_utc_now_naive(),
            )
        )
    else:
        loc.address = addr
        loc.address_normalized = addr_norm
        loc.city = _DEFAULT_CITY
        loc.state = _DEFAULT_STATE
        loc.zip = provider.zip
        loc.lat = provider.lat
        loc.lng = provider.lng
        loc.google_place_id = provider.google_place_id
        loc.district = district
        loc.updated_at = _utc_now_naive()

    db.execute(delete(ContactPoint).where(ContactPoint.entity_id == ent.id))
    _add_contact(db, ent.id, "phone", provider.phone, is_primary=True)
    _add_contact(db, ent.id, "email", provider.email, is_primary=False)
    _add_contact(db, ent.id, "website", provider.website, is_primary=False)
    _add_contact(db, ent.id, "facebook", provider.facebook, is_primary=False)
