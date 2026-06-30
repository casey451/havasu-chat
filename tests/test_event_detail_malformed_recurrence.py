"""The event detail page must render (not 500) for a malformed recurring row.

N1's fix added recurrence parsing to the detail render path
(_event_is_past / _format_event_datetime → recurrence.next_occurrence). Prod
recurrence data is known-messy, so a row with an unparseable rrule / exdate /
rdate must degrade to its anchor date and still return 200 — never bubble a parse
error into a 500.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(db: Session, **kw) -> str:
    ev = Event(
        title="Broken Recurring",
        normalized_title="broken recurring",
        date=kw.pop("date", date(2026, 12, 1)),
        start_time=kw.pop("start_time", time(9, 0)),
        end_time=kw.pop("end_time", time(10, 0)),
        location_name="Test Venue",
        location_normalized="test venue",
        description="A recurring thing",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test_malformed_recurrence",
        verified=True,
        is_recurring=True,
        **kw,
    )
    db.add(ev)
    db.commit()
    return ev.id


def test_detail_page_renders_for_malformed_recurrence(db: Session) -> None:
    eid = _seed(
        db,
        rrule="RRULE:FREQ=GARBAGE;BYDAY=ZZ",
        exdate=["not-a-date", "2026-13-99"],
        rdate=["also-bad"],
    )
    try:
        r = TestClient(app).get(f"/events/{eid}")
        assert r.status_code == 200  # degrades to the anchor, never 500s
        assert "Broken Recurring" in r.text
    finally:
        db.query(Event).filter(Event.id == eid).delete()
        db.commit()


# ── F5: is_recurring=True but NO rrule and NO rdate (266 live rows 2026-06-29) ──
# These have no real schedule. next_occurrence used to return None for them, so
# _event_is_past wore a false "This event has passed" banner while the anchor was
# today/upcoming. Degrade to one-off semantics instead.


def _oneoff_recurring(anchor: date) -> Event:
    """In-memory recurring-flagged Event with no rrule/rdate (not DB-persisted)."""
    return Event(
        title="No-rule recurring",
        normalized_title="no-rule recurring",
        date=anchor,
        start_time=time(0, 0),  # TBD time, like the Craft Series row
        end_time=None,
        location_name="V",
        location_normalized="v",
        description="d",
        event_url="",
        tags=[],
        status="live",
        source="t",
        verified=True,
        is_recurring=True,
        rrule=None,
        rdate=None,
        entity_id="x",
    )


def test_recurring_no_schedule_today_anchor_not_past() -> None:
    from app.core.timezone import now_lake_havasu
    from app.events.recurrence import next_occurrence
    from app.main import _display_date, _event_is_past

    today = now_lake_havasu().date()
    ev = _oneoff_recurring(today)
    assert next_occurrence(ev, on_or_after=today) == today
    assert _event_is_past(ev) is False
    assert _display_date(ev) == today


def test_recurring_no_schedule_past_anchor_is_past() -> None:
    from app.core.timezone import now_lake_havasu
    from app.events.recurrence import next_occurrence
    from app.main import _event_is_past

    today = now_lake_havasu().date()
    past = date(today.year - 1, 1, 1)
    ev = _oneoff_recurring(past)
    assert next_occurrence(ev, on_or_after=today) is None
    assert _event_is_past(ev) is True


def test_detail_page_no_false_passed_banner_for_no_schedule_recurring(db: Session) -> None:
    from app.core.timezone import now_lake_havasu

    today = now_lake_havasu().date()
    eid = _seed(db, date=today, start_time=time(0, 0), end_time=None, rrule=None, rdate=None)
    try:
        r = TestClient(app).get(f"/events/{eid}")
        assert r.status_code == 200
        assert "has passed" not in r.text  # no false "This event has passed" banner
    finally:
        db.query(Event).filter(Event.id == eid).delete()
        db.commit()
