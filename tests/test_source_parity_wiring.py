"""PR C wiring tests: golakehavasu leaf mapping + water-misfiled routing.

Verifies the audit's core fix end-to-end at the unit level: the CVB source
category resolves to the precise leaf, and charters/fishing-guides trapped in
the rentals leaf are routed out.
"""

from __future__ import annotations

import pytest

from app.categories.water_misfiled_rules import classify_water_misfiled_leaf
from app.contrib.golakehavasu_partners import map_cvb_leaf
from app.contrib.source_category_map import map_business_leaf

# ---------------------------------------------------------------------------
# map_cvb_leaf — the loader's crosswalk entry point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cvb,name,leaf",
    [
        ("Charters", "Arizona's Fun on the Water", "boat-tours-and-charters"),
        ("Boat Rental With Captain", "Channel Catz", "boat-tours-and-charters"),
        ("Water Tours", "Dixie Belle", "boat-tours-and-charters"),
        ("Fishing Guide", "Ron's Fishing Guide Service", "fishing-charters-and-guides"),
        ("Restaurant/Bar", "Lobster 3 Ways", "restaurants"),
        ("Birding", "Havasu NWR", "wildlife-and-nature"),
        ("Venues", "Stetson Winery Event Center", "event-venues"),
        # ambiguous CVB tag -> name decides (decision #4)
        ("Boating", "Lake Havasu Luxury Charter LLC", "boat-tours-and-charters"),
        ("Boating", "Havasu Springs Marina", "marinas-and-launch-ramps"),
    ],
)
def test_map_cvb_leaf(cvb: str, name: str, leaf: str) -> None:
    assert map_cvb_leaf(cvb, name) == leaf


def test_map_cvb_leaf_unknown_falls_to_none() -> None:
    # an unrecognised CVB tag returns None so the loader keeps its Tier-1 / default
    assert map_cvb_leaf("Some Day-Trip Town", "Whatever") is None


def test_long_form_hikes_map() -> None:
    assert map_business_leaf("Moderate Hikes with Climbing") == "hiking-trails"
    assert (
        map_business_leaf("Difficult Hikes with Long Slopes or Scrambling")
        == "hiking-trails"
    )


# ---------------------------------------------------------------------------
# water_misfiled_rules — charters/fishing routed out, rentals stay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,leaf",
    [
        ("Captain Bob's Boat Adventures", "boat-tours-and-charters"),
        ("London Bridge Jet Boat Tour", "boat-tours-and-charters"),
        ("Havasu Net 'Em Guide Service", "fishing-charters-and-guides"),
        ("Ron's Fishing Guide Service", "fishing-charters-and-guides"),
    ],
)
def test_water_misfiled_routes_charters_and_guides(name: str, leaf: str) -> None:
    assert classify_water_misfiled_leaf(name) == leaf


@pytest.mark.parametrize(
    "name",
    [
        # genuine rentals stay put (None = leave in boat-and-watercraft-rentals)
        "Tortuga Boat Rentals",
        "Lake Havasu Jet Ski Rentals",
        "Havasu Kayak Rentals",
        "Nautical Watercraft Rentals",
    ],
)
def test_water_misfiled_keeps_genuine_rentals(name: str) -> None:
    assert classify_water_misfiled_leaf(name) is None


def test_water_misfiled_detailing_still_wins() -> None:
    # existing behaviour preserved: detailing shops route to detailing, not charter
    assert classify_water_misfiled_leaf("Premier Marine Detailing") == "auto-marine-detailing"
