"""Multi-source event dedup + venue resolution + merge semantics (Phase 9b)."""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz, process
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.db.models import Entity, Event, Provider
from app.events.scrapers.base import EventPayload, normalize_event_title
from app.events.time_labels import is_time_tbd

DEDUP_DATETIME_WINDOW_MINUTES = int(os.environ.get("EVENT_DEDUP_DATETIME_WINDOW_MINUTES", "30"))
DEDUP_TITLE_FUZZY_THRESHOLD = int(os.environ.get("EVENT_DEDUP_TITLE_THRESHOLD", "85"))

# Catalog-scan normalization cache. resolve_venue_entity_id re-normalizes the
# SAME ~3k entity names / provider addresses on every call (once per event in a
# scrape batch). normalize_event_title is pure (regex over the input string),
# so a string-keyed cache is safe; scoped to this module's scan loops so
# unbounded one-off inputs (raw titles, descriptions) don't churn it.
_norm_cached = functools.lru_cache(maxsize=8192)(normalize_event_title)

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

    # A bare-noon (12:00, no end) placeholder some aggregators emit is really a
    # "time unknown", so it must merge onto a really-timed twin regardless of the
    # ±window — otherwise the noon placeholder and the real 9 PM event (Jul 4
    # fireworks) both survive ingest. Treat either side being TBD/bare-noon as
    # time-agnostic.
    incoming_tbd = _start_is_tbd_for_dedup(start_time_obj, None)

    def _within_window(cand: Event) -> bool:
        if target_dt and cand.start_time:
            if incoming_tbd or _start_is_tbd_for_dedup(cand.start_time, cand.end_time):
                return True
            cand_dt = datetime.combine(cand.date, cand.start_time)
            return abs((target_dt - cand_dt).total_seconds()) <= (
                DEDUP_DATETIME_WINDOW_MINUTES * 60
            )
        return True

    # T3.1 fast path: most duplicates are *exact* normalized-title matches
    # (same scraper, same source). One dict build replaces a token_sort_ratio
    # call per candidate; the fuzzy loop below stays as the fallback for
    # near-miss titles.
    by_norm: dict[str, list[Event]] = {}
    for cand in candidates:
        by_norm.setdefault(
            normalize_event_title(cand.normalized_title or cand.title), []
        ).append(cand)
    for cand in by_norm.get(norm, ()):
        if _within_window(cand):
            return cand

    for cand in candidates:
        if (
            fuzz.token_sort_ratio(
                normalize_event_title(cand.normalized_title or cand.title),
                norm,
            )
            < DEDUP_TITLE_FUZZY_THRESHOLD
        ):
            continue
        if _within_window(cand):
            return cand
    return None


def resolve_venue_entity_id(
    db: Session,
    venue_name: str | None,
    venue_address: str | None = None,
) -> str | None:
    """Match venue name to an existing Entity id when confidence is high.

    Perf shape (this runs once per event payload on the ingest path): the
    previous implementation hydrated every active Entity as a full ORM object
    and ran a Python-loop ``token_sort_ratio`` per row (~165-215ms/call at
    3.2k entities). Now: column-only ``(id, name)`` scan, an exact
    normalized-name probe first (re-scraped venue strings repeat verbatim, and
    an exact match is a 100-score that nothing can beat), and the fuzzy
    fallback via ``process.extractOne`` (C loop, same scorer/first-max-wins
    semantics as the old Python loop). The address tier likewise scans
    ``(entity_id, address)`` tuples only.
    """
    name = (venue_name or "").strip()
    if not name:
        return None
    norm = normalize_event_title(name)
    rows = db.execute(select(Entity.id, Entity.name).where(Entity.is_active.is_(True))).all()
    ids: list[str] = []
    normed: list[str] = []
    for eid, ename in rows:
        n = _norm_cached(ename or "")
        if n == norm:
            return eid
        ids.append(eid)
        normed.append(n)
    hit = process.extractOne(norm, normed, scorer=fuzz.token_sort_ratio, score_cutoff=90)
    if hit is not None:
        return ids[hit[2]]
    if venue_address:
        addr_norm = normalize_event_title(venue_address)
        prov_rows = db.execute(
            select(Provider.entity_id, Provider.address).where(
                Provider.is_active.is_(True), Provider.entity_id.is_not(None)
            )
        ).all()
        for ent_id, addr in prov_rows:
            pa = _norm_cached(addr or "")
            if pa and fuzz.partial_ratio(addr_norm, pa) >= 85:
                return ent_id
    return None


# --------------------------------------------------------------------------- #
# Render-time cross-source dedup (display paths only; never writes the DB)
# --------------------------------------------------------------------------- #
# Two scrape sources routinely carry the SAME real-world event with cosmetic
# differences the ingest-time matchers above miss: one source stores the street
# address as the venue and fabricates a noon start ("Lake Havasu Farmers Market"
# at "2144 McCulloch Blvd N ..." 12:00 PM), the other has the named venue and
# the real 8:00 AM time; titles can differ only by a curly apostrophe ("Lady
# Lee's" vs "Lady Lee's"). These helpers collapse such twins at render time --
# grouped by (normalized title, occurrence date), one survivor per group -- so
# every display surface that opts in (home week strip, month calendar,
# /events-ui buckets and day view) shows the event once. Read-only by design:
# the rows stay in the DB untouched for ingest reconciliation and admin review.

# Two events with the same title but REAL start times further apart than this
# are legitimately separate sessions (matinee vs evening) -- never merged.
_SEPARATE_SESSION_GAP_MINUTES = 120


