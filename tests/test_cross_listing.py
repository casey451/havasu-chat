"""Hybrid-venue cross-listing map behaves safely.

Locks: empty/unknown leaves return an empty set (no accidental surfacing), the
lookup is case/whitespace-insensitive, and any curated value is a frozenset of
slugs — so a populated entry can only ADD named entities to a leaf.
"""

from __future__ import annotations

from app.categories import cross_listing
from app.categories.cross_listing import (
    CROSS_LISTED_ENTITY_SLUGS,
    cross_listed_slugs_for_leaf,
)


def test_unknown_leaf_returns_empty() -> None:
    assert cross_listed_slugs_for_leaf("family-fun-and-arcades") == frozenset()
    assert cross_listed_slugs_for_leaf(None) == frozenset()
    assert cross_listed_slugs_for_leaf("") == frozenset()


def test_lookup_is_normalized() -> None:
    """A curated entry resolves regardless of case/whitespace in the query."""
    cross_listing.CROSS_LISTED_ENTITY_SLUGS["demo-leaf"] = frozenset({"the-spot"})
    try:
        assert cross_listed_slugs_for_leaf("  Demo-Leaf ") == frozenset({"the-spot"})
    finally:
        cross_listing.CROSS_LISTED_ENTITY_SLUGS.pop("demo-leaf", None)


def test_all_curated_values_are_frozensets_of_str() -> None:
    for leaf_slug, slugs in CROSS_LISTED_ENTITY_SLUGS.items():
        assert isinstance(leaf_slug, str)
        assert isinstance(slugs, frozenset)
        assert all(isinstance(s, str) for s in slugs)
