"""Hava -- ``GET /home`` route (Direction C / ``home_c.html``).

Also hosts the sponsor attribution endpoints (v52 P0):

* ``GET /sponsor/click`` — bumps ``Sponsor.clicks`` and 302s to the row's
  ``cta_url``. Linked from ``_partials/marquee.html``. Without this route,
  every marquee CTA 404s.
* ``GET /sponsor`` — advertiser landing stub. Linked from the marquee unsold
  fallback and from the home/category footers.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, time, timedelta
from datetime import date as dt_date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analytics import record_event
from app.categories import queries as cat_queries
from app.conditions.cache import read_source
from app.conditions.constants import GAS_STALE_AFTER_HOURS, SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.conditions.view_model import build_conditions_strip_view_model
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import limiter
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import AdSlot, Event, Provider, Sponsor
from app.events import series as event_series
from app.groups.themed_groups import group_label
from app.home import collections as curated_collections
from app.home import sandstone, sponsor_store
from app.home.queries import CATEGORY_LABELS
from app.v1.categories import BUCKET_SLUG_REDIRECTS, MASTER_BUCKETS

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["home"])

# Configurable home hero. The previous rotation hard-coded Unsplash IDs in the
# *page-slug* form (``photo-jp9Bdu6IGq4``) — not valid ``images.unsplash.com``
# asset URLs — so every hero 404'd on the live site. The hero is now a
# configurable asset: ``HOME_HERO_IMAGE_URL`` (a local ``/static`` path or remote
# URL) overrides the bundled golden-hour default at ``_DEFAULT_HERO_ASSET``.
# ``.ll-hero`` also paints a golden-hour gradient *under* the photo, so a missing
# or slow image degrades to an intentional sunset wash — never a broken box or a
# reused stock photo. Optional ``HOME_HERO_CREDIT`` / ``HOME_HERO_CREDIT_URL``
# add an attribution line when the owner supplies a licensed photo.
_DEFAULT_HERO_ASSET = "/static/img/home-hero.jpg"

# Place-grounded hero copy, env-overridable (same pattern as the hero image) so
# the headline can be tuned per season/campaign without a redeploy.
_HERO_EYEBROW_DEFAULT = "YOUR LAKE, RIGHT NOW"
_HERO_HEADLINE_DEFAULT = "Your day on Lake Havasu starts here"


def _hero_context() -> dict[str, Any]:
    url = (os.getenv("HOME_HERO_IMAGE_URL") or "").strip() or _DEFAULT_HERO_ASSET
    credit = (os.getenv("HOME_HERO_CREDIT") or "").strip()
    credit_url = (os.getenv("HOME_HERO_CREDIT_URL") or "").strip()
    attribution = (
        {"photographer": credit, "profile_url": credit_url} if credit and credit_url else None
    )
    return {
        "url": url,
        "attribution": attribution,
        "eyebrow": (os.getenv("HOME_HERO_EYEBROW") or "").strip() or _HERO_EYEBROW_DEFAULT,
        "headline": (os.getenv("HOME_HERO_HEADLINE") or "").strip() or _HERO_HEADLINE_DEFAULT,
    }


def _format_event_time_label(start_at: datetime) -> str:
    return start_at.strftime("%I:%M %p").lstrip("0")


# Event cards are image-optional: most events have no photo, so the date block is
# the hero (brief §3). Colour-code that block by a coarse category derived from
# the event's freeform ``tags`` — gives the feed visual rhythm without a real
# category column. (label, accent hex). First keyword hit wins; default last.
_EVENT_CATEGORY_ACCENTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("aquatic", "swim", "water", "pool", "boat", "lake"), "Water", "#2f7d9a"),
    (("music", "concert", "live"), "Music", "#b0468a"),
    (("art", "theater", "theatre", "gallery", "comedy", "movie", "film"), "Arts", "#7a5cb0"),
    (("food", "market", "wine", "beer", "dining", "taste"), "Food", "#c16b4a"),
    (("sport", "fitness", "run", "race", "pickle", "golf", "yoga"), "Active", "#3f7d55"),
    (("kid", "youth", "family", "camp", "child"), "Family", "#d39a2e"),
    (("fundraiser", "community", "civic", "nonprofit", "charity"), "Community", "#3f5c4b"),
    (("firework", "festival", "holiday", "parade"), "Festival", "#c0492f"),
)
_EVENT_CATEGORY_DEFAULT = ("Event", "#3f5c4b")


def _event_accent(tags: object) -> tuple[str, str]:
    """Return ``(category_label, accent_hex)`` from an event's tags list."""
    haystack = ""
    if isinstance(tags, list):
        haystack = " ".join(str(t).lower() for t in tags)
    elif isinstance(tags, str):
        haystack = tags.lower()
    for keywords, label, color in _EVENT_CATEGORY_ACCENTS:
        if any(k in haystack for k in keywords):
            return label, color
    return _EVENT_CATEGORY_DEFAULT


