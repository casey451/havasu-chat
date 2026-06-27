"""Tier 2 catalog lookup from structured filters (Phase 4.2).

``query`` returns up to eight JSON-serializable row dicts for ``tier2_formatter``.

When no query-shaping dimensions are set (entity, category, ages, location,
days, time window, or open-now), the function returns a small mixed sample of
live catalog rows so downstream formatting still has material to work with.

When ``open_now=True``, provider rows are filtered in Python using
structured hours (legacy ``hours_structured`` JSON or ENTITY ``hours`` rows
via :func:`app.providers.queries.effective_hours_structured`) and
:func:`app.contrib.hours_helper.is_open_at`.
Providers without structured hours are omitted. Events and programs are still
returned using the same SQL filters with ``open_now`` stripped for the query
builder (open/closed for events/programs is out of scope for Phase 5.6).

# open_now filtering happens in Python after SQL fetch because hours are JSON.
# At current scale (<100 providers) this is negligible. Consider a SQL-side
# derivation (e.g., computed column or materialized view) if scale grows.

**Phase 1C — Pattern A (ENTITY-aware):** legacy ``events`` / ``programs`` /
``providers`` rows are outer-joined to ``entities`` so orphan rows (no
``entity_id`` yet) stay eligible while linked rows verify ``entity_type``.
Category needle expansion can consult ``Entity`` M:M categories and
offerings after fetch. Row payloads remain sourced from legacy ORM objects so
chat formatting stays byte-stable.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.chat import tier2_synonyms as _tier2_synonyms
from app.chat.chat_request_context import ChatRequestContext
from app.chat.entity_catalog_query import prefers_entity_catalog, query_entities
from app.chat.tier2_schema import Tier2Filters
from app.contrib.hours_helper import LAKE_HAVASU_TZ, is_open_at
from app.db.database import SessionLocal
from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PROGRAM,
)
from app.db.models import Entity, EntityCategory, Event, Location, Program, Provider
from app.events.time_labels import is_time_tbd
from app.providers.photo_urls import first_renderable_google_photo
from app.providers.queries import effective_hours_structured
from app.search import fts as search_fts
from app.search import ranking as search_ranking

_category_needle_set = _tier2_synonyms._category_needle_set
_category_synonyms = _tier2_synonyms._category_synonyms
_singularize_category = _tier2_synonyms._singularize_category

MAX_ROWS = 8
# Broad calendar windows: fetch more before recurring collapse + time bucketing (Phase 8.8.4).
BROAD_EVENT_SQL_LIMIT = 500
NARROW_EVENT_SQL_LIMIT = 80

_WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_MONTH_TO_INT = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _today() -> date:
    """Lake Havasu calendar \"today\" for catalog date filters (monkeypatch in tests).

    Must be the America/Phoenix date, not the server-local (UTC in prod) date:
    ``date.today()`` rolls to tomorrow at 5 PM Phoenix on a UTC host, so evening
    \"what's happening today\" queries fetched the wrong day's events while the
    component builders labeled the answer with the Phoenix date.
    """
    return _now_lake_havasu().date()


def _is_postgres(db: Session) -> bool:
    """True when the session bind is Postgres (FTS + ``entities.search_vector``)."""
    return db.get_bind().dialect.name == "postgresql"


def _weekday_name(d: date) -> str:
    return _WEEKDAY_NAMES[d.weekday()]


def _event_covers_any_weekday(e: Event, allowed: set[str]) -> bool:
    """True if any calendar day in [e.date, coalesce(e.end_date, e.date)] is in ``allowed``."""
    end = e.end_date if e.end_date is not None else e.date
    d = e.date
    while d <= end:
        if _weekday_name(d) in allowed:
            return True
        d += timedelta(days=1)
    return False


def _next_weekday(start_date: date, weekday: int, allow_today: bool) -> date:
    """Next occurrence of ``weekday`` (0=Mon) — mirrors ``app.core.slots._next_weekday``."""
    days_ahead = (weekday - start_date.weekday()) % 7
    if days_ahead == 0 and not allow_today:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)


def _month_name_range(name: str, ref: date) -> tuple[date, date]:
    """Full calendar month: same year if month >= ref.month, else next year (spec §5)."""
    m = _MONTH_TO_INT[name]
    y = ref.year
    if m < ref.month:
        y += 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _season_range(season: str, ref: date) -> tuple[date, date]:
    """spring/summer/fall: calendar window; winter = Dec 1 .. end of Feb (next year)."""
    s = season.lower()
    y = ref.year
    if s == "spring":
        start, end = date(y, 3, 1), date(y, 5, 31)
        if ref > end:
            y += 1
            start, end = date(y, 3, 1), date(y, 5, 31)
        return start, end
    if s == "summer":
        start, end = date(y, 6, 1), date(y, 8, 31)
        if ref > end:
            y += 1
            start, end = date(y, 6, 1), date(y, 8, 31)
        return start, end
    if s == "fall":
        start, end = date(y, 9, 1), date(y, 11, 30)
        if ref > end:
            y += 1
            start, end = date(y, 9, 1), date(y, 11, 30)
        return start, end
    if s == "winter":
        m = ref.month
        if m == 12:
            y_end = y + 1
            feb_last = calendar.monthrange(y_end, 2)[1]
            return date(y, 12, 1), date(y_end, 2, feb_last)
        if m <= 2:
            y0 = y - 1
            y1 = y
            feb_last = calendar.monthrange(y1, 2)[1]
            return date(y0, 12, 1), date(y1, 2, feb_last)
        y_end = y + 1
        feb_last = calendar.monthrange(y_end, 2)[1]
        return date(y, 12, 1), date(y_end, 2, feb_last)
    raise ValueError("invalid season")


def _has_temporal_filter(filters: Tier2Filters) -> bool:
    return any(
        (
            filters.time_window is not None,
            filters.month_name is not None,
            filters.season is not None,
            filters.date_exact is not None,
            filters.date_start is not None,
            filters.date_end is not None,
        )
    )


def _only_time_window(filters: Tier2Filters) -> bool:
    """True when only temporal + optional open_now — events-only for programs/providers."""
    if not _has_temporal_filter(filters):
        return False
    return not any(
        (
            bool(filters.entity_name and filters.entity_name.strip()),
            bool(filters.category and filters.category.strip()),
            filters.age_min is not None,
            filters.age_max is not None,
            bool(filters.location and filters.location.strip()),
            bool(filters.day_of_week),
        )
    )


def _has_query_dimensions(filters: Tier2Filters) -> bool:
    if filters.open_now is True:
        return True
    return any(
        (
            bool(filters.entity_name and filters.entity_name.strip()),
            bool(filters.category and filters.category.strip()),
            filters.age_min is not None,
            filters.age_max is not None,
            bool(filters.location and filters.location.strip()),
            bool(filters.day_of_week),
            filters.time_window is not None,
            filters.month_name is not None,
            filters.season is not None,
            filters.date_exact is not None,
            filters.date_start is not None,
            filters.date_end is not None,
        )
    )


def _age_bounds(filters: Tier2Filters) -> tuple[int | None, int | None]:
    return filters.age_min, filters.age_max


def _ages_overlap_program(p: Program, fmin: int | None, fmax: int | None) -> bool:
    if fmin is None and fmax is None:
        return True
    lo = fmin if fmin is not None else 0
    hi = fmax if fmax is not None else 120
    if p.age_min is None and p.age_max is None:
        return True
    p_lo = p.age_min if p.age_min is not None else 0
    p_hi = p.age_max if p.age_max is not None else 120
    return not (p_hi < lo or p_lo > hi)


def _schedule_matches_days(p: Program, days: list[str] | None) -> bool:
    if not days:
        return True
    allowed = {d.lower() for d in days}
    sched = [str(d).lower() for d in (p.schedule_days or []) if isinstance(d, str)]
    if not sched:
        return False
    return bool(allowed.intersection(sched))


def _resolve_time_window(tw: str | None, ref: date) -> tuple[date | None, date | None]:
    """Inclusive (start, end); ``(ref, None)`` means from ``ref`` forward without upper bound."""
    if tw is None:
        return ref, None
    if tw == "today":
        return ref, ref
    if tw == "tomorrow":
        t = ref + timedelta(days=1)
        return t, t
    if tw == "this_week":
        return ref, ref + timedelta(days=6)
    if tw == "this_weekend":
        wd = ref.weekday()
        if wd < 4:
            days_to_fri = 4 - wd
        elif wd <= 6:
            days_to_fri = 0
        else:
            days_to_fri = 5
        fri = ref + timedelta(days=days_to_fri)
        sun = fri + timedelta(days=2)
        return fri, sun
    if tw == "this_month":
        start = date(ref.year, ref.month, 1)
        last = calendar.monthrange(ref.year, ref.month)[1]
        end = date(ref.year, ref.month, last)
        return start, end
    if tw == "upcoming":
        return ref, None
    if tw == "next_week":
        monday = _next_weekday(ref, 0, allow_today=False)
        if monday <= ref:
            monday += timedelta(days=7)
        return monday, monday + timedelta(days=6)
    if tw == "next_month":
        y = ref.year + (1 if ref.month == 12 else 0)
        m = 1 if ref.month == 12 else ref.month + 1
        last = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last)
    return ref, None


def _resolve_effective_event_window(
    filters: Tier2Filters, ref: date
) -> tuple[date | None, date | None]:
    """Inclusive event date window. ``(ref, None)`` means from ``ref`` forward (unbounded)."""
    if filters.date_start is not None or filters.date_end is not None:
        return filters.date_start, filters.date_end
    if filters.date_exact is not None:
        d = filters.date_exact
        return d, d
    if filters.month_name is not None:
        return _month_name_range(filters.month_name, ref)
    if filters.season is not None:
        return _season_range(filters.season, ref)
    return _resolve_time_window(filters.time_window, ref)


def _truncate(s: str | None, max_len: int) -> str:
    if not s:
        return ""
    t = s.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _program_location_display(
    location_name: str | None, location_address: str | None
) -> str | None:
    """Single compact location string for program row payloads (Phase 4.5)."""
    n = (location_name or "").strip()
    a = (location_address or "").strip()
    if not n and not a:
        return None
    if n and a and n != a:
        return f"{n} ({a})"
    return n or a or None


def _event_dict(e: Event) -> dict[str, Any]:
    # A null/midnight placeholder start (venues, undated happenings) is NOT a real
    # "12 am" — emit None so the chat agenda sorts it to the end and renders no
    # bogus time instead of dumping it under MORNING at "12 am" (site review §1).
    tbd = is_time_tbd(e.start_time, e.end_time)
    out: dict[str, Any] = {
        "type": "event",
        "name": e.title,
        "date": e.date.isoformat(),
        "start_time": None if tbd else (e.start_time.strftime("%H:%M") if e.start_time else None),
        "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
        "location_name": e.location_name,
        "description": _truncate(e.description, 120),
        "event_url": e.event_url,
        "tags": list(e.tags or [])[:8],
    }
    if e.end_date is not None:
        out["end_date"] = e.end_date.isoformat()
    return out


def _program_dict(p: Program) -> dict[str, Any]:
    ages = None
    if p.age_min is not None or p.age_max is not None:
        ages = f"{p.age_min if p.age_min is not None else '?'}-{p.age_max if p.age_max is not None else '?'}"
    loc = _program_location_display(p.location_name, p.location_address)
    # Slice 56 (Backlog #30 close): canonical schedule columns are typed Time;
    # strftime to HH:MM. The defensive None-guards survive from Slice 54 — they
    # cost nothing and protect against future schema drift even though the
    # post-Slice-56 columns are nullable=False.
    sched_st = p.schedule_start_time
    sched_et = p.schedule_end_time
    sched_st_s = sched_st.strftime("%H:%M") if sched_st is not None else ""
    sched_et_s = sched_et.strftime("%H:%M") if sched_et is not None else ""
    out: dict[str, Any] = {
        "type": "program",
        "name": p.title,
        "provider_name": p.provider_name,
        "activity_category": p.activity_category,
        "age_range": ages,
        "schedule_days": list(p.schedule_days or [])[:7],
        "schedule_hours": f"{sched_st_s}-{sched_et_s}",
        "cost": p.cost,
        "description": _truncate(p.description, 120),
        "tags": list(p.tags or [])[:8],
    }
    if loc:
        out["location"] = loc
    return out


def _leaf_slugs_text(p: Provider) -> str:
    """Space-joined taxonomy category slugs linked to ``p`` (for relevance ranking).

    The within-category signal for several buckets lives ONLY in the curated leaf
    slug (e.g. ``marinas-and-launch-ramps`` carries "launch"/"ramp", which appear
    nowhere on the Provider row), so build_business_list's P1-1.1 ranking needs it.
    Reads the already-eager-loaded ``entity.categories -> category`` relationship;
    degrades to ``""`` if it isn't loaded (no lazy N+1) — ranking just loses that
    one signal, never errors.
    """
    try:
        entity = getattr(p, "entity", None)
        slugs = [
            ec.category.slug
            for ec in (getattr(entity, "categories", None) or [])
            if getattr(ec, "category", None) is not None and ec.category.slug
        ]
        return " ".join(slugs)
    except Exception:
        return ""


def _provider_dict(p: Provider) -> dict[str, Any]:
    loc = getattr(getattr(p, "entity", None), "location", None)
    address = loc.address if loc is not None and loc.address else p.address
    thumb_url = first_renderable_google_photo(p)
    return {
        "type": "provider",
        "name": p.provider_name,
        "slug": p.slug,
        "category": p.category,
        "google_primary_category": p.google_primary_category,
        "category_slugs": _leaf_slugs_text(p),
        "address": address,
        "phone": p.phone,
        "hours": _truncate(p.hours, 120),
        "hours_structured": p.hours_structured,
        "description": _truncate(p.description, 120),
        "google_rating": p.google_rating,
        "google_review_count": p.google_review_count,
        "thumb_url": thumb_url,
        # Step 7.5 — spotlight surface (voice path MUST NOT read these).
        "tier": p.tier,
        "sponsored_until": p.sponsored_until,
        "featured_description": p.featured_description,
    }


def _now_lake_havasu() -> datetime:
    """Current instant in Lake Havasu local time (America/Phoenix; override in tests)."""
    return datetime.now(LAKE_HAVASU_TZ)


def _text_needle(s: str | None) -> str | None:
    if not s or not str(s).strip():
        return None
    return f"%{str(s).strip()}%"


def _category_match_event_sql_columns(e: Event, cat: str) -> bool:
    c = cat.strip().lower()
    if c in (e.title or "").lower():
        return True
    if c in (e.description or "").lower():
        return True
    for t in e.tags or []:
        if isinstance(t, str) and c in t.lower():
            return True
    return False


def _category_match_event(e: Event, cat: str) -> bool:
    if _category_match_event_sql_columns(e, cat):
        return True
    needles = _category_needle_set(cat)
    if not needles:
        return False
    ent = getattr(e, "entity", None)
    if ent is None:
        return False
    haystacks: list[str] = [
        (ent.name or "").lower(),
        (ent.description or "").lower(),
    ]
    for ec in ent.categories or []:
        cobj = ec.category
        if cobj is not None and cobj.name:
            haystacks.append(cobj.name.lower())
    for off in ent.offerings or []:
        if off.name:
            haystacks.append(off.name.lower())
        if off.description:
            haystacks.append((off.description or "").lower()[:500])
    for needle in needles:
        if not needle:
            continue
        for hay in haystacks:
            if hay and needle in hay:
                return True
    return False


def _category_match_program_sql_columns(p: Program, cat: str) -> bool:
    c = cat.strip().lower()
    if c in (p.title or "").lower():
        return True
    activity_category = (p.activity_category or "").lower()
    if c in ("art", "arts"):
        if activity_category in ("art", "arts"):
            return True
    elif c in activity_category:
        return True
    if c in (p.description or "").lower():
        return True
    for t in p.tags or []:
        if isinstance(t, str) and c in t.lower():
            return True
    return False


def _category_match_program(p: Program, cat: str) -> bool:
    if _category_match_program_sql_columns(p, cat):
        return True
    needles = _category_needle_set(cat)
    if not needles:
        return False
    ent = getattr(p, "entity", None)
    if ent is None:
        return False
    haystacks: list[str] = [
        (ent.name or "").lower(),
        (ent.description or "").lower(),
    ]
    for ec in ent.categories or []:
        cobj = ec.category
        if cobj is not None and cobj.name:
            haystacks.append(cobj.name.lower())
    for off in ent.offerings or []:
        if off.name:
            haystacks.append(off.name.lower())
        if off.description:
            haystacks.append((off.description or "").lower()[:500])
    for needle in needles:
        if not needle:
            continue
        for hay in haystacks:
            if hay and needle in hay:
                return True
    return False


def _normalize_for_match(s: str | None) -> str:
    """Lowercase + replace underscores with spaces so Google's ``coffee_shop`` token
    matches a user-typed ``coffee shop`` substring check."""
    if not s:
        return ""
    return s.lower().replace("_", " ")


def _category_match_provider(p: Provider, cat: str) -> bool:
    # Voice battery 2026-05-08 (§4.2): expand to synonym group + singularized
    # forms so "coffee shop" also matches providers whose google_primary_category
    # is "cafe", etc. _category_needle_set is empty-safe.
    needles = _category_needle_set(cat)
    if not needles:
        return False
    # Voice-battery 2026-05-07: dropped (p.provider_name or "").lower() from
    # haystacks — see SQL filter comment in _query_providers for full rationale.
    # Voice-battery 2026-05-08: dropped description AND google_categories. The
    # narrative description matches HVAC for "plumber" because plumbing was
    # mentioned as an adjacent service; the categories *array* matches multi-
    # trade companies (Air Control: primary=general_contractor, categories
    # includes "plumber") for the same reason. Stick to the primary category
    # only — specialist businesses surface, multi-trade ones don't unless
    # their primary type itself matches the user's query.
    haystacks: list[str] = [
        (p.category or "").lower(),
        _normalize_for_match(p.google_primary_category),
    ]
    if isinstance(p.google_categories, list):
        haystacks.extend(_normalize_for_match(t) for t in p.google_categories if isinstance(t, str))
    ent = getattr(p, "entity", None)
    if ent is not None:
        haystacks.append((ent.name or "").lower())
        for ec in ent.categories or []:
            cobj = ec.category
            if cobj is not None and cobj.name:
                haystacks.append(cobj.name.lower())
        for off in ent.offerings or []:
            if off.name:
                haystacks.append(off.name.lower())
    for needle in needles:
        if not needle:
            continue
        for hay in haystacks:
            if hay and needle in hay:
                return True
    return False


def _row_dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Stable identity for merged rows after ``id`` was dropped from payloads (Phase 4.5)."""
    t = str(row.get("type"))
    if t == "event":
        return (t, row.get("name"), row.get("date"), row.get("start_time"))
    if t == "program":
        return (
            t,
            row.get("name"),
            row.get("provider_name"),
            row.get("schedule_hours"),
            row.get("location"),
        )
    if t == "provider":
        return (t, row.get("name"), row.get("address"), row.get("phone"))
    return (t, repr(row))


