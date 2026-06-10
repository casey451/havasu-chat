"""Data assembly for the Sandstone home (Ask) page.

Every figure here comes from a live query or is omitted — never a placeholder.
The prototype's hardcoded counts ("280 places", "12 happy hours", "448.7 ft")
are deliberately NOT reproduced: a tile with no live source is left out, and the
anti-confabulation contract in 01_UI_BUILD_GUIDE.md §4 is the spec.

Kept separate from ``router.py`` so the route stays a thin assembler and these
builders are unit-testable in isolation.
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Event
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.dedup import dedup_cross_source_occurrences
from app.events.recurrence import occurrences_in_window
from app.events.time_labels import format_short_time, short_time_label, time_sort_key


def _live_events_by_day(
    db: Session, *, window_start: date, window_end: date
) -> dict[date, list[Event]]:
    """Live events bucketed by *occurrence* date across the inclusive window.

    Events with a real schedule (``rrule``/``rdate``) are expanded via
    :func:`app.events.recurrence.occurrences_in_window`, so a weekly class shows
    on every occurrence in the window — not only on its stored start date — the
    same expansion ``/events-ui`` uses. Separately, any event whose *stored* date
    falls in the window is included on that date. This second pass is load-bearing:
    a row flagged ``is_recurring`` but carrying no rrule/rdate (a materialised
    single instance) would otherwise expand to nothing and vanish. Each
    ``(event, date)`` pair is emitted once, then cross-source duplicates of the
    same (title, date) occurrence (two scrapers carrying one real-world event)
    collapse to a single survivor via
    :func:`app.events.dedup.dedup_cross_source_occurrences`.
    """
    stmt = select(Event).where(
        Event.status == "live",
        or_(
            Event.date.between(window_start, window_end),
            Event.rrule.isnot(None),
            Event.rdate.isnot(None),
        ),
    )
    candidates = list(db.scalars(stmt).unique().all())

    pairs: list[tuple[Event, date]] = []
    seen: set[tuple[Any, date]] = set()

    def _emit(ev: Event, occ_date: date) -> None:
        key = (ev.id, occ_date)
        if key in seen:
            return
        seen.add(key)
        pairs.append((ev, occ_date))

    scheduled = [c for c in candidates if c.rrule or c.rdate]
    for ev, occ_date in occurrences_in_window(
        scheduled, window_start=window_start, window_end=window_end
    ):
        _emit(ev, occ_date)

    for ev in candidates:
        if ev.date is not None and window_start <= ev.date <= window_end:
            _emit(ev, ev.date)

    by_day: dict[date, list[Event]] = {}
    for ev, occ_date in dedup_cross_source_occurrences(pairs):
        by_day.setdefault(occ_date, []).append(ev)
    return by_day

# ---------------------------------------------------------------------------
# Explore strips — driven by the live A.3 taxonomy departments
# ---------------------------------------------------------------------------
#
# The 15 level-0 departments ARE the category nav (2026-06-09 rewire; the old
# lumped CATEGORY_FILTERS buckets are retired and 301 away). Labels and counts
# come from the live Category tree via ``leaf_pages.all_departments`` — one
# grouped query — so a renamed department or a newly gate-clearing leaf shows
# up here without touching this file. A department absent from the DB (or
# with no gate-clearing leaf) is omitted: honest omission, never a dead link.


def _department_rows(db: Session) -> list[dict[str, Any]]:
    """``{slug, name, count}`` per department in taxonomy order; [] on error."""
    from app.categories import leaf_pages

    try:
        return [
            {"slug": dept.slug, "name": dept.name, "count": total}
            for dept, _leaf_n, total in leaf_pages.all_departments(db)
        ]
    except Exception:  # pragma: no cover - defensive; never block the page
        return []


def explore_tiles(db: Session) -> list[dict[str, Any]]:
    """Every taxonomy department with its live leaf-summed count, in taxonomy
    order. Counts are primary-link based, so they never overlap or double
    count a business across tiles."""
    return [
        {
            "label": row["name"],
            "route": row["slug"],
            "url": f"/categories/{row['slug']}",
            "count": row["count"],
        }
        for row in _department_rows(db)
    ]


# The "Need something done?" strip: the service-side departments, in the order
# locals reach for them. Slugs reference the live tree; a missing department
# is skipped.
_SERVICE_DEPARTMENT_SLUGS: tuple[str, ...] = (
    "home-and-property-services",
    "auto-rv-and-marine",
    "beauty-and-personal-care",
    "pets",
    "professional-and-financial",
    "community-and-civic",
)


def service_tiles(db: Session) -> list[dict[str, Any]]:
    """Secondary service shortcuts (no counts — the strip reads as a directory)."""
    by_slug = {row["slug"]: row for row in _department_rows(db)}
    return [
        {"label": by_slug[slug]["name"], "url": f"/categories/{slug}"}
        for slug in _SERVICE_DEPARTMENT_SLUGS
        if slug in by_slug
    ]


# ---------------------------------------------------------------------------
# Explore mega-menu — six columns spanning all 15 taxonomy departments
# ---------------------------------------------------------------------------

_MEGA_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Eat & Drink", ("eat-and-drink",)),
    ("On the Water", ("on-the-water",)),
    (
        "Fun & Outdoors",
        (
            "things-to-do-and-attractions",
            "outdoors-and-recreation",
            "fitness-and-wellness",
            "family-and-education",
        ),
    ),
    (
        "Services",
        (
            "home-and-property-services",
            "auto-rv-and-marine",
            "professional-and-financial",
            "beauty-and-personal-care",
            "pets",
        ),
    ),
    ("Health & Medical", ("health-and-medical",)),
    ("Living Here", ("shopping-and-retail", "community-and-civic", "lodging")),
)


def mega_columns(db: Session) -> list[dict[str, Any]]:
    """Mega-menu columns; every link is a live ``/categories/{department}``
    landing. Departments missing from the DB are omitted; a column with no
    surviving links collapses away."""
    by_slug = {row["slug"]: row for row in _department_rows(db)}
    columns: list[dict[str, Any]] = []
    for heading, slugs in _MEGA_GROUPS:
        links = [
            {"label": by_slug[slug]["name"], "url": f"/categories/{slug}"}
            for slug in slugs
            if slug in by_slug
        ]
        if links:
            columns.append({"heading": heading, "links": links})
    return columns


# Header high-value direct links (recognition-over-recall): department
# landings only.
def primary_nav() -> list[dict[str, str]]:
    return [
        {"label": "Eat & Drink", "url": "/categories/eat-and-drink"},
        {"label": "On the Water", "url": "/categories/on-the-water"},
        {"label": "Things to Do", "url": "/categories/things-to-do-and-attractions"},
        {"label": "Health", "url": "/categories/health-and-medical"},
    ]


# ---------------------------------------------------------------------------
# Today module — real cards only, honest omission of unbuilt sources
# ---------------------------------------------------------------------------

def today_cards(
    *,
    utility_chips: list[dict[str, Any]],
    tonight_card: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Assemble the 'Today around the lake' cards from live data only.

    - 'Tonight' (``tonight_card``) is the next not-yet-started event, with a
      label that swaps Tonight/Today/Tomorrow per DL-16. The router builds it so
      the time-of-day logic stays testable; omitted when there is nothing ahead.
    - 'Water' summarizes live conditions (omitted when conditions are down).
    - Happy-hours ('On now') and kid-event tagging do NOT exist yet, so those
      cards are omitted entirely rather than faked with the mock's "12 happy
      hours" / "6 kid events" numbers.
    """
    cards: list[dict[str, Any]] = []

    if tonight_card:
        cards.append(tonight_card)

    water = _water_card(utility_chips)
    if water:
        cards.append(water)

    return cards


