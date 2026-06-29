"""News filler removal + title dedup (Casey 2026-06-29).

The wire feeds repeat Celebrity Cipher and other syndicated columns under many
URLs/dates; URL-dedup alone misses them, so we drop the filler outright and
collapse near-duplicate titles on our end (both at pull time and read time).
"""

from __future__ import annotations

from app.news.store import _is_filler, _normalize_title


def test_syndicated_filler_is_dropped() -> None:
    assert _is_filler("Celebrity Cipher for June 28") is True
    assert _is_filler("Daily Horoscope") is True
    assert _is_filler("Today's Sudoku") is True
    # Real local news is kept.
    assert _is_filler("City Council approves new lakefront park") is False


def test_title_normalization_collapses_dated_reruns() -> None:
    # Same recurring column, different date/URL → one key.
    assert _normalize_title("Police Beat for June 28, 2026") == _normalize_title(
        "Police Beat for July 1"
    )
    # Genuinely different headlines stay distinct.
    assert _normalize_title("Fire damages home on Oak St") != _normalize_title(
        "School board approves budget"
    )
