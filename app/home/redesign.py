"""View-models for the home + calendar redesign (the v4 reskin, ``home_redesign``).

This module is presentation-only glue: it adapts the SAME live data the existing
home consumes (``conditions``, ``events_views.day_groups``, ``today_feed`` movies,
``sandstone.calendar_month``, the gas cache) into the shape the v4 templates
render. No new data sources, no fabrication — every count/blurb traces to a live
row or is omitted.

Design source of truth: ``design-exploration/ask-hava-premium-v4.html`` +
``ASK_HAVA_HOME_DESIGN_SPEC.md``.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conditions.api_payload import build_conditions_api_payload
from app.conditions.cache import read_source
from app.conditions.constants import GAS_STALE_AFTER_HOURS, SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.db.models import Event
from app.events.tag_display import public_event_tags
from app.home import events_views, sandstone

# ── category accents / icons (v4 CICON + CCOLOR, mapped onto the app's real
# bucket keys). The app's "classes" bucket is Fitness & sports, so it borrows the
# v4 "fitness" accent; everything else maps 1:1. ───────────────────────────────
CAT_ICON: dict[str, str] = {
    "events": "ticket",
    "things": "compass",
    "music": "music",
    "water": "sail",
    "family": "balloon",
    "seniors": "person",
    "fitness": "activity",
    "classes": "activity",
    "movies": "film",
    "civic": "bank",
}
CAT_COLOR: dict[str, str] = {
    "events": "var(--c-events)",
    "things": "var(--c-things)",
    "music": "var(--c-music)",
    "water": "var(--c-water)",
    "family": "var(--c-family)",
    "seniors": "var(--c-seniors)",
    "fitness": "var(--c-fitness)",
    "classes": "var(--c-fitness)",
    "movies": "var(--c-movies)",
    "civic": "var(--c-civic)",
    # calendar month-cell pill types (sandstone._event_css_type) → v4 accents
    "special": "var(--c-events)",
    "community": "var(--c-things)",
    "aquatic": "var(--c-water)",
    "class": "var(--c-fitness)",
}
# Short category label used in the calendar agenda + chips (v4 CLABEL).
CAT_LABEL: dict[str, str] = {
    "events": "Event",
    "things": "Things to do",
    "music": "Music",
    "water": "Lake",
    "family": "Kids",
    "seniors": "Seniors",
    "fitness": "Fitness",
    "classes": "Fitness",
    "movies": "Movie",
    "civic": "City",
}

# Gradient thumbnail class per category (the v4 .im-* fallbacks until a real
# photo exists). Honest fallback — never a fake photo.
CAT_THUMB: dict[str, str] = {
    "events": "im-sunset",
    "things": "im-market",
    "music": "im-sunset",
    "water": "im-boat",
    "family": "im-water",
    "seniors": "im-court",
    "fitness": "im-court",
    "classes": "im-art",
    "movies": "im-movie",
    "civic": "im-civic",
}


def category_color(key: str) -> str:
    return CAT_COLOR.get(key, "var(--c-civic)")


def uv_color(uv: float | int) -> str:
    """v4 ``uvColor`` — index → severity color (still shows the number too)."""
    if uv <= 2:
        return "#2c7551"
    if uv <= 5:
        return "#9a8a00"
    if uv <= 7:
        return "#b5611f"
    if uv <= 10:
        return "#b4452f"
    return "#8a4fb8"


# ── conditions bar (Temp · Wind · UV · Clouds · Gas) ───────────────────────────
_SKY_SHORT = (
    (re.compile(r"mostly\s+sunny|mostly\s+clear", re.I), "Mostly clear"),
    (re.compile(r"partly\s+sunny|partly\s+cloudy", re.I), "Partly cloudy"),
    (re.compile(r"mostly\s+cloudy", re.I), "Mostly cloudy"),
    (re.compile(r"\bsunny\b|\bclear\b|\bfair\b", re.I), "Clear"),
    (re.compile(r"\bcloud", re.I), "Cloudy"),
    (re.compile(r"\brain|\bshower|\bstorm|\bthunder", re.I), "Rain"),
    (re.compile(r"\bwind", re.I), "Windy"),
)


def _short_sky(text: str) -> str:
    for pat, label in _SKY_SHORT:
        if pat.search(text):
            return label
    # First word, capitalized — never longer than the tile can hold.
    return (text.split(",")[0].split()[0] if text.split() else text).title()


def conditions_tiles(db: Session, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """The 5 clean conditions tiles. Each is honest-omit: a tile only renders when
    its live source has a value.

    NOTE on "Clouds": the conditions pipeline exposes the NWS sky *condition* word
    (e.g. "Mostly cloudy"), not a numeric cloud-cover %. The v4 mockup showed a
    placeholder "15%"; we render the real sky word instead (no fabricated number).
    """
    # The conditions payload + gas read use naive-UTC time internally (and an
    # in-process cache keyed on it); the caller's ``now`` may be Lake-tz-aware, so
    # never thread it into the payload — conditions always reflect "right now".
    payload = build_conditions_api_payload(db)
    tiles: list[dict[str, Any]] = []

    temp = payload.get("current_temp_f")
    if isinstance(temp, (int, float)):
        tiles.append(
            {
                "key": "temp",
                "icon": "thermo",
                "label": "Temp",
                "value": f"{round(temp)}°",
                "unit": None,
                "color": None,
                "is_gas": False,
                "is_stale": bool(payload.get("temp_is_stale")),
            }
        )

    wind = payload.get("wind_speed_mph")
    if isinstance(wind, (int, float)):
        tiles.append(
            {
                "key": "wind",
                "icon": "wind",
                "label": "Wind",
                "value": f"{round(wind)}",
                "unit": "mph",
                "color": None,
                "is_gas": False,
                "is_stale": bool(payload.get("temp_is_stale")),
            }
        )

    uv = payload.get("uv_index")
    if isinstance(uv, (int, float)):
        tiles.append(
            {
                "key": "uv",
                "icon": "sun",
                "label": "UV",
                "value": f"{round(uv)}",
                "unit": None,
                "color": uv_color(uv),
                "is_gas": False,
                "is_stale": bool(payload.get("uv_is_stale")),
            }
        )

    sky = payload.get("sky_condition")
    if isinstance(sky, str) and sky.strip():
        tiles.append(
            {
                "key": "clouds",
                "icon": "cloud",
                "label": "Clouds",
                "value": _short_sky(sky.strip()),
                "unit": None,
                "color": None,
                "is_gas": False,
                "is_stale": bool(payload.get("sky_is_stale")),
            }
        )

    # Water temp (USGS 09426630, ~25mi south in the Bill Williams backwater).
    # Added to the conditions bar at Casey's request (2026-06-29). Honest-omit:
    # only renders when FEATURE_FLAG_WATER_TEMP_GAGE_09426630 is ON and the gage
    # has a reading; otherwise the bar simply shows one fewer tile.
    water_temp = payload.get("water_temp_f")
    if isinstance(water_temp, (int, float)):
        tiles.append(
            {
                "key": "water_temp",
                "icon": "wave",
                "label": "Water",
                "value": f"{round(water_temp)}°",
                "unit": None,
                "color": None,
                "is_gas": False,
                "is_stale": bool(payload.get("water_temp_is_stale")),
            }
        )

    gas = gas_top5(db, now=now)
    if gas["cheapest"]:
        top = gas["cheapest"][0]
        tiles.append(
            {
                "key": "gas",
                "icon": "fuel",
                "label": "Gas",
                "value": top["price"],
                "unit": None,
                "color": None,
                "is_gas": True,
                "is_stale": gas["is_stale"],
            }
        )

    return tiles


def _maps_url(name: str, cross_street: str | None) -> str:
    dest = ", ".join(p for p in (name, cross_street, "Lake Havasu City AZ") if p)
    from urllib.parse import quote_plus

    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(dest)}"


def gas_top5(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """The 5 cheapest current stations for the gas-tile expander (price + name +
    cross-street + directions). Mirrors the home gas chip's single source of truth
    (``data['cheapest']`` from the gas pull) so it never disagrees with /gas."""
    now_utc = now or datetime.now(UTC).replace(tzinfo=None)
    if now_utc.tzinfo is not None:
        now_utc = now_utc.astimezone(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now_utc)
    if row is None or not isinstance(row.data, dict):
        return {"cheapest": [], "is_stale": False, "staleness_label": None}
    raw = [s for s in (row.data.get("cheapest") or []) if isinstance(s, dict)]
    label, stale = staleness_label(
        row.fetched_at, now_utc, stale_after_hours=GAS_STALE_AFTER_HOURS
    )
    out: list[dict[str, Any]] = []
    for s in raw[:5]:
        price = s.get("prices", {}).get("regular") if isinstance(s.get("prices"), dict) else None
        if not isinstance(price, (int, float)):
            continue
        name = s.get("station_name") or s.get("name") or "Station"
        cross = s.get("cross_street") or s.get("address")
        out.append(
            {
                "price": f"${price:.2f}",
                "name": name,
                "cross_street": cross,
                "directions_url": _maps_url(name, cross),
            }
        )
    return {
        "cheapest": out,
        "is_stale": bool(stale or row.is_stale),
        "staleness_label": label,
    }


# ── events feed (count overview + accordion buckets + blurbs + fitness subs) ────
_EVENT_ID_RE = re.compile(r"^/events/([^/?#]+)")


def _blurb(text: str | None) -> str | None:
    """A one-line blurb from an event description: first sentence, whitespace
    collapsed, capped. Returns None for empty/placeholder descriptions."""
    if not text:
        return None
    flat = re.sub(r"\s+", " ", text).strip()
    if not flat:
        return None
    # First sentence (or the whole thing if short), then a hard length cap.
    m = re.match(r"(.{20,140}?[.!?])(?:\s|$)", flat)
    blurb = m.group(1) if m else flat
    if len(blurb) > 150:
        blurb = blurb[:147].rstrip() + "…"
    return blurb


def _blurbs_for_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, str]:
    ids: list[str] = []
    for r in rows:
        m = _EVENT_ID_RE.match(r.get("url") or "")
        if m:
            ids.append(m.group(1))
    if not ids:
        return {}
    out: dict[str, str] = {}
    for eid, desc in db.execute(
        select(Event.id, Event.description).where(Event.id.in_(ids))
    ).all():
        b = _blurb(desc)
        if b:
            out[str(eid)] = b
    return out


def _enrich(row: dict[str, Any], blurbs: dict[str, str], cat: str) -> dict[str, Any]:
    m = _EVENT_ID_RE.match(row.get("url") or "")
    out = dict(row)
    out["blurb"] = blurbs.get(m.group(1)) if m else None
    out["thumb"] = CAT_THUMB.get(cat, "im-market")
    out["cat"] = cat
    # SEO: the v4 home row template renders ``row.tags`` verbatim, so the
    # internal ``KEY:value`` taxonomy tokens (``activity:billiards``,
    # ``facet:hours``, ``venue-kind:simulator``, ``audience:youth``) leaked into
    # the indexed page text. Grouping/tiering already ran upstream on the raw
    # tags in ``calendar_day_view_model``; this enrichment step is display-only,
    # so strip them to the friendly tags here (same rule as the event permalink
    # and chat builders — see app/events/tag_display.py).
    out["tags"] = public_event_tags(row.get("tags"))
    return out


def _feed_walk(node: dict[str, Any], acc: list[dict[str, Any]]) -> None:
    """Depth-first collect of every event row in a section/subgroup/child node."""
    acc.extend(node.get("rows") or [])
    for sub in node.get("subgroups") or []:
        _feed_walk(sub, acc)
    for child in node.get("children") or []:
        _feed_walk(child, acc)


def _feed_enrich(node: dict[str, Any], blurbs: dict[str, str], cat: str) -> None:
    """Enrich every row in a node tree in place (blurb + category thumb)."""
    node["rows"] = [_enrich(r, blurbs, cat) for r in (node.get("rows") or [])]
    for sub in node.get("subgroups") or []:
        _feed_enrich(sub, blurbs, cat)
    for child in node.get("children") or []:
        _feed_enrich(child, blurbs, cat)


def feed_view_model(
    db: Session, *, day: date, now: datetime | None = None, family: bool = False
) -> dict[str, Any]:
    """The v4 home feed — the SAME nested Calendar tree ``/events-ui`` renders
    (parity Rule 0, 2026-06-26): sections → subgroups → (youth/facet children) →
    rows. The structure comes straight from
    :func:`events_views.calendar_day_view_model`, so the home and the main
    calendar can't drift; the home only *enriches* each event row (a one-line
    blurb + a category thumb) and styles it in the v4 idiom. No more chips."""
    vm = events_views.calendar_day_view_model(db, day=day, now=now, family=family)
    sections = vm["sections"]

    # One blurb query for every event row across the tree (movies carry their own).
    all_rows: list[dict[str, Any]] = []
    for s in sections:
        if not s.get("is_movies"):
            _feed_walk(s, all_rows)
    blurbs = _blurbs_for_rows(db, all_rows)
    for s in sections:
        if not s.get("is_movies"):
            _feed_enrich(s, blurbs, s["key"])
        # Classes & Workshops ("learn") and Fitness & classes ("classes") list flat
        # — no activity sub-categories (Casey 2026-06-29: "classes and workshops
        # can just all be put together"). The section keeps its full sorted `rows`,
        # so dropping the split `subgroups` renders them as one flat list.
        if s.get("key") in ("classes", "learn"):
            s["subgroups"] = []

    return {"sections": sections, "total": vm["total"]}


# ── calendar (glanceable month grid + selected-day agenda) ─────────────────────
def calendar_month_view(
    db: Session,
    *,
    year: int,
    month: int,
    today: date,
    selected: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The v4 glanceable calendar: a month grid (chips on desktop, dots on mobile)
    + an agenda for the selected day. Built over the SAME ``calendar_month`` grid
    and ``day_groups`` agenda the existing surfaces use."""
    grid = sandstone.calendar_month(db, year=year, month=month, today=today)
    sel = selected or (today if today.year == year and today.month == month else None)

    weeks: list[list[dict[str, Any]]] = []
    for src_week in grid.get("weeks", []):
        week: list[dict[str, Any]] = []
        for cell in src_week:
            if not cell.get("in_month"):
                week.append({"empty": True})
                continue
            iso = cell["iso"]
            d = date.fromisoformat(iso)
            chips = [
                {
                    "title": ev["title"],
                    "time": ev.get("time"),
                    "color": category_color(ev.get("type", "events")),
                }
                for ev in cell.get("events", [])[:3]
            ]
            dots = [
                category_color(ev.get("type", "events"))
                for ev in cell.get("events", [])[:4]
            ]
            more = cell.get("overflow", 0) + cell.get("class_count", 0)
            week.append(
                {
                    "empty": False,
                    "day": cell["day"],
                    "iso": iso,
                    "is_today": cell.get("is_today", False),
                    "is_selected": sel is not None and d == sel,
                    "is_past": d < today,
                    "is_weekend": d.weekday() >= 5,
                    "chips": chips,
                    "dots": dots,
                    "more": more,
                    "count": cell.get("count", 0) + cell.get("class_count", 0),
                }
            )
        weeks.append(week)

    agenda = _agenda(db, sel, now=now) if sel else None

    prev_month = date(year, month, 1) - timedelta(days=1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    return {
        "title": date(year, month, 1).strftime("%B %Y"),
        "year": year,
        "month": month,
        "weeks": weeks,
        "agenda": agenda,
        "prev_url": f"/calendar?cal={prev_month.year:04d}-{prev_month.month:02d}",
        "next_url": f"/calendar?cal={next_month.year:04d}-{next_month.month:02d}",
        "month_total": grid.get("month_oneoff_total", 0),
        "month_class_total": grid.get("month_class_total", 0),
    }


def _agenda(db: Session, day: date, *, now: datetime | None = None) -> dict[str, Any]:
    # UNIFY (Rule 0b 2026-06-26): the agenda shows the full unified tree (hours +
    # classes inline) — the same builder every calendar surface consumes.
    groups = events_views.calendar_day_view_model(db, day=day, now=now)["sections"]
    rows: list[dict[str, Any]] = []
    for g in groups:
        key = g["key"]
        src: list[dict[str, Any]] = []
        if g.get("subgroups"):
            for sub in g["subgroups"]:
                src.extend(sub.get("rows", []))
        else:
            src.extend(g.get("rows", []))
        for r in src:
            _tl = r.get("time_label") or ""
            rows.append(
                {
                    # Drop the "Time TBD" placeholder so the agenda shows a clean
                    # blank instead of a wall of "TBD" (Casey 2026-06-29); a real
                    # clock time still renders. The deeper fix is better ingest-
                    # time parsing, tracked separately.
                    "time_label": "" if "TBD" in _tl.upper() else _tl,
                    "title": r.get("title") or "",
                    "url": r.get("url"),
                    "cat": key,
                    "cat_label": CAT_LABEL.get(key, "Event"),
                    "color": category_color(key),
                    "_h": _first_hour(r.get("time_label") or ""),
                }
            )
    rows.sort(key=lambda it: (it["_h"] is None, it["_h"] or 0))
    return {
        "iso": day.isoformat(),
        "heading": day.strftime("%A, %B ") + str(day.day),
        "total": len(rows),
        "rows": rows[:8],
        "more": max(0, len(rows) - 8),
    }


_HOUR_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m", re.I)


def _first_hour(time_label: str) -> float | None:
    m = _HOUR_RE.search(time_label or "")
    if not m:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hour += 12
    return hour + (int(m.group(2) or 0) / 60.0)
