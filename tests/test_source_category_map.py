"""Tests for the Source Category Crosswalk (businesses + events + locality).

These lock the parity contract: golakehavasu's on-the-water operators land in
charters/tours/fishing-guides (never plain rentals), ambiguous tags defer to the
name, and out-of-area listings resolve to an excluded region.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contrib.source_category_map import (
    CANONICAL_EVENT_CATEGORIES,
    HAVASU_CORE,
    KNOWN_BUSINESS_SOURCE_CATEGORIES,
    KNOWN_EVENT_SOURCE_CATEGORIES,
    is_out_of_area,
    map_business_leaf,
    map_event_category,
    normalize_source_category,
    resolve_region,
)

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"


def _all_leaf_slugs() -> set[str]:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for dept in data.values():
        slugs.update(dept.get("leaves", {}))
    return slugs


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Restaurant/Bar", "restaurant bar"),
        ("Boat Rental With Captain", "boat rental with captain"),
        ("Family-Fun", "family fun"),
        ("Breweries and Wine Bar", "breweries and wine bar"),
        ("Gaming & Casinos", "gaming and casinos"),
        ("  Off-Road  ", "off road"),
        ("Hotels/Motels/Suites", "hotels motels suites"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_source_category(raw: str | None, expected: str) -> None:
    assert normalize_source_category(raw) == expected


# ---------------------------------------------------------------------------
# Business crosswalk — the parity contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cvb_category,leaf",
    [
        # On the water — the whole point: charters/tours/fishing are NOT rentals.
        ("Charters", "boat-tours-and-charters"),
        ("Boat Rental With Captain", "boat-tours-and-charters"),
        ("Water Tours", "boat-tours-and-charters"),
        ("Fishing", "fishing-charters-and-guides"),
        ("Fishing Guide", "fishing-charters-and-guides"),
        ("Launch Ramps and Marinas", "marinas-and-launch-ramps"),
        ("Beaches and Swimming", "beaches-and-swim-areas"),
        # Outdoors
        ("Parks", "parks-and-playgrounds"),
        ("Dog Parks", "dog-parks"),
        ("Hiking", "hiking-trails"),
        ("Difficult Hikes with Big Payoffs", None),  # not an exact key -> unmapped (CI catches)
        ("Birding", "wildlife-and-nature"),
        ("Golf", "golf-courses"),
        # Things to do
        ("Attractions", "landmarks-and-sights"),
        ("Family-Fun", "family-fun-and-arcades"),
        ("Venues", "event-venues"),
        ("Gaming and Casinos", "casinos-and-gaming"),
        ("Movie Theaters", "theaters-and-cinema"),
        ("Performing Arts", "theaters-and-cinema"),
        # Eat / lodging / shopping / transport
        ("Restaurant/Bar", "restaurants"),
        ("Breweries and Wine Bar", "bars-and-breweries"),
        ("Hotels/Motels/Suites", "hotels-and-motels"),
        ("Resorts", "hotels-and-motels"),
        ("RV Parks", "rv-parks-and-campgrounds"),
        ("Vacation Rentals/Condos", "vacation-rentals"),
        ("Transportation", "shuttles-and-transportation"),
    ],
)
def test_map_business_leaf_direct(cvb_category: str, leaf: str | None) -> None:
    assert map_business_leaf(cvb_category) == leaf


def test_all_mapped_leaves_exist_in_taxonomy() -> None:
    """Every leaf the crosswalk can emit must be a real taxonomy leaf.

    (wildlife-and-nature + event-venues are added by PR B; this test tolerates
    their absence until then so PR A stays green standalone.)
    """
    leaves = _all_leaf_slugs() | {"wildlife-and-nature", "event-venues"}
    emitted: set[str] = set()
    for cat in KNOWN_BUSINESS_SOURCE_CATEGORIES:
        # feed a neutral name so ambiguous tags return their default leaf
        leaf = map_business_leaf(cat, name="Acme Company")
        if leaf:
            emitted.add(leaf)
    missing = emitted - leaves
    assert not missing, f"crosswalk emits non-existent leaves: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Name signal lifts / ambiguous tags
# ---------------------------------------------------------------------------


def test_name_lifts_boating_to_charter() -> None:
    # generic "boating" tag, but the name says captained charter
    assert map_business_leaf("Boating", name="Lake Havasu Luxury Charter LLC") == "boat-tours-and-charters"


def test_name_lifts_boating_to_marina() -> None:
    assert map_business_leaf("Boating", name="Havasu Springs Marina") == "marinas-and-launch-ramps"


def test_boating_without_name_signal_defaults_to_rentals() -> None:
    assert map_business_leaf("Boating", name="Havasu Boat Co") == "boat-and-watercraft-rentals"


def test_water_sports_kayak_name_lifts_to_paddle() -> None:
    assert map_business_leaf("Water Sports", name="Havasu Kayak & Paddle Rentals") == "kayak-and-paddle"


def test_water_sports_default_jetski() -> None:
    assert map_business_leaf("Water Sports", name="Havasu Fun Rentals") == "jet-ski-and-watersports"


def test_guided_tour_water_name_is_charter() -> None:
    assert map_business_leaf("Guided Tour", name="London Bridge Jet Boat Tour") == "boat-tours-and-charters"


def test_guided_tour_land_name_is_sightseeing() -> None:
    assert map_business_leaf("Guided Tour", name="Route 66 Desert Jeep Tours") == "tours-and-sightseeing"


def test_water_tours_named_kayak_lifts_to_paddle() -> None:
    # direct water leaf, but a stronger name signal refines it
    assert map_business_leaf("Water Tours", name="Havasu Kayak Tours") == "kayak-and-paddle"


def test_off_road_tag_rental_name_lifts_to_utv_rentals() -> None:
    # Session 6b: the CVB "off road"/"ohv" tag maps to the off-road-and-ohv
    # *trails* leaf, but a UTV *rental* name lifts it to the rentals leaf.
    assert map_business_leaf("Off Road", name="Desert Experience UTV Offroad Rentals") == "utv-and-offroad-rentals"
    assert map_business_leaf("OHV", name="Havasu RZR Rentals") == "utv-and-offroad-rentals"


def test_off_road_tag_trailhead_name_stays_trails() -> None:
    # No rental language in the name -> no lift; a genuine trailhead stays put.
    assert map_business_leaf("Off Road", name="SARA Park OHV Trailhead") == "off-road-and-ohv"


def test_water_sports_tag_utv_rental_name_lifts_to_utv() -> None:
    # "water sports" is an ambiguous tag: the name decides. A UTV-rental name
    # wins over the jet-ski default.
    assert map_business_leaf("Water Sports", name="Wet Monkey Powersport Rentals") == "utv-and-offroad-rentals"


def test_shopping_name_routing() -> None:
    assert map_business_leaf("Shopping", name="Havasu Jewelry Co") == "jewelry"
    assert map_business_leaf("Shopping", name="Main Street Hardware") == "hardware-and-home-improvement"
    assert map_business_leaf("Shopping", name="Just A Store") == "gifts-and-boutiques"


def test_unknown_category_returns_none() -> None:
    assert map_business_leaf("Totally Made Up Category") is None
    assert map_business_leaf(None) is None
    assert map_business_leaf("") is None


# ---------------------------------------------------------------------------
# Event crosswalk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,canonical",
    [
        ("boating", "boating-and-lake"),
        ("boat-show", "boating-and-lake"),
        ("racing", "racing-and-motorsports"),
        ("car-show", "racing-and-motorsports"),
        ("air-show", "air-show"),
        ("music", "music"),
        ("london-bridge-days", "festival"),
        ("comedy-show", "comedy"),
        ("movies", "film"),
        ("farmers-market", "farmers-market"),
        ("fundraiser", "fundraiser-and-charity"),
        ("christmas", "holiday"),
        ("veterans-military", "military-and-veterans"),
        ("uncategorized", "misc"),
        ("select-category", "misc"),
    ],
)
def test_map_event_category(src: str, canonical: str) -> None:
    assert map_event_category(src) == canonical


def test_map_event_category_unknown() -> None:
    assert map_event_category("brand-new-tag") is None
    assert map_event_category(None) is None


def test_event_categories_count_reasonable() -> None:
    # ~22 canonical buckets per the plan (River Scene's 90 tags, grouped)
    assert 20 <= len(CANONICAL_EVENT_CATEGORIES) <= 30


def test_known_sets_nonempty() -> None:
    assert KNOWN_BUSINESS_SOURCE_CATEGORIES
    assert KNOWN_EVENT_SOURCE_CATEGORIES


# ---------------------------------------------------------------------------
# Locality / region exclusion gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "signal,region",
    [
        ("Lake Havasu City, AZ", HAVASU_CORE),
        ("123 Main St, Lake Havasu City", HAVASU_CORE),
        ("Laughlin, NV", "laughlin-bullhead"),
        ("Bullhead City", "laughlin-bullhead"),
        ("Needles, CA", "needles"),
        ("Parker, AZ", "parker"),
        ("Oatman, AZ", "oatman"),
        ("Hoover Dam", "other-daytrip"),
        (None, HAVASU_CORE),
    ],
)
def test_resolve_region(signal: str | None, region: str) -> None:
    assert resolve_region(signal) == region


def test_resolve_region_any_signal_out_of_area() -> None:
    # if any signal is out of area, the listing is out of area
    assert resolve_region("Lake Havasu City", "Parker, AZ") == "parker"


def test_is_out_of_area() -> None:
    assert not is_out_of_area(HAVASU_CORE)
    assert is_out_of_area("parker")
    assert is_out_of_area("laughlin-bullhead")
    assert not is_out_of_area(None)
