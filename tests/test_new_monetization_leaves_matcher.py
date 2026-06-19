"""Unit tests for the pure matcher in
``scripts/backfill_new_monetization_leaves_2026_06`` (the 2026-06-19 monetization
leaf backfill).

DB-free: locks the name/Google-type matching rules so a future edit can't
silently widen or break them. The DB-touching ``run()`` is gated/dry-run and was
exercised against prod on 2026-06-19; these tests pin the offline planning logic.

Key invariants:
  * PRIMARY-only by default — a secondary Google category never drives a match
    unless ``--wide`` is on (the 2026-06-19 "Havasu Handyman Services -> painters"
    false-positive guard).
  * ``--wide`` only fills the empty, name-poor leaves, and NEVER painters.
  * a strong name match always wins; an ambiguous strong hit returns None.
"""

from __future__ import annotations

import pytest

from scripts.backfill_new_monetization_leaves_2026_06 import (
    NEW_LEAVES,
    WIDE_SECONDARY_SLUGS,
    _RULES,
    match_new_leaf,
)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Premier Golf Cars", "golf-carts"),
        ("Havasu Off-Road & 4x4 Accessories", "off-road-shops-and-accessories"),
        ("Desert Tint & Wraps", "window-tint-and-wraps"),
        ("Window Tint Pros", "window-tint-and-wraps"),
        ("Lake Havasu Auto Glass", "auto-glass"),
        ("Bullseye Auto Glass & Chip Repair", "auto-glass"),
        ("Frank's Trailer Repair, LLC", "trailer-sales-and-repair"),
        ("Havasu Marine Supply & Boat Parts", "marine-supply"),
        ("Integrity Garage Door Repair", "garage-doors"),
        ("Premier House Painting LLC", "painters"),
        ("Blue Water Pressure Washing", "pressure-washing-and-exterior-cleaning"),
        ("Havasu Junk Removal & Hauling", "junk-removal-and-hauling"),
        ("Sun Screens of Havasu patio covers", "shade-screens-and-patio-covers"),
        ("Freedom Point Property Management", "property-management"),
        ("Desert Hearing Aid Center", "hearing-and-audiology"),
    ],
)
def test_name_matches(name: str, expected: str) -> None:
    assert match_new_leaf(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "Joe's Boat Rentals",          # rental, not supply
        "Havasu Boat Repair",          # repair, not supply
        "Havasu Auto Body & Paint",    # auto body, not a painter
        "Sunset Trailer Park",         # trailer PARK, not trailer sales
        "Riverside RV Park",
        "Mountain Trail Off-Road Tours",  # tour, not a shop
        "Tropic Tanning Salon",        # tanning, not window tint
        "Lash & Brow Studio",          # beauty, not window tint
        "McCulloch Restaurant",
    ],
)
def test_negative_guards(name: str) -> None:
    assert match_new_leaf(name) is None


def test_default_ignores_secondary_categories() -> None:
    """A general contractor that merely *lists* painting must NOT move to
    painters — the 2026-06-19 false positive. Default mode never reads the
    secondary array."""
    assert (
        match_new_leaf(
            "Havasu Handyman Services", "general_contractor", "Painter, Painting"
        )
        is None
    )


def test_wide_never_fills_painters() -> None:
    """Even with --wide, painters is excluded from the secondary sweep, so a GC
    listing 'Painter' as a secondary still does not move."""
    assert (
        match_new_leaf(
            "Havasu Handyman Services",
            "general_contractor",
            "Painter, Painting",
            wide_slugs=WIDE_SECONDARY_SLUGS,
        )
        is None
    )


@pytest.mark.parametrize(
    "name,primary,secondary,expected",
    [
        ("Coast Detail Shop", "car_repair", "Window tinting service", "window-tint-and-wraps"),
        ("Havasu Boat Center", "store", "Marine supplies store", "marine-supply"),
        ("ABC Hauling", "service", "Junk removal service", "junk-removal-and-hauling"),
    ],
)
def test_wide_fills_empty_leaves_from_secondary(
    name: str, primary: str, secondary: str, expected: str
) -> None:
    # Off in default mode (PRIMARY-only)...
    assert match_new_leaf(name, primary, secondary) is None
    # ...on only with --wide and only for the allowed empty leaves.
    assert match_new_leaf(name, primary, secondary, wide_slugs=WIDE_SECONDARY_SLUGS) == expected


def test_strong_name_match_wins_over_wide() -> None:
    """A confident name signal resolves in stage 1 regardless of --wide."""
    assert (
        match_new_leaf("Premier Golf Cars", "store", "anything", wide_slugs=WIDE_SECONDARY_SLUGS)
        == "golf-carts"
    )


def test_every_rule_slug_is_a_real_new_leaf() -> None:
    """No rule can target a slug the script doesn't know how to create."""
    rule_slugs = {slug for slug, _, _ in _RULES}
    assert rule_slugs <= set(NEW_LEAVES)
    assert WIDE_SECONDARY_SLUGS <= set(NEW_LEAVES)
    assert "painters" not in WIDE_SECONDARY_SLUGS
