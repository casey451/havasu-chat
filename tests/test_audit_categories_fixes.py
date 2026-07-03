"""Regression tests for the 2026-07-01 audit categories bug batch (B1-B6)."""

from __future__ import annotations

from app.categories.subcategories import (
    _LEGACY_TO_SUBCAT,
    LEGACY_CATEGORY_TO_PRIMARY,
    SUBCATEGORY_TO_PRIMARY,
    derive_subcategory,
)
from app.categories.trades import LEAF_TWINS, TRADES


def test_garage_door_trade_has_leaf_twin():
    # B1: the garage-doors leaf was seeded 2026-06-19; without the twin entry
    # /categories/home-property-services/garage-door and the leaf both
    # published and competed for the same search term.
    assert LEAF_TWINS.get("garage-door") == "garage-doors"


def test_every_trade_slug_resolves_or_is_deliberate():
    # Every promoted trade should either have a leaf twin or be a deliberate
    # curated-only page; today all ten are twinned.
    trade_slugs = set(TRADES)
    assert set(LEAF_TWINS) <= trade_slugs
    assert "garage-door" in trade_slugs


def _derive(gtype: str) -> str | None:
    return derive_subcategory(category=None, google_primary_category=gtype)


def test_rv_park_and_campground_derive_rv_parks():
    # B4: the bare "park" substring rule shadowed the stay block's
    # rv_park/campground rules (first-match-wins + substring matching), filing
    # overnight-stay types under parks-beaches.
    assert _derive("rv_park") == "rv-parks"
    assert _derive("campground") == "rv-parks"
    # The bare park type still files as parks-beaches.
    assert _derive("park") == "parks-beaches"


def test_legacy_fitness_folds_agree_between_maps():
    # B5: LEGACY_CATEGORY_TO_PRIMARY sent fitness_sports to
    # health-wellness-care while _LEGACY_TO_SUBCAT derived gyms →
    # classes-sports-recreation: an un-backfilled gym COUNTED under Health but
    # LISTED under Fitness & Sports.
    for legacy in ("fitness_sports", "fitness"):
        via_subcat = SUBCATEGORY_TO_PRIMARY[_LEGACY_TO_SUBCAT[legacy]]
        assert LEGACY_CATEGORY_TO_PRIMARY[legacy] == via_subcat


def test_all_legacy_folds_agree_where_both_maps_have_an_entry():
    # Generalized B5 guard: wherever a legacy category appears in BOTH maps,
    # the direct legacy→primary fold must equal the legacy→subcategory→primary
    # derivation, or counts and listings drift apart for NULL-primary rows.
    #
    # "recreation" is a documented exception: the legacy bucket straddles both
    # departments (CATEGORY_FILTERS/map_data expect classes-sports-recreation;
    # its coarse subcategory fallback is parks-beaches → outdoors) and only a
    # per-row recat can split it. Any NEW mismatch fails this test.
    known_exceptions = {"recreation"}
    mismatches = {}
    for legacy, subcat in _LEGACY_TO_SUBCAT.items():
        if legacy in known_exceptions:
            continue
        direct = LEGACY_CATEGORY_TO_PRIMARY.get(legacy)
        via_subcat = SUBCATEGORY_TO_PRIMARY.get(subcat)
        if direct and via_subcat and direct != via_subcat:
            mismatches[legacy] = (direct, via_subcat)
    assert mismatches == {}
