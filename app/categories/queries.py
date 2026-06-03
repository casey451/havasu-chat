"""Direction C category-page queries -- filtered Provider lists per slug.

PR D5: powers ``/categories/{slug}``. Builds on D2/D3/D4's pattern: read
``Provider`` rows whose legacy ``category`` string is in the route's
slug set, hydrate with live ``_hours_status``, and return a uniform
card list shaped for the category grid partial.

Two-tier route model:
- **Mega-tab routes** aggregate multiple legacy slugs.
- **Tile routes** filter on one slug (or a small semantic group).

Both shapes return the same card dict so the template doesn't branch.

No-zero discipline (BUILD.md): when a route matches 0 providers, the
function returns an empty list. The template renders an editorial empty
state rather than "0 listed". Sort is rating desc with NULLs last,
matching D3's eat row.

Never raises: a DB outage or schema drift returns an empty list rather
than 500 the category page.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.db.models import Provider
from app.home.queries import _hours_status, _provider_image_url
from app.home.queries_c import _load_eat_photos, _rating_display, _rating_sort_key
from app.providers.queries import (
    _parse_hours_time,
    effective_hours_structured,
    is_open_now,
)

_CATEGORY_PHOTOS_PATH = Path(__file__).resolve().parent / "curated_category_photos.json"

# ---------------------------------------------------------------------------
# Route -> Provider.category filter mapping
# ---------------------------------------------------------------------------
#
# Source of truth for which legacy ``Provider.category`` strings each
# route surface includes. Keys here are the URL path segments that the
# D1 tab anchors and D4 service tiles point at; values are tuples of
# legacy slug strings drawn from ``LEGACY_PROVIDER_CATEGORY_LABELS``
# (see ``app/home/queries.py``).
#
# Editing rule: add a new route by adding a new key. Add new legacy
# slugs to an existing route by extending its tuple. Never share a
# slug string between two routes silently if both surface providers
# (it's fine for ``lodging`` to appear in both ``on-the-water`` and
# ``lodging-vacation-rentals`` -- that's an editorial cross-listing,
# not an error).

CATEGORY_FILTERS: dict[str, tuple[str, ...]] = {
    # -- Mega-tab routes (aggregations) --
    "eat-drink": (
        "food_drink",
        "food",
        "restaurant",
        "bakery",
    ),
    "on-the-water": (
        "lake_recreation",
        "boat_repair",
        "boat_rental",
        "lodging",
    ),
    # "Things to Do & Attractions" is attractions/tourism only. The fitness,
    # childcare/education, recreation, and religion/civic types it used to also
    # pull in have their own canonical homes (classes-sports-recreation,
    # public-civic-resources), so a church or gym no longer appears under BOTH
    # this route and Community/Sports (audit S2/P-4 cross-listing). This also
    # aligns the page with its own [Attractions, Venues] chips.
    "things-to-do": (
        "entertainment_attractions",
        "tourism",
    ),
    "services": (
        "home_services",
        "professional_services",
        "auto",
        "beauty_personal_care",
        "retail",
        "health_medical",
        "pets",
        "general_contractor",
        "plumbing",
    ),
    # -- D4 tile routes (specific) --
    "health-wellness-care": (
        "health_medical",
        "fitness",
        "fitness_sports",
    ),
    "home-property-services": (
        "home_services",
        "general_contractor",
        "plumbing",
        "services",
    ),
    "shopping-essentials": ("retail",),
    "professional": (
        "professional_services",
        "real_estate",
        "insurance",
        "financial",
        "legal",
    ),
    "beauty-care": ("beauty_personal_care",),
    "auto-rv-fuel": ("auto",),
    "public-civic-resources": ("religion_community",),
    "classes-sports-recreation": (
        "fitness_sports",
        "childcare_education",
        "education",
        "edu",
        "recreation",
    ),
    "attractions": (
        "entertainment_attractions",
        "tourism",
    ),
    "lodging-vacation-rentals": ("lodging",),
    "pets": (
        "pets",
        "pet",
        "veterinary",
    ),
}


# ---------------------------------------------------------------------------
# Editorial copy per route (label + one-liner)
# ---------------------------------------------------------------------------
#
# Labels are sentence-case (matching D4 tile names where they overlap).
# One-liners are short -- one sentence, locals voice, no question marks
# unless asking one. Headers on category pages are utility surfaces;
# the cinematic editorial copy is reserved for /home's hero.

CATEGORY_DISPLAY: dict[str, tuple[str, str]] = {
    # -- Mega-tabs --
    "eat-drink": (
        "Eat & drink",
        "Restaurants, bars, cafes. Open right now or coming up.",
    ),
    "on-the-water": (
        "On the water",
        "Marinas, rentals, lake stays. Everything within shouting distance of the channel.",
    ),
    "things-to-do": (
        "Things to do",
        "Classes, attractions, community. What to do tonight or this weekend.",
    ),
    "services": (
        "Services",
        "Plumbers, contractors, salons, vets, lawyers. Who to call when something needs doing.",
    ),
    # -- Tile routes --
    "health-wellness-care": (
        "Health & wellness",
        "Doctors, dentists, gyms, yoga. Local care and well-being.",
    ),
    "home-property-services": (
        "Home & property",
        "Plumbing, HVAC, contractors, landscaping. The trade pros.",
    ),
    "shopping-essentials": (
        "Shopping",
        "Grocery, retail, specialty shops.",
    ),
    "professional": (
        "Professional",
        "Real estate, legal, financial, insurance.",
    ),
    "beauty-care": (
        "Beauty & care",
        "Salons, barbers, spas.",
    ),
    "auto-rv-fuel": (
        "Auto, RV & fuel",
        "Mechanics, RV repair, gas, tires.",
    ),
    "public-civic-resources": (
        "Community",
        "Civic orgs, places of worship, public resources.",
    ),
    "classes-sports-recreation": (
        "Fitness & sports",
        "Studios, leagues, classes, childcare.",
    ),
    "attractions": (
        "Attractions",
        "Museums, parks, lake attractions.",
    ),
    "lodging-vacation-rentals": (
        "Lodging",
        "Hotels, resorts, vacation rentals.",
    ),
    "pets": (
        "Pets",
        "Vets, groomers, supplies.",
    ),
}


# ---------------------------------------------------------------------------
# Tab navigation -- which mega-tab is "active" for a given route
# ---------------------------------------------------------------------------
#
# Each category route maps to one of five tab slugs. The home page uses
# ``today`` (no slug); category pages use the mega-tab they belong to.
# Tile routes that don't belong to a mega-tab map to the closest one.

_TAB_FOR_ROUTE: dict[str, str] = {
    # Mega-tabs map to themselves.
    "eat-drink": "eat-drink",
    "on-the-water": "on-the-water",
    "things-to-do": "things-to-do",
    "services": "services",
    # Tile routes map to their semantic mega-tab.
    "health-wellness-care": "services",
    "home-property-services": "services",
    "shopping-essentials": "services",
    "professional": "services",
    "beauty-care": "services",
    "auto-rv-fuel": "services",
    "public-civic-resources": "services",
    "classes-sports-recreation": "things-to-do",
    "attractions": "things-to-do",
    "lodging-vacation-rentals": "on-the-water",
    "pets": "services",
}


def active_tab_for(slug: str) -> str:
    """Return the mega-tab slug this route belongs to.

    Used by templates to apply the ``is-active`` class to the right tab
    in the shared topbar. Falls back to ``today`` (which makes no tab
    active visually) when the slug is unknown.
    """
    return _TAB_FOR_ROUTE.get(slug, "today")


def is_valid_category_slug(slug: str) -> bool:
    """Whether ``slug`` is a known category route.

    Trims and lowercases the input -- a defensive parse so the router's
    404 path doesn't depend on the exact casing of URL noise.
    """
    if not slug:
        return False
    return slug.strip().lower() in CATEGORY_FILTERS


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------
#
# Card shape (matches scroll_row.html / category_grid.html templates):
#
#   slug          Provider.slug; None means non-linking anchor
#   name          Provider.provider_name
#   image_url     curated Unsplash from curated_eat_photos.json or None
#   neighborhood  Provider.district or ""
#   status        "open" / "closing-soon" / "closed-soon" / "closed"
#   status_text   pill copy from _hours_status
#   rating        single-decimal string or None
#
# Photo coverage: ``curated_category_photos.json`` first, then curated eat
# photos, then ``_provider_image_url`` (which delegates to
# ``first_renderable_google_photo`` — ``google_photo_urls`` first, then
# upgraded raw refs from ``google_photo_refs``).

# Hard cap on how many Provider rows to pull per page before any
# in-Python filtering. Set large enough that even sparse categories
# (pets=37) render everything and dense ones (services aggregation
# could be 1k+) don't drag the page.
_DEFAULT_CARD_LIMIT = 60


@lru_cache(maxsize=1)
def _load_category_photos() -> dict[str, str]:
    """Read and cache the hand-picked category card photo map.

    Returns ``{slug: image_url}`` or ``{}`` on any file-read failure.
    """
    try:
        with _CATEGORY_PHOTOS_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    photos = data.get("photos") or {}
    if not isinstance(photos, dict):
        return {}
    return {str(k): str(v) for k, v in photos.items() if isinstance(v, str) and v}


def _resolve_category_card_image(provider: Provider) -> str | None:
    """Photo URL for a category card: curated override → eat row → Google."""
    slug = provider.slug
    if not slug:
        return _provider_image_url(provider)
    category_photos = _load_category_photos()
    if slug in category_photos:
        return category_photos[slug]
    eat_photos = _load_eat_photos()
    if slug in eat_photos:
        return eat_photos[slug]
    return _provider_image_url(provider)


def _card_subcategory_token(provider: Provider, allowed: set[str] | None) -> str:
    """The card's subtype token, blanked when off-taxonomy for the page (C-1)."""
    token = (provider.subcategory or "") if hasattr(provider, "subcategory") else ""
    if token and allowed is not None and token not in allowed:
        return ""
    return token


