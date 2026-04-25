"""Tier 2 catalog lookup from structured filters (Phase 4.2).

``query`` returns up to eight JSON-serializable row dicts for ``tier2_formatter``.

When no query-shaping dimensions are set (entity, category, ages, location,
days, time window, or open-now), the function returns a small mixed sample of
live catalog rows so downstream formatting still has material to work with.

When ``open_now=True``, provider rows are filtered in Python using
``providers.hours_structured`` and :func:`app.contrib.hours_helper.is_open_at`.
Providers without structured hours are omitted. Events and programs are still
returned using the same SQL filters with ``open_now`` stripped for the query
builder (open/closed for events/programs is out of scope for Phase 5.6).

# open_now filtering happens in Python after SQL fetch because hours are JSON.
# At current scale (<100 providers) this is negligible. Consider a SQL-side
# derivation (e.g., computed column or materialized view) if scale grows.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.chat.tier2_schema import Tier2Filters
from app.contrib.hours_helper import LAKE_HAVASU_TZ, is_open_at
from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider

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
    """Calendar \"today\" for catalog date filters (monkeypatch in tests)."""
    return date.today()


def _weekday_name(d: date) -> str:
    return _WEEKDAY_NAMES[d.weekday()]


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


def _resolve_time_window(
    tw: str | None, ref: date
) -> tuple[date | None, date | None]:
    """Inclusive (start, end); ``(ref, None)`` means from ``ref`` forward without upper bound."""
    if tw is None:
        return ref, None
    if tw == "today":
        return ref, ref
    if tw == "tomorrow":
        t = ref + timedelta(days=1)
        return t, t
    if tw == "this_week":
        start = ref - timedelta(days=ref.weekday())
        end = start + timedelta(days=6)
        return start, end
    if tw == "this_weekend":
        wd = ref.weekday()
        if wd < 5:
            days_to_sat = 5 - wd
        elif wd == 5:
            days_to_sat = 0
        else:
            days_to_sat = 6
        sat = ref + timedelta(days=days_to_sat)
        sun = sat + timedelta(days=1)
        return sat, sun
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


def _program_location_display(location_name: str | None, location_address: str | None) -> str | None:
    """Single compact location string for program row payloads (Phase 4.5)."""
    n = (location_name or "").strip()
    a = (location_address or "").strip()
    if not n and not a:
        return None
    if n and a and n != a:
        return f"{n} ({a})"
    return n or a or None


def _event_dict(e: Event) -> dict[str, Any]:
    return {
        "type": "event",
        "name": e.title,
        "date": e.date.isoformat(),
        "start_time": e.start_time.strftime("%H:%M") if e.start_time else None,
        "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
        "location_name": e.location_name,
        "description": _truncate(e.description, 120),
        "tags": list(e.tags or [])[:8],
    }


def _program_dict(p: Program) -> dict[str, Any]:
    ages = None
    if p.age_min is not None or p.age_max is not None:
        ages = f"{p.age_min if p.age_min is not None else '?'}-{p.age_max if p.age_max is not None else '?'}"
    loc = _program_location_display(p.location_name, p.location_address)
    out: dict[str, Any] = {
        "type": "program",
        "name": p.title,
        "provider_name": p.provider_name,
        "activity_category": p.activity_category,
        "age_range": ages,
        "schedule_days": list(p.schedule_days or [])[:7],
        "schedule_hours": f"{p.schedule_start_time}-{p.schedule_end_time}",
        "cost": p.cost,
        "description": _truncate(p.description, 120),
        "tags": list(p.tags or [])[:8],
    }
    if loc:
        out["location"] = loc
    return out


def _provider_dict(p: Provider) -> dict[str, Any]:
    return {
        "type": "provider",
        "name": p.provider_name,
        "category": p.category,
        "address": p.address,
        "phone": p.phone,
        "hours": _truncate(p.hours, 120),
        "description": _truncate(p.description, 120),
    }


def _now_lake_havasu() -> datetime:
    """Current instant in Lake Havasu local time (America/Phoenix; override in tests)."""
    return datetime.now(LAKE_HAVASU_TZ)


def _text_needle(s: str | None) -> str | None:
    if not s or not str(s).strip():
        return None
    return f"%{str(s).strip()}%"


def _category_match_event(e: Event, cat: str) -> bool:
    c = cat.strip().lower()
    if c in (e.title or "").lower():
        return True
    if c in (e.description or "").lower():
        return True
    for t in e.tags or []:
        if isinstance(t, str) and c in t.lower():
            return True
    return False


def _category_match_program(p: Program, cat: str) -> bool:
    c = cat.strip().lower()
    if c in (p.title or "").lower() or c in (p.activity_category or "").lower():
        return True
    if c in (p.description or "").lower():
        return True
    for t in p.tags or []:
        if isinstance(t, str) and c in t.lower():
            return True
    return False


def _category_match_provider(p: Provider, cat: str) -> bool:
    c = cat.strip().lower()
    if c in (p.provider_name or "").lower() or c in (p.category or "").lower():
        return True
    if p.description and c in p.description.lower():
        return True
    return False


