"""P1-1.1 regression: the resolve()->run_query listing path must apply
within-category relevance ranking, not just the Tier-2 business-listing shortcut.

Before this fix, `_build_providers` called `build_business_list` without
`intent_query`, so category-resolved listing queries ("where can I rent a kayak?"
-> Rentals bucket) were re-sorted by rating-then-name and the relevance ranking
was discarded. These tests pin the threading through `_render` -> `_build_providers`.
"""

from __future__ import annotations

from datetime import date

from app.chat.intents.queries import QueryResult
from app.chat.intents.runtime import _build_providers, _render


def _rows(*providers: dict) -> list[dict]:
    return [{"type": "provider", **p} for p in providers]


def _result() -> QueryResult:
    # Higher-rated non-matching row vs. lower-rated rental-named row.
    rows = _rows(
        {
            "name": "Boat Body Shop",
            "slug": "boat-body-shop",
            "google_rating": 4.9,
            "google_primary_category": "Boat repair shop",
        },
        {
            "name": "Havasu Watercraft Rental",
            "slug": "havasu-watercraft-rental",
            "google_rating": 4.1,
            "google_primary_category": "Boat rental service",
        },
    )
    return QueryResult("find_service", "providers", rows, "rentals", "Where to rent:", label="rentals")


def test_build_providers_threads_query_for_relevance() -> None:
    _voice, ctype, data = _build_providers(_result(), "where can I rent a kayak?")
    assert ctype == "business_list"
    # "rent" (substring of "rental") lifts the rental row above the higher-rated
    # body shop, which matches none of the distinctive terms.
    assert data["items"][0]["name"] == "Havasu Watercraft Rental"
    assert data["items"][1]["name"] == "Boat Body Shop"


def test_build_providers_no_query_falls_back_to_rating() -> None:
    # No query -> empty rank terms -> legacy rating-then-name sort (zero regression).
    _voice, _ctype, data = _build_providers(_result(), None)
    assert data["items"][0]["name"] == "Boat Body Shop"


def test_render_passes_query_through_to_providers() -> None:
    _voice, ctype, data = _render(
        _result(), today=date.today(), query="where can I rent a kayak?"
    )
    assert ctype == "business_list"
    assert data["items"][0]["name"] == "Havasu Watercraft Rental"