def _route_bucket_id(route_slug: str) -> str | None:
    """The single canonical bucket a category route belongs to.

    Mega routes resolve via the chip mapping; tile routes (which carry no chips)
    fall back to the bucket of their representative legacy category. Used to decide
    whether a card's subtype label is on-taxonomy for the page (C-1).
    """
    from app.categories.subcategories import bucket_for_category_route
    from app.v1.categories import bucket_for_legacy_category

    bid = bucket_for_category_route(route_slug)
    if bid:
        return bid
    slugs = CATEGORY_FILTERS.get(route_slug) or ()
    return bucket_for_legacy_category(slugs[0]) if slugs else None


def _allowed_subcategory_slugs(route_slug: str) -> set[str] | None:
    """Subcategory slugs that legitimately belong on ``route_slug``'s page.

    Returns ``None`` (= no restriction) when the route has no resolvable bucket.
    A card whose subcategory is outside this set gets no subtype label, so a
    Shopping ``Specialty`` row that leaked onto the Services page via a foreign
    legacy category no longer mislabels the card (audit C-1).
    """
    from app.categories.subcategories import subcategories_for_bucket

    bucket_id = _route_bucket_id(route_slug)
    if not bucket_id:
        return None
    return {s.slug for s in subcategories_for_bucket(bucket_id)}


