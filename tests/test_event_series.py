"""P0 Task 4 — recurring-series collapse + schedule labels + time relabel."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events import series as es
from app.home.router import _events_for_window
from app.main import app

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


def test_recurring_series_collapses_to_one_card() -> None:
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Lap Swim {suffix}"
    oneoff_title = f"ZZ Festival {suffix}"
    ids: list[str] = []
    start = now_lake_havasu()
    monday = start.date() - timedelta(days=start.weekday())  # this week's Monday
    with SessionLocal() as db:
        # 5 weekday occurrences of the same series (Mon-Fri this week).
        for d in range(5):
            ids.append(
                _add_event(
                    db,
                    title=title,
                    on=monday + timedelta(days=d),
                    start=time(5, 0),
                    loc="Aquatic Center",
                    tags=["aquatics"],
                )
            )
        ids.append(
            _add_event(
                db, title=oneoff_title, on=monday, start=time(18, 0), loc="London Bridge"
            )
        )
        db.commit()
    try:
        # Wide window covering the whole week.
        win_start = datetime.combine(monday, time.min)
        items = _events_for_window(
            SessionLocal(),
            start_day=win_start,
            end_day=win_start + timedelta(days=6),
            limit=100,
        )
        swim = [i for i in items if i["title"] == title]
        fest = [i for i in items if i["title"] == oneoff_title]
        assert len(swim) == 1, "recurring series should collapse to a single card"
        assert swim[0]["recurring"] is True
        assert swim[0]["schedule_label"] == "Mon–Fri"
        assert len(fest) == 1
        assert fest[0]["recurring"] is False
        assert fest[0]["schedule_label"] == ""
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()


def test_time_group_labels_are_plain_language() -> None:
    with TestClient(app) as client:
        home = client.get("/home").text
        events = client.get("/events-ui").text
    assert "Tonight through next week" not in home
    # The events page uses plain Today / Week / Month zoom levels (the old
    # mislabeled rolling buckets — and their labels — are gone).
    assert "Today" in events
    assert ">Week</a>" in events
    assert ">Month</a>" in events


def test_split_oneoff_and_ongoing_dedupes_recurring_across_windows() -> None:
    from app.home.router import _split_oneoff_and_ongoing

    klass = {"title": "Lap Swim", "venue": "Pool", "recurring": True, "schedule_label": "Mon–Fri"}
    groups = {
        "today": [klass, {"title": "Gala", "venue": "Bridge", "recurring": False}],
        "weekend": [klass],  # same series, later window
        "next_week": [{"title": "Fair", "venue": "Park", "recurring": False}],
    }
    oneoff, ongoing = _split_oneoff_and_ongoing(groups)
    # One-off festivals stay in their time buckets...
    assert [i["title"] for i in oneoff["today"]] == ["Gala"]
    assert [i["title"] for i in oneoff["next_week"]] == ["Fair"]
    assert oneoff["weekend"] == []
    # ...and the recurring class is pulled out once into "Classes & ongoing".
    assert [i["title"] for i in ongoing] == ["Lap Swim"]
