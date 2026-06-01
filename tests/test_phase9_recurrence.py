"""Phase 9a — RRULE expansion edge cases."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.db.models import Event
from app.events.recurrence import expand_event, occurrences_in_window, parsed_until_from_rrule


def _ev(**kwargs) -> Event:
    base = dict(
        title="Yoga",
        normalized_title="yoga",
        date=date(2026, 1, 6),
        start_time=time(18, 0),
        location_name="Park",
        location_normalized="park",
        description="Class",
        event_url="https://example.com",
        status="live",
        source="test",
        is_recurring=True,
    )
    base.update(kwargs)
    return Event(**base)


def test_single_instance_in_window() -> None:
    ev = _ev(is_recurring=False, rrule=None, date=date(2026, 6, 15))
    assert expand_event(ev, window_start=date(2026, 6, 1), window_end=date(2026, 6, 30)) == [
        date(2026, 6, 15)
    ]


def test_weekly_byday_phoenix() -> None:
    ev = _ev(rrule="FREQ=WEEKLY;BYDAY=TU", date=date(2026, 1, 6))
    out = expand_event(ev, window_start=date(2026, 1, 1), window_end=date(2026, 2, 28))
    assert date(2026, 1, 6) in out
    assert date(2026, 1, 13) in out
    assert all(d.weekday() == 1 for d in out)


def test_exdate_removes_occurrence() -> None:
    ev = _ev(
        rrule="FREQ=WEEKLY;BYDAY=TU",
        exdate=["2026-01-13"],
        date=date(2026, 1, 6),
    )
    out = expand_event(ev, window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
    assert date(2026, 1, 6) in out
    assert date(2026, 1, 13) not in out


def test_rdate_adds_extra() -> None:
    ev = _ev(
        rrule="FREQ=WEEKLY;BYDAY=TU",
        rdate=["2026-01-10"],
        date=date(2026, 1, 6),
    )
    out = expand_event(ev, window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
    assert date(2026, 1, 10) in out


def test_cap_exceeded_raises() -> None:
    ev = _ev(rrule="FREQ=DAILY", date=date(2026, 1, 1))
    with pytest.raises(ValueError, match="cap"):
        expand_event(
            ev,
            window_start=date(2026, 1, 1),
            window_end=date(2027, 1, 1),
            cap=10,
        )


def test_parsed_until_from_rrule() -> None:
    assert parsed_until_from_rrule("FREQ=WEEKLY;UNTIL=20261201T000000Z") == date(2026, 12, 1)
    assert parsed_until_from_rrule("FREQ=WEEKLY") is None


def test_occurrences_in_window_sorted() -> None:
    a = _ev(title="A", normalized_title="a", date=date(2026, 3, 1), rrule=None, is_recurring=False)
    b = _ev(
        title="B",
        normalized_title="b",
        date=date(2026, 3, 1),
        start_time=time(9, 0),
        rrule="FREQ=WEEKLY;BYDAY=SU",
        is_recurring=True,
    )
    flat = occurrences_in_window(
        [b, a],
        window_start=date(2026, 3, 1),
        window_end=date(2026, 3, 15),
    )
    dates = [d for _, d in flat]
    assert dates == sorted(dates)
