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
from app.conditions.constants import SOURCE_GAS
from app.db.models import Event
from app.events.tag_display import public_event_tags
from app.gas.service import board_from_cache
from app.home import events_views, sandstone
from app.home.day_counts import day_counts

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
    # "learn" is the Classes & Workshops bucket (app.home.event_buckets); the
    # historical "classes" key is Fitness & Sports (2026-07-01 month audit —
    # learn used to fall through every one of these maps to the civic fallback).
    "learn": "activity",
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
    # Classes & Workshops wears the palette's until-now-unmapped --c-classes
    # accent, so workshops stop rendering in the civic gray fallback.
    "learn": "var(--c-classes)",
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
    "learn": "Workshop",
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
    "learn": "im-art",
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


# ── conditions bar (Temp · Water · Wind · UV · Sunset · Gas) ───────────────────
def conditions_tiles(db: Session, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """The conditions tiles in the v4.4 order Temp · Water · Wind · UV · Sunset ·
    Gas. Each is honest-omit: a tile only renders when its live source has a value
    (the strip simply shows fewer columns). Clouds retired (v4.4 Δ2): the pipeline
    only exposed the NWS sky *word*, not a real cloud-cover %, so it was dropped in
    favor of Water + Sunset — both honest, computed/measured values.
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

    # Water temp — second in the strip (v4.4 §1), carries the teal-soft tint via
    # ``is_water``. Honest-omit: only when the gage feed has a live reading.
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
                "is_water": True,
                "is_stale": bool(payload.get("water_temp_is_stale")),
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

    # Sunset — computed astronomically (app.conditions.sun), always available and
    # never stale; ``sunset_local`` is Lake-local wall-clock like "7:42 PM", split
    # into the "7:42" value + "pm" unit the v4.4 tile renders (§1).
    sunset_local = payload.get("sunset_local")
    if isinstance(sunset_local, str) and sunset_local.strip():
        parts = sunset_local.split()
        tiles.append(
            {
                "key": "sunset",
                "icon": "sunset",
                "label": "Sunset",
                "value": parts[0],
                "unit": parts[1].lower() if len(parts) > 1 else None,
                "color": None,
                "is_gas": False,
                "is_stale": bool(payload.get("sunset_is_stale")),
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


def gas_top5(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """The 5 cheapest current stations for the gas-tile expander (price + name +
    cross-street + directions).

    Built from the single :class:`~app.gas.service.GasBoard` (v4.4 PR-1), the
    same board the strip tile and /gas page use, so the figures can never
    disagree. ``read_source`` stays imported here so tests that patch this
    module's cache seam still feed the board."""
    now_utc = now or datetime.now(UTC).replace(tzinfo=None)
    if now_utc.tzinfo is not None:
        now_utc = now_utc.astimezone(UTC).replace(tzinfo=None)
    board = board_from_cache(read_source(db, SOURCE_GAS, now=now_utc), now=now_utc)
    out: list[dict[str, Any]] = []
    for s in board.cheapest("reg", 5):
        price = s.prices["reg"]
        out.append(
            {
                "price": f"${price:.2f}",
                "name": s.name,
                "cross_street": s.address,
                "directions_url": s.directions_url,
            }
        )
    return {
        "cheapest": out,
        "is_stale": board.is_stale,
        "staleness_label": board.label,
    }


# ── directory launcher (v4.4 PR-5 rail card) ───────────────────────────────────
# The 8 launcher categories (DESIGN_SPEC §4.1): department slug → short label
# (exact — they truncate otherwise) + monoline icon. Counts come from the cached
# /categories index payload (DATA_CONTRACTS §5), so the launcher can never disagree
# with the directory's own numbers.
_LAUNCHER_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("eat-and-drink", "Eat & Drink", "fork"),
    ("home-and-property-services", "Home Services", "wrench"),
    ("auto-rv-and-marine", "Auto & Boat", "car"),
    ("health-and-medical", "Health", "health"),
    ("shopping-and-retail", "Shopping", "bag"),
    ("beauty-and-personal-care", "Salons", "scissors"),
    ("on-the-water", "Lake & Boating", "anchor"),
    ("lodging", "Lodging", "bed"),
)


def directory_launcher(db: Session) -> dict[str, Any]:
    """The rail's Find-any-business launcher: the 8 category tiles with live counts
    + a floor-rounded total, all from the cached /categories index (the same query
    the directory pages use, DATA_CONTRACTS §5). A category with no row is omitted
    (honest — never a fabricated count)."""
    # Function-scope import avoids a module-load cycle (categories.router imports
    # a wide slice of the app).
    from app.categories.router import _get_index_payload

    rows = _get_index_payload(db)
    by_slug = {r.get("slug"): r for r in rows}
    total = sum(int(r.get("count") or 0) for r in rows)
    tiles: list[dict[str, Any]] = []
    for slug, label, icon in _LAUNCHER_CATEGORIES:
        row = by_slug.get(slug)
        if row is None:
            continue
        tiles.append(
            {
                "label": label,
                "url": f"/categories/{slug}",
                "count": int(row.get("count") or 0),
                "icon": icon,
            }
        )
    # Floor-rounded hundreds, e.g. 2437 -> "2,400+"; None when the directory is
    # empty so the template can omit the count clause.
    total_label = f"{total // 100 * 100:,}+" if total >= 100 else None
    return {"total": total_label, "total_raw": total, "tiles": tiles}


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
        # Classes & Workshops ("learn") lists flat — no activity sub-categories
        # (Casey 2026-06-29: "classes and workshops can just all be put together").
        # Fitness & sports ("classes") KEEPS its activity subgroups (Casey
        # 2026-06-30 wanted those back). The section keeps its full sorted `rows`,
        # so dropping the split `subgroups` renders just the learn list flat.
        if s.get("key") == "learn":
            s["subgroups"] = []

    # The headline count comes from the single day-count service (v4.4 PR-3), the
    # same base the calendar agenda header uses — so they can never disagree.
    return {"sections": sections, "total": day_counts(db, day, now=now, family=family, vm=vm).total}


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
    vm = events_views.calendar_day_view_model(db, day=day, now=now)
    groups = vm["sections"]
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
            # A venue-hours row (a curated ``ongoing`` row or its DB
            # ``facet:hours`` twin) is a place being OPEN, not an event — the
            # agenda used to caption every billiards hall / trampoline park
            # "Event" (2026-07-01 month audit). Label it honestly instead.
            _tags = {str(t).strip().lower() for t in (r.get("tags") or [])}
            _hours = bool(r.get("ongoing")) or "facet:hours" in _tags
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
                    "cat_label": "Open today" if _hours else CAT_LABEL.get(key, "Event"),
                    "color": category_color(key),
                    "_h": _first_hour(r.get("time_label") or ""),
                }
            )
    rows.sort(key=lambda it: (it["_h"] is None, it["_h"] or 0))
    # "N events & classes" header = the single day-count base (v4.4 PR-3), the same
    # number the home headline shows — reusing the vm we already built so the day
    # is never counted twice.
    total = day_counts(db, day, now=now, vm=vm).total
    shown = rows[:8]
    return {
        "iso": day.isoformat(),
        "heading": day.strftime("%A, %B ") + str(day.day),
        "total": total,
        "rows": shown,
        "more": max(0, total - len(shown)),
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
