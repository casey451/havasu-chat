"""Multi-source event dedup + venue resolution + merge semantics (Phase 9b)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.db.models import Entity, Event, Provider
from app.events.scrapers.base import EventPayload, normalize_event_title

DEDUP_DATETIME_WINDOW_MINUTES = int(os.environ.get("EVENT_DEDUP_DATETIME_WINDOW_MINUTES", "30"))
DEDUP_TITLE_FUZZY_THRESHOLD = int(os.environ.get("EVENT_DEDUP_TITLE_THRESHOLD", "85"))


def find_duplicate(
    db: Session,
    *,
    venue_entity_id: str | None,
    start_date: date,
    start_time_obj: time | None,
    normalized_title: str,
) -> Event | None:
    """Return existing Event row if a likely duplicate, else None."""
    stmt = select(Event).where(Event.date == start_date)
    if venue_entity_id:
        prov_ids = list(
            db.scalars(select(Provider.id).where(Provider.entity_id == venue_entity_id)).all()
        )
        clauses = [Event.entity_id == venue_entity_id]
        if prov_ids:
            clauses.append(Event.provider_id.in_(prov_ids))
        stmt = stmt.where(or_(*clauses) if clauses else false())
    candidates = list(db.scalars(stmt).all())
    target_dt = datetime.combine(start_date, start_time_obj) if start_time_obj else None
    norm = normalize_event_title(normalized_title)

    for cand in candidates:
        if (
            fuzz.token_sort_ratio(
                normalize_event_title(cand.normalized_title or cand.title),
                norm,
            )
            < DEDUP_TITLE_FUZZY_THRESHOLD
        ):
            continue
        if target_dt and cand.start_time:
            cand_dt = datetime.combine(cand.date, cand.start_time)
            delta = abs((target_dt - cand_dt).total_seconds())
            if delta > DEDUP_DATETIME_WINDOW_MINUTES * 60:
                continue
        return cand
    return None


def resolve_venue_entity_id(
    db: Session,
    venue_name: str | None,
    venue_address: str | None = None,
) -> str | None:
    """Match venue name to an existing Entity id when confidence is high."""
    name = (venue_name or "").strip()
    if not name:
        return None
    norm = normalize_event_title(name)
    best_id: str | None = None
    best_score = 0
    for ent in db.scalars(select(Entity).where(Entity.is_active.is_(True))).all():
        score = fuzz.token_sort_ratio(normalize_event_title(ent.name or ""), norm)
        if score > best_score:
            best_score = score
            best_id = ent.id
    if best_score >= 90:
        return best_id
    if venue_address:
        addr_norm = normalize_event_title(venue_address)
        for prov in db.scalars(select(Provider).where(Provider.is_active.is_(True))).all():
            if not prov.entity_id:
                continue
            pa = normalize_event_title(prov.address or "")
            if pa and fuzz.partial_ratio(addr_norm, pa) >= 85:
                return prov.entity_id
    return None


def merge_scraper_into_event(
    db: Session,
    event: Event,
    payload: EventPayload,
    *,
    scrape_source: str,
) -> list[str]:
    """Apply §6.4 merge semantics; return list of field names updated."""
    updated: list[str] = []
    now = datetime.now(UTC).replace(tzinfo=None)

    def _set(attr: str, value: Any) -> None:
        if value is None or value == "":
            return
        current = getattr(event, attr, None)
        if event.operator_override and current not in (None, "", [], {}):
            return
        if current == value:
            return
        setattr(event, attr, value)
        updated.append(attr)

    _set("description", (payload.description or "").strip())
    _set("event_url", (payload.event_url or "").strip())
    if payload.venue_name and not event.location_name:
        _set("location_name", payload.venue_name.strip())
        _set("location_normalized", payload.venue_name.lower().strip())
    if payload.tags:
        existing = list(event.tags or [])
        merged = sorted(set(existing + list(payload.tags)))
        if merged != existing:
            event.tags = merged
            updated.append("tags")

    event.scraped_at = now
    event.source = scrape_source
    if updated:
        db.add(event)
    return updated
