"""Unit tests for the pure planning logic of scripts/backfill_leaf_categories.

Covers ``provider_types`` (token ordering, JSON-string google_categories) and
``target_leaf`` (delegates to the single-source leaf resolver, incl. the
event-venue guardrail). DB-touching ``run()`` is gated/dry-run and exercised by
the resolver + apply_taxonomy_remap suites; these lock the offline planning.
"""

from __future__ import annotations

from scripts.backfill_leaf_categories import (
    GENERIC_PRIMARY_TYPES,
    is_generic_primary,
    provider_types,
    target_leaf,
)


def test_provider_types_is_primary_only() -> None:
    """Only the primary type is used; the noisy secondary array is ignored
    (2026-06-12 backfill incident fix)."""
    assert provider_types("bowling_alley", ["establishment", "point_of_interest"]) == [
        "bowling_alley"
    ]
    assert provider_types("department_store", ["shoe_store", "jewelry_store"]) == [
        "department_store"
    ]


def test_provider_types_no_primary_is_empty() -> None:
    """No primary type → unmapped (existing leaf kept), never guessed from
    secondaries."""
    assert provider_types(None, '["gas_station", "convenience_store"]') == []
    assert provider_types(None, None) == []
    assert provider_types("", []) == []


def test_target_leaf_reassigns_bowling_to_arcades() -> None:
    slug, non_directory = target_leaf("bowling_alley", [])
    assert slug == "family-fun-and-arcades"
    assert non_directory is False


def test_target_leaf_event_venue_is_non_directory() -> None:
    slug, non_directory = target_leaf("event_venue", [])
    assert slug is None
    assert non_directory is True


def test_target_leaf_unmapped_returns_none_not_guess() -> None:
    slug, non_directory = target_leaf("some_unknown_type", [])
    assert slug is None
    assert non_directory is False


def test_generic_primary_types_are_flagged() -> None:
    """Every generic umbrella primary is caught by the hard guard so it can
    never drive a reassignment (2026-06-12 incident hardening)."""
    for tok in ("service", "supplier", "store", "consultant", "establishment", "point_of_interest"):
        assert tok in GENERIC_PRIMARY_TYPES
        assert is_generic_primary(tok) is True
    # case/whitespace-insensitive, matching the resolver's normalization.
    assert is_generic_primary("  Service  ") is True
    assert is_generic_primary("STORE") is True


def test_is_generic_primary_passes_specific_and_empty_types() -> None:
    """Specific types and absent primaries are NOT generic (they go through the
    normal resolver path, not the skip)."""
    for tok in ("bowling_alley", "hamburger_restaurant", "doctor", "gym"):
        assert is_generic_primary(tok) is False
    assert is_generic_primary(None) is False
    assert is_generic_primary("") is False
