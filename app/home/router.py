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
from app.categories.display_labels import map_scope_label
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
from app.events.class_occurrences import class_occurrences_in_window
from app.events.dedup import dedup_cross_source_event_rows
from app.events.time_labels import TIME_TBD_LABEL, is_time_tbd, time_sort_key
from app.groups.themed_groups import group_label
from app.home import collections as curated_collections
from app.home import events_views, sandstone, sponsor_store
from app.home.today_feed import today_feed
from app.monetization import serving
from app.movies.queries import movies_today
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


def _is_midnight_fallback(ev: Event) -> bool:
    """Aggregator feeds without a time component land as a 00:00 start (the
    ingest fallback) — "time unknown", not a real 12:00 AM event. The single
    definition lives in :mod:`app.events.time_labels` (shared with the home
    week strip and month grid)."""
    return is_time_tbd(ev.start_time, ev.end_time)


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
    # WP-4 allows NULL times; combine with midnight only for the date labels.
    start_at = datetime.combine(ev.date, ev.start_time or time(0, 0))
    category_label, accent = _event_accent(ev.tags)
    # M-16/M-17: render the start-end span when an end time is known so a class
    # reads "5:00 - 6:00 AM", not just a start. Falls back to the start label.
    # Time-unknown rows (NULL or the midnight ingest fallback) read "Time TBD",
    # never a fabricated "12:00 AM".
    midnight_fallback = _is_midnight_fallback(ev)
    time_label = TIME_TBD_LABEL if midnight_fallback else _format_event_time_label(start_at)
    if ev.end_time is not None and not midnight_fallback:
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
    # Time-unknown rows (NULL or the midnight ingest fallback) sort after the
    # timed events of their day instead of leading it as a fake 12 AM.
    rows.sort(key=lambda ev: (ev.date, time_sort_key(ev.start_time, ev.end_time)))
    # Cross-source dedup: two scrapers carrying the same real-world event (same
    # normalized title + date; one with a fake-noon/TBD time or an address-as-
    # venue) collapse to one survivor before series grouping, so neither the
    # bucket cards nor the honest totals double-count it (display-only filter).
    rows = dedup_cross_source_event_rows(rows)
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

    items.extend(
        _class_schedule_cards(db, start_day=start_day, end_day=end_day, event_rows=rows)
    )

    # One-offs first (preserving chronological order within each group), then
    # featured-but-one-off rise within the one-off block, then recurring.
    items.sort(key=lambda it: (it["recurring"], not it["featured"]))
    return items


