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
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Provider
from app.home.queries import _hours_status, _provider_image_url
from app.home.queries_c import _load_eat_photos, _rating_display, _rating_sort_key

_CATEGORY_PHOTOS_PATH = (
    Path(__file__).resolve().parent / "curated_category_photos.json"
)

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
    "things-to-do": (
        "entertainment_attractions",
        "fitness_sports",
        "childcare_education",
        "religion_community",
        "recreation",
        "education",
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
    "shopping-essentials": (
        "retail",
    ),
    "professional": (
        "professional_services",
        "real_estate",
        "insurance",
        "financial",
        "legal",
    ),
    "beauty-care": (
        "beauty_personal_care",
    ),
    "auto-rv-fuel": (
        "auto",
    ),
    "public-civic-resources": (
        "religion_community",
    ),
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
    "lodging-vacation-rentals": (
        "lodging",
    ),
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
    return {
        str(k): str(v)
        for k, v in photos.items()
        if isinstance(v, str) and v
    }


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


def _build_category_card(
    provider: Provider,
    *,
    status_class: str,
    status_text: str,
    image_url: str | None,
) -> dict[str, Any]:
    """Shape a Provider row into the category-grid card contract."""
    rating, review_count = _rating_display(
        provider.google_rating, getattr(provider, "google_review_count", None)
    )
    return {
        "slug": provider.slug,
        "name": provider.provider_name,
        "image_url": image_url,
        "neighborhood": (provider.district or "") if hasattr(provider, "district") else "",
        "status": status_class,
        "status_text": status_text,
        "rating": rating,
        "review_count": review_count,
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

    slugs_for_route = CATEGORY_FILTERS[slug.strip().lower()]

    try:
        rows: list[Provider] = (
            db.query(Provider)
            .filter(
                Provider.category.in_(slugs_for_route),
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

    slugs_for_route = CATEGORY_FILTERS[slug.strip().lower()]
    try:
        row = (
            db.query(sa_func.count(Provider.id))
            .filter(
                Provider.category.in_(slugs_for_route),
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
