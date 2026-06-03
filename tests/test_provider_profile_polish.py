"""P-1 / P-3 — provider profile breadcrumb URL + address cleanup."""

from __future__ import annotations

from types import SimpleNamespace

from app.providers.queries import _clean_address
from app.providers.view_models import _category_url_for


def test_clean_address_strips_orphan_leading_number() -> None:
    assert _clean_address("2806, 950 N Lake Havasu Ave") == "950 N Lake Havasu Ave"


def test_clean_address_leaves_well_formed_unchanged() -> None:
    assert _clean_address("950 N Lake Havasu Ave, Lake Havasu City, AZ 86403") == (
        "950 N Lake Havasu Ave, Lake Havasu City, AZ 86403"
    )
    assert _clean_address(None) is None
    assert _clean_address("") == ""


def test_category_url_routes_church_to_community_not_explore() -> None:
    # P-1: the breadcrumb must link to the actual category page, preferring the
    # specific tile route (Community) over the broad Services mega.
    church = SimpleNamespace(category="religion_community")
    assert _category_url_for(church) == "/categories/public-civic-resources"


def test_category_url_routes_restaurant_to_eat_drink() -> None:
    rest = SimpleNamespace(category="restaurant")
    assert _category_url_for(rest) == "/categories/eat-drink"


def test_category_url_unknown_category_falls_back_to_explore() -> None:
    assert _category_url_for(SimpleNamespace(category=None)) == "/categories"
    assert _category_url_for(SimpleNamespace(category="totally_made_up")) == "/categories"
