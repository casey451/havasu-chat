"""Tier2Filters v2 schema and DB date-window resolution (Phase 8.8.4 Step 1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.chat.tier2_db_query import (
    _month_name_range,
    _next_weekday,
    _resolve_effective_event_window,
    _resolve_time_window,
    _season_range,
)
from app.chat.tier2_schema import Tier2Filters


def test_time_window_next_week_next_month() -> None:
    ref = date(2026, 4, 10)  # Friday
    s, e = _resolve_time_window("next_week", ref)
    assert s == date(2026, 4, 13)  # Mon
    assert e == date(2026, 4, 19)  # Sun
    s2, e2 = _resolve_time_window("next_month", ref)
    assert s2 == date(2026, 5, 1)
    assert e2 == date(2026, 5, 31)


def test_next_week_monday_on_ref_advances() -> None:
    ref = date(2026, 4, 13)  # Monday
    s, e = _resolve_time_window("next_week", ref)
    assert s == date(2026, 4, 20)
    assert e == date(2026, 4, 26)


def test_month_name_rolls_to_next_year_when_earlier_month() -> None:
    ref = date(2026, 4, 24)
    s, e = _month_name_range("march", ref)
    assert s == date(2027, 3, 1)
    assert e == date(2027, 3, 31)


def test_month_name_same_year_when_later_month() -> None:
    ref = date(2026, 4, 24)
    s, e = _month_name_range("october", ref)
    assert s == date(2026, 10, 1)
    assert e == date(2026, 10, 31)


def test_season_summer() -> None:
    ref = date(2026, 4, 24)
    s, e = _season_range("summer", ref)
    assert s == date(2026, 6, 1)
    assert e == date(2026, 8, 31)


def test_season_winter_from_march() -> None:
    ref = date(2026, 3, 15)
    s, e = _season_range("winter", ref)
    assert s == date(2026, 12, 1)
    assert e == date(2027, 2, 28)


def test_schema_mutex_time_window_and_month() -> None:
    with pytest.raises(ValidationError):
        Tier2Filters(
            parser_confidence=0.9,
            fallback_to_tier3=False,
            time_window="tomorrow",
            month_name="october",
        )


def test_schema_mutex_time_window_and_season() -> None:
    with pytest.raises(ValidationError):
        Tier2Filters(
            parser_confidence=0.9,
            fallback_to_tier3=False,
            time_window="this_month",
            season="summer",
        )


def test_schema_date_exact_mutex_with_range() -> None:
    with pytest.raises(ValidationError):
        Tier2Filters(
            parser_confidence=0.9,
            fallback_to_tier3=False,
            date_exact=date(2026, 7, 4),
            date_start=date(2026, 7, 1),
        )


def test_schema_valid_minimal() -> None:
    f = Tier2Filters(
        parser_confidence=0.8,
        fallback_to_tier3=False,
        month_name="july",
    )
    assert f.time_window is None
    assert f.month_name == "july"


def test_resolve_effective_event_window_date_exact() -> None:
    ref = date(2026, 1, 1)
    f = Tier2Filters(
        parser_confidence=0.9,
        fallback_to_tier3=False,
        date_exact=date(2026, 7, 4),
    )
    s, e = _resolve_effective_event_window(f, ref)
    assert s == date(2026, 7, 4) and e == date(2026, 7, 4)


def test_resolve_effective_event_window_range() -> None:
    ref = date(2026, 1, 1)
    f = Tier2Filters(
        parser_confidence=0.9,
        fallback_to_tier3=False,
        date_start=date(2026, 6, 1),
        date_end=date(2026, 6, 30),
    )
    s, e = _resolve_effective_event_window(f, ref)
    assert s == date(2026, 6, 1) and e == date(2026, 6, 30)


def test_next_weekday_matches_slots_semantics() -> None:
    """Keep in sync with ``app.core.slots`` next-week resolution (Mon start + Sun end)."""
    ref = date(2026, 4, 10)
    mon = _next_weekday(ref, 0, allow_today=False)
    if mon <= ref:
        mon += timedelta(days=7)
    assert mon == date(2026, 4, 13)