def _class_schedule_cards(
    db: Session, *, start_day: datetime, end_day: datetime, event_rows: list[Event]
) -> list[dict[str, str]]:
    """Venue class schedules (entity Schedule rows, not events) as series cards.

    The captured gym/class schedules publish onto venue entities and render on
    provider pages -- but they are invisible to the events feed, so a "Mon-Thu
    BJJ" venue looked classless on /events-ui and the calendar day pages. Emit
    one recurring card per class series with an occurrence in the window,
    anchored on its next occurrence, linking to the venue page (class series
    have no event permalink). Classes that ALSO exist as recurring events (the
    aquatic programs) are dropped by title so they never show twice.
    """
    event_titles = {(ev.title or "").strip().lower() for ev in event_rows}
    occs = class_occurrences_in_window(
        db, window_start=start_day.date(), window_end=end_day.date()
    )
    cards: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for occ in occs:
        title_l = occ.title.strip().lower()
        if title_l in event_titles:
            continue
        skey = (title_l, occ.venue.strip().lower())
        if skey in seen:
            continue  # one card per series -- anchored on its next occurrence
        seen.add(skey)
        start_at = datetime.combine(occ.date, occ.start_time or time(0, 0))
        time_label = TIME_TBD_LABEL if occ.start_time is None else _format_event_time_label(start_at)
        if occ.start_time is not None and occ.end_time is not None:
            end_at = datetime.combine(occ.date, occ.end_time)
            if end_at > start_at:
                time_label = (
                    f"{_format_event_time_label(start_at)} - "
                    f"{_format_event_time_label(end_at)}"
                )
        category_label, accent = _event_accent(["class"])
        cards.append(
            {
                "id": f"class:{occ.venue}:{occ.title}",
                "title": occ.title,
                "venue": occ.venue,
                "url": occ.url,
                "time_label": time_label,
                "day_label": start_at.strftime("%a"),
                "date_label": str(start_at.day),
                "month_label": start_at.strftime("%b"),
                "image_url": None,
                "featured": False,
                "category_label": category_label,
                "accent_color": accent,
                "recurring": True,
                "schedule_label": event_series.schedule_label(set(occ.weekdays)),
            }
        )
    return cards


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
    # Cap the one-offs only: recurring rows are already collapsed to one card
    # per series and get pulled out into the venue-grouped "Classes & ongoing"
    # section. Capping them here silently dropped every venue class card on
    # busy days (12+ one-offs filled the cap before any class survived).
    oneoffs = [it for it in collapsed if not it["recurring"]]
    recurring = [it for it in collapsed if it["recurring"]]
    return oneoffs[:limit] + recurring, len(collapsed)


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
        # One-offs win ties so a festival beats a recurring class at the same
        # time; time-unknown rows sort after timed ones (never a fake 12 AM pick).
        ranked = sorted(
            rows, key=lambda e: (time_sort_key(e.start_time, e.end_time), bool(e.is_recurring))
        )
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

    start_at = datetime.combine(chosen.date, chosen.start_time or time(0, 0))
    time_bit = "" if _is_midnight_fallback(chosen) else _format_event_time_label(start_at)
    sub_bits = [b for b in (time_bit, chosen.location_name) if b]
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
    {"label": "Lake Life", "url": "/lake-havasu/on-the-water"},
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
    # Phase 1 (home IA, PHASE1 brief §3): the live-conditions strip is trimmed to
    # the four highest-value, always-relevant signals — temp · UV · wind · gas —
    # so the band stays scannable. AQI, lake level, water temp and the advisory
    # tile were dropped from the strip; they are still surfaced on /today and in
    # the conditions JSON payload (honest omission, never fabricated values).
    "temp": ("weather", "🌡", "Now"),
    "uv": ("uv", "☀", "UV index"),
    "wind": ("wind", "🌬", "Wind"),
}

# Fixed strip order for the conditions tiles (gas is appended after these so the
# rendered band reads temp · UV · wind · gas · Live). A tile with no live source
# is simply skipped — the strip never invents a value.
_STRIP_TILE_ORDER: tuple[str, ...] = ("temp", "uv", "wind")