def _render_title_key(event: Event) -> str:
    """Title key: lowercased, punctuation/curly quotes stripped, spaces collapsed."""
    return normalize_event_title(event.normalized_title or event.title or "")


def _start_is_tbd_for_dedup(start_time: time | None, end_time: time | None) -> bool:
    """Time-TBD for dedup purposes: the shared midnight-fallback contract
    (:func:`app.events.time_labels.is_time_tbd`) PLUS the bare-noon fabrication
    some aggregator sources emit instead of midnight. A noon start with a real
    end time is a real noon event; only the bare 12:00-with-no-end is suspect.
    Display labels are untouched -- this widens TBD only inside a duplicate
    group, where a bare-noon twin should lose to its really-timed sibling."""
    if is_time_tbd(start_time, end_time):
        return True
    if start_time is None:
        return False
    # Bare-noon fabrication: a noon start with no end time.
    if start_time.hour == 12 and start_time.minute == 0 and end_time is None:
        return True
    # Deep pre-dawn (01:00–04:59) with no end time is almost always an aggregator
    # AM/PM parse error (the live "Troy's Alligator Feed" parsed a 3 PM event as
    # 3 AM), so it reads as TBD and loses to a real daytime twin inside its
    # duplicate group. 05:00+ is left alone — early classes (5 AM Lap Swim) are
    # real. Guarded on no-end-time so a genuine timed pre-dawn block is untouched.
    if 1 <= start_time.hour <= 4 and end_time is None:
        return True
    return False


def _venue_is_named_place(venue: str | None) -> bool:
    """A named place ("Go Lake Havasu Visitor Center") vs a bare street address
    ("2144 McCulloch Blvd N ..."): contains letters and doesn't start with a
    digit. Heuristic, used only to rank survivors inside a duplicate group."""
    v = (venue or "").strip()
    return bool(v) and any(c.isalpha() for c in v) and not v[0].isdigit()


def _source_priority(source: str | None) -> int:
    """Min EVENT_SOURCE_PRIORITY across the comma-separated provenance string.

    Imported lazily: :mod:`app.contrib.event_reconciler` imports this module at
    its top level, so a module-level import here would be circular.
    """
    from app.contrib.event_reconciler import EVENT_SOURCE_PRIORITY

    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return 99
    return min(EVENT_SOURCE_PRIORITY.get(p, 99) for p in parts)


def _survivor_rank(event: Event) -> tuple[bool, bool, int, int, str]:
    """Sort key for picking ONE survivor in a duplicate cluster (lowest wins):
    real start time > named venue > longer description > source priority > id."""
    return (
        _start_is_tbd_for_dedup(event.start_time, event.end_time),
        not _venue_is_named_place(event.location_name),
        -len((event.description or "").strip()),
        _source_priority(event.source),
        str(event.id),
    )


def _start_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _group_survivor_positions(members: list[tuple[int, Event]]) -> set[int]:
    """Positions (into the caller's occurrence list) that survive one group.

    Timed (non-TBD) members are clustered by start-time proximity: starts within
    :data:`_SEPARATE_SESSION_GAP_MINUTES` of the previous one chain into the same
    cluster; a bigger gap means a genuinely separate session, so each cluster
    keeps its own survivor (the matinee/evening guard). Time-TBD members are
    duplicates of a timed sibling when one exists (the fake-noon twin loses);
    with no timed sibling they all collapse onto a single TBD survivor.
    """
    timed = [
        m for m in members if not _start_is_tbd_for_dedup(m[1].start_time, m[1].end_time)
    ]
    if not timed:
        return {min(members, key=lambda m: _survivor_rank(m[1]))[0]}
    timed.sort(key=lambda m: _start_minutes(m[1].start_time))
    clusters: list[list[tuple[int, Event]]] = [[timed[0]]]
    for member in timed[1:]:
        gap = _start_minutes(member[1].start_time) - _start_minutes(clusters[-1][-1][1].start_time)
        if gap <= _SEPARATE_SESSION_GAP_MINUTES:
            clusters[-1].append(member)
        else:
            clusters.append([member])
    return {min(cluster, key=lambda m: _survivor_rank(m[1]))[0] for cluster in clusters}


def dedup_cross_source_occurrences(
    occurrences: Sequence[tuple[Event, date]],
) -> list[tuple[Event, date]]:
    """Collapse cross-source duplicates of the same (title, date) occurrence.

    Input/output are ``(event, occurrence_date)`` pairs; survivors keep their
    input order. Untitled rows never group. Pure + read-only: callers on the
    display read paths filter what they render, nothing is written.
    """
    groups: dict[tuple[str, date], list[tuple[int, Event]]] = {}
    for idx, (ev, occ_date) in enumerate(occurrences):
        key = _render_title_key(ev)
        if key:
            groups.setdefault((key, occ_date), []).append((idx, ev))

    dropped: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        survivors = _group_survivor_positions(members)
        dropped.update(idx for idx, _ev in members if idx not in survivors)
    return [pair for idx, pair in enumerate(occurrences) if idx not in dropped]


def dedup_cross_source_event_rows(rows: Sequence[Event]) -> list[Event]:
    """Row-shaped wrapper over :func:`dedup_cross_source_occurrences` for read
    paths that work with plain Event rows (each row dated by ``Event.date``)."""
    return [ev for ev, _d in dedup_cross_source_occurrences([(ev, ev.date) for ev in rows])]


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
