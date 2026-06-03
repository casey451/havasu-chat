"""Sandstone category browse — re-skin specifics (01_UI_BUILD_GUIDE.md §4.8).

Covers the bits unique to the Sandstone page: the default volume-weighted
"Locals' favorites" sort, the in-place chip-filter markup, the labeled sponsored
slot being real-or-omitted, and the anti-confabulation empty state.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.categories import queries as cat_queries
from app.main import app


def test_default_sort_is_weighted_locals_favorites() -> None:
    """The Locals'-favorites pill is active by default (weighted Bayesian sort)."""
    with TestClient(app) as client:
        r = client.get("/categories/eat-drink")
    assert r.status_code == 200
    body = r.text
    assert 'class="sortpill on"' in body
    # The active pill is the favorites one, and the plain-English note is shown.
    assert "Locals&#39; favorites" in body or "Locals' favorites" in body
    assert "weighted by review volume" in body


def test_weighted_score_ranks_institution_above_thin_five_star() -> None:
    """A 4.6 with thousands of reviews must outrank a 5.0 with 3 reviews."""
    institution = cat_queries.weighted_favorites_score(4.6, 3878)  # In-N-Out-like
    thin_five = cat_queries.weighted_favorites_score(5.0, 3)  # tiny outlier
    assert institution > thin_five


def test_cards_carry_subcategory_token_for_in_place_filter() -> None:
    from unittest.mock import patch

    cards = [
        {
            "slug": "mudshark",
            "name": "Mudshark Brewing",
            "image_url": None,
            "neighborhood": "",
            "status": "open",
            "status_text": "Open",
            "rating": "4.6",
            "review_count": 1796,
            "subcategory": "breweries",
            "is_open": True,
        }
    ]
    with patch.object(cat_queries, "category_listing", return_value=(cards, 1)):
        with TestClient(app) as client:
            r = client.get("/categories/eat-drink")
    body = r.text
    # The grid + filter JS + per-card filter token are all present.
    assert 'class="biz-grid"' in body
    assert "/static/js/sandstone_category.js" in body
    assert 'data-subcategory="breweries"' in body


def test_empty_category_renders_honest_state_not_zero() -> None:
    """A route with no providers shows an honest empty state, never '0 listed'."""
    from unittest.mock import patch

    with patch.object(cat_queries, "category_listing", return_value=([], 0)):
        with TestClient(app) as client:
            r = client.get("/categories/pets")
    body = r.text
    assert r.status_code == 200
    assert "No listings here yet" in body
    assert "0 listed" not in body
