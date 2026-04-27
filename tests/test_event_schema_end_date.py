"""``EventCreate`` / ``EventBase`` validation for ``end_date`` (multi-day events)."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from app.schemas.event import EventCreate, normalize_event_url


def _minimal_event_create(**overrides) -> None:
    base = {
        "title": "Test Event Title Here",
        "date": date(2026, 5, 7),
        "start_time": time(9, 0),
        "end_time": None,
        "location_name": "Test Location Name",
        "description": "Twenty chars minimum for description here.",
        "event_url": normalize_event_url("https://example.com/e"),
    }
    EventCreate.model_validate({**base, **overrides})


def test_end_date_none_allowed() -> None:
    _minimal_event_create(end_date=None)


def test_end_date_equal_to_date_allowed() -> None:
    d = date(2026, 5, 7)
    _minimal_event_create(date=d, end_date=d)


def test_end_date_after_start_allowed() -> None:
    _minimal_event_create(
        date=date(2026, 5, 7),
        end_date=date(2026, 5, 9),
    )


def test_end_date_before_start_raises() -> None:
    with pytest.raises(ValidationError) as ei:
        _minimal_event_create(
            date=date(2026, 5, 9),
            end_date=date(2026, 5, 7),
        )
    err = str(ei.value).lower()
    assert "end_date" in err