def _gas_chip(db: Session) -> dict[str, Any] | None:
    """The cheapest-gas chip (or None when there's no live gas data). Split out of
    the conditions strip so the home page can show weather at the top and gas as a
    separate line below it (P3 weather-widget grouping), while every other surface
    keeps gas inline in the shared conditions band."""
    gas = _gas_snapshot(db)
    if not gas.get("has_data"):
        return None
    top = gas["cheapest"][0] if gas.get("cheapest") else {}
    price = top.get("prices", {}).get("regular") if isinstance(top, dict) else None
    if not isinstance(price, (int, float)):
        return None
    name = top.get("station_name") or top.get("name") or "Lowest station"
    return {
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


def _utility_chips(db: Session, *, include_gas: bool = True) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []

    # Conditions lead the strip in a fixed order (temp · UV · wind); each tile is
    # included only when its source has a live value.
    vm = build_conditions_strip_view_model(db)
    by_kind = {tile.kind: tile for tile in vm.tiles}
    for kind in _STRIP_TILE_ORDER:
        tile = by_kind.get(kind)
        if tile is None:
            continue
        chip_kind, icon, label = _UTILITY_TILE_MAP[kind]
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

    # Gas closes the strip — the figure people open the app for, with a tap-
    # through to the full gas list. The home page passes include_gas=False and
    # renders it as a separate line below the weather (P3); every other surface
    # keeps it inline here.
    if include_gas:
        gas_chip = _gas_chip(db)
        if gas_chip is not None:
            chips.append(gas_chip)

    return chips


def _gas_snapshot(db: Session) -> dict[str, object]:
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now_utc)
    if row is None or not isinstance(row.data, dict):
        return {"has_data": False}
    # Render the SAME pre-computed cheapest list the /gas page shows
    # (``data["cheapest"]``, built by app.contrib.gas_prices), NOT a fresh re-sort
    # of ``data["stations"]``. A re-sort can disagree with /gas — a station that
    # the pull excluded from ``cheapest`` (e.g. one missing a real regular price)
    # could surface as the home chip's "cheapest" while /gas showed a different,
    # higher figure (live: home $3.95 vs /gas $4.19). One source of truth = the
    # home chip and /gas always match.
    cheapest = [s for s in (row.data.get("cheapest") or []) if isinstance(s, dict)]
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
    date: str | None = None,
) -> HTMLResponse:
    """Render /home — the Sandstone editorial home (Ask mode).

    Every count/badge traces to a live query or is omitted (the anti-confabulation
    contract in 01_UI_BUILD_GUIDE.md §4). The optional ``cal=YYYY-MM`` param drives
    the server-rendered month calendar's prev/next without any client JS.

    The optional ``date=YYYY-MM-DD`` param (the home day-picker tiles, FIX_DAYPICKER
    item 4) re-renders the unified feed for that day on the SAME home page — no
    font/page jump, no stale "Happening today" heading. It defaults to today and
    only steers the feed + its date label; the 7-day strip stays today-anchored and
    highlights the selected tile. Past-item muting keys off the real clock vs the
    selected day (``today_feed``'s ``now`` no-ops off the current date), so a future
    day shows nothing muted.
    """
    now = now_lake_havasu()
    feed_day = _parse_iso_date(date) or now.date()
    # P3 weather grouping: the top conditions band shows weather only (date · temp
    # · UV · wind); gas renders as its own simple line below it on the home page.
    utility_chips = _utility_chips(db, include_gas=False)
    gas_chip = _gas_chip(db)
    cal_year, cal_month = sandstone.parse_cal_param(cal, default=now)
    spotlights = sponsor_store.active_spotlights(db)
    # G ad ladder: Tier-1 marquee (above the fold) + Tier-3 promoted (after the
    # Explore grid). Both real-or-omit — None when unsold, never a fake sponsor.
    # §7.1: a sold homepage rotating PLACEMENT wins the marquee; otherwise fall
    # back to the legacy sponsor marquee, then the unsold claim. Dormant until a
    # placement exists — serve_homepage_placement returns None on an empty pool.
    marquee = serving.serve_homepage_placement(db) or sponsor_store.active_marquee(db)
    # Phase 6C: the home Featured (Tier-2) + Promoted (Tier-3) slots now run on the
    # SAME Placement homepage-rotating pool as the marquee, drawing DISTINCT
    # businesses per load (each slot excludes the ids the higher slots took). Each
    # falls back to its legacy sponsor when the pool has nothing left, so the home
    # page stays dormant-safe — an empty pool means today's behavior.
    taken: set[str] = set()
    if marquee and marquee.get("is_placement") and marquee.get("id"):
        taken.add(marquee["id"])
    featured_placement = serving.serve_homepage_featured(db, exclude_ids=taken, limit=3)
    if featured_placement:
        featured_cards = featured_placement
        taken.update(c["id"] for c in featured_placement if c.get("id"))
    else:
        featured_cards = sandstone.featured_cards(spotlights)
    promoted = serving.serve_homepage_promoted(db, exclude_ids=taken) or sponsor_store.active_promoted(db)
    # Hero copy defaults to the locked prototype wording (with its italic accent);
    # owners can retune the eyebrow/headline per season via env without a redeploy.
    hero_eyebrow_override = os.getenv("HOME_HERO_EYEBROW") or None
    hero_headline_override = os.getenv("HOME_HERO_HEADLINE") or None
    # THEME flag (Lake Ink & Brass, Phase 1): the lake home reskins the SAME
    # real context into the v10 layout. Default stays desert until the flip.
    template_name = (
        "home_lake.html"
        if getattr(request.state, "theme", "desert") == "lake"
        else "home_sandstone.html"
    )
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "hero_eyebrow_override": hero_eyebrow_override,
            "hero_headline_override": hero_headline_override,
            "utility_chips": utility_chips,
            "gas_chip": gas_chip,
            "primary_nav": sandstone.primary_nav(),
            "mega_columns": sandstone.mega_columns(db),
            "week": sandstone.week_strip(db, today=now.date()),
            # The home feed now renders the SAME organized day-group structure as
            # /events-ui (typed subsections, Kids & Family / Seniors / City &
            # Government groups, clean venue labels) for the selected day, so the
            # two calendars are consistent (Casey 2026-06-23). ``now`` stays the
            # real clock for today's auto-expiry.
            "today_groups": events_views.day_groups(db, day=feed_day, now=now),
            "today_highlights": events_views.day_highlights(db, day=now.date(), now=now, limit=3),
            # ``today_feed`` is still computed for its collapsed "At the movies"
            # group (the per-film showtime rollup), which the day-group view does
            # not build; the home template renders only that group from it.
            "today_feed": today_feed(db, day=feed_day, now=now),
            # FIX_DAYPICKER item 4: the feed's small date label ("Saturday,
            # June 20") + the iso the day-picker highlights as selected.
            "feed_day_label": _long_day_label(feed_day),
            "selected_iso": feed_day.isoformat(),
            "marquee": marquee,
            "promoted": promoted,
            "featured_cards": featured_cards,
            "calendar": sandstone.calendar_month(
                db, year=cal_year, month=cal_month, today=now.date()
            ),
            "explore_tiles": sandstone.explore_tiles(db),
            "service_tiles": sandstone.service_tiles(db),
            # Phase 3: the slim home directory's six high-traffic front doors.
            "directory_tiles": sandstone.directory_primary_tiles(),
            "movies_today": movies_today(db, day=now.date()),
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


