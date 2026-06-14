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

from app.categories.subcategories import derive_cuisine
from app.core.liveness import DAMPENER_FLOOR, liveness_dampener
from app.db.models import Provider
from app.home.queries import _hours_status, _provider_image_url
from app.home.queries_c import (
    _format_rating,
    _load_eat_photos,
)
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
    "professional-services": (
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
        "Lake Life",
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
    "professional-services": (
        "Professional Services",
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
    "professional-services": "services",
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

# DL-12 (WP-5): a card shows a star/numeric rating only once it has at least
# this many reviews; below it the card reads "New / few reviews yet". This is
# the SAME canonical field profiles read (``google_review_count`` /
# ``google_rating``) but a category-surface threshold of >=3 -- deliberately
# looser than ``app.home.queries_c.MIN_RATING_REVIEWS`` (5, used by the
# editorial home rows). Implemented inline here rather than via a shared helper
# so WP-6 (profiles) can apply the identical >=3 rule in its own surface without
# a cross-package coupling (see PR notes: a shared ratings helper is a possible
# follow-up).
_DL12_MIN_REVIEWS = 3

# DL-8 (WP-5): a listing whose geo sits past this many km from the Lake Havasu
# City civic anchor is "out of area" -- it still renders, but the card carries a
# visible distance hint ("~40 min away . Parker area") instead of being hidden.
# 32 km ~= the Parker / Black Meadow Landing cluster the audit (M-07) flagged as
# appearing on the Lodging page with no hint.
_OUT_OF_AREA_KM = 32.0
# Beyond this the listing is not plausibly in the Lake Havasu region at all (Parker
# ~60 km, Kingman ~90 km, Blythe ~135 km are the realistic out-of-area cluster);
# a larger distance means mis-geocoded coords or a non-regional row, so we suppress
# the hint rather than print a fabricated "~2405 min away . Parker area" line (the
# prod-smoke bug). Consistent with "never fabricate a distance" for geo-less rows.
_FAR_OUT_OF_REGION_KM = 150.0
# Rough drive-time estimate from straight-line km (no routing data): town surface
# streets + the lake detour run ~1.3x crow-flight at ~55 km/h effective.
_DRIVE_MIN_PER_KM = 1.35


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
    "professional-services": ("professional",),
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


def _route_primary_categories(route_slug: str) -> set[str]:
    """Canonical primary-category slugs (the 12) a route lists (WP-9).

    Derived deterministically from the route's subcategory set mapped through
    ``SUBCATEGORY_TO_PRIMARY``. So ``health-wellness-care`` → {health-wellness-care},
    the ``services`` mega-route → the union of every primary its subcategories fold
    into. Empty set when the route owns no subcategories. This is what lets the
    grid filter on the canonical ``Provider.primary_category`` first.
    """
    from app.categories.subcategories import SUBCATEGORY_TO_PRIMARY

    subs = _route_subcategory_slugs(route_slug)
    return {p for s in subs if (p := SUBCATEGORY_TO_PRIMARY.get(s))}


# ---------------------------------------------------------------------------
# WP-12 — ONE canonical per-category count, shared by every surface
# ---------------------------------------------------------------------------
#
# Audit S4 ("one count query everywhere"): Home tiles, the Explore header, and
# the Map each used to compute their per-category provider count differently
# (an ``EntityCategory`` join here, ``route_provider_filter`` there), so the
# same category read e.g. 41 on Home and 38 on Explore. ``primary_listing_filter``
# is the single clause they now all share. It resolves a category the SAME way
# WP-9's listing filters do — canonical ``primary_category`` first, legacy
# ``Provider.category`` only while primary is still NULL — so the number a
# surface SHOWS always equals the listings it renders for that category.


def _legacy_categories_for_primaries(primary_slugs: set[str] | frozenset[str]) -> set[str]:
    """Legacy ``Provider.category`` strings that fold into ``primary_slugs`` (WP-12).

    Inverts ``LEGACY_CATEGORY_TO_PRIMARY`` (the same map WP-9 uses to backfill the
    primary column), so the count's NULL-primary fallback tier covers exactly the
    un-backfilled rows that the listing's fallback would also pick up. Keeping the
    two tiers derived from one source is what makes count == len(listing) hold for
    rows that have no ``primary_category`` yet.
    """
    from app.categories.subcategories import LEGACY_CATEGORY_TO_PRIMARY

    wanted = {s for s in primary_slugs if s}
    return {
        legacy for legacy, primary in LEGACY_CATEGORY_TO_PRIMARY.items() if primary in wanted
    }


def primary_listing_filter(primary_slugs: set[str] | frozenset[str] | list[str] | tuple[str, ...]):
    """The ONE canonical clause selecting providers for a set of primary categories.

    Two-tier, strongest first (WP-9 / WP-12 / audit S4 + R2):

    1. **primary_category** — the canonical column (one of the 13). Authoritative
       when set: a provider belongs iff its primary is in ``primary_slugs``.
    2. **legacy ``category``** (primary NULL only) — the un-backfilled fallback,
       expanded from ``primary_slugs`` via ``LEGACY_CATEGORY_TO_PRIMARY`` so rows
       that have not been classified yet still count toward — and render under —
       the right category.

    Returns a SQLAlchemy boolean clause; ``false()`` for an empty/unknown set.
    Every count surface (Home tiles, Explore header, Map) builds on this, and
    ``route_provider_filter`` delegates its primary + legacy tiers here, so all
    surfaces agree on which providers belong to a category.
    """
    from sqlalchemy import and_, false, or_

    primaries = {s for s in primary_slugs if s}
    if not primaries:
        return false()
    legacy = _legacy_categories_for_primaries(primaries)
    clauses = [Provider.primary_category.in_(primaries)]
    if legacy:
        clauses.append(
            and_(Provider.primary_category.is_(None), Provider.category.in_(legacy))
        )
    return or_(*clauses)


def category_listing_count(
    db: Session | None,
    primary_slugs: set[str] | frozenset[str] | list[str] | tuple[str, ...],
) -> int:
    """Canonical count of active non-draft providers for a set of primary categories.

    The single source of truth behind every surface's "N businesses / N listed"
    label (WP-12). Counts via :func:`primary_listing_filter`, so the number equals
    the listings the same filter renders. Returns 0 on an empty set or any DB
    hiccup — callers that need the no-zero ``None`` semantics (the Explore header)
    map 0 -> None themselves.
    """
    if db is None:
        return 0
    primaries = {s for s in primary_slugs if s}
    if not primaries:
        return 0
    from sqlalchemy import func as sa_func

    try:
        row = (
            db.query(sa_func.count(Provider.id))
            .filter(
                primary_listing_filter(primaries),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .scalar()
        )
    except Exception:
        return 0
    if row is None:
        return 0
    try:
        return max(int(row), 0)
    except (TypeError, ValueError):
        return 0


def route_provider_filter(route_slug: str):
    """SQLAlchemy clause selecting the providers that belong on ``route_slug``.

    Three-tier signal, strongest first (WP-9 / audit R2):

    1. **primary_category** — the canonical column (one of the 13). When set, it is
       authoritative: a provider belongs iff its primary is in the route's primary
       set.
    2. **subcategory** (primary NULL) — the strong Google-derived signal; matched
       against the route's canonical subcategory set.
    3. **legacy ``category``** (primary AND subcategory NULL) — the last-resort
       ``CATEGORY_FILTERS`` match, so un-backfilled prod rows and test fixtures keep
       routing until they are classified.

    The ``IS NULL`` guards make a weaker (often wrong) signal irrelevant once a
    stronger one exists — e.g. a hospital mis-filed as legacy ``retail`` routes to
    Health via its primary/subcategory, never to Shopping.

    Note the subcategory middle tier: this surface keeps it (un-backfilled rows
    that carry a derived subcategory but no primary). The canonical count helpers
    (:func:`primary_listing_filter` / :func:`category_listing_count`) deliberately
    omit it — they count on primary-then-legacy only — which is why they are used
    by the Home/Explore/Map count surfaces that key on the canonical 13 primaries.
    """
    from sqlalchemy import and_, false, or_

    primaries = _route_primary_categories(route_slug)
    subs = _route_subcategory_slugs(route_slug)
    legacy = CATEGORY_FILTERS.get((route_slug or "").strip().lower(), ())
    clauses = []
    if primaries:
        clauses.append(Provider.primary_category.in_(primaries))
    if subs:
        clauses.append(
            and_(Provider.primary_category.is_(None), Provider.subcategory.in_(subs))
        )
    if legacy:
        clauses.append(
            and_(
                Provider.primary_category.is_(None),
                Provider.subcategory.is_(None),
                Provider.category.in_(legacy),
            )
        )
    if not clauses:
        return false()
    return or_(*clauses)


def _card_rating_display(
    rating: float | None, review_count: int | None
) -> tuple[str | None, int | None]:
    """DL-12 rating display for a category card: render only at >=3 reviews.

    Reads the same canonical fields as profiles (``google_rating`` /
    ``google_review_count``) but applies the category-surface threshold of 3
    (vs the home rows' 5). Below threshold -> ``(None, None)`` so the card shows
    the "New / few reviews yet" badge instead of a star it hasn't earned.
    """
    formatted = _format_rating(rating)
    if formatted is None:
        return None, None
    try:
        n = int(review_count) if review_count is not None else 0
    except (TypeError, ValueError):
        n = 0
    if n < _DL12_MIN_REVIEWS:
        return None, None
    return formatted, n


def _card_area(provider: Provider) -> str:
    """Second meta-line locator for a card (D7): district label, else the street
    line of the address (everything before the first comma). ``""`` when neither
    is known -- the template then omits the line rather than printing noise."""
    district = (getattr(provider, "district", None) or "").strip()
    if district:
        return district
    address = (getattr(provider, "address", None) or "").strip()
    if address:
        # First address segment is the street line ("2126 McCulloch Blvd N").
        return address.split(",", 1)[0].strip()
    return ""


def _card_distance_hint(provider: Provider) -> str:
    """DL-8 out-of-area hint, or ``""`` for in-area / geo-unknown providers.

    Past ``_OUT_OF_AREA_KM`` from the civic anchor the card keeps its place but
    gains a visible "~N min away . Parker area" note. Geo-less rows (no lat/lng)
    get no hint -- we never fabricate a distance.
    """
    if getattr(provider, "lat", None) is None or getattr(provider, "lng", None) is None:
        return ""
    km = _distance_km(provider, _REF_LAT, _REF_LNG)
    # In-area, or so far the coords aren't trustworthy (incl. the 9e6 geo-less
    # sentinel) -> no hint instead of a fabricated minute count + wrong locale.
    if km < _OUT_OF_AREA_KM or km >= _FAR_OUT_OF_REGION_KM:
        return ""
    minutes = int(round(km * _DRIVE_MIN_PER_KM / 5.0)) * 5 or 5
    return f"~{minutes} min away . Parker area"


def _build_category_card(
    provider: Provider,
    *,
    status_class: str,
    status_text: str,
    image_url: str | None,
    allowed_subcategories: set[str] | None = None,
    is_sponsored: bool = False,
) -> dict[str, Any]:
    """Shape a Provider row into the category-grid card contract.

    ``subcategory`` rides along so the Sandstone page can filter the
    server-rendered grid in place by chip (the JS shows/hides on this token).
    It is blanked when off-taxonomy for the page (``allowed_subcategories``), so
    a foreign subtype never labels a card or matches a chip it doesn't belong to.
    ``is_open`` drives the Sandstone open/closed pill: True/False from the live
    hours status, None when hours are unknown (pill omitted, no fabrication).

    DL-12: ``rating`` renders only at >=3 reviews; below that ``has_reviews`` is
    False and the template shows a "New / few reviews yet" badge. DL-8:
    ``distance_hint`` flags out-of-area listings. D7: ``area`` is the card's
    second meta line (district / cross-street).
    """
    rating, review_count = _card_rating_display(
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
        # DL-12: True only when a credible rating (>=3 reviews) is shown.
        "has_reviews": rating is not None,
        # D7: second meta line (district / cross-street); "" -> line omitted.
        "area": _card_area(provider),
        # DL-8: out-of-area hint; "" for in-area / geo-unknown rows.
        "distance_hint": _card_distance_hint(provider),
        "subcategory": _card_subcategory_token(provider, allowed_subcategories),
        "cuisine": derive_cuisine(
            getattr(provider, "google_primary_category", None),
            getattr(provider, "google_categories", None),
        )
        or "",
        "is_open": is_open,
        # Honesty gate (§7.2): True only when this provider holds an active paid
        # placement on the surface being rendered. Default False keeps every
        # existing caller's cards unlabeled until placements are wired in.
        "is_sponsored": is_sponsored,
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
            .order_by(*_dampened_rating_sort_key(db))
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

    # Phase F §7.2 honesty gate: pin active paid sticky-tier placements to the top
    # and label them Sponsored. No-op (organic order, no badges) until a placement
    # is sold for this route. Defensive: a lookup failure leaves the grid organic.
    try:
        from app.monetization.serving import active_category_tiers, apply_category_order

        tiers = active_category_tiers(db, slug.strip().lower())
    except Exception:
        tiers = {}
    sponsored_ids = set(tiers.values())
    if tiers:
        by_id = {p.id: p for p in rows}
        rows = [
            by_id[pid]
            for pid in apply_category_order([p.id for p in rows], tiers)
            if pid in by_id
        ]

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
                is_sponsored=provider.id in sponsored_ids,
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


def _liveness_dampener_expr():
    """SQL mirror of :func:`app.core.liveness.liveness_dampener`.

    ``FLOOR + (1 - FLOOR) * COALESCE(liveness_score, 1.0)`` — a NULL score
    (non-Google-sourced provider, or backfill not yet applied) collapses to a
    1.0 multiplier, so only listings with evidence of staleness are dampened.
    Uses the **stored** ``Provider.liveness_score`` column (no exp/sqrt in SQL),
    mirroring the search-path decision in LIVENESS_RANKING_HANDOFF_2026-06-03.
    """
    return DAMPENER_FLOOR + (1.0 - DAMPENER_FLOOR) * sa_func.coalesce(
        Provider.liveness_score, 1.0
    )


def _dampened_rating_sort_key(db):
    """``queries_c._rating_sort_key`` with the liveness dampener folded in.

    Bayesian-shrunk rating (WS-2, ``app.core.rating_prior``: ``(R*n + m*C) /
    (n + C)``, C=25, live review-weighted ``m``) replacing the old hard
    ``MIN_RATING_REVIEWS`` tier — the prior shrinks thin-review ratings toward
    the global mean continuously instead of bucketing them, so a 2-review 5.0
    can't top a leaf page while a review-rich head keeps its order (top-20
    identical at C=25 on the 2026-06-10 prod calibration). The score is
    multiplied by the liveness dampener, so a stale-but-once-popular listing
    sinks (the bury-don't-remove rule). NULL ratings still sort last; NULL
    liveness leaves the ordering identical to the undampened sort.
    """
    from app.core.rating_prior import bayesian_rating_expr, global_mean_rating

    score = bayesian_rating_expr(global_mean_rating(db))
    return (
        (score * _liveness_dampener_expr()).desc().nullslast(),
        Provider.google_review_count.desc().nullslast(),
    )

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
    cuisine: str | None = None
    open_now: bool = False
    top_rated: bool = False
    open_late: bool = False
    open_weekends: bool = False
    sort: str = "default"  # default | favorites | closest | alpha

    @property
    def any_active(self) -> bool:
        return bool(
            self.subcategory
            or self.cuisine
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
            or bool(self.cuisine)
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
    sponsored_provider_ids: set[str] | None = None,
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
        is_sponsored=bool(sponsored_provider_ids and provider.id in sponsored_provider_ids),
    )


def available_cuisines_for_route(db: Session | None, slug: str) -> list[dict[str, str]]:
    """Cuisine chips present among a route's providers (C-2), in canonical order.

    Returns ``[]`` for non-food routes (no cuisine tokens match) or on any DB
    hiccup — the template then renders no cuisine row. One light two-column query.
    """
    from app.categories.subcategories import cuisine_label, cuisine_slugs_in_order

    if db is None:
        return []
    slugs = CATEGORY_FILTERS.get((slug or "").strip().lower())
    if not slugs:
        return []
    try:
        rows = (
            db.query(Provider.google_primary_category, Provider.google_categories)
            .filter(
                Provider.category.in_(slugs),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .all()
        )
    except Exception:
        return []
    present: set[str] = set()
    for primary, cats in rows:
        c = derive_cuisine(primary, cats)
        if c:
            present.add(c)
    return [
        {"slug": s, "label": cuisine_label(s) or s}
        for s in cuisine_slugs_in_order()
        if s in present
    ]


def subcategory_chips_for_route(
    db: Session | None, slug: str
) -> list[dict[str, Any]]:
    """C8: subtype chips for a route, generated from members ACTUALLY present.

    A chip renders only for a subcategory that (a) belongs on this route's
    taxonomy *and* (b) has at least one active non-draft provider here, ordered
    by descending count. So a "Things to do" page no longer shows chips whose
    subtypes have zero members, and never omits a busy live subtype that lacks a
    hand-listed chip. Returns ``[]`` for tile routes / unknown routes / on any DB
    hiccup -- the template then renders no chip row at all (closing N-16).

    Each chip: ``{"slug", "label", "count"}``.
    """
    from app.categories.subcategories import bucket_for_category_route, subcategories_for_bucket

    if db is None:
        return []
    route_key = (slug or "").strip().lower()
    bucket_id = bucket_for_category_route(route_key)
    if not bucket_id:
        return []
    # Label/order source: the curated subcategory list for this bucket.
    subs = subcategories_for_bucket(bucket_id)
    if not subs:
        return []
    label_by_slug = {s.slug: s.label for s in subs}
    try:
        rows = (
            db.query(
                Provider.subcategory,
                sa_func.count(Provider.id),
            )
            .filter(
                route_provider_filter(route_key),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                Provider.subcategory.in_(list(label_by_slug.keys())),
            )
            .group_by(Provider.subcategory)
            .all()
        )
    except Exception:
        return []
    counts: list[dict[str, Any]] = []
    for sub_slug, n in rows:
        if not sub_slug or sub_slug not in label_by_slug:
            continue
        cnt = int(n or 0)
        if cnt <= 0:
            continue
        counts.append(
            {"slug": sub_slug, "label": label_by_slug[sub_slug], "count": cnt}
        )
    # Order by count desc, then label for a stable tiebreak.
    counts.sort(key=lambda c: (-c["count"], c["label"].lower()))
    return counts


def category_listing(
    db: Session | None,
    slug: str,
    *,
    now: datetime,
    facets: CategoryFacets | None = None,
    limit: int = _DEFAULT_CARD_LIMIT,
    page: int = 1,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(cards, total)`` for a category page under the given facets.

    ``total`` is the count of providers matching the facets (so the header's
    "N listed" always matches the grid's basis — same no-mismatch discipline as
    the home bucket counts). ``page`` (1-based) selects the ``limit``-sized
    window into that full set (M-20): ``total`` is always the unpaged match
    count, while ``cards`` is the slice for the requested page. Never raises: a
    DB error degrades to ``([], 0)``.
    """
    if db is None or not is_valid_category_slug(slug):
        return [], 0
    facets = facets or CategoryFacets()
    try:
        page = max(int(page), 1)
    except (TypeError, ValueError):
        page = 1
    per_page = max(int(limit), 1)
    offset = (page - 1) * per_page
    route_key = slug.strip().lower()
    allowed_subs = _allowed_subcategory_slugs(route_key)
    try:
        # Phase F §7.2 honesty gate: active paid sticky-tier placements for this
        # route. Empty today (nothing sold) → the fast SQL-only path below stays
        # byte-identical. A non-empty set diverts to the materialized path so paid
        # tiers can be pinned to the top (page 1) and labeled Sponsored.
        from app.monetization.serving import active_category_tiers, apply_category_order

        try:
            tiers = active_category_tiers(db, route_key)
        except Exception:
            tiers = {}  # placement lookup must never empty the organic grid
        sponsored_ids = set(tiers.values())

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
        if not needs_scan and not tiers:
            # SQL-only path (B4): subcategory + top_rated predicates and the
            # rating/alpha orderings are all expressible in SQL, so COUNT runs in
            # the DB and only the requested page is fetched -- no Python
            # materialize. The rating sort already sinks unrated rows after rated
            # peers (``_dampened_rating_sort_key`` NULL-score nullslast), satisfying
            # DL-10's sort-after for the non-favorites sorts.
            total = int(base.with_entities(sa_func.count(Provider.id)).scalar() or 0)
            ordered = (
                base.order_by(Provider.provider_name.asc())
                if facets.sort == "alpha"
                else base.order_by(*_dampened_rating_sort_key(db))
            )
            rows = ordered.offset(offset).limit(per_page).all()
            return [_provider_card(db, p, now=now, allowed_subcategories=allowed_subs) for p in rows], total

        rows = base.order_by(*_dampened_rating_sort_key(db)).limit(_MATERIALIZE_CAP).all()
        if facets.cuisine:
            want = facets.cuisine.strip().lower()
            rows = [
                p
                for p in rows
                if derive_cuisine(
                    getattr(p, "google_primary_category", None),
                    getattr(p, "google_categories", None),
                )
                == want
            ]
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
                    -(
                        weighted_favorites_score(
                            p.google_rating, getattr(p, "google_review_count", None)
                        )
                        # Liveness dampener — bury stale listings in the default
                        # favorites sort too. NULL → 1.0 (no dampening).
                        * liveness_dampener(getattr(p, "liveness_score", None))
                    ),
                    (p.provider_name or "").lower(),
                )
            )
        elif facets.sort == "alpha":
            rows.sort(key=lambda p: (p.provider_name or "").lower())
        total = len(rows)
        if tiers:
            # Pin paid tiers into the top-5 (organic order preserved below them),
            # so a sold placement leads page 1. No-op when no tier is held here.
            by_id = {p.id: p for p in rows}
            rows = [
                by_id[pid]
                for pid in apply_category_order([p.id for p in rows], tiers)
                if pid in by_id
            ]
        window = rows[offset : offset + per_page]
        return [
            _provider_card(
                db,
                p,
                now=now,
                allowed_subcategories=allowed_subs,
                sponsored_provider_ids=sponsored_ids,
            )
            for p in window
        ], total
    except Exception:
        return [], 0