# Look-ahead horizon for inferring a series' weekly cadence. The display window
# (e.g. "Today") is too narrow to see that Lap Swim runs Mon–Fri, so we sample a
# month ahead to derive the schedule label and "runs regularly" status.
_SERIES_HORIZON_DAYS = 28


def _series_index_for(db: Session, *, start_day: datetime, end_day: datetime) -> dict:
    """Build the recurring-series index over the display window + look-ahead."""
    from datetime import timedelta as _td

    horizon_end = max(end_day.date(), start_day.date() + _td(days=_SERIES_HORIZON_DAYS))
    horizon_rows = (
        db.query(
            Event.normalized_title,
            Event.location_normalized,
            Event.start_time,
            Event.date,
            Event.is_recurring,
        )
        .filter(
            Event.status == "live",
            Event.date >= start_day.date(),
            Event.date <= horizon_end,
        )
        .all()
    )
    return event_series.build_series_index(
        [(t, loc, st, d, bool(rec)) for (t, loc, st, d, rec) in horizon_rows]
    )


def _window_event_dict(ev: Event, *, recurring: bool, schedule_label: str) -> dict[str, str]:
    start_at = datetime.combine(ev.date, ev.start_time)
    category_label, accent = _event_accent(ev.tags)
    # M-16/M-17: render the start-end span when an end time is known so a class
    # reads "5:00 - 6:00 AM", not just a start. Falls back to the start label.
    time_label = _format_event_time_label(start_at)
    if ev.end_time is not None:
        end_at = datetime.combine(ev.end_date or ev.date, ev.end_time)
        if end_at > start_at:
            time_label = f"{_format_event_time_label(start_at)} - {_format_event_time_label(end_at)}"
    return {
        "id": ev.id,
        "title": ev.title,
        "venue": ev.location_name,
        "url": f"/events/{ev.id}",
        "time_label": time_label,
        "day_label": start_at.strftime("%a"),
        "date_label": str(start_at.day),
        "month_label": start_at.strftime("%b"),
        "image_url": None,
        "featured": bool(ev.featured),
        "category_label": category_label,
        "accent_color": accent,
        "recurring": recurring,
        "schedule_label": schedule_label,
    }


def _collapse_window_events(
    db: Session, *, start_day: datetime, end_day: datetime
) -> list[dict[str, str]]:
    """All events in the window, recurring series collapsed to one entry each.

    A class that occurs every weekday (28 separate rows for "Lap Swim") would
    otherwise flood the feed and bury one-off events. We detect series by their
    natural key and emit each once -- anchored on its next occurrence in the
    window, tagged ``recurring`` with a human ``schedule_label`` (brief §4).

    Ordering puts one-offs first (then by date/time) so that a later cap never
    drops a one-off festival in favour of a recurring class. ``featured`` is a
    secondary key *within* the one-off and recurring groups, not the primary
    sort -- the old ``featured.desc()`` primary let featured recurring classes
    fill the cap ahead of plain one-offs (brief §2).
    """
    rows = (
        db.query(Event)
        .filter(
            Event.status == "live",
            Event.date >= start_day.date(),
            Event.date <= end_day.date(),
        )
        .order_by(Event.date.asc(), Event.start_time.asc())
        .all()
    )
    index = _series_index_for(db, start_day=start_day, end_day=end_day)

    items: list[dict[str, str]] = []
    seen_series: set[tuple[str, str, str]] = set()
    for ev in rows:
        key = event_series.series_key(ev.normalized_title, ev.location_normalized, ev.start_time)
        info = index.get(key)
        recurring = bool(info and info.is_series)
        if recurring:
            if key in seen_series:
                continue  # one card per series -- this is the next occurrence
            seen_series.add(key)
        items.append(
            _window_event_dict(
                ev,
                recurring=recurring,
                schedule_label=event_series.schedule_label(info.weekdays) if recurring else "",
            )
        )

    # One-offs first (preserving chronological order within each group), then
    # featured-but-one-off rise within the one-off block, then recurring.
    items.sort(key=lambda it: (it["recurring"], not it["featured"]))
    return items


