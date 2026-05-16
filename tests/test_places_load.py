"""Unit tests for ``scripts/places_load`` helpers (pure, no DB)."""

from __future__ import annotations

import pytest

from app.contrib.google_places_scraper import DISCOVERY_CATEGORY_TO_DOMAINS
from scripts.places_load import filter_by_category, filter_by_zip


def test_filter_by_category_eat_drink_single_domain() -> None:
    rows = [
        {"place_id": "a", "_first_seen_domain": "food_drink"},
        {"place_id": "b", "_first_seen_domain": "lake_recreation"},
        {"place_id": "c", "_first_seen_domain": "food_drink"},
    ]
    out = filter_by_category(rows, "eat-drink")
    assert [r["place_id"] for r in out] == ["a", "c"]


def test_filter_by_category_health_wellness_multiple_domains() -> None:
    rows = [
        {"place_id": "h", "_first_seen_domain": "health_medical"},
        {"place_id": "f", "_first_seen_domain": "fitness_sports"},
        {"place_id": "z", "_first_seen_domain": "retail"},
    ]
    out = filter_by_category(rows, "health-wellness-care")
    assert [r["place_id"] for r in out] == ["h", "f"]


def test_filter_by_category_drops_missing_first_seen_domain() -> None:
    rows = [{"place_id": "x"}, {"place_id": "y", "_first_seen_domain": "food_drink"}]
    out = filter_by_category(rows, "eat-drink")
    assert [r["place_id"] for r in out] == ["y"]


def test_filter_by_category_unknown_slug_system_exit() -> None:
    rows = [{"place_id": "a", "_first_seen_domain": "food_drink"}]
    with pytest.raises(SystemExit) as excinfo:
        filter_by_category(rows, "not-a-category")
    msg = str(excinfo.value)
    assert "Expected one of:" in msg
    for slug in sorted(DISCOVERY_CATEGORY_TO_DOMAINS):
        assert slug in msg


def test_filter_by_category_empty_input() -> None:
    assert filter_by_category([], "eat-drink") == []


def test_filter_by_category_does_not_mutate_input_rows() -> None:
    rows = [
        {"place_id": "a", "_first_seen_domain": "food_drink"},
        {"place_id": "b", "_first_seen_domain": "lake_recreation"},
    ]
    snapshot = [(r["place_id"], r["_first_seen_domain"]) for r in rows]
    out = filter_by_category(rows, "eat-drink")
    assert out is not rows
    assert len(rows) == 2
    assert [(r["place_id"], r["_first_seen_domain"]) for r in rows] == snapshot
    assert len(out) == 1


# --- filter_by_zip regression guards (Phase 5.4 dispatch fix) ---
#
# Phase 5.4 health-wellness-care dry-run surfaced 3 real LHC rows being
# dropped as non-LHC because their `zip` field was ZIP+4 with the dash
# stripped (e.g. ``864035889`` for ``86403-5889``). Normalize to the
# 5-digit prefix before comparison.


def test_filter_by_zip_bare_lhc_zips_kept() -> None:
    rows = [
        {"place_id": "a", "zip": "86403"},
        {"place_id": "b", "zip": "86404"},
        {"place_id": "c", "zip": "86405"},
        {"place_id": "d", "zip": "86406"},
    ]
    kept, drops = filter_by_zip(rows)
    assert [r["place_id"] for r in kept] == ["a", "b", "c", "d"]
    assert drops == {}


def test_filter_by_zip_plus_four_with_dash_kept() -> None:
    rows = [
        {"place_id": "a", "zip": "86403-5889"},
        {"place_id": "b", "zip": "86404-1234"},
    ]
    kept, drops = filter_by_zip(rows)
    assert [r["place_id"] for r in kept] == ["a", "b"]
    assert drops == {}


def test_filter_by_zip_plus_four_no_dash_kept() -> None:
    # Phase 5.4 dispatch bug: Google returned 864035889/864036710/864035647
    # without the dash, and the exact-string match dropped them as non-LHC.
    rows = [
        {"place_id": "a", "zip": "864035889"},
        {"place_id": "b", "zip": "864036710"},
        {"place_id": "c", "zip": "864035647"},
    ]
    kept, drops = filter_by_zip(rows)
    assert [r["place_id"] for r in kept] == ["a", "b", "c"]
    assert drops == {}


def test_filter_by_zip_non_lhc_dropped() -> None:
    rows = [
        {"place_id": "kingman", "zip": "86401"},
        {"place_id": "bullhead", "zip": "86442"},
        {"place_id": "needles", "zip": "92363"},
    ]
    kept, drops = filter_by_zip(rows)
    assert kept == []
    assert drops == {"non_lhc:86401": 1, "non_lhc:86442": 1, "non_lhc:92363": 1}


def test_filter_by_zip_none_dropped_with_no_zip_key() -> None:
    rows = [
        {"place_id": "a", "zip": None},
        {"place_id": "b"},  # missing zip key entirely
    ]
    kept, drops = filter_by_zip(rows)
    assert kept == []
    assert drops == {"no_zip": 2}


def test_filter_by_zip_mixed_realistic_input() -> None:
    # Mirrors the 5.4 dry-run shape: mostly LHC with a few ZIP+4 (no dash),
    # plus the typical non-LHC spillover.
    rows = [
        {"place_id": "lhc1", "zip": "86403"},
        {"place_id": "lhc2_plus4_nodash", "zip": "864036710"},
        {"place_id": "lhc3_plus4_dash", "zip": "86404-2000"},
        {"place_id": "kingman", "zip": "86401"},
        {"place_id": "missing"},
    ]
    kept, drops = filter_by_zip(rows)
    assert [r["place_id"] for r in kept] == ["lhc1", "lhc2_plus4_nodash", "lhc3_plus4_dash"]
    assert drops == {"non_lhc:86401": 1, "no_zip": 1}
