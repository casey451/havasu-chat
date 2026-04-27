"""Unit tests for app.contrib.event_date_line.parse_event_date_line."""

from __future__ import annotations

from datetime import date

import pytest

from app.contrib.event_date_line import parse_event_date_line


def test_single_with_date_prefix() -> None:
    assert parse_event_date_line("Date: May 16, 2026") == (date(2026, 5, 16), None)


def test_single_without_date_prefix() -> None:
    assert parse_event_date_line("May 16, 2026") == (date(2026, 5, 16), None)


def test_single_zero_padded_day() -> None:
    assert parse_event_date_line("Date: August 01, 2026") == (date(2026, 8, 1), None)


def test_single_unpadded_day() -> None:
    assert parse_event_date_line("Date: May 16, 2026") == (date(2026, 5, 16), None)


def test_range_en_dash() -> None:
    assert parse_event_date_line("Date: May 8–10, 2026") == (date(2026, 5, 8), date(2026, 5, 10))


def test_range_ascii_hyphen() -> None:
    assert parse_event_date_line("Date: May 8-10, 2026") == (date(2026, 5, 8), date(2026, 5, 10))


def test_range_em_dash() -> None:
    assert parse_event_date_line("Date: May 8—10, 2026") == (date(2026, 5, 8), date(2026, 5, 10))


def test_range_whitespace_around_separator() -> None:
    assert parse_event_date_line("Date: May 8  –  10, 2026") == (date(2026, 5, 8), date(2026, 5, 10))


def test_cross_month_two_segment_returns_none() -> None:
    assert (
        parse_event_date_line("Date: May 8, 2026 – May 10, 2026")
        is None
    )


def test_garbage_returns_none() -> None:
    assert parse_event_date_line("garbage") is None


def test_empty_returns_none() -> None:
    assert parse_event_date_line("") is None


def test_reversed_range_invalid() -> None:
    assert parse_event_date_line("Date: May 10–8, 2026") is None


def test_date_prefix_case_insensitive() -> None:
    assert parse_event_date_line("dAtE: May 1, 2026") == (date(2026, 5, 1), None)


def test_trailing_whitespace() -> None:
    assert parse_event_date_line("  May 1, 2026  \n") == (date(2026, 5, 1), None)
    assert parse_event_date_line("Date: May 8–10, 2026   \t") == (
        date(2026, 5, 8),
        date(2026, 5, 10),
    )


@pytest.mark.parametrize(
    "sep",
    ["\u2013", "-", "\u2014"],
    ids=["en_dash", "ascii_hyphen", "em_dash"],
)
def test_all_defensive_separators_in_range(sep: str) -> None:
    s = f"Date: April 24{sep}25, 2026"
    assert parse_event_date_line(s) == (date(2026, 4, 24), date(2026, 4, 25))
