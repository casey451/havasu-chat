"""Query templates for resolved intents (Ask Hava intent catalog, Phase 1).

Each ``run_query`` dispatch turns a ``ResolvedIntent`` into a ``QueryResult``
against the REAL models -- no fabricated fields. Empty results are returned
honestly (``rows == []``); the runtime renders the "/contribute" nudge.

Rows are emitted in the **tier2 row-dict shape** so the existing component
builders (``app.chat.component_builders``) can render real cards
(``business_list`` for providers, ``day_agenda`` / ``week_strip`` for events)
without a parallel card format.

Grounding cheat-sheet (see app/chat/intents/__init__.py):
* Providers: rank by ``google_rating`` / ``google_review_count``; service
  granularity via ``subcategory`` group + name tokens; ``district`` ilike.
* Events: ``app.events.queries.events_in_window`` (status='live', date+time).
* Programs: ``age_min`` / ``age_max`` overlap, ``cost`` lives here (not Event).
* Gas: ``external_conditions_cache`` source ``gas_prices_lhc``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.chat.intents import dicts
from app.chat.intents.resolver import ResolvedIntent
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.core.liveness import liveness_dampener
from app.core.timezone import now_lake_havasu
from app.db.models import Event, Offering, Program, Provider
from app.programs.pricing import format_offering_price, format_program_price
from app.providers.queries import is_open_now

_PROVIDER_LIMIT = 12
_EVENT_LIMIT = 24


@dataclass
class QueryResult:
    intent_key: str
    kind: str  # "providers" | "events" | "programs" | "gas"
    rows: list[dict[str, Any]] = field(default_factory=list)
    category_hint: str | None = None
    lead_in: str = ""
    label: str = "businesses"  # human noun for the business_list header
    window: str | None = None  # event window token (for day_agenda vs week_strip)

    @property
    def result_count(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Provider queries
# ---------------------------------------------------------------------------


def _provider_sort_key(p: Provider) -> tuple:
    """Rated-first, then rating desc, then review count desc (reverse=True).

    The rating term is scaled by the liveness dampener so a stale-but-once-
    popular listing sinks below fresh peers in chat business lists (bury,
    never remove). NULL liveness -> multiplier 1.0 (non-Google rows / backfill
    pending are unaffected).
    """
    return (
        p.google_rating is not None,
        (p.google_rating or 0.0)
        * liveness_dampener(getattr(p, "liveness_score", None)),
        p.google_review_count or 0,
    )


def _query_providers(
    db: Session,
    *,
    subcats: tuple[str, ...] = (),
    legacy_categories: tuple[str, ...] = (),
    name_tokens: tuple[str, ...] = (),
    district: str | None = None,
    open_now: bool = False,
    limit: int = _PROVIDER_LIMIT,
    now: datetime | None = None,
) -> list[Provider]:
    q = db.query(Provider).filter(
        Provider.is_active.is_(True),
        Provider.draft.is_(False),
    )
    bucket_conds = []
    if subcats:
        bucket_conds.append(Provider.subcategory.in_(subcats))
    if legacy_categories:
        bucket_conds.append(Provider.category.in_(legacy_categories))
    if bucket_conds:
        q = q.filter(or_(*bucket_conds))

    if name_tokens:
        token_conds = []
        for tok in name_tokens:
            like = f"%{tok}%"
            token_conds.append(Provider.provider_name.ilike(like))
            token_conds.append(Provider.google_primary_category.ilike(like))
            token_conds.append(Provider.category.ilike(like))
        q = q.filter(or_(*token_conds))

    if district:
        # District is sparsely populated (Phase-0 audit: ~0% on the dev DB), so
        # treat area as a soft preference: filter by it, but fall back to the
        # un-filtered set rather than erasing all results.
        district_rows = list(q.filter(Provider.district.ilike(f"%{district}%")).all())
        rows = district_rows if district_rows else list(q.all())
    else:
        rows = list(q.all())
    rows.sort(key=_provider_sort_key, reverse=True)

    if open_now:
        kept: list[Provider] = []
        for p in rows:
            is_open, _ = is_open_now(p, now=now)
            if is_open is False:
                continue  # explicitly closed -> drop for an open-now ask
            kept.append(p)  # open or hours-unknown (degrade gracefully)
        rows = kept

    return rows[:limit]


def _thumb_url(p: Provider) -> str | None:
    try:
        from app.providers.photo_urls import first_renderable_google_photo

        return first_renderable_google_photo(p)
    except Exception:
        return None


def _provider_to_row(p: Provider) -> dict[str, Any]:
    """Tier2 provider-row shape consumed by build_business_list."""
    return {
        "type": "provider",
        "id": p.id,
        "name": p.provider_name,
        "slug": p.slug,
        "phone": p.phone,
        "address": p.address,
        "category": p.category,
        "google_primary_category": p.google_primary_category,
        "google_rating": p.google_rating,
        "google_review_count": p.google_review_count,
        "hours_structured": p.hours_structured,
        "description": p.description,
        "tier": p.tier,
        "sponsored_until": p.sponsored_until,
        "thumb_url": _thumb_url(p),
    }


# ---------------------------------------------------------------------------
# Event window helper + rows
# ---------------------------------------------------------------------------


def _event_window_dates(window: str, today: date) -> tuple[date, date]:
    from app.events.queries import event_window_for_chip

    if window == "today":
        return today, today
    if window == "tomorrow":
        t = today + timedelta(days=1)
        return t, t
    if window == "this_weekend":
        return event_window_for_chip("this-weekend", today=today)
    if window == "this_week":
        return event_window_for_chip("this-week", today=today)
    if window == "next_week":
        monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
        return monday, monday + timedelta(days=6)
    if window == "next_month":
        return event_window_for_chip("next-month", today=today)
    return today, today + timedelta(days=30)


def _event_to_row(event, occ: date) -> dict[str, Any]:
    """Tier2 event-row shape consumed by build_day_agenda / build_week_strip."""
    return {
        "type": "event",
        "name": event.title,
        "date": occ.isoformat(),
        "end_date": event.end_date.isoformat() if event.end_date else None,
        "start_time": event.start_time.strftime("%H:%M") if event.start_time else None,
        "end_time": event.end_time.strftime("%H:%M") if event.end_time else None,
        "location_name": event.location_name,
        "tags": list(event.tags or []),
        "event_url": event.event_url,
    }


def _query_events(
    db: Session, window: str, *, today: date, activity: str | None
) -> list[dict[str, Any]]:
    from app.events.queries import events_in_window

    start, end = _event_window_dates(window, today)
    pairs = events_in_window(db, window_start=start, window_end=end, limit=_EVENT_LIMIT)
    rows: list[dict[str, Any]] = []
    for event, occ in pairs:
        if activity == "live_music":
            tags = [str(x).lower() for x in (event.tags or [])]
            blob = f"{event.title} {' '.join(tags)}".lower()
            if not any(k in blob for k in ("music", "concert", "band", "dj", "acoustic")):
                continue
        rows.append(_event_to_row(event, occ))
    return rows


# ---------------------------------------------------------------------------
# Programs (kids lessons / classes) -- cost + age live here, not on Event.
# ---------------------------------------------------------------------------


def _safe_time_label(t) -> str:
    if t is None:
        return ""
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {suffix}" if t.minute else f"{h12} {suffix}"


def _offering_by_program(db: Session, programs: list[Program]) -> dict[str, Offering]:
    """Map program id -> its entity's first priced ``Offering``.

    Price "lives on offerings": Program.provider_id -> Provider.entity_id ->
    Offering.entity_id. Picks the lowest-display_order offering that actually
    carries a price; programs with no linked priced offering are absent (the
    caller falls back to ``Program.cost``). Two batched queries, no N+1.
    """
    prov_ids = {p.provider_id for p in programs if p.provider_id}
    if not prov_ids:
        return {}
    ent_by_prov = dict(
        db.query(Provider.id, Provider.entity_id).filter(Provider.id.in_(prov_ids)).all()
    )
    eids = {e for e in ent_by_prov.values() if e}
    if not eids:
        return {}
    priced_by_eid: dict[str, Offering] = {}
    for off in (
        db.query(Offering).filter(Offering.entity_id.in_(eids)).order_by(Offering.display_order).all()
    ):
        if off.entity_id not in priced_by_eid and format_offering_price(off):
            priced_by_eid[off.entity_id] = off
    out: dict[str, Offering] = {}
    for p in programs:
        eid = ent_by_prov.get(p.provider_id) if p.provider_id else None
        if eid and eid in priced_by_eid:
            out[p.id] = priced_by_eid[eid]
    return out


# Venue-name tokens that never identify a venue (town words + connectors).
# "Lake Havasu City Aquatic Center" and the events feed's "Lake Havasu Aquatic
# Center" must both reduce to {aquatic, center}.
_VENUE_STOP_TOKENS: frozenset[str] = frozenset(
    {"the", "a", "an", "of", "and", "at", "in", "on",
     "lake", "havasu", "city", "arizona", "az", "lhc"}
)


def _venue_core_tokens(venue: str) -> list[str]:
    return [
        t
        for t in re.split(r"[^a-z0-9]+", (venue or "").lower())
        if t and t not in _VENUE_STOP_TOKENS
    ]


def _fmt_time(t: time) -> str:
    """12-hour 'H:MM AM' label. Cross-platform — ``%-I`` is glibc-only and
    raises ``ValueError: Invalid format string`` on Windows (and ``%#I`` is the
    MSVC spelling), so compute the hour/meridiem directly instead of strftime."""
    hour12 = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    return f"{hour12}:{t.minute:02d} {meridiem}"


def _query_venue_schedule(
    db: Session, venue: str, *, today: date, limit: int = _PROVIDER_LIMIT
) -> list[dict[str, Any]]:
    """Programs + upcoming events at a matched venue (2026-06-06 gap report:
    "what water exercise classes does the aquatic center offer and when" paid
    Tier 3). Match = every core venue token appears in the row's provider/
    location name (per-token ilike, AND), so feed spelling variants still hit
    while "Mudshark Pizza" can never match "Mudshark Brewery and Public House".
    """
    core = _venue_core_tokens(venue)
    if not core:
        return []
    rows: list[dict[str, Any]] = []

    pq = db.query(Program).filter(Program.is_active.is_(True))
    for tok in core:
        like = f"%{tok}%"
        pq = pq.filter(
            or_(Program.provider_name.ilike(like), Program.location_name.ilike(like))
        )
    programs = pq.limit(limit).all()
    offering_by_prog = _offering_by_program(db, programs)
    for prog in programs:
        days = ", ".join(prog.schedule_days) if prog.schedule_days else ""
        start = _fmt_time(prog.schedule_start_time) if prog.schedule_start_time else ""
        when = " ".join(b for b in (days, start) if b)
        rows.append(
            {
                "type": "program",
                "name": prog.title,
                "subtitle": when or prog.location_name,
                "detail": format_program_price(prog.cost, offering_by_prog.get(prog.id)),
            }
        )

    eq = db.query(Event).filter(Event.status == "live", Event.date >= today)
    for tok in core:
        eq = eq.filter(Event.location_name.ilike(f"%{tok}%"))
    events = eq.order_by(Event.date, Event.start_time).limit(limit).all()
    for ev in events:
        start = _fmt_time(ev.start_time) if ev.start_time else ""
        rows.append(
            {
                "type": "event",
                "name": ev.title,
                "subtitle": " ".join(b for b in (ev.date.isoformat(), start) if b),
                "detail": "",
            }
        )
    return rows[:limit]


def _query_programs(
    db: Session,
    *,
    age_band: str | None,
    activity_category: str | None = None,
    limit: int = _PROVIDER_LIMIT,
) -> list[dict[str, Any]]:
    q = db.query(Program).filter(Program.is_active.is_(True))
    if activity_category:
        q = q.filter(Program.activity_category.ilike(f"%{activity_category}%"))
    rng = dicts.age_band_range(age_band)
    if rng is not None:
        lo, hi = rng
        # Overlap: program's [age_min, age_max] intersects the band. NULL age
        # bounds are treated as open (kept) so thin age data degrades gracefully.
        q = q.filter(
            or_(Program.age_min.is_(None), Program.age_min <= hi),
            or_(Program.age_max.is_(None), Program.age_max >= lo),
        )
    programs = q.limit(limit).all()
    offering_by_prog = _offering_by_program(db, programs)
    rows: list[dict[str, Any]] = []
    for prog in programs:
        days = ", ".join(prog.schedule_days) if prog.schedule_days else ""
        sub_bits = [b for b in (prog.provider_name, days) if b]
        rows.append(
            {
                "type": "program",
                "name": prog.title,
                "subtitle": " · ".join(sub_bits),
                # Price lives on offerings; fall back to the program's freeform cost.
                "detail": format_program_price(prog.cost, offering_by_prog.get(prog.id)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Gas
# ---------------------------------------------------------------------------


def _query_gas(db: Session) -> list[dict[str, Any]]:
    res = read_source(db, SOURCE_GAS)
    if res is None or not isinstance(res.data, dict):
        return []
    stations = res.data.get("stations")
    if not isinstance(stations, list):
        return []
    priced: list[tuple[float, dict]] = []
    for st in stations:
        if not isinstance(st, dict):
            continue
        prices = st.get("prices") if isinstance(st.get("prices"), dict) else st
        regular = prices.get("regular") if isinstance(prices, dict) else None
        try:
            val = float(regular)
        except (TypeError, ValueError):
            continue
        priced.append((val, st))
    priced.sort(key=lambda x: x[0])
    rows: list[dict[str, Any]] = []
    for val, st in priced[:5]:
        name = str(st.get("name") or st.get("brand") or "Gas station")
        addr = st.get("address") or ""
        rows.append(
            {
                "type": "gas",
                "name": name,
                "subtitle": str(addr),
                "detail": f"${val:.2f}/gal regular",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_EAT_LEAD = "Here's what's good to eat:"
_SERVICE_LEAD = "Here's who can help:"


def run_query(
    resolved: ResolvedIntent,
    db: Session,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> QueryResult:
    key = resolved.intent_key
    slots = resolved.slots
    if today is None:
        today = now_lake_havasu().date()

    if key == "cheapest_gas":
        return QueryResult(key, "gas", _query_gas(db), None, "Cheapest gas in town right now:")

    if key.startswith("events_"):
        window = str(slots.get("window") or "upcoming")
        activity = slots.get("activity")
        rows = _query_events(
            db, window, today=today, activity=activity if isinstance(activity, str) else None
        )
        return QueryResult(
            key, "events", rows, "events", "Here's what's coming up:", window=window
        )

    if key in ("find_service", "urgent_care"):
        if key == "urgent_care":
            route = dicts.SYMPTOM_MAP.get(str(slots.get("symptom") or ""))
            subcats = ("health-medical",)
            name_tokens = route.name_tokens if route else ()
            legacy: tuple[str, ...] = ("health_medical",)
            label = "clinics"
        else:
            sroute = dicts.SERVICE_DICT.get(str(slots.get("service") or ""))
            if sroute is None:
                return QueryResult(key, "providers", [], "services", _SERVICE_LEAD)
            subcats = (sroute.subcat,)
            name_tokens = sroute.name_tokens
            legacy = sroute.legacy_categories
            label = str(slots.get("service") or "businesses")
        rows = _query_providers(
            db,
            subcats=subcats,
            legacy_categories=legacy,
            name_tokens=name_tokens,
            district=_area(slots),
            open_now=bool(slots.get("open_now")),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "services",
            _SERVICE_LEAD,
            label=label,
        )

    if key in ("eat_find", "eat_open_now"):
        cuisine = str(slots.get("cuisine") or "")
        name_tokens = dicts.CUISINE_DICT.get(cuisine, ())
        subcats = dicts.EAT_SUBCATS
        if cuisine in dicts.CUISINE_TO_SUBCAT:
            subcats = (dicts.CUISINE_TO_SUBCAT[cuisine],)
        rows = _query_providers(
            db,
            subcats=subcats,
            legacy_categories=dicts.EAT_LEGACY_CATEGORIES,
            name_tokens=name_tokens,
            district=_area(slots),
            open_now=bool(slots.get("open_now")) or key == "eat_open_now",
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "food_drink",
            _EAT_LEAD,
            label=f"{cuisine} spot" if cuisine else "restaurant",
        )

    if key in ("gym_fitness", "yoga_pilates", "martial_arts", "pickleball"):
        subcat = {
            "gym_fitness": "gyms",
            "yoga_pilates": "studios",
            "martial_arts": "martial-arts",
            "pickleball": "racquet-sports",
        }[key]
        label = {
            "gym_fitness": "gym",
            "yoga_pilates": "studio",
            "martial_arts": "martial arts studio",
            "pickleball": "court",
        }[key]
        rows = _query_providers(
            db,
            subcats=(subcat,),
            legacy_categories=("fitness_sports", "fitness"),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "classes_sports_recreation",
            "Here's where to break a sweat:",
            label=label,
        )

    if key == "venue_schedule":
        venue = str(slots.get("venue") or "")
        if today is None:
            today = now_lake_havasu().date()
        rows = _query_venue_schedule(db, venue, today=today)
        return QueryResult(
            key,
            "programs",
            rows,
            "venue_schedule",
            f"On the calendar at {venue}:",
            label=venue,
        )

    if key == "kids_lessons":
        rows = _query_programs(db, age_band=str(slots.get("age_band") or "kids"))
        return QueryResult(
            key, "programs", rows, "classes_sports_recreation", "Classes for the kids:"
        )

    if key == "classes_find":
        topic = str(slots.get("topic") or "") or None
        rows = _query_programs(db, age_band=None, activity_category=topic)
        lead = f"{topic.title()} classes around town:" if topic else "Classes and programs around town:"
        return QueryResult(key, "programs", rows, "classes_sports_recreation", lead)

    if key == "lodging_find":
        rows = _query_providers(
            db,
            subcats=dicts.STAY_SUBCATS,
            legacy_categories=dicts.STAY_LEGACY_CATEGORIES,
            district=_area(slots),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "lodging_vacation_rentals",
            "Places to stay:",
            label="hotel",
        )

    if key == "shopping_find":
        rows = _query_providers(
            db,
            subcats=dicts.SHOPPING_SUBCATS,
            legacy_categories=dicts.SHOPPING_LEGACY_CATEGORIES,
            district=_area(slots),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "shopping_essentials",
            "Where to shop:",
            label="shop",
        )

    if key in ("boat_rental", "boat_repair", "on_the_water"):
        # Rent / repair narrow the on-the-water bucket by name token; the general
        # on_the_water ask returns the whole bucket. Tokens are a soft narrowing
        # within the bucket -- an empty result falls through to the honest gap.
        name_tokens: tuple[str, ...] = ()
        if key == "boat_rental":
            name_tokens = ("rent", "rental", "boat", "kayak", "paddle", "watercraft")
            lead = "Where to get out on the water:"
            label = "rental"
        elif key == "boat_repair":
            name_tokens = ("repair", "service", "marine", "boat")
            lead = "Boat service and repair:"
            label = "shop"
        else:
            lead = "Out on the water:"
            label = "spot"
        rows = _query_providers(
            db,
            subcats=dicts.WATER_SUBCATS,
            legacy_categories=dicts.WATER_LEGACY_CATEGORIES,
            name_tokens=name_tokens,
            district=_area(slots),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "on_the_water",
            lead,
            label=label,
        )

    if key == "parks_trails":
        rows = _query_providers(
            db,
            subcats=dicts.RECREATION_SUBCATS,
            legacy_categories=dicts.RECREATION_LEGACY_CATEGORIES,
            district=_area(slots),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "recreation_outdoors",
            "Parks, trails, and beaches:",
            label="spot",
        )

    if key == "civic_resources":
        rows = _query_providers(
            db,
            subcats=dicts.CIVIC_SUBCATS,
            legacy_categories=dicts.CIVIC_LEGACY_CATEGORIES,
            district=_area(slots),
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "civic_community",
            "Community resources:",
            label="resource",
        )

    # Unknown intent key -> empty (caller falls through / renders nothing).
    return QueryResult(key, "providers", [], None, "")


def _area(slots: dict[str, object]) -> str | None:
    a = slots.get("area")
    return a if isinstance(a, str) and a else None