def _events_for_window(
    db: Session, *, start_day: datetime, end_day: datetime, limit: int
) -> list[dict[str, str]]:
    """Capped, series-collapsed window feed (one-offs prioritised before fill)."""
    return _collapse_window_events(db, start_day=start_day, end_day=end_day)[:limit]


def _events_for_window_with_total(
    db: Session, *, start_day: datetime, end_day: datetime, limit: int
) -> tuple[list[dict[str, str]], int]:
    """Return ``(shown_rows, total_after_collapse)`` for honest "N total" copy.

    The total is the *collapsed* count (recurring series counted once) so the
    "N coming up . showing M" line matches what the user can actually scroll to,
    not the raw row count that the series collapse hides (brief §2).
    """
    collapsed = _collapse_window_events(db, start_day=start_day, end_day=end_day)
    return collapsed[:limit], len(collapsed)


def _tonight_card(db: Session, *, now: datetime) -> dict[str, Any] | None:
    """Build the home "Tonight" card per DL-16.

    Selection: the next event today that has *not yet started* (start_time strictly
    after ``now``), preferring one-offs over recurring classes. If nothing remains
    today, fall back to the earliest event tomorrow. The card label switches:

    * "Tonight" -- a remaining event today when it is already evening (>= 16:00).
    * "Today"   -- a remaining event today earlier in the day.
    * "Tomorrow"-- when today is exhausted and the next event is tomorrow.

    Returns ``None`` (card omitted) when neither today nor tomorrow has an event
    -- never a fabricated placeholder (anti-confabulation contract).
    """
    today = now.date()
    now_t = now.time()

    def _earliest(rows: list[Event]) -> Event | None:
        # One-offs win ties so a festival beats a recurring class at the same time.
        ranked = sorted(rows, key=lambda e: (e.start_time, bool(e.is_recurring)))
        return ranked[0] if ranked else None

    todays = (
        db.query(Event)
        .filter(
            Event.status == "live",
            Event.date == today,
            Event.start_time > now_t,
        )
        .all()
    )
    chosen = _earliest(todays)
    if chosen is not None:
        label = "Tonight" if now.hour >= 16 else "Today"
    else:
        tomorrow = today + timedelta(days=1)
        rows = (
            db.query(Event)
            .filter(
                Event.status == "live",
                Event.date == tomorrow,
            )
            .all()
        )
        chosen = _earliest(rows)
        label = "Tomorrow"

    if chosen is None:
        return None

    start_at = datetime.combine(chosen.date, chosen.start_time)
    sub_bits = [b for b in (_format_event_time_label(start_at), chosen.location_name) if b]
    return {
        "kind": "tonight",
        "k": label,
        "title": chosen.title,
        "sub": " · ".join(sub_bits),
        "href": f"/events/{chosen.id}",
        "live": False,
    }


def _bucket_destination_route(bucket_id: str) -> str:
    """Tier-1 ``/categories/{route}`` slug a master bucket 301s to.

    The home Browse rows link to ``/categories/{bucket}``, which
    ``app/categories/router.py`` redirects to a Tier-1 page via
    ``BUCKET_SLUG_REDIRECTS`` (e.g. ``recreation-outdoors`` →
    ``/categories/on-the-water``). Extract that route slug so the count we
    show equals the count that page's header shows.
    """
    return BUCKET_SLUG_REDIRECTS[bucket_id].rsplit("/", 1)[-1]


# P0 Task 2 — high-value subcategory shortcuts so users don't wade through the
# full bucket list. Editorial/curated (like the hero rotation). "Home services"
# expands to its top trades on the rich /category/ filter pages; the popular row
# deep-links to the new /lake-havasu/{subcategory} SEO landings.
_HOME_SERVICES_SHORTCUT: dict[str, Any] = {
    "title": "Home services",
    "url": "/lake-havasu/home-services",
    "items": (
        {"label": "Plumbers", "url": "/category/home-property-services?trade=plumber"},
        {"label": "Electricians", "url": "/category/home-property-services?trade=electrician"},
        {"label": "HVAC", "url": "/category/home-property-services?trade=hvac"},
        {"label": "Roofers", "url": "/category/home-property-services?trade=roofer"},
    ),
}