def _merge_simple(
    events: list[dict[str, Any]],
    programs: list[dict[str, Any]],
    providers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Events first, then programs, then providers; dedupe without row ``id`` fields."""
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for bucket in (events, programs, providers):
        for row in bucket:
            key = _row_dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= MAX_ROWS:
                return out
    return out


def _filter_window_span_inclusive(win_start: date | None, win_end: date | None, ref: date) -> int:
    """Inclusive day span of the *filter* window. Unbounded upper = broad (large)."""
    if win_start is not None and win_end is not None:
        return max(0, (win_end - win_start).days) + 1
    if win_start is not None and win_end is None:
        return 10_000
    if win_start is None and win_end is not None:
        return max(0, (win_end - ref).days) + 1
    return 10_000


def _recurring_series_key(e: Event) -> object:
    """Recurring events collapse with ``is_recurring``; series id is title + start time. One-off rows stay distinct."""
    if e.is_recurring:
        return ("R", e.normalized_title, e.start_time)
    return ("1", e.id)


def _dedupe_recurring_preserving_chrono(events: list[Event]) -> list[Event]:
    """Keep the earliest event per series key; input must be time-ordered."""
    seen: set[object] = set()
    out: list[Event] = []
    for e in events:
        k = _recurring_series_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def _upper_bound_for_clustering(
    win_end: date | None, events: list[Event], lower: date
) -> date | None:
    if win_end is not None:
        return win_end
    if not events:
        return None
    mx = max((x.end_date if x.end_date is not None else x.date) for x in events)
    if mx < lower:
        return lower
    return mx


def _is_still_clustered_early(events: list[Event], lower: date, upper: date) -> bool:
    if len(events) < 4:
        return False
    w = max(0, (upper - lower).days) + 1
    if w < 2:
        return False
    mid = events[min(7, len(events) - 1)]
    return (mid.date - lower).days < (w * 0.3)


def _time_bucket_first_hits(evs: list[Event], lower: date, upper: date, k: int) -> list[Event]:
    """Partition ``[lower, upper]`` into k day-subranges; one earliest event per subrange, then chrono backfill to k."""
    if not evs or upper < lower or k < 1:
        return []
    n_days = max(1, (upper - lower).days + 1)
    used: set[str] = set()
    out: list[Event] = []
    for i in range(k):
        i0 = (i * n_days) // k
        i1 = (i + 1) * n_days // k - 1
        a = lower + timedelta(days=int(i0))
        b = min(lower + timedelta(days=int(i1)), upper)
        if a < lower:
            a = lower
        if a > b:
            continue
        for e in evs:
            if e.id in used:
                continue
            if a <= e.date <= b:
                out.append(e)
                used.add(e.id)
                break
    for e in evs:
        if len(out) >= k:
            break
        if e.id in used:
            continue
        out.append(e)
        used.add(e.id)
    return out


def _event_time_bucket_first_hits(evs: list[Event], k: int) -> list[Event]:
    """For crowded one-day lists, preserve coverage across the day, then sort chrono."""
    if not evs or k < 1:
        return []
    used: set[str] = set()
    selected: list[Event] = []
    minutes_per_day = 24 * 60
    for i in range(k):
        lo = (i * minutes_per_day) // k
        hi = ((i + 1) * minutes_per_day) // k
        for e in evs:
            if e.id in used:
                continue
            minute = (
                (e.start_time.hour * 60 + e.start_time.minute)
                if e.start_time is not None
                else 12 * 60
            )
            if lo <= minute < hi:
                selected.append(e)
                used.add(e.id)
                break
    for e in evs:
        if len(selected) >= k:
            break
        if e.id in used:
            continue
        selected.append(e)
        used.add(e.id)
    return sorted(
        selected,
        key=lambda e: (
            e.date,
            e.start_time is None,
            e.start_time,
            e.title or "",
        ),
    )


def _query_events(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    today = _today()
    win_start, win_end = _resolve_effective_event_window(filters, today)
    has_explicit_date_bounds = (
        filters.date_start is not None
        or filters.date_end is not None
        or filters.date_exact is not None
    )
    if has_explicit_date_bounds and win_start is not None:
        lower = win_start
    elif win_start is not None:
        lower = max(win_start, today)
    else:
        lower = today
    if win_end is not None and win_end < lower:
        return []
    span = _filter_window_span_inclusive(win_start, win_end, today)
    limit = NARROW_EVENT_SQL_LIMIT if span <= 30 else BROAD_EVENT_SQL_LIMIT
    q = (
        select(Event)
        .outerjoin(Entity, Event.entity_id == Entity.id)
        .where(
            Event.status == "live",
            func.coalesce(Event.end_date, Event.date) >= lower,
            or_(Event.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_EVENT),
        )
        .options(
            selectinload(Event.entity)
            .selectinload(Entity.categories)
            .joinedload(EntityCategory.category),
            selectinload(Event.entity).selectinload(Entity.offerings),
        )
    )
    if win_end is not None:
        q = q.where(Event.date <= win_end)

    if needle := _text_needle(filters.entity_name):
        tsq = search_fts.build_tsquery_entity_name_only(filters) if _is_postgres(db) else None
        if tsq:
            q = q.where(
                or_(
                    Event.title.ilike(needle),
                    Event.description.ilike(needle),
                    search_fts.entities_search_vector_match(tsq),
                )
            )
        else:
            q = q.where(or_(Event.title.ilike(needle), Event.description.ilike(needle)))
    if needle := _text_needle(filters.location):
        q = q.where(Event.location_name.ilike(needle))

    if filters.category and filters.category.strip():
        cat_like = _text_needle(filters.category)
        if cat_like:
            q = q.where(
                or_(
                    Event.title.ilike(cat_like),
                    Event.description.ilike(cat_like),
                    cast(Event.tags, String).ilike(cat_like),
                )
            )

    rank_prefix: list[Any] = []
    if _is_postgres(db):
        rank_expr = search_ranking.build_rank_score_expr_for_filters(
            filters,
            last_verified_col=Event.last_verified_at,
            featured_col=Event.featured,
            ref_now=_now_lake_havasu(),
        )
        if rank_expr is not None:
            rank_prefix.append(rank_expr.desc())

    if filters.date_exact is not None:
        starts_today_first = case((Event.date == filters.date_exact, 0), else_=1).asc()
        ordered_q = q.order_by(
            *rank_prefix, starts_today_first, Event.date.asc(), Event.start_time.asc()
        )
    else:
        ordered_q = q.order_by(*rank_prefix, Event.date.asc(), Event.start_time.asc())
    rows = list(db.scalars(ordered_q.limit(limit)).all())

    if filters.category and filters.category.strip():
        rows = [e for e in rows if _category_match_event(e, filters.category or "")]

    if filters.day_of_week:
        allowed = {d.lower() for d in filters.day_of_week}
        rows = [e for e in rows if _event_covers_any_weekday(e, allowed)]

    if span <= 30:
        if len(rows) > MAX_ROWS and win_start is not None and win_end == win_start:
            rows = _event_time_bucket_first_hits(rows, MAX_ROWS)
        return [_event_dict(e) for e in rows[:MAX_ROWS]]

    # Broad window: collapse ``is_recurring`` series (see :func:`_recurring_series_key`), then bucketing if still skewed.
    rows = _dedupe_recurring_preserving_chrono(rows)
    upper = _upper_bound_for_clustering(win_end, rows, lower)
    if upper is None or upper < lower:
        return []
    if _is_still_clustered_early(rows, lower, upper) and len(rows) > MAX_ROWS:
        logging.info(
            "tier2_db_query: time-bucket fired (window_days=%s, total_matches=%s)",
            (upper - lower).days + 1,
            len(rows),
        )
        rows = _time_bucket_first_hits(rows, lower, upper, MAX_ROWS)[:MAX_ROWS]
    else:
        if len(rows) > MAX_ROWS:
            logging.info(
                "tier2_db_query: time-bucket NOT fired (window_days=%s, total_matches=%s)",
                (upper - lower).days + 1,
                len(rows),
            )
        rows = rows[:MAX_ROWS]
    return [_event_dict(e) for e in rows]


def _query_programs(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    if _has_temporal_filter(filters):
        return []

    q = (
        select(Program)
        .outerjoin(Entity, Program.entity_id == Entity.id)
        .where(
            Program.is_active.is_(True),
            Program.draft.is_(False),
            or_(Program.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_PROGRAM),
        )
        .options(
            selectinload(Program.entity)
            .selectinload(Entity.categories)
            .joinedload(EntityCategory.category),
            selectinload(Program.entity).selectinload(Entity.offerings),
        )
    )

    if needle := _text_needle(filters.entity_name):
        tsq = search_fts.build_tsquery_entity_name_only(filters) if _is_postgres(db) else None
        if tsq:
            q = q.where(
                or_(
                    Program.title.ilike(needle),
                    Program.provider_name.ilike(needle),
                    search_fts.entities_search_vector_match(tsq),
                )
            )
        else:
            q = q.where(or_(Program.title.ilike(needle), Program.provider_name.ilike(needle)))
    if needle := _text_needle(filters.location):
        q = q.where(
            or_(
                Program.location_name.ilike(needle),
                Program.location_address.ilike(needle),
            )
        )
    if filters.category and filters.category.strip():
        cat_like = _text_needle(filters.category)
        if cat_like:
            q = q.where(
                or_(
                    Program.title.ilike(cat_like),
                    Program.activity_category.ilike(cat_like),
                    Program.description.ilike(cat_like),
                )
            )

    prog_order: list[Any] = []
    if _is_postgres(db):
        rank_expr = search_ranking.build_rank_score_expr_for_filters(
            filters,
            last_verified_col=Entity.last_verified_at,
            featured_col=Program.featured,
            ref_now=_now_lake_havasu(),
        )
        if rank_expr is not None:
            prog_order.append(rank_expr.desc())
    prog_order.append(Program.title.asc())
    rows = list(db.scalars(q.order_by(*prog_order).limit(80)).all())

    if filters.category and filters.category.strip():
        rows = [p for p in rows if _category_match_program(p, filters.category or "")]

    fmin, fmax = _age_bounds(filters)
    rows = [p for p in rows if _ages_overlap_program(p, fmin, fmax)]

    if filters.day_of_week:
        rows = [p for p in rows if _schedule_matches_days(p, filters.day_of_week)]

    return [_program_dict(p) for p in rows[:MAX_ROWS]]


def _query_providers_orm(db: Session, filters: Tier2Filters) -> list[Provider]:
    if _has_temporal_filter(filters):
        return []

    fmin, fmax = _age_bounds(filters)
    if fmin is not None or fmax is not None:
        return []

    q = (
        select(Provider)
        .outerjoin(Entity, Provider.entity_id == Entity.id)
        .where(
            Provider.draft.is_(False),
            Provider.is_active.is_(True),
            Provider.is_local.isnot(False),  # Lake Havasu-local only (2026-06-19)
            or_(Provider.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
        )
        .options(
            selectinload(Provider.entity)
            .selectinload(Entity.categories)
            .joinedload(EntityCategory.category),
            selectinload(Provider.entity).selectinload(Entity.offerings),
            selectinload(Provider.entity).joinedload(Entity.location),
        )
    )

    if needle := _text_needle(filters.entity_name):
        tsq = search_fts.build_tsquery_entity_name_only(filters) if _is_postgres(db) else None
        if tsq:
            q = q.where(
                or_(
                    Provider.provider_name.ilike(needle),
                    Provider.description.ilike(needle),
                    search_fts.entities_search_vector_match(tsq),
                )
            )
        else:
            q = q.where(
                or_(Provider.provider_name.ilike(needle), Provider.description.ilike(needle))
            )
    if needle := _text_needle(filters.location):
        q = q.outerjoin(Location, Location.entity_id == Entity.id).where(
            or_(Provider.address.ilike(needle), Location.address.ilike(needle))
        )
    if filters.category and filters.category.strip():
        cat = filters.category.strip().lower()
        # Voice battery 2026-05-08 (§4.2): synonym expansion. _category_needle_set
        # returns the full equivalence group + singularized variants so the SQL
        # filter widens to all interchangeable terms (e.g. "coffee shop" also
        # tries "cafe", "barbershop" also tries "barber"). Replaces the prior
        # cat / cat_singular pair logic.
        needle_set = _category_needle_set(cat)
        if needle_set:
            # Slice D: include the Google taxonomy fields. Provider.category is the
            # high-level domain (food_drink, beauty_personal_care, …) — too coarse for
            # category queries like "barber". google_primary_category holds Google's
            # own primary type ("barber_shop", "hair_salon"); google_categories holds
            # the full types array. Stringify + replace("_", " ") so user-typed phrasing
            # ("coffee shop") matches Google's tag format ("coffee_shop"). Both the
            # original and singularized forms run so "coffee shops" still finds matches.
            norm_primary = func.replace(
                func.coalesce(Provider.google_primary_category, ""), "_", " "
            )
            # Voice-battery 2026-05-07: dropped Provider.provider_name from the
            # category-match conditions. Substring match on names produced false
            # positives — "vet" matched "Brooke Vetter, OD" (an optometrist) and
            # "bar" matched "Bare Body and Beauty Bar" + "Barnet Dulaney Perkins
            # Eye Center".
            #
            # Voice-battery 2026-05-08: dropped Provider.description for the same
            # reason. "i need a plumber" matched "Air Control Home Services" (HVAC)
            # because their narrative description mentioned plumbing as an
            # adjacent service. Description is a free-text field, not a taxonomy
            # column; substring match catches narrative mentions that aren't the
            # provider's primary category. Minor recall loss for businesses whose
            # only category signal is in their description text is acceptable vs.
            # the wrong-category bugs the battery surfaced. The actual category
            # signals are now strictly the taxonomy fields below.
            # Voice-battery 2026-05-08 (second pass): also dropped
            # google_categories from the match conditions. Google labels
            # multi-trade companies with the full set of services they offer
            # (Air Control: primary=general_contractor, categories=[plumber,
            # electrician, general_contractor, ...]) — matching against the
            # whole array surfaces general contractors for "I need a plumber"
            # queries. Stick to the *primary* category instead: specialist
            # businesses surface, multi-trade ones don't unless their primary
            # matches. Recall cost is small in practice (most businesses have
            # primary aligned with the most-specific service they offer).
            conditions: list[Any] = []
            for n in needle_set:
                n_like = _text_needle(n)
                if n_like is None:
                    continue
                conditions.append(Provider.category.ilike(n_like))
                conditions.append(norm_primary.ilike(n_like))
            if conditions:
                q = q.where(or_(*conditions))

    order_cols: list[Any] = []
    if _is_postgres(db):
        rank_expr = search_ranking.build_rank_score_expr_for_filters(
            filters,
            last_verified_col=Provider.last_verified_at,
            featured_col=Provider.featured,
            ref_now=_now_lake_havasu(),
        )
        if rank_expr is not None:
            order_cols.append(rank_expr.desc())
    order_cols.append(Provider.provider_name.asc())
    rows = list(db.scalars(q.order_by(*order_cols).limit(80)).all())

    if filters.category and filters.category.strip():
        rows = [p for p in rows if _category_match_provider(p, filters.category or "")]

    if filters.day_of_week:
        return []

    return rows


def _query_providers(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    return [_provider_dict(p) for p in _query_providers_orm(db, filters)[:MAX_ROWS]]


def _sample_mixed(db: Session, cap: int) -> list[dict[str, Any]]:
    """Browse-mode sample: future events, then programs, then providers."""
    today = _today()
    events = list(
        db.scalars(
            select(Event)
            .outerjoin(Entity, Event.entity_id == Entity.id)
            .where(
                Event.status == "live",
                func.coalesce(Event.end_date, Event.date) >= today,
                or_(Event.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_EVENT),
            )
            .order_by(Event.date.asc(), Event.start_time.asc())
            .limit(cap)
        ).all()
    )
    programs = list(
        db.scalars(
            select(Program)
            .outerjoin(Entity, Program.entity_id == Entity.id)
            .where(
                Program.is_active.is_(True),
                Program.draft.is_(False),
                or_(Program.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_PROGRAM),
            )
            .order_by(Program.title.asc())
            .limit(cap)
        ).all()
    )
    providers = list(
        db.scalars(
            select(Provider)
            .outerjoin(Entity, Provider.entity_id == Entity.id)
            .where(
                Provider.draft.is_(False),
                Provider.is_active.is_(True),
                or_(Provider.entity_id.is_(None), Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
            )
            .order_by(Provider.provider_name.asc())
            .limit(cap)
        ).all()
    )
    ev_d = [_event_dict(e) for e in events]
    pr_d = [_program_dict(p) for p in programs]
    pv_d = [_provider_dict(p) for p in providers]
    return _merge_simple(ev_d, pr_d, pv_d)[:cap]


def query(
    filters: Tier2Filters,
    *,
    ctx: ChatRequestContext | None = None,
) -> list[dict[str, Any]]:
    """Return up to eight catalog rows matching ``filters``."""
    request_ctx = ctx or ChatRequestContext()
    with SessionLocal() as db:
        if not _has_query_dimensions(filters):
            if prefers_entity_catalog(filters, request_ctx):
                return query_entities(db, filters, request_ctx, max_rows=MAX_ROWS)
            return _sample_mixed(db, MAX_ROWS)

        if prefers_entity_catalog(filters, request_ctx) and not _has_temporal_filter(filters):
            entity_rows = query_entities(db, filters, request_ctx, max_rows=MAX_ROWS)
            if entity_rows:
                return entity_rows

        f_sql = filters.model_copy(update={"open_now": False})
        events = _query_events(db, f_sql)
        programs = _query_programs(db, f_sql)
        prov_orm = _query_providers_orm(db, f_sql)

        if filters.open_now is True:
            now_local = _now_lake_havasu()
            # Lenient open-now (P1-11): keep providers that are open OR whose
            # hours are unknown; drop only those whose hours say closed. This
            # matches the intent layer (intents/queries.py "degrade gracefully")
            # and avoids gutting "what's open now" for the many catalog
            # providers without structured hours — a soft filter, not a hard one.
            kept = []
            for p in prov_orm:
                hs = effective_hours_structured(p)
                if hs and not is_open_at(hs, now_local):
                    continue
                kept.append(p)
            prov_orm = kept

        providers = [_provider_dict(p) for p in prov_orm[:MAX_ROWS]]
        return _merge_simple(events, programs, providers)[:MAX_ROWS]