def _water_card(utility_chips: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_kind = {c.get("kind"): c for c in utility_chips}
    weather = by_kind.get("weather")
    water_temp = by_kind.get("water")
    if not weather and not water_temp:
        return None
    title_bits = []
    if water_temp and water_temp.get("value"):
        title_bits.append(f"Water {water_temp['value']}")
    if weather and weather.get("value"):
        title_bits.append(f"Air {weather['value']}")
    sub = ""
    if weather and weather.get("detail"):
        sub = str(weather["detail"])
    elif water_temp and water_temp.get("detail"):
        sub = str(water_temp["detail"])
    if not title_bits:
        return None
    return {
        "kind": "water",
        "k": "Water",
        "title": " · ".join(title_bits),
        "sub": sub,
        "href": "/today",
        "live": False,
    }


# ---------------------------------------------------------------------------
# This-week strip — next 7 days, one-off headlines + class rollup (DL-16 evo)
# ---------------------------------------------------------------------------
#
# Replaces the old "Today around the lake" card pair (Tonight + Water). The strip
# shows the next 7 days; each day card headlines up to two named ONE-OFF events,
# while recurring classes (recurring Event rows and venue Schedule classes)
# collapse into a "N classes" rollup line — never a headline — so a one-off
# festival is never drowned by 50 aquatic-center class instances.
#
# Owner-approved headline ranking (highest first):
#   special/festival > music/nightlife > community > water > other one-off
# Tiering is heuristic — keyword + tag + featured signals — and is deliberately
# a *ranking* prior, never a filter: every event still appears in its day's
# tap-through (/events-ui?date=) and rollup count.

(
    _TIER_SPECIAL,
    _TIER_MUSIC,
    _TIER_COMMUNITY,
    _TIER_WATER,
    _TIER_OTHER,
    _TIER_CLASS,
) = range(6)
_TIER_CSS = {
    _TIER_SPECIAL: "special",
    _TIER_MUSIC: "music",
    _TIER_COMMUNITY: "community",
    _TIER_WATER: "water",
    _TIER_OTHER: "community",
    _TIER_CLASS: "class",
}

_SPECIAL_HINTS = (
    "festival", "fest", "parade", "derby", "tournament", "poker run", "balloon",
    "boat show", "fireworks", "rodeo", "grand prix", "london bridge days",
    "concert series", "car show", "expo", "championship", "celebration",
)
_WEEK_WATER_HINTS = (
    "water", "lake", "kayak", "swim", "boat", "paddle", "channel", "regatta",
    "jet ski", "wakeboard", "sail", "fishing", "fish", "marina", "river",
)
_MUSIC_HINTS = (
    "live music", "music", "band", "concert", "dj", "karaoke", "dance party",
    "nightlife", "open mic", "comedy",
)
_COMMUNITY_HINTS = (
    "market", "farmers", "art walk", "artwalk", "fair", "fundraiser", "charity",
    "library", "story time", "bingo", "potluck", "meetup", "club", "workshop",
)
_CLASS_HINTS = (
    "aqua", "aerobics", "yoga", "pilates", "lap swim", "pickleball", "fitness",
    "lesson", "class", "zumba", "dodgeball", "bootcamp", "tai chi", "spin",
    "water fitness", "senior", "story hour",
)


def _event_tier(*, title: str, tags: list[str] | None, featured: bool, recurring: bool) -> int:
    """Importance tier (lower = more prominent). See the module note above."""
    joined = (title + " " + " ".join(tags or [])).lower()
    if featured or any(h in joined for h in _SPECIAL_HINTS):
        return _TIER_SPECIAL
    # A class signal ("lap swim", "water fitness", …) is the lowest tier, so it
    # must never be promoted to MUSIC/WATER just because it shares a keyword
    # (e.g. "swim"). Only consider the one-off tiers when there's no class signal.
    if any(h in joined for h in _CLASS_HINTS):
        return _TIER_CLASS
    if any(h in joined for h in _MUSIC_HINTS):
        return _TIER_MUSIC
    if any(h in joined for h in _COMMUNITY_HINTS):
        return _TIER_COMMUNITY
    if any(h in joined for h in _WEEK_WATER_HINTS):
        return _TIER_WATER
    # No keyword signal: a one-off is a real (untyped) event; a recurring block
    # reads as an ongoing class so it never outranks a one-off.
    return _TIER_CLASS if recurring else _TIER_OTHER


def _event_css_type(*, title: str, tags: list[str] | None, tier: int) -> str:
    """Display pill for a week-strip headline. Ranking and display are separate
    concerns: a "Kayak Meetup" *ranks* at the community tier (the approved
    headline order puts community above water), but it still *wears* the water
    pill — on-the-water is this town's identity category and the legend keys
    color to activity type, not headline priority."""
    if tier in (_TIER_COMMUNITY, _TIER_OTHER):
        joined = (title + " " + " ".join(tags or [])).lower()
        if any(h in joined for h in _WEEK_WATER_HINTS):
            return "water"
    return _TIER_CSS[tier]


def _short_time(t: time | None) -> str | None:
    """12-hour label; see :func:`app.events.time_labels.format_short_time`."""
    if t is None:
        return None
    return format_short_time(t)


def week_strip(
    db: Session, *, today: date, days: int = 7, per_day: int = 2
) -> dict[str, Any]:
    """Build the next-``days`` strip: one-off headlines + a per-day class rollup.

    Mirrors ``calendar_month``'s honest-omission contract: empty days render an
    em-dash, never fabricated content. Each day links to ``/events-ui?date=`` so
    everything stays one tap away. Recurring classes (recurring Event rows plus
    venue Schedule classes) never take a headline slot — they appear only in the
    ``summary`` rollup ("2 events · 14 classes"). Time-unknown one-offs (the
    midnight ingest fallback) show no time — never "12 AM" — and sort after
    timed events within their tier.
    """
    end = today + timedelta(days=days - 1)
    by_day = _live_events_by_day(db, window_start=today, window_end=end)

    # Venue Schedule classes (entity Schedule rows, not events) join the per-day
    # class count so the rollup matches the day's /events-ui?date= page;
    # event-table twins (the aquatic programs) are dropped by title+date, same
    # as calendar_month.
    event_keys = {
        ((ev.title or "").strip().lower(), d) for d, evs in by_day.items() for ev in evs
    }
    sched_classes_by_day: dict[date, int] = {}
    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=today, window_end=end), event_keys
    ):
        sched_classes_by_day[occ.date] = sched_classes_by_day.get(occ.date, 0) + 1

    def _tier(ev: Event) -> int:
        return _event_tier(
            title=ev.title,
            tags=ev.tags,
            featured=bool(ev.featured),
            recurring=bool(ev.is_recurring),
        )

    def _sort_key(ev: Event) -> tuple[int, int, time]:
        return (_tier(ev), *time_sort_key(ev.start_time, ev.end_time))

    out_days: list[dict[str, Any]] = []
    for i in range(days):
        d = today + timedelta(days=i)
        evs = by_day.get(d, [])
        oneoffs = sorted((ev for ev in evs if not ev.is_recurring), key=_sort_key)
        class_count = sum(1 for ev in evs if ev.is_recurring) + sched_classes_by_day.get(d, 0)
        if i == 0:
            label = "Today"
        elif i == 1:
            label = "Tomorrow"
        else:
            label = d.strftime("%a")
        visible = [
            {
                "title": ev.title,
                "type": _event_css_type(title=ev.title, tags=ev.tags, tier=_tier(ev)),
                "time": short_time_label(ev.start_time, ev.end_time),
            }
            for ev in oneoffs[:per_day]
        ]
        summary_bits: list[str] = []
        if oneoffs:
            summary_bits.append(f"{len(oneoffs)} event{'' if len(oneoffs) == 1 else 's'}")
        if class_count:
            summary_bits.append(f"{class_count} class{'' if class_count == 1 else 'es'}")
        total = len(oneoffs) + class_count
        out_days.append(
            {
                "iso": d.isoformat(),
                "label": label,
                "md": f"{d.month}/{d.day}",
                "is_today": i == 0,
                "events": visible,
                "overflow": max(0, len(oneoffs) - per_day),
                "event_count": len(oneoffs),
                "class_count": class_count,
                "summary": " · ".join(summary_bits),
                "count": total,
                "has": total > 0,
            }
        )
    return {"days": out_days, "has_any": any(day["has"] for day in out_days)}


