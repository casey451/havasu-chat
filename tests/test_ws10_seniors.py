"""WS10 — /seniors: the static Senior-Center guide + today's live senior feed.

WS2 shipped the static hub (address, monthly-calendar images, the weekly grid,
Meals on Wheels). WS10 adds the live "Today at the Senior Center" feed — the same
``seniors=True`` narrow the calendar uses — guarded so a cold DB never 500s.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import seniors_hub
from app.main import app


def _add_senior_event(db, *, title, on, start=time(12, 30), loc="Lake Havasu Senior Center"):
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=["senior"],
        status="live",
        source="test-ws10-seniors",
        verified=True,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _cleanup(eids):
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_seniors_page_renders_static_grid() -> None:
    """The WS2 content stays: the weekly grid, lunch program, and calendars."""
    with TestClient(app) as client:
        body = client.get("/seniors").text
    assert "Lake Havasu Senior Center" in body
    assert "Weekly activities" in body
    assert "Meals on Wheels" in body
    assert "chat?q=" not in body


def test_seniors_today_feed_lists_todays_senior_event() -> None:
    today = now_lake_havasu().date()
    suf = uuid.uuid4().hex[:8]
    title = f"ZZ Senior Bunco {suf}"
    with SessionLocal() as db:
        eid = _add_senior_event(db, title=title, on=today)
        db.commit()
    try:
        with SessionLocal() as db:
            rows = seniors_hub.today_seniors_rows(db, day=today)
        match = next((r for r in rows if r["title"].startswith("ZZ Senior Bunco")), None)
        assert match is not None
        assert match["url"].startswith("/events/")
        with TestClient(app) as client:
            body = client.get("/seniors").text
        assert "Today at the Senior Center" in body
        assert title in body
    finally:
        _cleanup([eid])


def test_seniors_today_feed_honest_omit_when_none() -> None:
    """A day with no senior programming returns [] (the section is hidden)."""
    with SessionLocal() as db:
        rows = seniors_hub.today_seniors_rows(db, day=date(2099, 12, 25))
    assert rows == []


def test_seniors_feed_excludes_non_senior_event() -> None:
    today = now_lake_havasu().date()
    suf = uuid.uuid4().hex[:8]
    title = f"ZZ Teen Skate Night {suf}"  # youth, not senior-tagged/venued
    with SessionLocal() as db:
        ev = Event(
            title=title,
            normalized_title=title.lower(),
            date=today,
            start_time=time(18, 0),
            end_time=None,
            location_name="Skate Park",
            location_normalized="skate park",
            description="x",
            event_url="https://example.com/e",
            tags=["youth"],
            status="live",
            source="test-ws10-seniors",
            verified=True,
        )
        db.add(ev)
        db.flush()
        eid = ev.entity_id
        db.commit()
    try:
        with SessionLocal() as db:
            rows = seniors_hub.today_seniors_rows(db, day=today)
        assert not any(r["title"].startswith("ZZ Teen Skate Night") for r in rows)
    finally:
        _cleanup([eid])
