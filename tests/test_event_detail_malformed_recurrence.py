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