# ---------------------------------------------------------------------------
# Taxonomy pivot — list providers by their (Google-derived) subcategory bucket
# instead of the often-wrong legacy ``Provider.category`` (prod audit: 397 rows
# misfiled, e.g. a hospital as ``retail``). Each route owns a canonical
# subcategory set; mega routes own their whole bucket, tile routes a slice.
# ---------------------------------------------------------------------------

_TILE_ROUTE_SUBCATS: dict[str, tuple[str, ...]] = {
    "health-wellness-care": ("health-medical",),
    "home-property-services": ("home-services",),
    "professional": ("professional",),
    "beauty-care": ("beauty",),
    "auto-rv-fuel": ("auto",),
    "public-civic-resources": ("civic-community",),
    "pets": ("pets",),
    "attractions": ("attractions",),
}


def _route_subcategory_slugs(route_slug: str) -> set[str]:
    """Canonical subcategory slugs a route lists. Tile routes own a slice; mega
    routes own their whole bucket; unknown routes own nothing."""
    from app.categories.subcategories import (
        bucket_for_category_route,
        subcategories_for_bucket,
    )

    route = (route_slug or "").strip().lower()
    if route in _TILE_ROUTE_SUBCATS:
        return set(_TILE_ROUTE_SUBCATS[route])
    bucket = bucket_for_category_route(route)
    if bucket:
        return {s.slug for s in subcategories_for_bucket(bucket)}
    return set()


