"""Pure parsing helpers for the Movies Havasu scraper."""

from __future__ import annotations

from datetime import date, time

from app.movies.havasu_parse import (
    parse_clock_time,
    parse_runtime_minutes,
    resolve_strip_dates,
)


def test_parse_clock_time():
    assert parse_clock_time("7:00PM") == time(19, 0)
    assert parse_clock_time("11:00 AM") == time(11, 0)
    assert parse_clock_time("12:00PM") == time(12, 0)  # noon
    assert parse_clock_time("12:30AM") == time(0, 30)  # after midnight
    assert parse_clock_time("9:45 p.m.") == time(21, 45)
    assert parse_clock_time("") is None
    assert parse_clock_time("soon") is None


def test_parse_runtime_minutes():
    assert parse_runtime_minutes("2 hr 2 min") == 122
    assert parse_runtime_minutes("1 hr 42 min") == 102
    assert parse_runtime_minutes("1 hr") == 60
    assert parse_runtime_minutes("95 min") == 95
    assert parse_runtime_minutes("Action, Adventure") is None
    assert parse_runtime_minutes(None) is None


def test_resolve_strip_dates_consecutive():
    dates = resolve_strip_dates(["Fri19", "Sat20", "Sun21"], today=date(2026, 6, 19))
    assert dates == [date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21)]


def test_resolve_strip_dates_month_rollover():
    dates = resolve_strip_dates(
        ["Mon29", "Tue30", "Wed1", "Thu2"], today=date(2026, 6, 29)
    )
    assert dates == [
        date(2026, 6, 29),
        date(2026, 6, 30),
        date(2026, 7, 1),
        date(2026, 7, 2),
    ]
