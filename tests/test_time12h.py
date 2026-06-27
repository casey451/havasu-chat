"""24-hour → 12-hour Jinja filter for place-page hours (site review §6)."""

from __future__ import annotations

import pytest

from app.core.provider_name import time12h


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12:00", "12 PM"),
        ("00:00", "12 AM"),
        ("21:00", "9 PM"),
        ("09:00", "9 AM"),
        ("18:30", "6:30 PM"),
        ("23:59", "11:59 PM"),
        ("9:00", "9 AM"),  # single-digit hour
    ],
)
def test_time12h_converts(raw: str, expected: str) -> None:
    assert time12h(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "noon", "25:00", "12:99", "abc"])
def test_time12h_passes_through_unparseable(raw: str | None) -> None:
    assert time12h(raw) == (raw or "")