# ---------------------------------------------------------------------------
# Server-rendered month calendar (real Event rows; JS-free prev/next)
# ---------------------------------------------------------------------------

_WATER_TAG_HINTS = ("water", "lake", "kayak", "swim", "boat", "paddle", "channel")


def _event_pill_type(tags: list[str] | None, *, featured: bool) -> str:
    joined = " ".join(tags or []).lower()
    if any(hint in joined for hint in _WATER_TAG_HINTS):
        return "water"
    if featured:
        return "special"
    return "class"


def _pill_sort_key(pill: dict[str, str]) -> tuple[int, int]:
    """Order pills so one-offs/specials win the 2 visible slots (DL-16).

    Recurring classes sink to the bottom so they fall into the "+N" overflow
    count rather than crowding out a one-off festival.
    """
    ptype = pill.get("type")
    type_rank = {"special": 0, "water": 1, "class": 2}.get(ptype, 1)
    recurring_rank = 1 if pill.get("recurring") else 0
    return (recurring_rank, type_rank)


def calendar_month(db: Session, *, year: int, month: int, today: date) -> dict[str, Any]:
    """Build a month grid of real events. Empty days stay empty (no fabrication).

    Each in-month cell carries an ISO date (``iso``) so the template can link
    every day to ``/events-ui?date=``. Only one-off events take the two visible
    pill slots and the cell ``count``; recurring classes (recurring Event rows
    plus venue Schedule classes) collapse into ``class_count`` — rendered as a
    small "N classes" badge — instead of flooding the cell ("+44").
    """
    first_weekday, days_in_month = _calendar.monthrange(year, month)
    # Python's monthrange: Monday=0. The grid leads with Sunday, so shift.
    lead_blanks = (first_weekday + 1) % 7

    occ_by_date = _live_events_by_day(
        db,
        window_start=date(year, month, 1),
        window_end=date(year, month, days_in_month),
    )
    by_day: dict[int, list[dict[str, Any]]] = {}
    event_keys: set[tuple[str, date]] = set()
    for occ_date, evs in occ_by_date.items():
        bucket = by_day.setdefault(occ_date.day, [])
        for ev in evs:
            event_keys.add(((ev.title or "").strip().lower(), occ_date))
            bucket.append(
                {
                    "title": ev.title,
                    "type": _event_pill_type(ev.tags, featured=bool(ev.featured)),
                    "recurring": bool(ev.is_recurring),
                }
            )

    # Venue class schedules (Schedule rows on entities) are not events; union
    # them in so a "Mon-Thu BJJ" venue shows on every class day. They count as
    # recurring class pills, so they feed the "+N" overflow, never the two
    # visible one-off slots. Aquatic-style duplicates (classes that are ALSO
    # recurring events) are dropped by title+date.
    class_occs = drop_event_duplicates(
        class_occurrences_in_window(
            db,
            window_start=date(year, month, 1),
            window_end=date(year, month, days_in_month),
        ),
        event_keys,
    )
    for occ in class_occs:
        by_day.setdefault(occ.date.day, []).append(
            {"title": occ.title, "type": "class", "recurring": True}
        )

    cells: list[dict[str, Any]] = [{"in_month": False} for _ in range(lead_blanks)]
    for day in range(1, days_in_month + 1):
        evs = by_day.get(day, [])
        # Only one-offs claim the two visible pill slots (and the cell count);
        # recurring classes collapse into the "N classes" badge.
        oneoffs = sorted((e for e in evs if not e.get("recurring")), key=_pill_sort_key)
        class_count = sum(1 for e in evs if e.get("recurring"))
        cells.append(
            {
                "in_month": True,
                "day": day,
                "iso": date(year, month, day).isoformat(),
                "is_today": (year == today.year and month == today.month and day == today.day),
                "events": oneoffs[:2],
                "overflow": max(0, len(oneoffs) - 2),
                "count": len(oneoffs),
                "class_count": class_count,
                "has": bool(evs),
                "special": any(e.get("type") == "special" for e in oneoffs),
            }
        )
    while len(cells) % 7 != 0:
        cells.append({"in_month": False})

    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return {
        "label": f"{_calendar.month_name[month]} {year}",
        "weeks": weeks,
        "has_any": bool(by_day),
        "prev": f"{prev_year:04d}-{prev_month:02d}",
        "next": f"{next_year:04d}-{next_month:02d}",
    }


