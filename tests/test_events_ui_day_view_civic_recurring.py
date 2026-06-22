"""P1 fix-up: the /events-ui DAY view path (events_views.day_groups + the lake
day-view template).

Two things the existing pure-function civic test (test_event_buckets_civic.py)
never exercised:

1. A civic event on the day view buckets under "City & Government" — not left in
   the chronological "Happening today" (events) group.
2. The day-view rows emit NO "recurring" row badge ("Runs regularly ↻" /
   "Recurring") — that banner was retired in P1. The distinct headline
   ``recurrence_label`` (week view) is intentional and untouched here.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Event
from app.home import events_views
from app.main import app

_SRC = "_p1fix_dayview_probe"


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe(db: Session):
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()
    yield
    db.query(Event).filter(Event.source == _SRC).delete()
    db.commit()


def _add(db: Session, *, title: str, on: date, recurring: bool = False, rrule: str | None = None) -> None:
    db.add(
        Event(
            title=title,
            normalized_title=title.lower(),
            date=on,
            start_time=time(17, 0),
            end_time=time(19, 0),
            location_name="City Hall",
            location_normalized="city hall",
            description="x",
            event_url="https://example.com/e",
            tags=["civic", "government", "meeting"] if "council" in title.lower() else [],
            status="live",
            source=_SRC,
            verified=True,
            is_recurring=recurring,
            rrule=rrule,
        )
    )
    db.commit()


def test_civic_event_buckets_under_city_and_government_on_day_view(db: Session) -> None:
    d = now_lake_havasu().date() + timedelta(days=2)
    _add(db, title="City Council Meeting", on=d)

    groups = events_views.day_groups(db, day=d, now=now_lake_havasu())
    by_key = {g["key"]: g for g in groups}
    assert "civic" in by_key, [g["key"] for g in groups]
    assert by_key["civic"]["label"] == "City & Government"
    titles = [r["title"] for r in by_key["civic"]["rows"]]
    assert any("Council" in t for t in titles)
    # ...and it is NOT left in the leisure "Happening today" (events) group.
    if "events" in by_key:
        assert not any("Council" in r["title"] for r in by_key["events"]["rows"])


def test_day_view_renders_city_and_government_group(db: Session) -> None:
    d = now_lake_havasu().date() + timedelta(days=2)
    _add(db, title="City Council Meeting", on=d)
    body = TestClient(app).get(f"/events-ui?date={d.isoformat()}&theme=lake").text
    assert "City &amp; Government" in body or "City & Government" in body


def test_day_view_rows_have_no_recurring_badge(db: Session) -> None:
    d = now_lake_havasu().date() + timedelta(days=2)
    dow = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[d.weekday()]
    _add(db, title="Vinyasa Yoga", on=d, recurring=True, rrule=f"FREQ=WEEKLY;BYDAY={dow}")
    _add(db, title="City Council Meeting", on=d)
    body = TestClient(app).get(f"/events-ui?date={d.isoformat()}&theme=lake").text
    # The retired row banner must not reappear in the day-view DOM. (The headline
    # recurrence_label in the WEEK view is a different, intentional feature.)
    assert "Runs regularly" not in body
    assert "↻" not in body  # ↻
    assert "Recurring" not in body
