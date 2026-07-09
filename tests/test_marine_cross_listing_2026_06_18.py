"""Issue 1 (2026-06-18): genuine marine repair shops cross-listed onto boat-repair.

Hybrid "Auto & Marine" shops (and a few marine repair shops with no primary leaf)
were missing from the boat-repair-and-service leaf because leaf pages render only
the PRIMARY entity_categories link. The curated cross_listing map surfaces them on
that leaf without touching their primary. These tests pin the curated set and guard
against a future re-run re-adding the non-repair categories (dealers, rentals,
storage, tours, retail) that were deliberately trimmed.
"""

from __future__ import annotations

from app.categories.cross_listing import (
    CROSS_LISTED_ENTITY_SLUGS,
    cross_listed_slugs_for_leaf,
)

_LEAF = "boat-repair-and-service"


def test_named_hybrids_and_repair_shops_are_cross_listed() -> None:
    slugs = cross_listed_slugs_for_leaf(_LEAF)
    # The issue's named auto+marine hybrids, plus clear repair/service shops.
    for s in (
        "everything-tire-automotive-marine",
        "brandon-s-auto-rv-marine",
        "balistreri-s-auto-marine",
        "barnacle-bills-boat-repairs",
        "hy-tech-watercraft-repair",
        "mark-s-marine-service-llc",
    ):
        assert s in slugs


def test_non_repair_categories_are_not_cross_listed() -> None:
    """Rentals, dealers/brokers, storage, tours, retail must stay off boat-repair."""
    slugs = cross_listed_slugs_for_leaf(_LEAF)
    for bad in (
        "cabana-boat-rentals",  # rental
        "lake-havasu-jet-ski-rentals",  # rental
        "germaine-marine",  # boat-sales (dealer)
        "havasu-rv-marine",  # car-dealership
        "the-boat-broker",  # broker (sales)
        "boat-storage-of-lake-havasu",  # storage
        "west-marine",  # retail
        "boat-house-grill",  # restaurant
        "havasu-tiki-boat",  # tours
    ):
        assert bad not in slugs


def test_existing_arcade_cross_listing_unchanged() -> None:
    assert "the-spot" in cross_listed_slugs_for_leaf("family-fun-and-arcades")


def test_cross_listed_slugs_are_clean_and_deduped() -> None:
    raw = CROSS_LISTED_ENTITY_SLUGS[_LEAF]
    assert isinstance(raw, frozenset)  # set semantics dedupe
    for slug in raw:
        assert slug == slug.lower().strip()
        assert " " not in slug


def test_unknown_leaf_returns_empty() -> None:
    assert cross_listed_slugs_for_leaf("not-a-real-leaf") == frozenset()