# C11: the curated "/lake" mode landing and the "Lake Life" directory category
# (``/categories/on-the-water``) were two pages for the same thing. Merged into
# one: ``/lake`` now permanently redirects to the canonical Lake Life category,
# so the inbound URL keeps working while there is a single surface. (Night/Family
# keep their mode landings.)
LAKE_LIFE_CATEGORY_URL = "/categories/on-the-water"


@router.get("/lake", response_class=HTMLResponse, response_model=None)
def serve_lake(request: Request) -> RedirectResponse:
    """Permanent redirect: /lake → the Lake Life category (merged surfaces)."""
    return RedirectResponse(url=LAKE_LIFE_CATEGORY_URL, status_code=301)


@router.get("/ask", response_class=HTMLResponse, response_model=None)
def serve_ask(request: Request) -> RedirectResponse:
    """1.2: ``/ask`` is the marketing/nav alias for the chat surface. 302 (not
    301) to ``/chat`` so the redirect is never cached — the chat entry point can
    move without a stale permanent redirect pinning ``/ask`` to the old path."""
    return RedirectResponse(url="/chat", status_code=302)


@router.get("/night", response_class=HTMLResponse)
def serve_night(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Night mode landing (fires the dark transformation)."""
    return _serve_mode_landing(request, db, "night")


@router.get("/family", response_class=HTMLResponse)
def serve_family(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Family mode landing."""
    return _serve_mode_landing(request, db, "family")


# Phase 3.2 label unification: the /map scope tabs now read their labels from the
# canonical department source (app.categories.display_labels.map_scope_label), so
# a category reads identically on /map, the directory, and the home grid (the live
# drift was "Lake Life"/"Outdoors & Recreation" on /map vs "Lake & Boating"/"Things
# to Do" in the directory). The scope SLUGS are unchanged, so /api/map_data/{scope}
# and map.js are untouched — only the displayed strings move to one source.


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
        {
            "slug": slug,
            "label": map_scope_label(slug),
        }
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
    _lake = getattr(request.state, "theme", "desert") == "lake"
    return templates.TemplateResponse(
        request=request,
        name="map_c_lake.html" if _lake else "map_c.html",
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
    """Honest, contiguous, gap-free buckets for event windows (E-1).

    The /events-ui page now renders Today/Week/Month views (see
    ``serve_events_ui``); these windows remain the canonical bucket contract
    for window-feed consumers and their regression tests.

    Anchored to real calendar-week boundaries in Lake Havasu local time:

    * **today**     — today only.
    * **this_week** — tomorrow through Friday of the current week.
    * **weekend**   — the upcoming Saturday + Sunday. When today is already
      Sat/Sun, today's events stay in **today** and this window holds only the
      remaining weekend day(s) (empty span on Sunday).
    * **next_week** — the following Monday–Sunday.

    Windows are disjoint and together tile every day from today through the end
    of next week, so no event is dropped or double-listed — in particular,
    Saturday/Sunday events can never fall in a gap between "This Week" and
    "Next Week". A collapsed window (start > end) simply queries nothing.
    """
    days_to_sunday = (6 - now.weekday()) % 7  # Mon=0 … Sun=6
    this_sunday = now + timedelta(days=days_to_sunday)
    this_saturday = this_sunday - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    return {
        "today": (now, now),
        "this_week": (tomorrow, this_saturday - timedelta(days=1)),
        "weekend": (max(tomorrow, this_saturday), this_sunday),
        "next_week": (this_sunday + timedelta(days=1), this_sunday + timedelta(days=7)),
    }


_WINDOW_CAP = 16


def _parse_iso_date(value: str | None) -> dt_date | None:
    if not value or not str(value).strip():
        return None
    try:
        return dt_date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


_EVENT_VIEWS: tuple[tuple[str, str], ...] = (
    ("today", "Today"),
    ("week", "Week"),
    ("month", "Month"),
)


def _long_day_label(d: dt_date) -> str:
    return d.strftime("%A, %B ") + str(d.day)


@router.get("/events-ui", response_class=HTMLResponse)
def serve_events_ui(
    request: Request,
    db: Session = Depends(get_db),
    when: str | None = None,
    date: str | None = None,
    view: str | None = None,
    cal: str | None = None,
    family: str | None = None,
    seniors: str | None = None,
) -> HTMLResponse:
    """Render the Sandstone events page — three zoom levels of one concept.

    * default — TODAY: a category accordion (Events / Music & nightlife / On
      the water / Fitness & classes) for the current lake-local date.
    * ``?view=week`` — 7 rows from today: top one-off headline + an honest
      per-group rollup; each row links to its day.
    * ``?view=month`` — a compact date-picker grid (one-off counts + a class
      badge; ``?cal=YYYY-MM`` pages it, same param as /home).
    * ``?date=YYYY-MM-DD`` (the home-calendar day links) — the same accordion
      for that date, with prev/next-day and back-to-today links.
    * ``?when=`` is legacy (the old bucket chips) and still answers: ``today``
      maps to the Today view; ``weekend``/``this-week``/``next-week``/``all``
      map to the Week view, which tiles every upcoming day gap-free.
    """
    now = now_lake_havasu()
    today = now.date()
    single_day = _parse_iso_date(date)

    view_key = (view or "").strip().lower()
    if view_key not in {key for key, _label in _EVENT_VIEWS}:
        when_key = (when or "").strip().lower()
        view_key = "today" if when_key in ("", "today") else "week"

    # Audience narrows (?family=1 / ?seniors=1) — kid/family or senior
    # occurrences only, across all three zoom levels. Mutually exclusive (family
    # wins if both). ``family_qs`` carries the ACTIVE audience on every intra-
    # page link so the narrow survives day paging, view switches, and month
    # paging (name kept for the desert template; value is whichever is on).
    _TRUE = ("1", "true", "yes", "on")
    family_on = (family or "").strip().lower() in _TRUE
    seniors_on = (seniors or "").strip().lower() in _TRUE and not family_on
    aud = "family" if family_on else ("seniors" if seniors_on else "")
    family_qs = f"&{aud}=1" if aud else ""

    def _view_url(key: str) -> str:
        base = "/events-ui" if key == "today" else f"/events-ui?view={key}"
        if not aud:
            return base
        return base + (f"?{aud}=1" if "?" not in base else f"&{aud}=1")

    def _toggle_url(target: str) -> str:
        """Current page URL with the ``target`` audience flipped (the toggle's
        href). Turning one audience on clears the other (mutually exclusive)."""
        params: list[str] = []
        if single_day is not None:
            params.append(f"date={single_day.isoformat()}")
        elif view_key == "week":
            params.append("view=week")
        elif view_key == "month":
            params.append("view=month")
            if cal:
                params.append(f"cal={cal}")
        if aud != target:  # not already this audience → turn it on (clears other)
            params.append(f"{target}=1")
        return "/events-ui" + ("?" + "&".join(params) if params else "")

    context: dict[str, Any] = {
        "active_tab": "events",
        "primary_nav": sandstone.primary_nav(),
        "mega_columns": sandstone.mega_columns(db),
        "utility_chips": _utility_chips(db),
        "family_mode": family_on,
        "seniors_mode": seniors_on,
        "family_qs": family_qs,
        "family_toggle_url": _toggle_url("family"),
        "seniors_toggle_url": _toggle_url("seniors"),
        "view_links": [
            {
                "key": key,
                "label": label,
                "url": _view_url(key),
                "active": single_day is None and key == view_key,
            }
            for key, label in _EVENT_VIEWS
        ],
    }

    if single_day is not None:
        context.update(
            {
                "mode": "day",
                "groups": events_views.day_groups(
                    db, day=single_day, family=family_on, seniors=seniors_on, now=now
                ),
                "day_label": _long_day_label(single_day),
                "prev_iso": (single_day - timedelta(days=1)).isoformat(),
                "next_iso": (single_day + timedelta(days=1)).isoformat(),
                "is_today": single_day == today,
                "movies_today": movies_today(db, day=single_day),
            }
        )
    elif view_key == "week":
        context.update(
            {
                "mode": "week",
                "week_rows": events_views.week_rows(
                    db, start=today, family=family_on, seniors=seniors_on
                ),
                # Item 3: consecutive weeks for the mobile swipeable calendar
                # (lake template renders these as a swipe carousel; the desert
                # template ignores it and keeps the flat week list).
                "swipe_weeks": events_views.swipe_weeks(
                    db, today=today, family=family_on, seniors=seniors_on
                ),
            }
        )
    elif view_key == "month":
        cal_year, cal_month = sandstone.parse_cal_param(cal, default=now)
        context.update(
            {
                "mode": "month",
                "calendar": sandstone.calendar_month(
                    db, year=cal_year, month=cal_month, today=today,
                    family=family_on, seniors=seniors_on,
                ),
                # Mobile falls back to the swipeable week here too (a month grid
                # is unreadable on a phone); desktop keeps the visible grid.
                "swipe_weeks": events_views.swipe_weeks(
                    db, today=today, family=family_on, seniors=seniors_on
                ),
            }
        )
    else:
        context.update(
            {
                "mode": "today",
                "groups": events_views.day_groups(
                    db, day=today, family=family_on, seniors=seniors_on, now=now
                ),
                "day_label": _long_day_label(today),
                "movies_today": movies_today(db, day=today),
            }
        )
    # THEME flag (Lake Ink & Brass, Phase 2): the lake events surface reskins
    # the SAME real context. Default stays desert until the flip.
    events_template = (
        "events_lake.html"
        if getattr(request.state, "theme", "desert") == "lake"
        else "events_sandstone.html"
    )
    return templates.TemplateResponse(
        request=request, name=events_template, context=context
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
    _lake = getattr(request.state, "theme", "desert") == "lake"
    return templates.TemplateResponse(
        request=request,
        name="collection_landing_lake.html" if _lake else "collection_landing.html",
        context={
            "collection": collection,
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "active_tab": "explore",
        },
    )


@router.get("/sponsor", response_class=HTMLResponse, response_model=None)
def sponsor_landing(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Public advertiser storefront (/sponsor). Shows the rate card (prices from
    config, never hardcoded) and routes to the real self-serve buy flow. The
    category "Advertise" CTAs land here, so the purchase path is public up front;
    payment itself is login + claim gated downstream.
    """
    _lake = getattr(request.state, "theme", "desert") == "lake"
    from app.portal.products import storefront_offers

    return templates.TemplateResponse(
        request=request,
        name="sponsor_landing_lake.html" if _lake else "sponsor_landing.html",
        context={"offers": storefront_offers(db)},
    )
