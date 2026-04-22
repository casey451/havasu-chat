"""Phase 6.5-lite — local voice matcher scoring and filters."""

from __future__ import annotations

from datetime import date

import pytest

from app.chat.local_voice_matcher import find_matching_blurbs
from app.data.local_voice import _validate_entry


def test_single_keyword_match() -> None:
    blurbs = [{"id": "a", "keywords": ["lake"], "category": "x", "text": "hint"}]
    r = find_matching_blurbs("fun on the lake today", None, date(2026, 6, 1), blurbs=blurbs)
    assert len(r) == 1 and r[0]["id"] == "a"


def test_multiword_keyword() -> None:
    blurbs = [{"id": "m", "keywords": ["farmers market"], "category": "x", "text": "hint"}]
    r = find_matching_blurbs("the farmers market saturday", None, date(2026, 6, 1), blurbs=blurbs)
    assert len(r) == 1


def test_max_results_limits_output() -> None:
    blurbs = [
        {"id": "a", "keywords": ["x"], "category": "c", "text": "1"},
        {"id": "b", "keywords": ["x"], "category": "c", "text": "2"},
    ]
    r = find_matching_blurbs("x y", None, date(2026, 6, 1), max_results=1, blurbs=blurbs)
    assert len(r) == 1


def test_sorted_by_keyword_score_desc_stable() -> None:
    blurbs = [
        {"id": "low", "keywords": ["alpha"], "category": "x", "text": "a"},
        {"id": "hi", "keywords": ["alpha", "beta"], "category": "x", "text": "b"},
    ]
    r = find_matching_blurbs("alpha beta gamma", None, date(2026, 6, 1), blurbs=blurbs)
    assert [e["id"] for e in r] == ["hi", "low"]


def test_word_boundary_no_substring_match() -> None:
    blurbs = [{"id": "bmx", "keywords": ["bmx"], "category": "x", "text": "t"}]
    assert find_matching_blurbs("bmxing race", None, date(2026, 6, 1), blurbs=blurbs) == []


def test_adults_only_filtered_when_has_kids() -> None:
    blurbs = [
        {"id": "wine", "keywords": ["wine"], "category": "x", "text": "t", "context_tags": ["adults_only"]}
    ]
    assert (
        find_matching_blurbs("wine tasting", {"has_kids": True}, date(2026, 6, 1), blurbs=blurbs) == []
    )


def test_kids_ok_still_returned_without_kids() -> None:
    blurbs = [{"id": "p", "keywords": ["park"], "category": "x", "text": "t", "context_tags": ["kids_ok"]}]
    r = find_matching_blurbs("park ideas", {"has_kids": False}, date(2026, 6, 1), blurbs=blurbs)
    assert len(r) == 1


def test_summer_season_excluded_in_january() -> None:
    blurbs = [{"id": "sum", "keywords": ["water"], "category": "x", "text": "t", "season": "summer"}]
    assert find_matching_blurbs("water fun", None, date(2026, 1, 15), blurbs=blurbs) == []


def test_year_round_in_january() -> None:
    blurbs = [
        {"id": "yr", "keywords": ["water"], "category": "x", "text": "t", "season": "year_round"}
    ]
    r = find_matching_blurbs("water fun", None, date(2026, 1, 15), blurbs=blurbs)
    assert len(r) == 1


def test_evening_tag_with_tonight_query() -> None:
    blurbs = [
        {
            "id": "ev",
            "keywords": ["tonight", "fun"],
            "category": "x",
            "text": "t",
            "context_tags": ["evening"],
        }
    ]
    r = find_matching_blurbs("fun things tonight", None, date(2026, 6, 1), blurbs=blurbs)
    assert len(r) == 1


def test_evening_tag_without_temporal_words_still_in_play() -> None:
    blurbs = [
        {"id": "ev", "keywords": ["bmx"], "category": "x", "text": "t", "context_tags": ["evening"]}
    ]
    r = find_matching_blurbs("what is bmx", None, date(2026, 6, 1), blurbs=blurbs)
    assert len(r) == 1


def test_local_focused_filtered_for_visiting() -> None:
    blurbs = [
        {
            "id": "loc",
            "keywords": ["secret"],
            "category": "x",
            "text": "t",
            "context_tags": ["local_focused"],
        }
    ]
    assert (
        find_matching_blurbs(
            "secret spot", {"visitor_status": "visiting"}, date(2026, 6, 1), blurbs=blurbs
        )
        == []
    )


def test_visitor_friendly_filtered_for_local_status() -> None:
    blurbs = [
        {
            "id": "vf",
            "keywords": ["bridge"],
            "category": "x",
            "text": "t",
            "context_tags": ["visitor_friendly"],
        }
    ]
    assert (
        find_matching_blurbs(
            "bridge walk", {"visitor_status": "local"}, date(2026, 6, 1), blurbs=blurbs
        )
        == []
    )


def test_validate_entry_rejects_bad_season() -> None:
    with pytest.raises(ValueError):
        _validate_entry(
            {"id": "x", "keywords": ["a"], "category": "c", "text": "t", "season": "not_a_season"}
        )
