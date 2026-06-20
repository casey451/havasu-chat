"""Query-routing regression harness (2026-06-19).

Locks that the many ways people phrase a category — synonyms, singular/plural,
the combined Golf hub, pool cleaning, the new monetization trades, and common
MISSPELLINGS — all resolve to the right place, across BOTH routing surfaces:

  1. Chat navigational routing: ``_normalize`` (which runs domain
     ``spell_correct``) → ``_QUERY_TO_LEAF`` → leaf slug.
  2. Keyword search needles: ``_category_needle_set`` over the query AND its
     spell-corrected form (what ``app.search.routes._search_needles`` does) →
     the needle that reaches the provider rows.

DB-free: the >=1-provider gate and FTS are exercised elsewhere; this pins the
phrase→target mapping so a dict edit can't silently drop coverage. Misspellings
here use the deterministic ``_SPELL_ALIASES`` map (zero fuzzy flakiness).
"""

from __future__ import annotations

import pytest

from app.categories.leaf_query import _QUERY_TO_LEAF, _normalize
from app.chat.normalizer import spell_correct
from app.chat.tier2_synonyms import _category_needle_set

# --- 1. navigational phrasing → leaf slug ---------------------------------
# Each variant, after normalization (incl. spell-correction), must be a known
# navigational term pointing at the expected leaf.
_NAV_CASES: dict[str, str] = {
    # Golf hub (courses + driving range/Toptracer + indoor simulators)
    "golf": "golf-courses",
    "golf course": "golf-courses",
    "golf courses": "golf-courses",
    "driving range": "golf-courses",
    "driving ranges": "golf-courses",
    "golf simulator": "golf-courses",
    "golf simulators": "golf-courses",
    "indoor golf": "golf-courses",
    "virtual golf": "golf-courses",
    "toptracer": "golf-courses",
    # Pool service / cleaning
    "pool service": "pools-and-spas",
    "pool cleaning": "pools-and-spas",
    "pool cleaner": "pools-and-spas",
    "pool cleaners": "pools-and-spas",
    "pool maintenance": "pools-and-spas",
    # New monetization leaves
    "golf carts": "golf-carts",
    "window tint": "window-tint-and-wraps",
    "window tinting": "window-tint-and-wraps",
    "auto glass": "auto-glass",
    "windshield repair": "auto-glass",
    "marine supply": "marine-supply",
    "boat parts": "marine-supply",
    "garage door": "garage-doors",
    "garage doors": "garage-doors",
    "painters": "painters",
    "pressure washing": "pressure-washing-and-exterior-cleaning",
    "property management": "property-management",
    "hearing aids": "hearing-and-audiology",
    "off road shop": "off-road-shops-and-accessories",
    # Core categories (sanity)
    "mechanics": "auto-repair",
    "plumbers": "plumbing",
    "boat rentals": "boat-and-watercraft-rentals",
}

# Misspellings handled by the deterministic alias map (token → canonical) that
# then resolve to a known navigational term. No fuzzy matching relied on here.
_MISSPELL_NAV_CASES: dict[str, str] = {
    "plummer": "plumbing",          # plummer -> plumber
    "barbar": "hair-salons-and-barbers",  # barbar -> barber
    "resturant": "restaurants",     # resturant -> restaurant
    "cofee": "cafes-and-coffee",    # cofee -> coffee
    "grommer": "grooming",          # grommer -> groomer
    "windsheild repair": "auto-glass",  # windsheild -> windshield
}


@pytest.mark.parametrize("variant,slug", sorted(_NAV_CASES.items()))
def test_navigational_phrasings_route(variant: str, slug: str) -> None:
    norm = _normalize(variant)
    assert norm in _QUERY_TO_LEAF, (variant, norm, "normalized form not a known term")
    assert _QUERY_TO_LEAF[norm] == slug, (variant, norm, _QUERY_TO_LEAF[norm])


@pytest.mark.parametrize("variant,slug", sorted(_MISSPELL_NAV_CASES.items()))
def test_misspelled_phrasings_route(variant: str, slug: str) -> None:
    norm = _normalize(variant)
    assert norm in _QUERY_TO_LEAF, (variant, norm)
    assert _QUERY_TO_LEAF[norm] == slug, (variant, norm, _QUERY_TO_LEAF[norm])


# --- 2. keyword-search needle expansion -----------------------------------
# Mirrors app.search.routes._search_needles: needles from the query AND its
# spell-corrected form. Each query must yield the canonical needle that matches
# the provider's Google primary type / category.
_NEEDLE_CASES: tuple[tuple[str, str], ...] = (
    ("golf", "golf course"),
    ("driving range", "golf course"),
    ("golf simulator", "golf course"),
    ("toptracer", "golf course"),
    ("pool cleaner", "pool cleaning"),
    ("pool service", "pool cleaning"),
    ("window tint", "tint"),
    ("auto glass", "windshield"),
    ("property management", "rental management"),
    ("garage door", "overhead door"),
    # misspellings via the alias map
    ("windsheild", "windshield"),
    ("detialing", "detailing"),
    ("laundrymat", "laundromat"),
)


def _needles(q: str) -> set[str]:
    out = set(_category_needle_set(q.strip().lower()))
    corrected = spell_correct(q.strip().lower())
    if corrected and corrected != q.strip().lower():
        out |= set(_category_needle_set(corrected))
    return out


@pytest.mark.parametrize("query,expected_needle", _NEEDLE_CASES)
def test_search_needles_reach_category(query: str, expected_needle: str) -> None:
    needles = _needles(query)
    assert expected_needle in needles, (query, expected_needle, sorted(needles))
