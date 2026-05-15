"""Unit tests for ``scripts/places_load`` helpers (pure, no DB)."""

from __future__ import annotations

import pytest

from app.contrib.google_places_scraper import DISCOVERY_CATEGORY_TO_DOMAINS
from scripts.places_load import filter_by_category


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
