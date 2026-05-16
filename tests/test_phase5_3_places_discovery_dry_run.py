"""Phase 5.3 — regression guard for cdf3d0c (places_discovery dry-run +
--category produces empty intersection).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib.google_places_scraper import (
    DISCOVERY_CATEGORY_TO_DOMAINS,
    load_categories_for_discovery,
)

CATEGORIES_PATH = Path("scripts/places_categories.json")


@pytest.mark.parametrize(
    "slug",
    sorted(DISCOVERY_CATEGORY_TO_DOMAINS.keys()),
)
def test_dry_run_with_category_returns_nonzero_for_every_slug(slug: str) -> None:
    """--dry-run + --category <slug> must return >=1 category for every
    known Tier-1 slug. Pre-cdf3d0c this silently returned 0 for any slug
    whose labels didn't happen to overlap with the legacy DRY_RUN_LABELS
    frozenset (which excluded home-property-services entirely)."""
    cats = load_categories_for_discovery(
        CATEGORIES_PATH, dry_run=True, category_slug=slug
    )
    assert len(cats) > 0, (
        f"--dry-run --category {slug!r} returned 0 categories. "
        "Regression of cdf3d0c — DRY_RUN_LABELS intersection bug is back."
    )


def test_dry_run_eat_drink_category_returns_exactly_two_preview_labels() -> None:
    """--dry-run --category must use the first-2-label preview (cdf3d0c);
    eat-drink has many labels so this guards the [:2] cap."""
    cats = load_categories_for_discovery(
        CATEGORIES_PATH, dry_run=True, category_slug="eat-drink"
    )
    assert len(cats) == 2


def test_dry_run_without_category_returns_legacy_5_label_sample() -> None:
    """--dry-run without --category preserves the legacy 5-label sample
    behaviour (this is the original dry-run mode; unchanged by cdf3d0c)."""
    cats = load_categories_for_discovery(
        CATEGORIES_PATH, dry_run=True, category_slug=None
    )
    labels = {c["label"] for c in cats}
    expected = {
        "restaurants",
        "coffee shops",
        "hair salons",
        "auto repair",
        "boat rentals",
    }
    assert labels == expected, (
        f"Legacy 5-label dry-run sample changed. Got: {labels}, expected: {expected}"
    )
