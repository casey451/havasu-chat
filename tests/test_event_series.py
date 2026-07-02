"""P0 Task 4 — recurring-series collapse + schedule labels + time relabel."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.db.models import Event
from app.events import series as es

# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    "weekdays,expected",
    [
        ({0, 1, 2, 3, 4, 5, 6}, "Daily"),
        ({0, 1, 2, 3, 4}, "Mon–Fri"),
        ({5, 6}, "Weekends"),
        ({1, 2, 3}, "Tue–Thu"),  # contiguous range
        ({0, 2, 4}, "Mon, Wed, Fri"),  # explicit list
        (set(), ""),
    ],
)
def test_schedule_label(weekdays: set[int], expected: str) -> None:
    assert es.schedule_label(weekdays) == expected


def test_series_key_normalizes() -> None:
    a = es.series_key("Lap Swim", "Aquatic Center", time(5, 0))
    b = es.series_key("  lap swim ", "aquatic center", time(5, 0))
    assert a == b
    assert es.series_key("Lap Swim", "Aquatic Center", time(19, 0)) != a  # time matters


def test_series_index_threshold() -> None:
    base = date(2026, 6, 1)  # a Monday
    rows = [
        ("lap swim", "pool", time(5, 0), base + timedelta(days=d), False)
        for d in range(5)  # Mon-Fri
    ]
    rows.append(("one off", "park", time(18, 0), base, False))
    idx = es.build_series_index(rows)
    swim = idx[es.series_key("lap swim", "pool", time(5, 0))]
    assert swim.is_series is True
    assert es.schedule_label(swim.weekdays) == "Mon–Fri"
    oneoff = idx[es.series_key("one off", "park", time(18, 0))]
    assert oneoff.is_series is False


# --- integration: collapse in the feed --------------------------------------


def _add_event(db, *, title: str, on: date, start: time, loc: str, tags=None) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source="test-series",
        verified=True,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id




