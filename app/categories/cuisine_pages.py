"""Cuisine SEO landing pages (A3) — ``/lake-havasu/{cuisine}``.

A cuisine landing is the Eat & Drink listing pre-filtered to one cuisine
(``derive_cuisine`` over a provider's Google types), rendered through the SAME
machinery as the plural category page and the ``/lake-havasu/{subcategory}``
landings, with its own ``<h1>`` and — crucially — an independently sellable
**placement key** (:func:`placement_key_for`, ``"cuisine:{slug}"``) so a
restaurant can pay to top its cuisine page without topping all of Eat & Drink.

Publish gate (mirrors the trade/leaf pattern): a cuisine page resolves, joins
the sitemap, and is monetizable only at/above
:data:`CUISINE_PAGE_MIN_PROVIDERS` active non-draft listings. Thin cuisines
404 and stay out of the sitemap so near-empty templated pages are never exposed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.categories.subcategories import (
    cuisine_label,
    cuisine_slugs_in_order,
    derive_cuisine,
)
from app.db.models import Provider

#: Scaled-content thin-page gate — a cuisine page publishes only at/above this
#: many active non-draft Eat & Drink providers of that cuisine.
CUISINE_PAGE_MIN_PROVIDERS = 7

#: The plural ``CATEGORY_FILTERS`` route the cuisine pages draw their pool from.
EAT_DRINK_ROUTE = "eat-drink"


def placement_key_for(cuisine_slug: str) -> str:
    """The category_rank placement key a cuisine page sells against.

    Namespaced (``cuisine:mexican``) so it never collides with a real category
    route slug — selling a placement on this key pins + labels a provider on the
    cuisine page only, not on the whole Eat & Drink grid.
    """
    return f"cuisine:{(cuisine_slug or '').strip().lower()}"


def _eat_drink_cuisine_counts(db: Session) -> dict[str, int]:
    """``{cuisine_slug: count}`` over the SAME pool the cuisine page renders.

    Uses ``route_provider_filter('eat-drink')`` (not the legacy-only filter) so
    the gate count matches what :func:`category_listing` actually lists for the
    cuisine facet. ``derive_cuisine`` isn't SQL-expressible, so one bounded scan
    classifies the pool in Python. Empty on any DB hiccup."""
    try:
        rows = (
            db.query(Provider.google_primary_category, Provider.google_categories)
            .filter(
                cat_queries.route_provider_filter(EAT_DRINK_ROUTE),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .limit(cat_queries._MATERIALIZE_CAP)
            .all()
        )
    except Exception:
        return {}
    counts: dict[str, int] = {}
    for primary, cats in rows:
        c = derive_cuisine(primary, cats)
        if c:
            counts[c] = counts.get(c, 0) + 1
    return counts


def cuisine_provider_count(db: Session, cuisine_slug: str) -> int:
    """Active non-draft Eat & Drink providers of ``cuisine_slug`` (gate input)."""
    c = (cuisine_slug or "").strip().lower()
    if not c:
        return 0
    return _eat_drink_cuisine_counts(db).get(c, 0)


def is_publishable_cuisine(db: Session, cuisine_slug: str) -> bool:
    """Whether ``cuisine_slug`` is a known cuisine clearing the thin-page gate."""
    if cuisine_label(cuisine_slug) is None:
        return False
    return cuisine_provider_count(db, cuisine_slug) >= CUISINE_PAGE_MIN_PROVIDERS


def qualifying_cuisines(db: Session) -> list[tuple[str, str, int]]:
    """``(slug, label, count)`` for every cuisine clearing the gate, in canonical
    display order. Used by the sitemap so under-minimum cuisines stay unlisted.
    One pool scan total (not one per cuisine)."""
    counts = _eat_drink_cuisine_counts(db)
    out: list[tuple[str, str, int]] = []
    for slug in cuisine_slugs_in_order():
        n = counts.get(slug, 0)
        if n >= CUISINE_PAGE_MIN_PROVIDERS:
            out.append((slug, cuisine_label(slug) or slug, n))
    return out