def route_provider_filter(route_slug: str):
    """SQLAlchemy clause selecting the providers that belong on ``route_slug``.

    A provider belongs when its **subcategory** (the strong Google-derived signal)
    is in the route's canonical set. Providers not yet subcategorized (``NULL``)
    fall back to the legacy ``CATEGORY_FILTERS`` match — so already-classified prod
    rows route correctly (a hospital → Health, not Shopping) while unclassified
    rows and test fixtures keep their prior behavior. The ``subcategory IS NULL``
    guard is what makes a wrong legacy category irrelevant once a subcategory exists.
    """
    from sqlalchemy import and_, false, or_

    subs = _route_subcategory_slugs(route_slug)
    legacy = CATEGORY_FILTERS.get((route_slug or "").strip().lower(), ())
    clauses = []
    if subs:
        clauses.append(Provider.subcategory.in_(subs))
    if legacy:
        clauses.append(and_(Provider.subcategory.is_(None), Provider.category.in_(legacy)))
    if not clauses:
        return false()
    return or_(*clauses)


def _build_category_card(
    provider: Provider,
    *,
    status_class: str,
    status_text: str,
    image_url: str | None,
    allowed_subcategories: set[str] | None = None,
) -> dict[str, Any]:
    """Shape a Provider row into the category-grid card contract.

    ``subcategory`` rides along so the Sandstone page can filter the
    server-rendered grid in place by chip (the JS shows/hides on this token).
    It is blanked when off-taxonomy for the page (``allowed_subcategories``), so
    a foreign subtype never labels a card or matches a chip it doesn't belong to.
    ``is_open`` drives the Sandstone open/closed pill: True/False from the live
    hours status, None when hours are unknown (pill omitted, no fabrication).
    """
    rating, review_count = _rating_display(
        provider.google_rating, getattr(provider, "google_review_count", None)
    )
    if status_class in ("open", "closing-soon"):
        is_open: bool | None = True
    elif status_class in ("closed", "closed-soon"):
        is_open = False
    else:
        is_open = None
    return {
        "slug": provider.slug,
        "name": provider.provider_name,
        "image_url": image_url,
        "neighborhood": (provider.district or "") if hasattr(provider, "district") else "",
        "status": status_class,
        "status_text": status_text,
        "rating": rating,
        "review_count": review_count,
        "subcategory": _card_subcategory_token(provider, allowed_subcategories),
        "is_open": is_open,
    }