_POPULAR_SUBCATEGORIES: tuple[dict[str, str], ...] = (
    {"label": "Restaurants", "url": "/lake-havasu/restaurants"},
    {"label": "On the Water", "url": "/lake-havasu/on-the-water"},
    {"label": "Health & Medical", "url": "/lake-havasu/health-medical"},
    {"label": "Auto", "url": "/lake-havasu/auto"},
    {"label": "Pets", "url": "/lake-havasu/pets"},
)


def _category_cards(db: Session) -> list[dict[str, str | int]]:
    """Per-bucket counts for the home Browse list.

    Counts are computed with the SAME source/filter the destination category
    page uses (``cat_queries.category_count`` over ``CATEGORY_FILTERS``) rather
    than a separate ``Provider.category`` → bucket remap. The old remap keyed
    on spec-style slugs (``on_the_water``, ``shopping_essentials``, …) that
    never matched the real legacy ``Provider.category`` values (``lake_recreation``,
    ``retail``, ``lodging``, …), so every unmapped row fell through to Services —
    zeroing Recreation/Sports/Shopping/Stay while inflating Services. Delegating
    to ``category_count`` guarantees the home figure matches the page it links to.
    """
    cards: list[dict[str, str | int]] = []
    for bucket in MASTER_BUCKETS:
        dest_route = _bucket_destination_route(bucket["id"])
        # category_count returns None for an empty route (BUILD.md no-zero
        # rule); the home row coerces to 0 so a genuinely empty bucket reads
        # honestly rather than vanishing.
        count = cat_queries.category_count(db, dest_route) or 0
        cards.append(
            {
                "id": bucket["id"],
                "label": bucket["label"],
                "slug": bucket["slug"],
                "count": count,
            }
        )
    return cards


# P0 Task 5 — slim top utility strip. Combines the ambient data we already pull
# (cheapest gas + NWS temp + AirNow AQI + USGS lake/water + active advisory) into
# one compact chip row instead of a full-width gas panel. Each chip expands its
# detail on tap (template uses <details>). UV index is now fetched (Open-UV with
# a keyless EPA fallback — see app/conditions/uv.py) and leads the sun/sky slot;
# the lower-value sky/condition description was demoted (still in the JSON
# payload, no longer a strip tile).
_UTILITY_TILE_MAP: dict[str, tuple[str, str, str]] = {
    # conditions-tile kind -> (chip kind, icon, label)
    # Task 0 (source-expansion): the "sky_condition" chip was demoted in favour
    # of UV — view_model.py no longer emits a sky_condition tile, so its map
    # entry was removed. UV now leads the sun/sky slot.
    "temp": ("weather", "🌡", "Now"),
    "uv": ("uv", "☀", "UV index"),
    "aqi": ("air", "💨", "Air quality"),
    "water_temp": ("water", "🌊", "Water temp"),
    "lake_level": ("lake", "🏞", "Lake level"),
    "advisory": ("alert", "⚠", "Advisory"),
}


def _utility_chips(db: Session) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []

    # Gas leads — it's the figure people open the app for.
    gas = _gas_snapshot(db)
    if gas.get("has_data"):
        top = gas["cheapest"][0] if gas.get("cheapest") else {}
        price = top.get("prices", {}).get("regular") if isinstance(top, dict) else None
        if isinstance(price, (int, float)):
            name = top.get("station_name") or top.get("name") or "Lowest station"
            chips.append(
                {
                    "kind": "gas",
                    "icon": "⛽",
                    "value": f"${price:.2f}",
                    "label": "Cheapest gas",
                    "detail": f"{name} · regular, per gallon",
                    "source": None,
                    "freshness": gas.get("staleness_label"),
                    "is_stale": bool(gas.get("is_stale")),
                    "severity": "neutral",
                    "href": "/gas",
                }
            )

    vm = build_conditions_strip_view_model(db)
    for tile in vm.tiles:
        mapped = _UTILITY_TILE_MAP.get(tile.kind)
        if not mapped:
            continue
        chip_kind, icon, label = mapped
        chips.append(
            {
                "kind": chip_kind,
                "icon": icon,
                "value": tile.primary_value,
                "label": label,
                "detail": tile.secondary_value or tile.detail_text,
                "source": tile.attribution_chip,
                "freshness": tile.staleness_label,
                "is_stale": tile.is_stale,
                "severity": tile.severity,
                "href": None,
            }
        )
    return chips


