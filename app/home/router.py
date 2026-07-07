"""Hava -- ``GET /home`` route (Direction C / ``home_c.html``).

Also hosts the sponsor attribution endpoints (v52 P0):

* ``GET /sponsor/click`` — bumps ``Sponsor.clicks`` and 302s to the row's
  ``cta_url``. Linked from ``_partials/marquee.html``. Without this route,
  every marquee CTA 404s.
* ``GET /sponsor`` — advertiser landing stub. Linked from the marquee unsold
  fallback and from the home/category footers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.analytics import record_event
from app.categories.display_labels import map_scope_label
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.conditions.view_model import build_conditions_strip_view_model
from app.core.rate_limit import limiter
from app.core.templates import make_templates
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import AdSlot, Provider, Sponsor
from app.gas.service import board_from_cache
from app.groups.themed_groups import group_label
from app.home import collections as curated_collections
from app.home import events_views, redesign, sandstone, sponsor_store
from app.monetization import serving
from app.news import store as news_store

templates = make_templates()

router = APIRouter(tags=["home"])

# (The pre-v4 home builders — hero config, window feeds, tonight card,
# category cards, series collapse — were deleted 2026-07-02: no route or
# template consumed them after the Sandstone/v4 homes; only their own tests
# kept them green. The live event surfaces are events_views/sandstone/
# redesign.)

_UTILITY_TILE_MAP: dict[str, tuple[str, str, str]] = {
    # conditions-tile kind -> (chip kind, icon, label)
    # Phase 1 (home IA, PHASE1 brief §3): the live-conditions strip is trimmed to
    # the highest-value, always-relevant signals so the band stays scannable.
    # AQI, lake level and the advisory tile are surfaced on /today and in the
    # conditions JSON payload rather than the strip (honest omission, never
    # fabricated values). Water temp was re-added to the strip at Casey's request
    # (2026-06-29): it only renders when its water-temp feed is live, so the band
    # degrades to temp · UV · wind when the reading is absent — never a
    # fabricated value.
    "temp": ("weather", "🌡", "Now"),
    "uv": ("uv", "☀", "UV index"),
    "wind": ("wind", "🌬", "Wind"),
    "water_temp": ("water_temp", "🌊", "Water"),
}

# Fixed strip order for the conditions tiles (gas is appended after these so the
# rendered band reads temp · UV · wind · water · gas · Live). A tile with no live
# source is simply skipped — the strip never invents a value.
_STRIP_TILE_ORDER: tuple[str, ...] = ("temp", "uv", "wind", "water_temp")


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
    """Cheapest-gas snapshot for the conditions strip, from the single GasBoard
    (v4.4 PR-1). The board is the ONE source the strip tile, home panel and /gas
    page all derive from, so a re-sort can never surface a figure that disagrees
    with /gas (the live home $3.95 vs /gas $4.19 split). ``read_source`` stays
    this module's own seam so its unit tests keep patching here."""
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    board = board_from_cache(read_source(db, SOURCE_GAS, now=now_utc), now=now_utc)
    cheapest = [
        {"name": s.name, "station_name": s.name, "prices": {"regular": s.prices.get("reg")}}
        for s in board.cheapest("reg")
    ]
    return {
        "has_data": bool(cheapest),
        "staleness_label": board.label,
        "is_stale": board.is_stale,
        "cheapest": cheapest,
    }


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
    cal: str | None = None,
    date: str | None = None,
) -> HTMLResponse:
    """Render /home — the v4 home (Ask mode).

    Every count/badge traces to a live query or is omitted (the anti-confabulation
    contract in 01_UI_BUILD_GUIDE.md §4).

    The optional ``date=YYYY-MM-DD`` param (the home day-picker tiles, FIX_DAYPICKER
    item 4) re-renders the unified feed for that day on the SAME home page — no
    font/page jump, no stale "Happening today" heading. It defaults to today and
    only steers the feed + its date label; the 7-day strip stays today-anchored and
    highlights the selected tile.

    2026-07-02 flag collapse: v4 (HOME_REDESIGN) had been permanently on in prod
    since ~06-23, so the flag, the ?home_redesign= preview override, and the
    pre-v4 ``home_lake.html`` branch (with its own conditions strip, month
    calendar, and Featured slot) are gone. ``cal`` is accepted-and-ignored so
    old bookmarked ?cal= links don't 422.

    The Tier-2 Featured/Spotlight sponsor slot has no v4 surface, so it is not
    fetched (fetching counts an impression — impressions must equal renders).
    A SOLD homepage-featured Placement is therefore not served; wiring a
    Featured slot into home_redesign.html is a design decision.
    """
    del cal  # pre-v4 month-calendar param; accepted so old links don't 422
    now = now_lake_havasu()
    feed_day = _parse_iso_date(date) or now.date()
    # G ad ladder: Tier-1 marquee (above the fold) + Tier-3 promoted (after the
    # Explore grid). Both real-or-omit — None when unsold, never a fake sponsor.
    # §7.1: a sold homepage rotating PLACEMENT wins the marquee; otherwise fall
    # back to the legacy sponsor marquee, then the unsold claim. Dormant until a
    # placement exists — serve_homepage_placement returns None on an empty pool.
    marquee = serving.serve_homepage_placement(db) or sponsor_store.active_marquee(db)
    taken: set[str] = set()
    if marquee and marquee.get("is_placement") and marquee.get("id"):
        taken.add(marquee["id"])
    promoted = serving.serve_homepage_promoted(db, exclude_ids=taken) or sponsor_store.active_promoted(db)
    return templates.TemplateResponse(
        request=request,
        name="home_redesign.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "selected_iso": feed_day.isoformat(),
            "feed_day_label": _long_day_label(feed_day),
            "is_today": feed_day == now.date(),
            "cond_tiles": redesign.conditions_tiles(db, now=now),
            "gas": redesign.gas_panel_data(db, now=now),
            "week": sandstone.week_strip(db, today=now.date(), selected=feed_day),
            "feed": redesign.feed_view_model(db, day=feed_day, now=now),
            # (F6 2026-07-01: the headline now reads feed.total — the same
            # number as the "All today" pill on the same screen — so the
            # separate real_happenings_by_day headline count is gone.)
            "marquee": marquee,
            "promoted": promoted,
            # (directory_tiles / explore_tiles were dropped 2026-07-02: no v4
            # template renders them — they were pre-v4 context computed per
            # request, incl. DB queries, for nothing.)
            # Local news — one pull feeds both the mobile ticker and the desktop
            # rail news card (honest-omit when the pull is empty).
            "news": news_store.ticker_view(db),
            # v4.4 PR-5 rail: Find-any-business launcher (live directory counts).
            "directory": redesign.directory_launcher(db),
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
    # v4.5 PR-5: the Family / Night landings wear the standalone v4 shell
    # (base_redesign) — the live-conditions strip + cheapest-gas panel like every
    # other discovery page, instead of the retired desert mode-hero.
    from app.home import redesign

    now = now_lake_havasu()
    context: dict[str, object] = {
        "utility_chips": _utility_chips(db),
        "current_mode": mode,
        "cond_tiles": redesign.conditions_tiles(db, now=now),
        "gas": redesign.gas_panel_data(db, now=now),
        "active_tab": "family" if mode == "family" else None,
        **landing,
    }
    # WS10: /night gets a real "Late-night kitchens" list (Eat & Drink venues open
    # past 10 PM, from published hours) in place of the old chat deep-link tile.
    if mode == "night":
        context["late_kitchens"] = redesign.late_night_kitchens(db)
    return templates.TemplateResponse(
        request=request,
        name="mode_redesign.html",
        context=context,
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


@router.get("/kids", response_model=None)
def serve_kids_redirect() -> RedirectResponse:
    """The nav and old links say /kids; the surface lives at /family
    (2026-07-01 master audit §6.5: /kids 404'd)."""
    return RedirectResponse(url="/family", status_code=301)


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
    return templates.TemplateResponse(
        request=request,
        name="map_c_lake.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "group_scopes": group_scopes,
            "category_scopes": category_scopes,
            "default_scope": default_scope,
            "active_tab": "map",
        },
    )


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


def _short_day_label(d: dt_date) -> str:
    """Abbreviated day label for the day-view pager ("Sun Jul 6"). ``str(d.day)``
    avoids the non-portable ``%-d`` (Windows strftime lacks it)."""
    return d.strftime("%a %b ") + str(d.day)




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
    # UNIFY (Rule 0b 2026-06-26): the ?view=places surface is retired — one calendar
    # now shows the full tree (hours + classes inline, collapsed). A legacy
    # ?view=places link falls through to Today like any other unknown view.
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

    # UNIFY (Rule 0b 2026-06-26): one calendar, no Calendar⇄Places toggle. Just the
    # Today/Week/Month zoom levels over the single unified tree.
    context: dict[str, Any] = {
        "active_tab": "events",
        # v4.5 PR-1: /events-ui wears the v4 shell (base_redesign) — the cond-tile
        # strip + gas panel like home/calendar, not the old utility ribbon.
        "today_label": now.strftime("%A, %B ") + str(now.day),
        "cond_tiles": redesign.conditions_tiles(db, now=now),
        "gas": redesign.gas_panel_data(db, now=now),
        "family_mode": family_on,
        "seniors_mode": seniors_on,
        "family_qs": family_qs,
        "family_toggle_url": _toggle_url("family"),
        "seniors_toggle_url": _toggle_url("seniors"),
        # Calendar zoom levels (Today/Week/Month).
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
                "groups": events_views.calendar_day_view_model(
                    db, day=single_day, family=family_on, seniors=seniors_on, now=now
                )["sections"],
                "day_label": _long_day_label(single_day),
                "prev_iso": (single_day - timedelta(days=1)).isoformat(),
                "next_iso": (single_day + timedelta(days=1)).isoformat(),
                # Readable pager labels (spec §7.2: "‹ Sun Jul 5 / Tue Jul 7 ›"),
                # not a bare arrow — the day you'll land on is visible + announced.
                "prev_label": _short_day_label(single_day - timedelta(days=1)),
                "next_label": _short_day_label(single_day + timedelta(days=1)),
                "is_today": single_day == today,
            }
        )
    elif view_key == "week":
        context.update(
            {
                "mode": "week",
                "week_rows": events_views.week_rows(
                    db, start=today, family=family_on, seniors=seniors_on, events_only=True
                ),
                # Item 3: consecutive weeks for the mobile swipeable calendar
                # (lake template renders these as a swipe carousel; the desert
                # template ignores it and keeps the flat week list).
                "swipe_weeks": events_views.swipe_weeks(
                    db, today=today, family=family_on, seniors=seniors_on, events_only=True
                ),
            }
        )
    elif view_key == "month":
        cal_year, cal_month = sandstone.parse_cal_param(cal, default=now)
        context.update(
            {
                "mode": "month",
                "month_label": dt_date(cal_year, cal_month, 1).strftime("%B %Y"),
                "calendar": sandstone.calendar_month(
                    db, year=cal_year, month=cal_month, today=today,
                    family=family_on, seniors=seniors_on,
                ),
                # Mobile falls back to the swipeable week here too (a month grid
                # is unreadable on a phone); desktop keeps the visible grid.
                "swipe_weeks": events_views.swipe_weeks(
                    db, today=today, family=family_on, seniors=seniors_on, events_only=True
                ),
            }
        )
    else:
        context.update(
            {
                "mode": "today",
                "groups": events_views.calendar_day_view_model(
                    db, day=today, family=family_on, seniors=seniors_on, now=now
                )["sections"],
                "day_label": _long_day_label(today),
            }
        )
    events_template = "events_redesign.html"
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
        sponsor_store.live_filter_for_slot(db.query(Sponsor), ad_slot)
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
        name="collection_landing_lake.html",
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
    from app.portal.products import storefront_offers

    return templates.TemplateResponse(
        request=request,
        name="sponsor_landing_lake.html",
        context={"offers": storefront_offers(db)},
    )
