"""Sandstone category browse — re-skin specifics (01_UI_BUILD_GUIDE.md §4.8).

Covers the bits unique to the Sandstone page: the default volume-weighted
"Locals' favorites" sort, the in-place chip-filter markup, the labeled sponsored
slot being real-or-omitted, and the anti-confabulation empty state.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.categories import queries as cat_queries
from app.main import app


def test_weighted_score_ranks_institution_above_thin_five_star() -> None:
    """A 4.6 with thousands of reviews must outrank a 5.0 with 3 reviews."""
    institution = cat_queries.weighted_favorites_score(4.6, 3878)  # In-N-Out-like
    thin_five = cat_queries.weighted_favorites_score(5.0, 3)  # tiny outlier
    assert institution > thin_five


def test_cards_carry_subcategory_token_for_in_place_filter() -> None:
    """A Lake directory card carries its ``data-subcategory`` token (the
    in-place filter hook). The desert ``biz-grid`` wrapper + ``sandstone_category.js``
    were removed with the desert template."""
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
            r = client.get("/lake-havasu/restaurants")
    body = r.text
    assert 'data-subcategory="breweries"' in body


def test_cards_render_call_action_when_phone_present() -> None:
    """A card holding a phone shows a tappable Call action (Lake biz card)."""
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
            "phone": "(928) 453-9302",
            "phone_tel": "9284539302",
        }
    ]
    with patch.object(cat_queries, "category_listing", return_value=(cards, 1)):
        with TestClient(app) as client:
            r = client.get("/lake-havasu/restaurants")
    body = r.text
    assert 'href="tel:9284539302"' in body
    assert ">Call</a>" in body


def test_cards_omit_actions_when_no_phone_or_location() -> None:
    """A card lacking phone + directions never renders a dead action button."""
    from unittest.mock import patch

    cards = [
        {
            "slug": "noinfo",
            "name": "Bare Listing",
            "image_url": None,
            "neighborhood": "",
            "status": "open",
            "status_text": "Open",
            "rating": "4.0",
            "review_count": 5,
            "subcategory": "breweries",
            "is_open": True,
            "phone": "",
            "phone_tel": "",
            "directions_url": "",
        }
    ]
    with patch.object(cat_queries, "category_listing", return_value=(cards, 1)):
        with TestClient(app) as client:
            r = client.get("/lake-havasu/restaurants")
    body = r.text
    assert "Bare Listing" in body
    assert "biz-action" not in body


def test_empty_category_renders_honest_state_not_zero() -> None:
    """A route with no providers shows an honest empty state, never '0 listed'."""
    from unittest.mock import patch

    with patch.object(cat_queries, "category_listing", return_value=([], 0)):
        with TestClient(app) as client:
            r = client.get("/lake-havasu/storage")
    body = r.text
    assert r.status_code == 200
    assert "No listings here yet" in body
    assert "0 listed" not in body
