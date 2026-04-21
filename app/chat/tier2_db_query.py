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

_WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _today() -> date:
    """Calendar \"today\" for catalog date filters (monkeypatch in tests)."""
    return date.today()


def _weekday_name(d: date) -> str:
    return _WEEKDAY_NAMES[d.weekday()]


def _only_time_window(filters: Tier2Filters) -> bool:
    """True when ``time_window`` is the only structured dimension (events-only)."""
    if filters.time_window is None:
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
    return ref, None


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


def _query_events(db: Session, filters: Tier2Filters) -> list[dict[str, Any]]:
    today = _today()
    win_start, win_end = _resolve_time_window(filters.time_window, today)
    lower = win_start if win_start is not None else today
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
        db.scalars(q.order_by(Event.date.asc(), Event.start_time.asc()).limit(80)).all()
    )

    if filters.category and filters.category.strip():
        rows = [e for e in rows if _category_match_event(e, filters.category or "")]

    if filters.day_of_week:
        allowed = {d.lower() for d in filters.day_of_week}
        rows = [e for e in rows if _weekday_name(e.date) in allowed]

    return [_event_dict(e) for e in rows[:MAX_ROWS]]


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
