"""Multi-source event dedup + venue resolution + merge semantics (Phase 9b)."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.db.models import Entity, Event, Provider
from app.events.scrapers.base import EventPayload, normalize_event_title

DEDUP_DATETIME_WINDOW_MINUTES = int(os.environ.get("EVENT_DEDUP_DATETIME_WINDOW_MINUTES", "30"))
DEDUP_TITLE_FUZZY_THRESHOLD = int(os.environ.get("EVENT_DEDUP_TITLE_THRESHOLD", "85"))

# --------------------------------------------------------------------------- #
# Canonical-URL identity (cross-source dedup: go_lake_havasu + river_scene_import)
# --------------------------------------------------------------------------- #
# Tracking params that must never participate in a canonical identity (mirrors the
# ingest-time strip in the go_lake_havasu scraper).
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})

# A Facebook event URL carries a stable global event id -- the strongest cross-
# source identity we have (the same FB event is routinely surfaced by both
# go_lake_havasu's organizer link and a river_scene_import "Facebook" label).
_FB_EVENT_ID_RE = re.compile(r"facebook\.com/events/(\d+)", re.IGNORECASE)


def _strip_tracking_query(query: str) -> str:
    kept = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAM_EXACT
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    return urlencode(kept)


def canonical_event_identity(url: str | None) -> str | None:
    """Return a canonical identity key for an event URL, or ``None``.

    Two ingest sources (go_lake_havasu organizer links, river_scene_import
    "Website"/"Facebook" labels) frequently point at the *same* real event. We
    collapse them by deriving a stable key:

    * a Facebook event URL -> ``"fb:<event_id>"`` (the global FB event id);
    * any other URL -> ``"url:<scheme-stripped host+path+clean-query>"`` with the
      scheme dropped, host lowercased, ``www.`` removed, trailing slash trimmed,
      fragment dropped, and tracking params (fbclid/UTM) removed.

    Returns ``None`` for empty / unparseable input so callers can skip it.
    """
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    fb = _FB_EVENT_ID_RE.search(s)
    if fb:
        return f"fb:{fb.group(1)}"
    if "://" not in s:
        s = "https://" + s.lstrip("/")
    parts = urlsplit(s)
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    path = (parts.path or "").rstrip("/")
    query = _strip_tracking_query(parts.query) if parts.query else ""
    cleaned = urlunsplit(("", host, path, query, ""))  # scheme+fragment dropped
    cleaned = cleaned.lstrip("/")
    return f"url:{cleaned.lower()}" if cleaned else None


def find_duplicate_by_canonical_url(
    db: Session,
    *,
    candidate_urls: list[str | None],
) -> Event | None:
    """Return an existing Event sharing a canonical-URL identity, else ``None``.

    ``candidate_urls`` are the incoming event's click-through URLs (event_url,
    source_stable_url, organizer URL, etc.). Each is reduced to a canonical
    identity via :func:`canonical_event_identity`; if any existing Event's own
    URLs reduce to the same key, that Event is the cross-source duplicate.

    Scans live events only. ``O(events)``; acceptable at the current catalog size
    and only invoked on the at-ingest reconcile path.
    """
    wanted: set[str] = {
        key for u in candidate_urls if (key := canonical_event_identity(u)) is not None
    }
    if not wanted:
        return None
    for ev in db.scalars(select(Event).where(Event.status == "live")).all():
        for existing_url in (ev.event_url, getattr(ev, "source_url", None)):
            key = canonical_event_identity(existing_url)
            if key is not None and key in wanted:
                return ev
    return None


# --------------------------------------------------------------------------- #
# Recurring-series instance dedupe (venue + title + weekday)
# --------------------------------------------------------------------------- #
def recurring_series_key(
    venue_name: str | None,
    title: str | None,
    weekday: int | None,
) -> tuple[str, str, int] | None:
    """Natural key for one weekday-instance of a recurring series.

    ``(normalized venue, normalized title, weekday)`` -- the tuple that identifies
    a single occurrence of e.g. "Farmers Market @ Visitor Center, every Saturday".
    Returns ``None`` when venue/title/weekday is missing (no usable key).
    """
    v = normalize_event_title(venue_name or "")
    t = normalize_event_title(title or "")
    if not v or not t or weekday is None:
        return None
    return (v, t, weekday)


def find_recurring_series_instance(
    db: Session,
    *,
    venue_name: str | None,
    title: str | None,
    start_date: date,
) -> Event | None:
    """Return an existing same-weekday instance of this recurring series, if any.

    Recurring scrapes re-emit every weekly occurrence; a re-import of the same
    series for the *same calendar date* must collapse onto the existing row rather
    than minting a second "Saturday Farmers Market" for that day. Match key is
    ``(venue, title, weekday)`` constrained to the same date (so distinct weeks
    stay distinct occurrences -- this is instance dedupe, not series collapse).
    """
    key = recurring_series_key(venue_name, title, start_date.weekday())
    if key is None:
        return None
    for ev in db.scalars(select(Event).where(Event.date == start_date)).all():
        cand_key = recurring_series_key(
            ev.location_name, ev.normalized_title or ev.title, ev.date.weekday()
        )
        if cand_key == key:
            return ev
    return None


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
