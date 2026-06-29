"""Unit coverage for the classes-sports-recreation Youth/Adult audience bands.

The /group/<classes> page collapsed its four age buckets to Youth (under 18) /
Adult and now actually filters on them (Casey 2026-06-29). These pin the band
logic so the collapse can't silently regress.
"""

from __future__ import annotations

from app.api.routes.category_pages import _program_matches_age_band


class _Prog:
    """Minimal stand-in — the matcher only reads age_min / age_max."""

    def __init__(self, age_min: int | None, age_max: int | None) -> None:
        self.age_min = age_min
        self.age_max = age_max


def test_youth_band_matches_under_18_programs() -> None:
    assert _program_matches_age_band(_Prog(6, 12), "youth") is True   # kids
    assert _program_matches_age_band(_Prog(13, 17), "youth") is True  # teens
    assert _program_matches_age_band(_Prog(16, 40), "youth") is True  # spans under-18


def test_youth_band_excludes_adult_only_and_unknown() -> None:
    assert _program_matches_age_band(_Prog(18, 99), "youth") is False  # adults only
    assert _program_matches_age_band(_Prog(None, None), "youth") is False  # no ages


def test_adult_band_unchanged_by_youth_addition() -> None:
    assert _program_matches_age_band(_Prog(18, 99), "adults") is True
    assert _program_matches_age_band(_Prog(6, 12), "adults") is False
