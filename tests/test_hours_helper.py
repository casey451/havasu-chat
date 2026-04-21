"""Tests for ``hours_helper`` (Phase 5.6)."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.contrib.hours_helper import LAKE_HAVASU_TZ, is_open_at, places_hours_to_structured

PHX = LAKE_HAVASU_TZ


def test_places_standard_weekday() -> None:
    blob = {
        "periods": [
            {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 17, "minute": 0}},
        ]
    }
    out = places_hours_to_structured(blob)
    assert out.get("monday") == [{"open": "09:00", "close": "17:00"}]


def test_places_missing_periods() -> None:
    assert places_hours_to_structured({}) == {}
    assert places_hours_to_structured({"periods": None}) == {}
    assert places_hours_to_structured({"periods": []}) == {}


def test_places_malformed_period_skipped() -> None:
    blob = {"periods": [{"open": "not-a-dict"}, {"close": {"day": 1, "hour": 1, "minute": 0}}]}
    assert places_hours_to_structured(blob) == {}


def test_places_overnight_split() -> None:
    blob = {
        "periods": [
            {"open": {"day": 6, "hour": 22, "minute": 0}, "close": {"day": 0, "hour": 2, "minute": 0}},
        ]
    }
    out = places_hours_to_structured(blob)
    assert {"open": "22:00", "close": "23:59"} in out["saturday"]
    assert {"open": "00:00", "close": "02:00"} in out["sunday"]


def test_places_same_day_sunday() -> None:
    """Single-day Sunday window (e.g. all-day style as one period)."""
    blob = {
        "periods": [
            {"open": {"day": 0, "hour": 0, "minute": 0}, "close": {"day": 0, "hour": 23, "minute": 59}},
        ]
    }
    out = places_hours_to_structured(blob)
    assert out["sunday"]


def test_is_open_mid_window() -> None:
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    dt = datetime(2026, 6, 15, 12, 30, tzinfo=PHX)  # Monday
    assert is_open_at(hs, dt) is True


def test_is_open_outside_window() -> None:
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    dt = datetime(2026, 6, 15, 20, 0, tzinfo=PHX)
    assert is_open_at(hs, dt) is False


def test_is_open_weekday_missing() -> None:
    hs = {"tuesday": [{"open": "09:00", "close": "17:00"}]}
    dt = datetime(2026, 6, 15, 12, 0, tzinfo=PHX)  # Monday
    assert is_open_at(hs, dt) is False


def test_is_open_malformed() -> None:
    assert is_open_at({}, datetime.now(PHX)) is False
    assert is_open_at({"monday": "bad"}, datetime(2026, 6, 15, 12, 0, tzinfo=PHX)) is False


@pytest.mark.parametrize(
    ("cur", "expected"),
    [
        ("09:00", True),
        ("17:00", True),
    ],
)
def test_is_open_inclusive_endpoints(cur: str, expected: bool) -> None:
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    h, m = map(int, cur.split(":"))
    dt = datetime(2026, 6, 15, h, m, tzinfo=PHX)
    assert is_open_at(hs, dt) is expected


def test_is_open_naive_datetime_treated_as_phx_wall() -> None:
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    dt = datetime(2026, 6, 15, 12, 0)  # naive
    assert is_open_at(hs, dt) is True


def test_overnight_sunday_early_open() -> None:
    hs = places_hours_to_structured(
        {
            "periods": [
                {"open": {"day": 6, "hour": 22, "minute": 0}, "close": {"day": 0, "hour": 2, "minute": 0}},
            ]
        }
    )
    dt = datetime(2026, 6, 14, 1, 30, tzinfo=PHX)  # Sunday 1:30am
    assert is_open_at(hs, dt) is True
