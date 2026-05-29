"""Tests for app/home/algorithmic_picks.py — deterministic ranking helpers."""

from __future__ import annotations

from app.home.algorithmic_picks import (
    category_pick_index,
    new_on_hava_ranking,
    tonight_ranking,
)


class FakeRow:
    def __init__(self, featured: bool) -> None:
        self.featured = featured


def test_tonight_ranking_clauses_include_featured_tiebreaker() -> None:
    clauses = tonight_ranking()
    assert any("featured" in str(c).lower() for c in clauses)


def test_new_on_hava_drops_featured() -> None:
    clauses = new_on_hava_ranking()
    assert all("featured" not in str(c).lower() for c in clauses)


def test_category_pick_index_returns_zero_when_no_featured() -> None:
    rows = [FakeRow(False), FakeRow(False), FakeRow(False)]
    assert category_pick_index(rows) == 0


def test_category_pick_index_prefers_featured_when_present() -> None:
    rows = [FakeRow(False), FakeRow(True), FakeRow(False)]
    assert category_pick_index(rows) == 1


def test_category_pick_index_returns_none_for_empty() -> None:
    assert category_pick_index([]) is None