def parse_cal_param(value: str | None, *, default: datetime) -> tuple[int, int]:
    """Parse a ``?cal=YYYY-MM`` param, falling back to the current month."""
    if value:
        try:
            year_s, month_s = value.split("-", 1)
            year, month = int(year_s), int(month_s)
            if 1 <= month <= 12 and 2000 <= year <= 2100:
                return year, month
        except (ValueError, AttributeError):
            pass
    return default.year, default.month


# ---------------------------------------------------------------------------
# Featured row — real sponsors or the honest "claim this spot" empty state
# ---------------------------------------------------------------------------

def featured_cards(spotlights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real spotlight sponsors, always followed by one labeled claim slot.

    Never invents sponsors: an unsold surface renders only the claim CTA.
    """
    cards: list[dict[str, Any]] = []
    for sp in spotlights:
        sponsor_id = sp.get("id")
        cards.append(
            {
                "empty": False,
                "name": sp.get("headline") or sp.get("name"),
                "eyebrow": sp.get("eyebrow") or "",
                "deal": sp.get("pitch") or sp.get("line") or "",
                "image_url": sp.get("image_url"),
                "url": f"/sponsor/click?id={sponsor_id}&slot=spotlight" if sponsor_id else None,
            }
        )
    cards.append({"empty": True})
    return cards


# ---------------------------------------------------------------------------
# Mode landings — Lake / Night / Family (01_UI_BUILD_GUIDE.md §4.10)
# ---------------------------------------------------------------------------
#
# Each landing is a hero + a sub-tile strip. Sub-tiles are NAVIGATION: every
# tile resolves to a real ``/categories/{route}`` page when one fits, or a
# ``/chat?q=<intent>`` search when no category route is close enough — never a
# dead/404 link. The hero "live counters" from the prototype ("12 happy hours",
# "6 kid events", "4 live music") are NOT real data yet, so they are omitted
# entirely; the Lake hero's mini-conditions row uses ONLY live conditions
# (lake level / water temp / wind / sunset / air temp), and any tile without a
# live source is left out rather than faked (no hardcoded "448.7 ft").

# Theme accent per mode for the active-state stamp on the header toggle and the
# page's ``data-mode``. The palette itself lives in sandstone.css tokens.
MODE_LABELS: dict[str, str] = {
    "ask": "Ask",
    "lake": "Lake",
    "night": "Night",
    "family": "Family",
}


def _chat_url(query: str) -> str:
    """A real search URL into the existing 3-tier /chat backend."""
    from urllib.parse import quote_plus

    return f"/chat?q={quote_plus(query)}"


def _tile(emoji: str, title: str, blurb: str, url: str) -> dict[str, str]:
    return {"emoji": emoji, "label": title, "blurb": blurb, "url": url}


# -- Lake -------------------------------------------------------------------
# Boat rentals / launch ramps / marinas+fuel / gear+ice / tours+charters /
# watercraft service. The closest real page for all on-water sub-tiles is the
# ``/categories/on-the-water`` department landing. Where the sub-tile is a
# finer intent than that page exposes today, we deep-link a /chat search so
# the user still lands on real results instead of a generic page.
def _lake_tiles() -> list[dict[str, str]]:
    water = "/categories/on-the-water"
    return [
        _tile("⛵", "Boat Rentals", "Pontoons, wave runners", _chat_url("boat rental")),
        _tile("🛟", "Launch Ramps", "Fees, parking, status", _chat_url("boat launch ramp")),
        _tile("⛽", "Marinas & Fuel", "On-water fuel, slips", _chat_url("marina fuel")),
        _tile("🧊", "Gear & Ice", "Coolers, bait, tubes", _chat_url("boating gear and ice")),
        _tile("🧭", "Tours & Charters", "Guided, fishing", _chat_url("lake tours and charters")),
        _tile("🔧", "Watercraft Service", "Repair, storage", water),
    ]


# -- Night ------------------------------------------------------------------
# Bars / breweries+wineries / live music / happy hours / late kitchens /
# get-home-safe. Bars, breweries and late kitchens point at the
# ``/categories/eat-and-drink`` department; the time/event-specific intents
# (live music tonight, happy hours on now) have no category page, so they
# search.
def _night_tiles() -> list[dict[str, str]]:
    eat = "/categories/eat-and-drink"
    return [
        _tile("🍸", "Bars & Lounges", "Waterfront, dive, cocktail", eat),
        _tile("🍺", "Breweries & Wineries", "Tastings, taprooms", eat),
        _tile("🎶", "Live Music", "Who's playing & when", _chat_url("live music tonight")),
        _tile("🕙", "Happy Hours", "Sorted by ending soon", _chat_url("happy hour now")),
        _tile("🍔", "Late Kitchens", "Food after 10 PM", _chat_url("late night food")),
        _tile("🚖", "Get Home Safe", "Local taxi & rideshare", _chat_url("taxi or rideshare")),
    ]


# -- Family -----------------------------------------------------------------
# Parks / swim+splash / classes+camps / free events / beat-the-heat /
# kid-friendly eats. Parks map onto the outdoors department, classes onto
# family-and-education; free events and kid eats are finer intents routed to
# /chat search.
def _family_tiles() -> list[dict[str, str]]:
    outdoors = "/categories/outdoors-and-recreation"
    classes = "/categories/family-and-education"
    return [
        _tile("🛝", "Parks & Playgrounds", "Shade, splash pads", outdoors),
        _tile("🏊", "Swim & Splash", "Aquatic center, beaches", _chat_url("swimming and splash pads")),
        _tile("🎨", "Classes & Camps", "Art, music, sports", classes),
        _tile("🎈", "Free Family Events", "This week's lineup", _chat_url("free family events")),
        _tile("🌧️", "Beat-the-Heat / Rainy Day", "Indoor play, library", _chat_url("indoor activities for kids")),
        _tile("🍦", "Kid-Friendly Eats", "Menus, patios, treats", _chat_url("kid friendly restaurants")),
    ]


_MODE_CONFIG: dict[str, dict[str, Any]] = {
    "lake": {
        "eyebrow": "Lake Life",
        "heading": "Everything for a day on the water",
        "blurb": (
            "Conditions, ramps, rentals, fuel and ice — the lake organized "
            "around getting you out there."
        ),
        "sec_head": "Out on the water",
        "tiles": _lake_tiles,
    },
    "night": {
        "eyebrow": "Night",
        "heading": "Where the night goes",
        "blurb": (
            "Tonight's happy hours, the patios, live music, late kitchens — "
            "and a safe ride home."
        ),
        "sec_head": "Out tonight",
        "tiles": _night_tiles,
    },
    "family": {
        "eyebrow": "Family",
        "heading": "Plenty to do with the kids",
        "blurb": (
            "The answer to \"there's nothing to do here\" — parks, splash pads, "
            "classes, free events, and rainy-day backups, all in one place."
        ),
        "sec_head": "For the kids",
        "tiles": _family_tiles,
    },
}


def lake_mini_conditions(db: Session) -> list[dict[str, str]]:
    """Live mini-conditions for the Lake hero: wind / water temp / sunset (plus
    air temp). Each tile is omitted when its source has no live value — NEVER
    the prototype's hardcoded 448.7 ft / 74°F / 8 mph SW.

    Task 0 (source-expansion): the "Lake level" tile was removed from the hero
    strip; Wind now leads in its position. Lake level is still surfaced on the
    full conditions strip and /today, just not on the Lake-mode hero.
    """
    from app.conditions.api_payload import build_conditions_api_payload

    try:
        api = build_conditions_api_payload(db)
    except Exception:  # pragma: no cover - never block the page on conditions
        return []

    tiles: list[dict[str, str]] = []

    wind = api.get("wind_speed_mph")
    if isinstance(wind, (int, float)):
        tiles.append({"value": f"{int(round(float(wind)))} mph", "label": "Wind"})

    water = api.get("water_temp_f")
    if isinstance(water, (int, float)):
        tiles.append({"value": f"{float(water):.0f}°F", "label": "Water temp"})

    sunset = api.get("sunset_local")
    if isinstance(sunset, str) and sunset.strip():
        tiles.append({"value": sunset.strip(), "label": "Sunset"})

    air = api.get("current_temp_f")
    if isinstance(air, (int, float)) and not water:
        # Air temp is a useful fallback only when water temp is unavailable, so
        # the strip never goes empty when one upstream source is down.
        tiles.append({"value": f"{int(round(float(air)))}°F", "label": "Air temp"})

    return tiles


def mode_landing(db: Session, mode: str) -> dict[str, Any]:
    """Assemble a mode-landing context.

    ``mini_conditions`` is populated for Lake only (live conditions); Night and
    Family have no honest live hero metric yet, so their hero shows copy only —
    the mock counters are deliberately absent (anti-confabulation, §4.10).
    """
    if mode not in _MODE_CONFIG:
        raise KeyError(mode)
    cfg = _MODE_CONFIG[mode]
    mini = lake_mini_conditions(db) if mode == "lake" else []
    return {
        "mode": mode,
        "eyebrow": cfg["eyebrow"],
        "heading": cfg["heading"],
        "blurb": cfg["blurb"],
        "sec_head": cfg["sec_head"],
        "tiles": cfg["tiles"](),
        "mini_conditions": mini,
    }