def category_cards(
    db: Session | None,
    slug: str,
    *,
    now: datetime,
    limit: int = _DEFAULT_CARD_LIMIT,
) -> list[dict[str, Any]]:
    """Return cards for a single category page.

    Filters active non-draft Providers whose ``category`` is in the
    route's slug set, hydrates each with live hours status, and shapes
    the result for ``components/category_grid.html``.

    Args:
        db: SQLAlchemy session. ``None`` short-circuits to ``[]``.
        slug: route segment from the URL.
        now: datetime to evaluate ``_hours_status`` against. The status
            pill on the card uses this; the filter does NOT drop closed
            providers (a closed restaurant is still a valid card -- the
            visitor may want to know it exists). The eat-row pattern
            (open-only) is a D3 surface choice, not a category-page one.
        limit: cap on rows returned. Sparse categories return fewer.

    Returns:
        List of card dicts. Empty list when no rows match -- the
        template's ``{% if category_cards %}`` gate handles the
        empty case with editorial copy.
    """
    if db is None:
        return []
    if not is_valid_category_slug(slug):
        return []


    try:
        rows: list[Provider] = (
            db.query(Provider)
            .filter(
                route_provider_filter(slug.strip().lower()),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .order_by(*_rating_sort_key())
            .limit(max(limit, 1))
            .all()
        )
    except Exception:
        # Defensive: a DB outage leaves the page rendering its slim
        # header with no cards, not a 500. The template's empty-state
        # branch handles the rest.
        return []

    if not rows:
        return []

    cards: list[dict[str, Any]] = []
    for provider in rows:
        try:
            status_class, status_text = _hours_status(provider, now=now)
        except Exception:
            # One malformed hours_structured row should not poison the
            # whole grid. Surface the card without a status pill.
            status_class, status_text = "unknown", ""
        image_url = _resolve_category_card_image(provider)
        cards.append(
            _build_category_card(
                provider,
                status_class=status_class,
                status_text=status_text,
                image_url=image_url,
            )
        )
    return cards


def category_count(db: Session | None, slug: str) -> int | None:
    """Return the number of active non-draft providers matching this route.

    Used by the slim header (e.g. ``Health & wellness . 328 listed``).
    Returns ``None`` -- not 0 -- when there are no matches OR when the
    DB is unreachable, so the template can hide the count clause
    entirely (per BUILD.md no-zero rule).
    """
    if db is None:
        return None
    if not is_valid_category_slug(slug):
        return None

    from sqlalchemy import func as sa_func

    try:
        row = (
            db.query(sa_func.count(Provider.id))
            .filter(
                route_provider_filter(slug.strip().lower()),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .scalar()
        )
    except Exception:
        return None
    if row is None or int(row) <= 0:
        return None
    return int(row)


# ---------------------------------------------------------------------------
# P0 Task 2 — faceted listing (subcategory + Open now / Closest / Top rated)
# ---------------------------------------------------------------------------
#
# Powers both the plural mega-page and the /lake-havasu/{subcategory} landing.
# Facets are independent and combinable. SQL-expressible filters (subcategory,
# top_rated) run in the query; Open-now and Closest need each row's live hours /
# geo, so when either is active we materialize the candidate set (bounded by
# _MATERIALIZE_CAP) and finish in Python. Price/Hours facets from the brief are
# intentionally omitted — there is no price signal in the catalog yet (flagged).

# Civic-center anchor for the Closest sort. Mirrors category_pages._REF_*; a real
# device-geolocation "near me" is a client-side follow-up (P1).
_REF_LAT = 34.4839
_REF_LNG = -114.3225
_TOP_RATED_MIN = 4.0

# "Locals' favorites" weighted sort (01_UI_BUILD_GUIDE.md §4.8). A Bayesian
# shrink toward the prior mean: a venue's star rating is pulled toward
# ``_FAV_PRIOR_MEAN`` until it has accumulated reviews, with ``_FAV_PRIOR_WEIGHT``
# pseudo-reviews of weight. So a 4.6/3878 institution outranks a 5.0/3 outlier —
# the thin 5.0 barely moves off the 4.3 prior, while the institution's huge n
# lets its real rating dominate. Formula: (rating*n + mean*weight)/(n + weight).
_FAV_PRIOR_MEAN = 4.3
_FAV_PRIOR_WEIGHT = 30


def weighted_favorites_score(
    rating: float | None,
    review_count: int | None,
) -> float:
    """Volume-weighted "Locals' favorites" score for one provider.

    ``score = (rating*n + 4.3*30)/(n+30)``. A provider with no rating scores at
    the prior mean (it neither benefits nor suffers), so unrated rows sink below
    credibly-reviewed ones without being fabricated into a rating. Never raises.
    """
    try:
        r = float(rating) if rating is not None else _FAV_PRIOR_MEAN
    except (TypeError, ValueError):
        r = _FAV_PRIOR_MEAN
    try:
        n = int(review_count) if review_count is not None else 0
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    return (r * n + _FAV_PRIOR_MEAN * _FAV_PRIOR_WEIGHT) / (n + _FAV_PRIOR_WEIGHT)
# Upper bound on rows scanned when a Python-side facet (open_now / closest) is
# active. Comfortably above the largest bucket (Services ~1.5k) so the facet
# count stays accurate; only paid when the facet is engaged.
_MATERIALIZE_CAP = 2000


# Hours-derived facets (open_late / open_weekends) parse the same weekday-keyed
# hours_structured shape used for the open/closed pills. They never raise on
# malformed input — a bad span is skipped; missing/non-dict hours → False.
_WEEKEND_KEYS = ("saturday", "sunday")
_LATE_HOURS_THRESHOLD_HOUR = 20  # 8 PM — "open late"


def _has_late_hours(hours_structured: dict | None, threshold_hour: int = _LATE_HOURS_THRESHOLD_HOUR) -> bool:
    """Whether any day's close time is at/after ``threshold_hour`` (24h). A span
    wrapping past midnight (close <= open) counts as late."""
    if not hours_structured or not isinstance(hours_structured, dict):
        return False
    threshold = time(threshold_hour % 24, 0)
    for spans in hours_structured.values():
        if not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict):
                continue
            open_t = _parse_hours_time(str(span.get("open") or ""))
            close_t = _parse_hours_time(str(span.get("close") or ""))
            if close_t is None:
                continue
            if open_t is not None and close_t <= open_t:
                return True
            if close_t >= threshold:
                return True
    return False


def _has_weekend_hours(hours_structured: dict | None) -> bool:
    """Whether the provider has any open span on Saturday or Sunday."""
    if not hours_structured or not isinstance(hours_structured, dict):
        return False
    for day_key in _WEEKEND_KEYS:
        spans = hours_structured.get(day_key)
        if not isinstance(spans, list) or not spans:
            continue
        for span in spans:
            if isinstance(span, dict) and _parse_hours_time(str(span.get("open") or "")) is not None:
                return True
    return False


@dataclass(frozen=True)
class CategoryFacets:
    """Active facet selections for a category listing. All independent."""

    subcategory: str | None = None
    open_now: bool = False
    top_rated: bool = False
    open_late: bool = False
    open_weekends: bool = False
    sort: str = "default"  # default | favorites | closest | alpha

    @property
    def any_active(self) -> bool:
        return bool(
            self.subcategory
            or self.open_now
            or self.top_rated
            or self.open_late
            or self.open_weekends
            or self.sort != "default"
        )

    @property
    def needs_materialize(self) -> bool:
        """Whether a facet requires Python-side scanning (live hours / distance /
        weighted score).

        SQL-expressible facets (subcategory, top_rated) and the alpha sort do
        NOT; ``open_now`` / ``open_late`` / ``open_weekends`` / ``closest`` and
        the ``favorites`` weighted sort do (the latter ranks on a Python-side
        Bayesian score, not a column).
        """
        return (
            self.open_now
            or self.open_late
            or self.open_weekends
            or self.sort in ("closest", "favorites")
        )


def _distance_km(provider: Provider, ref_lat: float, ref_lng: float) -> float:
    if provider.lat is None or provider.lng is None:
        return 9e6
    r = 6371.0
    p1, p2 = math.radians(ref_lat), math.radians(float(provider.lat))
    dp = math.radians(float(provider.lat) - ref_lat)
    dl = math.radians(float(provider.lng) - ref_lng)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _provider_card(
    db: Session,
    provider: Provider,
    *,
    now: datetime,
    allowed_subcategories: set[str] | None = None,
) -> dict[str, Any]:
    try:
        status_class, status_text = _hours_status(provider, now=now)
    except Exception:
        status_class, status_text = "unknown", ""
    return _build_category_card(
        provider,
        status_class=status_class,
        status_text=status_text,
        image_url=_resolve_category_card_image(provider),
        allowed_subcategories=allowed_subcategories,
    )


def category_listing(
    db: Session | None,
    slug: str,
    *,
    now: datetime,
    facets: CategoryFacets | None = None,
    limit: int = _DEFAULT_CARD_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(cards, total)`` for a category page under the given facets.

    ``total`` is the count of providers matching the facets (so the header's
    "N listed" always matches the grid's basis — same no-mismatch discipline as
    the home bucket counts). Never raises: a DB error degrades to ``([], 0)``.
    """
    if db is None or not is_valid_category_slug(slug):
        return [], 0
    facets = facets or CategoryFacets()
    route_key = slug.strip().lower()
    allowed_subs = _allowed_subcategory_slugs(route_key)
    try:
        base = db.query(Provider).filter(
            route_provider_filter(slug.strip().lower()),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        if facets.subcategory:
            base = base.filter(Provider.subcategory == facets.subcategory.strip().lower())
        if facets.top_rated:
            base = base.filter(Provider.google_rating >= _TOP_RATED_MIN)

        needs_scan = facets.needs_materialize
        if not needs_scan:
            total = int(base.with_entities(sa_func.count(Provider.id)).scalar() or 0)
            ordered = (
                base.order_by(Provider.provider_name.asc())
                if facets.sort == "alpha"
                else base.order_by(*_rating_sort_key())
            )
            rows = ordered.limit(max(limit, 1)).all()
            return [_provider_card(db, p, now=now, allowed_subcategories=allowed_subs) for p in rows], total

        rows = base.order_by(*_rating_sort_key()).limit(_MATERIALIZE_CAP).all()
        if facets.open_now:
            rows = [p for p in rows if is_open_now(p, now=now)[0] is True]
        if facets.open_late:
            rows = [p for p in rows if _has_late_hours(effective_hours_structured(p))]
        if facets.open_weekends:
            rows = [p for p in rows if _has_weekend_hours(effective_hours_structured(p))]
        if facets.sort == "closest":
            rows.sort(key=lambda p: (_distance_km(p, _REF_LAT, _REF_LNG), (p.provider_name or "").lower()))
        elif facets.sort == "favorites":
            # C-3: the default "Locals' favorites" sort used to open with a wall of
            # high-rated but *closed* businesses. Demote definitively-closed rows
            # below open/unknown ones (rank 1 vs 0), keeping the favorites score as
            # the ordering within each band. Compute open-state once per row.
            open_state = {id(p): is_open_now(p, now=now)[0] for p in rows}
            rows.sort(
                key=lambda p: (
                    1 if open_state.get(id(p)) is False else 0,
                    -weighted_favorites_score(
                        p.google_rating, getattr(p, "google_review_count", None)
                    ),
                    (p.provider_name or "").lower(),
                )
            )
        elif facets.sort == "alpha":
            rows.sort(key=lambda p: (p.provider_name or "").lower())
        total = len(rows)
        return [_provider_card(db, p, now=now, allowed_subcategories=allowed_subs) for p in rows[:limit]], total
    except Exception:
        return [], 0