def _row_dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Stable identity for merged rows after ``id`` was dropped from payloads (Phase 4.5)."""
    t = str(row.get("type"))
    if t == "event":
        return (t, row.get("name"), row.get("date"), row.get("start_time"))
    if t == "program":
        return (t, row.get("name"), row.get("provider_name"), row.get("schedule_hours"), row.get("location"))
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


def _filter_window_span_inclusive(
    win_start: date | None, win_end: date | None, ref: date
) -> int:
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
    mx = max(x.date for x in events)
    if mx < lower:
        return lower
    return mx


def _is_still_clustered_early(
    events: list[Event], lower: date, upper: date
) -> bool:
    if len(events) < 4:
        return False
    w = max(0, (upper - lower).days) + 1
    if w < 2:
        return False
    mid = events[min(7, len(events) - 1)]
    return (mid.date - lower).days < (w * 0.3)


def _time_bucket_first_hits(
    evs: list[Event], lower: date, upper: date, k: int
) -> list[Event]:
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


def _query_events(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    today = _today()
    win_start, win_end = _resolve_effective_event_window(filters, today)
    lower = max(win_start, today) if win_start is not None else today
    if win_end is not None and win_end < lower:
        return []
    span = _filter_window_span_inclusive(win_start, win_end, today)
    limit = NARROW_EVENT_SQL_LIMIT if span <= 30 else BROAD_EVENT_SQL_LIMIT
    q = select(Event).where(Event.status == "live", Event.date >= lower)
    if win_end is not None:
        q = q.where(Event.date <= win_end)

    if needle := _text_needle(filters.entity_name):
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
                )
            )

    rows = list(
        db.scalars(
            q.order_by(Event.date.asc(), Event.start_time.asc()).limit(limit)
        ).all()
    )

    if filters.category and filters.category.strip():
        rows = [e for e in rows if _category_match_event(e, filters.category or "")]

    if filters.day_of_week:
        allowed = {d.lower() for d in filters.day_of_week}
        rows = [e for e in rows if _weekday_name(e.date) in allowed]

    if span <= 30:
        return [_event_dict(e) for e in rows[:MAX_ROWS]]

    # Broad window: collapse ``is_recurring`` series (see :func:`_recurring_series_key`), then bucketing if still skewed.
    rows = _dedupe_recurring_preserving_chrono(rows)
    upper = _upper_bound_for_clustering(win_end, rows, lower)
    if upper is None or upper < lower:
        return []
    if _is_still_clustered_early(rows, lower, upper) and len(rows) > MAX_ROWS:
        rows = _time_bucket_first_hits(rows, lower, upper, MAX_ROWS)[:MAX_ROWS]
    else:
        rows = rows[:MAX_ROWS]
    return [_event_dict(e) for e in rows]


def _query_programs(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    if _only_time_window(filters):
        return []

    q = select(Program).where(Program.is_active.is_(True), Program.draft.is_(False))

    if needle := _text_needle(filters.entity_name):
        q = q.where(
            or_(
                Program.title.ilike(needle),
                Program.provider_name.ilike(needle),
            )
        )
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

    rows = list(db.scalars(q.order_by(Program.title.asc()).limit(80)).all())

    if filters.category and filters.category.strip():
        rows = [p for p in rows if _category_match_program(p, filters.category or "")]

    fmin, fmax = _age_bounds(filters)
    rows = [p for p in rows if _ages_overlap_program(p, fmin, fmax)]

    if filters.day_of_week:
        rows = [p for p in rows if _schedule_matches_days(p, filters.day_of_week)]

    return [_program_dict(p) for p in rows[:MAX_ROWS]]


def _query_providers_orm(db: Session, filters: Tier2Filters) -> list[Provider]:
    if _only_time_window(filters):
        return []

    fmin, fmax = _age_bounds(filters)
    if fmin is not None or fmax is not None:
        return []

    q = select(Provider).where(Provider.draft.is_(False), Provider.is_active.is_(True))

    if needle := _text_needle(filters.entity_name):
        q = q.where(
            or_(
                Provider.provider_name.ilike(needle),
                Provider.description.ilike(needle),
            )
        )
    if needle := _text_needle(filters.location):
        q = q.where(Provider.address.ilike(needle))
    if filters.category and filters.category.strip():
        cat_like = _text_needle(filters.category)
        if cat_like:
            q = q.where(
                or_(
                    Provider.category.ilike(cat_like),
                    Provider.provider_name.ilike(cat_like),
                    Provider.description.ilike(cat_like),
                )
            )

    rows = list(db.scalars(q.order_by(Provider.provider_name.asc()).limit(80)).all())

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
            .where(Event.status == "live", Event.date >= today)
            .order_by(Event.date.asc(), Event.start_time.asc())
            .limit(cap)
        ).all()
    )
    programs = list(
        db.scalars(
            select(Program)
            .where(Program.is_active.is_(True), Program.draft.is_(False))
            .order_by(Program.title.asc())
            .limit(cap)
        ).all()
    )
    providers = list(
        db.scalars(
            select(Provider)
            .where(Provider.draft.is_(False), Provider.is_active.is_(True))
            .order_by(Provider.provider_name.asc())
            .limit(cap)
        ).all()
    )
    ev_d = [_event_dict(e) for e in events]
    pr_d = [_program_dict(p) for p in programs]
    pv_d = [_provider_dict(p) for p in providers]
    return _merge_simple(ev_d, pr_d, pv_d)[:cap]


def query(filters: Tier2Filters) -> list[dict[str, Any]]:
    """Return up to eight catalog rows matching ``filters``."""
    with SessionLocal() as db:
        if not _has_query_dimensions(filters):
            return _sample_mixed(db, MAX_ROWS)

        f_sql = filters.model_copy(update={"open_now": False})
        events = _query_events(db, f_sql)
        programs = _query_programs(db, f_sql)
        prov_orm = _query_providers_orm(db, f_sql)

        if filters.open_now is True:
            now_local = _now_lake_havasu()
            prov_orm = [
                p
                for p in prov_orm
                if isinstance(p.hours_structured, dict)
                and p.hours_structured
                and is_open_at(p.hours_structured, now_local)
            ]

        providers = [_provider_dict(p) for p in prov_orm[:MAX_ROWS]]
        return _merge_simple(events, programs, providers)[:MAX_ROWS]
