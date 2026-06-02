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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.analytics import record_event
from app.categories import queries as cat_queries
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.conditions.view_model import build_conditions_strip_view_model
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import limiter
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import AdSlot, Event, Sponsor
from app.events import series as event_series
from app.home import pullquote, queries_c, sponsor_store
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


def _hero_context() -> dict[str, Any]:
    url = (os.getenv("HOME_HERO_IMAGE_URL") or "").strip() or _DEFAULT_HERO_ASSET
    credit = (os.getenv("HOME_HERO_CREDIT") or "").strip()
    credit_url = (os.getenv("HOME_HERO_CREDIT_URL") or "").strip()
    attribution = (
        {"photographer": credit, "profile_url": credit_url} if credit and credit_url else None
    )
    return {"url": url, "attribution": attribution}


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


def _events_for_window(
    db: Session, *, start_day: datetime, end_day: datetime, limit: int
) -> list[dict[str, str]]:
    """Events in the window, with recurring series collapsed to one entry.

    A class that occurs every weekday (28 separate rows for "Lap Swim") would
    otherwise flood the feed and bury one-off events. We detect series by their
    natural key and emit each once — anchored on its next occurrence in the
    window, tagged ``recurring`` with a human ``schedule_label`` (brief §4).
    """
    rows = (
        db.query(Event)
        .filter(
            Event.status == "live",
            Event.date >= start_day.date(),
            Event.date <= end_day.date(),
        )
        .order_by(Event.featured.desc(), Event.date.asc(), Event.start_time.asc())
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
                continue  # one card per series — this is the next occurrence
            seen_series.add(key)
        start_at = datetime.combine(ev.date, ev.start_time)
        category_label, accent = _event_accent(ev.tags)
        items.append(
            {
                "id": ev.id,
                "title": ev.title,
                "venue": ev.location_name,
                "url": f"/events/{ev.id}",
                "time_label": _format_event_time_label(start_at),
                "day_label": start_at.strftime("%a"),
                "date_label": str(start_at.day),
                "month_label": start_at.strftime("%b"),
                "image_url": None,
                "featured": bool(ev.featured),
                "category_label": category_label,
                "accent_color": accent,
                "recurring": recurring,
                "schedule_label": event_series.schedule_label(info.weekdays) if recurring else "",
            }
        )
        if len(items) >= limit:
            break
    return items


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
# detail on tap (template uses <details>). NOTE: the brief also lists UV index and
# a sky/condition description — neither is currently fetched by the conditions
# pipeline (NWS-current gives temp/heat-index/wind only), so they are omitted
# rather than faked. Flagged for a future ingestion add.
_UTILITY_TILE_MAP: dict[str, tuple[str, str, str]] = {
    # conditions-tile kind -> (chip kind, icon, label)
    "temp": ("weather", "🌡", "Now"),
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
    label, stale = staleness_label(row.fetched_at, now_utc)
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
) -> HTMLResponse:
    """Render /home — Lake Light editorial home."""
    now = now_lake_havasu()
    hero = _hero_context()
    discover_cards = queries_c.discover_grid(db, now=now)
    eat_cards = queries_c.eat_row(db, now=now)
    service_cards = queries_c.services_grid(db)
    upcoming = _events_for_window(
        db,
        start_day=now,
        end_day=now + timedelta(days=7),
        limit=12,
    )
    utility_chips = _utility_chips(db)
    categories = _category_cards(db)
    spotlight = discover_cards[0] if discover_cards else None
    return templates.TemplateResponse(
        request=request,
        name="home_c.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "hero_image_url": hero["url"],
            "hero_attribution": hero["attribution"],
            "discover_cards": discover_cards,
            "eat_cards": eat_cards,
            "service_cards": service_cards,
            "events_soon": upcoming,
            "utility_chips": utility_chips,
            "category_cards": categories,
            "home_services_shortcut": _HOME_SERVICES_SHORTCUT,
            "popular_subcategories": _POPULAR_SUBCATEGORIES,
            "spotlight_card": spotlight,
            "active_tab": "today",
            "hava_read": pullquote.get_quote(db),
        },
    )


@router.get("/events-ui", response_class=HTMLResponse)
def serve_events_ui(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Render Lake Light events list/calendar shell (data via /api/events)."""
    now = now_lake_havasu()
    groups = {
        "today": _events_for_window(db, start_day=now, end_day=now, limit=12),
        "weekend": _events_for_window(
            db, start_day=now + timedelta(days=1), end_day=now + timedelta(days=3), limit=12
        ),
        "next_week": _events_for_window(
            db, start_day=now + timedelta(days=4), end_day=now + timedelta(days=10), limit=16
        ),
    }
    total = sum(len(v) for v in groups.values())
    return templates.TemplateResponse(
        request=request,
        name="events_lake_light.html",
        context={
            "events_groups": groups,
            "events_total": total,
            "month_label": now.strftime("%B %Y"),
            "active_tab": "events",
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