def _gas_snapshot(db: Session) -> dict[str, object]:
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now_utc)
    if row is None or not isinstance(row.data, dict):
        return {"has_data": False}
    stations = [s for s in (row.data.get("stations") or []) if isinstance(s, dict)]
    stations_sorted = sorted(
        stations,
        key=lambda s: float(
            s.get("prices", {}).get("regular")
            if isinstance(s.get("prices"), dict)
            and isinstance(s.get("prices", {}).get("regular"), (int, float))
            else 9999
        ),
    )
    cheapest = stations_sorted[:5]
    # Gas updates ~daily; use the daily-feed staleness threshold so a fresh fetch
    # doesn't read "stale" on the home widget (G-2 / H-2).
    label, stale = staleness_label(
        row.fetched_at, now_utc, stale_after_hours=GAS_STALE_AFTER_HOURS
    )
    return {
        "has_data": bool(cheapest),
        "staleness_label": label,
        "is_stale": bool(stale or row.is_stale),
        "cheapest": cheapest,
    }


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
    cal: str | None = None,
) -> HTMLResponse:
    """Render /home — the Sandstone editorial home (Ask mode).

    Every count/badge traces to a live query or is omitted (the anti-confabulation
    contract in 01_UI_BUILD_GUIDE.md §4). The optional ``cal=YYYY-MM`` param drives
    the server-rendered month calendar's prev/next without any client JS.
    """
    now = now_lake_havasu()
    utility_chips = _utility_chips(db)
    tonight_card = _tonight_card(db, now=now)
    cal_year, cal_month = sandstone.parse_cal_param(cal, default=now)
    spotlights = sponsor_store.active_spotlights(db)
    # Hero copy defaults to the locked prototype wording (with its italic accent);
    # owners can retune the eyebrow/headline per season via env without a redeploy.
    hero_eyebrow_override = os.getenv("HOME_HERO_EYEBROW") or None
    hero_headline_override = os.getenv("HOME_HERO_HEADLINE") or None
    return templates.TemplateResponse(
        request=request,
        name="home_sandstone.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "hero_eyebrow_override": hero_eyebrow_override,
            "hero_headline_override": hero_headline_override,
            "utility_chips": utility_chips,
            "primary_nav": sandstone.primary_nav(),
            "mega_columns": sandstone.mega_columns(db),
            "today_cards": sandstone.today_cards(
                utility_chips=utility_chips, tonight_card=tonight_card
            ),
            "featured_cards": sandstone.featured_cards(spotlights),
            "calendar": sandstone.calendar_month(
                db, year=cal_year, month=cal_month, today=now.date()
            ),
            "explore_tiles": sandstone.explore_tiles(db),
            "service_tiles": sandstone.service_tiles(db),
            "active_tab": "today",
        },
    )


def _serve_mode_landing(request: Request, db: Session, mode: str) -> HTMLResponse:
    """Shared renderer for the Lake / Night / Family landings.

    The page loads PRE-THEMED (``data-mode`` = mode) so Night fires its dark
    transformation server-side. Sub-tiles are navigation to real routes; the
    hero shows only live data (Lake conditions) or copy — never the mock
    counters (anti-confabulation, §4.10).
    """
    landing = sandstone.mode_landing(db, mode)
    return templates.TemplateResponse(
        request=request,
        name="mode_sandstone.html",
        context={
            "utility_chips": _utility_chips(db),
            "primary_nav": sandstone.primary_nav(),
            "mega_columns": sandstone.mega_columns(db),
            "current_mode": mode,
            **landing,
        },
    )


