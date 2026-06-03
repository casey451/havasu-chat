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
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.db.models import Event
from app.home.queries import CATEGORY_LABELS

# Display labels for tier-1 routes the canonical CATEGORY_LABELS map omits. These
# are presentation strings, not data; every *route* below is a real page in
# ``CATEGORY_FILTERS`` and every *count* is a live query, so nothing is fabricated.
_ROUTE_LABEL_FALLBACK: dict[str, str] = {
    "things-to-do": "Things to Do",
    "services": "Services",
    "professional": "Professional",
    "beauty-care": "Beauty & Personal Care",
    "attractions": "Attractions",
}


def _route_label(route: str) -> str:
    return CATEGORY_LABELS.get(route) or _ROUTE_LABEL_FALLBACK.get(
        route, route.replace("-", " ").title()
    )


def _route_count(db: Session, route: str) -> int | None:
    """Live provider count for a route, or None (never a fabricated 0)."""
    try:
        return cat_queries.category_count(db, route)
    except Exception:  # pragma: no cover - defensive; never block the page on a count
        return None


# ---------------------------------------------------------------------------
# Explore strips
# ---------------------------------------------------------------------------

# (emoji, short label, real tier-1 route). The six primary front doors from the
# prototype, mapped onto routes that actually exist today. Health and Stay are
# surfaced here as front doors per the blueprint; full Real-Estate / taxonomy
# restructuring is the step-3 job, so we link the closest real route now.
_PRIMARY_TILES: tuple[tuple[str, str, str], ...] = (
    ("\U0001F37D️", "Eat & Drink", "eat-drink"),
    ("⛵", "On the Water", "on-the-water"),
    ("\U0001F39F️", "Things to Do", "things-to-do"),
    ("\U0001F6CD️", "Shopping", "shopping-essentials"),
    ("\U0001FA7A", "Health", "health-wellness-care"),
    ("\U0001F3E1", "Stay & Rentals", "lodging-vacation-rentals"),
)

# Secondary "need something done?" service shortcuts — all real routes.
_SERVICE_TILES: tuple[tuple[str, str, str], ...] = (
    ("\U0001F527", "Home & Trades", "home-property-services"),
    ("\U0001F697", "Auto & RV", "auto-rv-fuel"),
    ("\U0001F488", "Beauty", "beauty-care"),
    ("\U0001F43E", "Pets", "pets"),
    ("\U0001F4BC", "Professional", "professional"),
    ("\U0001F3DB️", "Civic & Public", "public-civic-resources"),
)


def explore_tiles(db: Session) -> list[dict[str, Any]]:
    """Primary category front doors with live counts (count omitted when None)."""
    return [
        {
            "emoji": emoji,
            "label": label,
            "route": route,
            "url": f"/categories/{route}",
            "count": _route_count(db, route),
        }
        for emoji, label, route in _PRIMARY_TILES
    ]


def service_tiles(db: Session) -> list[dict[str, Any]]:
    """Secondary service shortcuts (no counts — the strip reads as a directory)."""
    return [
        {"emoji": emoji, "label": label, "url": f"/categories/{route}"}
        for emoji, label, route in _SERVICE_TILES
    ]


# ---------------------------------------------------------------------------
# Explore mega-menu — six columns driven by the real top-level taxonomy
# ---------------------------------------------------------------------------

_MEGA_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Eat & Drink", ("eat-drink",)),
    ("On the Water", ("on-the-water",)),
    ("Things to Do", ("things-to-do", "attractions", "classes-sports-recreation")),
    ("Services", ("services", "home-property-services", "auto-rv-fuel", "beauty-care", "professional", "pets")),
    ("Health & Medical", ("health-wellness-care",)),
    ("Living Here", ("lodging-vacation-rentals", "shopping-essentials", "public-civic-resources")),
)


def mega_columns(db: Session) -> list[dict[str, Any]]:
    """Mega-menu columns; every link is a real ``/categories/{route}`` page."""
    columns: list[dict[str, Any]] = []
    for heading, routes in _MEGA_GROUPS:
        links = [
            {"label": _route_label(route), "url": f"/categories/{route}"}
            for route in routes
        ]
        columns.append({"heading": heading, "links": links})
    return columns


# Header high-value direct links (recognition-over-recall): real routes only.
def primary_nav() -> list[dict[str, str]]:
    return [
        {"label": "Eat & Drink", "url": "/categories/eat-drink"},
        {"label": "On the Water", "url": "/categories/on-the-water"},
        {"label": "Things to Do", "url": "/categories/things-to-do"},
        {"label": "Health", "url": "/categories/health-wellness-care"},
    ]


# ---------------------------------------------------------------------------
# Today module — real cards only, honest omission of unbuilt sources
# ---------------------------------------------------------------------------

def today_cards(
    *,
    utility_chips: list[dict[str, Any]],
    events_today: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assemble the 'Today around the lake' cards from live data only.

    - 'Tonight' surfaces the next real event today (omitted when none).
    - 'Water' summarizes live conditions (omitted when conditions are down).
    - Happy-hours ('On now') and kid-event tagging do NOT exist yet, so those
      cards are omitted entirely rather than faked with the mock's "12 happy
      hours" / "6 kid events" numbers.
    """
    cards: list[dict[str, Any]] = []

    if events_today:
        ev = events_today[0]
        sub_bits = [b for b in (ev.get("time_label"), ev.get("venue")) if b]
        cards.append(
            {
                "kind": "tonight",
                "k": "Tonight",
                "title": ev.get("title"),
                "sub": " · ".join(sub_bits),
                "href": ev.get("url"),
                "live": False,
            }
        )

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


def calendar_month(db: Session, *, year: int, month: int, today: date) -> dict[str, Any]:
    """Build a month grid of real events. Empty days stay empty (no fabrication)."""
    first_weekday, days_in_month = _calendar.monthrange(year, month)
    # Python's monthrange: Monday=0. The grid leads with Sunday, so shift.
    lead_blanks = (first_weekday + 1) % 7

    rows = (
        db.query(Event)
        .filter(
            Event.status == "live",
            Event.date >= date(year, month, 1),
            Event.date <= date(year, month, days_in_month),
        )
        .order_by(Event.featured.desc(), Event.start_time.asc())
        .all()
    )
    by_day: dict[int, list[dict[str, str]]] = {}
    for ev in rows:
        bucket = by_day.setdefault(ev.date.day, [])
        if len(bucket) >= 4:  # cap stored pills; cell shows 2 + overflow
            bucket.append({})  # count-only marker for accurate "+N"
            continue
        bucket.append(
            {
                "title": ev.title,
                "type": _event_pill_type(ev.tags, featured=bool(ev.featured)),
            }
        )

    cells: list[dict[str, Any]] = [{"in_month": False} for _ in range(lead_blanks)]
    for day in range(1, days_in_month + 1):
        evs = by_day.get(day, [])
        named = [e for e in evs if e.get("title")]
        cells.append(
            {
                "in_month": True,
                "day": day,
                "is_today": (year == today.year and month == today.month and day == today.day),
                "events": named[:2],
                "overflow": max(0, len(evs) - 2),
                "has": bool(evs),
                "special": any(e.get("type") == "special" for e in named),
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