@router.get("/lake", response_class=HTMLResponse)
def serve_lake(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Lake Life mode landing."""
    return _serve_mode_landing(request, db, "lake")


@router.get("/night", response_class=HTMLResponse)
def serve_night(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Night mode landing (fires the dark transformation)."""
    return _serve_mode_landing(request, db, "night")


@router.get("/family", response_class=HTMLResponse)
def serve_family(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Family mode landing."""
    return _serve_mode_landing(request, db, "family")


@router.get("/map", response_class=HTMLResponse)
def serve_map_view(request: Request, scope: str | None = None) -> HTMLResponse:
    """Render /map — full-page Leaflet map (markers via /api/map_data/{scope}).

    Ships a scope selector (themed groups + tier-1 categories) whose tabs link to
    ``/map?scope=<slug>``; the server stamps ``data-map-scope`` on the body and
    the existing ``map.js`` reads it and calls ``/api/map_data``. ``map.js`` is
    reused unmodified (it captures the scope at init, so switching reloads).
    """
    now = now_lake_havasu()
    group_scopes = [
        {"slug": slug, "label": group_label(slug)}
        for slug in (
            "eat-drink-group",
            "on-the-water-group",
            "things-to-do-group",
            "home-auto-group",
            "health-fitness-group",
        )
    ]
    category_scopes = [
        {"slug": slug, "label": CATEGORY_LABELS.get(slug, slug.replace("-", " ").title())}
        for slug in (
            "eat-drink",
            "on-the-water",
            "outdoors-parks-trails",
            "classes-sports-recreation",
            "shopping-essentials",
            "home-property-services",
            "health-wellness-care",
            "auto-rv-fuel",
            "lodging-vacation-rentals",
            "pets",
            "public-civic-resources",
            "events",
        )
    ]
    valid_scopes = {s["slug"] for s in group_scopes} | {s["slug"] for s in category_scopes}
    requested = (scope or "").strip().lower()
    default_scope = requested if requested in valid_scopes else group_scopes[0]["slug"]
    return templates.TemplateResponse(
        request=request,
        name="map_c.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "group_scopes": group_scopes,
            "category_scopes": category_scopes,
            "default_scope": default_scope,
            "active_tab": "map",
        },
    )


def _split_oneoff_and_ongoing(
    groups: dict[str, list[dict]],
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Split time-grouped events into one-off (kept time-grouped) and recurring.

    Recurring series are pulled out into a single "Classes & ongoing" list,
    deduped across the time windows (a weekday class shows in Today *and* Next
    Week), so one-off festivals aren't buried under the daily-class repeats
    (brief §4 optional split).
    """
    ongoing: list[dict] = []
    seen: set[tuple] = set()
    oneoff_groups: dict[str, list[dict]] = {}
    for key, items in groups.items():
        oneoff: list[dict] = []
        for it in items:
            if it.get("recurring"):
                dedup_key = (it.get("title"), it.get("venue"), it.get("schedule_label"))
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    ongoing.append(it)
            else:
                oneoff.append(it)
        oneoff_groups[key] = oneoff
    return oneoff_groups, ongoing


def _group_series_by_venue(ongoing: list[dict]) -> list[dict]:
    """Group the recurring "Classes & ongoing" list by venue (brief §3).

    Returns ``[{"venue": str, "items": [...]}]`` ordered by first appearance so
    the events list can render one collapsible block per venue
    ("Aquatic Center -- 5 classes") instead of a flat flood of class rows.
    """
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for it in ongoing:
        venue = (it.get("venue") or "").strip()
        bkey = venue.lower()
        if bkey not in buckets:
            buckets[bkey] = {"venue": venue, "cards": []}
            order.append(bkey)
        buckets[bkey]["cards"].append(it)
    return [buckets[k] for k in order]


def _event_list_windows(now: datetime) -> dict[str, tuple[datetime, datetime]]:
    """Honest, contiguous, gap-free buckets for the events list (E-1).

    The old code used a naive rolling ``now+1..now+3`` window mislabeled "This
    Weekend" (so a Wednesday event showed under "This Weekend" and a Sunday under
    "Next Week"). Instead anchor to real calendar-week boundaries in Lake Havasu
    local time:

    * **today**     — today only.
    * **this_week** — tomorrow through the end of this week (Sunday).
    * **next_week** — the following Monday–Sunday.

    Windows are disjoint and adjacent, so no event is dropped or double-listed.
    """
    days_to_sunday = (6 - now.weekday()) % 7  # Mon=0 … Sun=6
    this_sunday = now + timedelta(days=days_to_sunday)
    return {
        "today": (now, now),
        "this_week": (now + timedelta(days=1), this_sunday),
        "next_week": (this_sunday + timedelta(days=1), this_sunday + timedelta(days=7)),
    }


# ``?when=`` chips on /events-ui. Each maps to the subset of buckets to show.
# ``all`` (and any unknown value) shows every bucket. ``today``/``this-week``/
# ``next-week`` narrow to a single bucket; ``weekend`` reuses the strict Sat-Sun
# window from ``event_window_for_chip`` so the chip agrees with the category page.
_EVENTS_WHEN_CHIPS: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("today", "Today"),
    ("weekend", "This Weekend"),
    ("this-week", "This Week"),
    ("next-week", "Next Week"),
)
_WINDOW_CAP = 16


def _parse_iso_date(value: str | None) -> dt_date | None:
    if not value or not str(value).strip():
        return None
    try:
        return dt_date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


@router.get("/events-ui", response_class=HTMLResponse)
def serve_events_ui(
    request: Request,
    db: Session = Depends(get_db),
    when: str | None = None,
    date: str | None = None,
) -> HTMLResponse:
    """Render the Sandstone events list (today / this week / next week).

    ``?when=`` narrows to a single bucket (``today``/``weekend``/``this-week``/
    ``next-week``); ``?date=YYYY-MM-DD`` (the home-calendar day links) shows a
    single-day window. Each rendered bucket carries an honest total so the
    section header reads "N coming up . showing M . See all ->".
    """
    now = now_lake_havasu()
    when_key = (when or "all").strip().lower()
    single_day = _parse_iso_date(date)

    windows = _event_list_windows(now)
    if single_day is not None:
        day_dt = datetime.combine(single_day, time(12, 0))
        window_defs = [("date", single_day.strftime("%A, %B ") + str(single_day.day), (day_dt, day_dt))]
    elif when_key == "weekend":
        from app.events.queries import event_window_for_chip as _chip

        w_start, w_end = _chip("weekend", today=now.date())
        window_defs = [
            (
                "weekend",
                "This Weekend",
                (datetime.combine(w_start, time(12, 0)), datetime.combine(w_end, time(12, 0))),
            )
        ]
    else:
        ordered = [
            ("today", "Today", windows["today"]),
            ("this_week", "This Week", windows["this_week"]),
            ("next_week", "Next Week", windows["next_week"]),
        ]
        key_map = {"today": "today", "this-week": "this_week", "next-week": "next_week"}
        if when_key in key_map:
            window_defs = [d for d in ordered if d[0] == key_map[when_key]]
        else:
            window_defs = ordered

    raw_groups: dict[str, list[dict[str, str]]] = {}
    totals: dict[str, int] = {}
    labels: dict[str, str] = {}
    for gkey, label, (start_day, end_day) in window_defs:
        rows, total = _events_for_window_with_total(
            db, start_day=start_day, end_day=end_day, limit=_WINDOW_CAP
        )
        raw_groups[gkey] = rows
        totals[gkey] = total
        labels[gkey] = label

    oneoff_groups, ongoing_classes = _split_oneoff_and_ongoing(raw_groups)
    ongoing_by_venue = _group_series_by_venue(ongoing_classes)
    # Sections preserve the requested order; each carries shown/total for the
    # honest header line. Recurring rows are pulled into ``ongoing_classes``, so
    # the per-section "showing M" counts the visible one-offs.
    sections = [
        {
            "key": gkey,
            "label": labels[gkey],
            "cards": oneoff_groups.get(gkey, []),
            "shown": len(oneoff_groups.get(gkey, [])),
            "total": totals[gkey],
            "capped": totals[gkey] > _WINDOW_CAP,
        }
        for gkey, _label, _w in window_defs
    ]
    events_total = sum(s["total"] for s in sections)
    chips = [
        {"key": key, "label": label, "active": (key == when_key and single_day is None)}
        for key, label in _EVENTS_WHEN_CHIPS
    ]
    return templates.TemplateResponse(
        request=request,
        name="events_sandstone.html",
        context={
            "event_sections": sections,
            "ongoing_classes": ongoing_by_venue,
            "events_total": events_total,
            "when_chips": chips,
            "active_when": when_key,
            "selected_date_label": single_day.strftime("%A, %B ") + str(single_day.day)
            if single_day
            else None,
            "month_label": now.strftime("%B %Y"),
            "active_tab": "events",
            "primary_nav": sandstone.primary_nav(),
            "mega_columns": sandstone.mega_columns(db),
            "utility_chips": _utility_chips(db),
        },
    )


# Sponsor attribution endpoints (v52 P0 — see module docstring) ----------------


def _parse_slot(slot: str) -> AdSlot:
    """Validate the ``slot`` query param against the four-tier enum."""
    try:
        return AdSlot(slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid sponsor slot") from exc


@router.get("/sponsor/click")
@limiter.limit("60/minute")
def sponsor_click(
    request: Request,
    id: str,
    slot: str = "marquee",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Attribute a sponsor click, then 302 to the booked ``cta_url``.

    GET (not POST) because the template uses a plain ``<a href>`` — switching
    to POST would force JS or a form, neither of which fits the editorial card
    design. Open-redirect-safe because ``cta_url`` is admin-curated at insert
    time and we only redirect when the row matches the live filter (approved +
    active + within booking window).
    """
    ad_slot = _parse_slot(slot)
    row = (
        sponsor_store._live_filter_for_slot(db.query(Sponsor), ad_slot)
        .filter(Sponsor.id == id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    # Atomic UPDATE — single statement, no row lock needed for ++ counter.
    db.execute(update(Sponsor).where(Sponsor.id == row.id).values(clicks=Sponsor.clicks + 1))
    db.commit()
    # v54 Track B — long-form click event. ``home.spotlight.click`` fires
    # only when the slot is spotlight (cleanest downstream join with the
    # ``home.spotlight.impression`` rows from sponsor_store.active_spotlights).
    # ``home.sponsor.click`` fires for every slot so cross-tier CTR roll-ups
    # don't need a UNION. Best-effort: ``record_event`` swallows DB errors.
    if ad_slot is AdSlot.SPOTLIGHT:
        record_event(
            db,
            "home.spotlight.click",
            slot=ad_slot.value,
            sponsor_id=row.id,
            ranking_score=row.weight,
        )
    record_event(
        db,
        "home.sponsor.click",
        slot=ad_slot.value,
        sponsor_id=row.id,
        ranking_score=row.weight,
    )
    # 302 (not 301) — never cache the redirect; CTA URLs can rotate.
    return RedirectResponse(url=row.cta_url, status_code=302)


def _delink_stale_places(db: Session, collection: dict) -> dict:
    """Return a copy of ``collection`` with place links pruned to live providers.

    A curated place ``slug`` that no longer resolves to an active, non-draft
    provider would render a card linking to a 404 ``/provider/<slug>`` page. We
    null those slugs so the card still shows (name/blurb/image) but isn't a dead
    link — the same drop-broken-links discipline the Discover grid uses. Never
    mutates the loader's cached dict.
    """
    places = collection.get("places") or []
    wanted = [p["slug"] for p in places if isinstance(p, dict) and p.get("slug")]
    resolved: set[str] = set()
    if wanted:
        rows = db.scalars(
            select(Provider.slug).where(
                Provider.slug.in_(wanted),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
        ).all()
        resolved = {s for s in rows if s}
    safe_places = [
        ({**p, "slug": None} if p.get("slug") and p["slug"] not in resolved else p)
        for p in places
        if isinstance(p, dict)
    ]
    return {**collection, "places": safe_places}


@router.get("/collection/{slug}", response_class=HTMLResponse)
def collection_landing(
    request: Request, slug: str, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Render a curated editorial collection (e.g. "Dog-friendly patios").

    Source of truth is ``app/home/curated_collections.json`` via
    ``app.home.collections``. Unknown slug 404s; the loader never raises, so a
    stale entry degrades to a clean 404 rather than a 500. Place links that no
    longer point at a live provider are de-linked (rendered as non-link cards).
    """
    collection = curated_collections.get_collection(slug)
    if collection is None:
        raise HTTPException(status_code=404, detail="unknown_collection")
    collection = _delink_stale_places(db, collection)
    now = now_lake_havasu()
    return templates.TemplateResponse(
        request=request,
        name="collection_landing.html",
        context={
            "collection": collection,
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "active_tab": "explore",
        },
    )


@router.get("/sponsor", response_class=HTMLResponse)
def sponsor_landing(request: Request) -> HTMLResponse:
    """Advertiser landing page. Static stub for v52; copy lands in a follow-up.

    Linked from ``home_c.html`` / ``category_c.html`` footers and from the
    marquee unsold-fallback. Was a 404 before this PR.
    """
    return templates.TemplateResponse(
        request=request,
        name="sponsor_landing.html",
        context={},
    )
