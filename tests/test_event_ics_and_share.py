"""UX-4: per-event "Add to calendar" (.ics) + Share + organizer card.

The single-event .ics reuses the sitewide feed's VEVENT builder; the route is
registered before the HTML permalink so ``/events/{id}.ics`` is not swallowed by
the ``{event_id}`` catch-all.
"""

from __future__ import annotations

from datetime import date, time

from fastapi.testclient import TestClient

from app.api.routes.calendar_feed import build_single_event_ics
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate

client = TestClient(app)


def _make_event(*, title: str, status: str = "live", contact: bool = True) -> str:
    payload = EventCreate(
        title=title,
        date=date(2026, 6, 18),
        end_date=None,
        start_time=time(18, 30, 0),
        end_time=time(21, 0, 0),
        location_name="London Bridge Beach",
        description="Live music and local vendors.",
        event_url="https://example.com/event",
        contact_name="Havasu Events Team" if contact else None,
        contact_phone="928-555-0102" if contact else None,
        tags=["music", "community"],
        embedding=None,
        status=status,
        created_by="user",
        admin_review_by=None,
    )
    with SessionLocal() as db:
        ev = Event.from_create(payload)
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev.id


def test_single_event_ics_builder():
    eid = _make_event(title="Builder Test Event")
    with SessionLocal() as db:
        ev = db.query(Event).filter(Event.id == eid).first()
        ics = build_single_event_ics(ev)
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in ics and "END:VEVENT" in ics
    assert "SUMMARY:Builder Test Event" in ics
    assert ics.endswith("\r\n")


def test_event_ics_route_serves_calendar():
    eid = _make_event(title="ICS Route Event")
    r = client.get(f"/events/{eid}.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in r.text
    assert "ICS Route Event" in r.text
    assert "attachment" in r.headers.get("content-disposition", "")


def test_ics_route_404_for_unknown():
    # Proves the .ics route is matched (not the HTML catch-all) and 404s cleanly.
    r = client.get("/events/does-not-exist-xyz.ics")
    assert r.status_code == 404


def test_permalink_has_addtocal_share_and_organizer():
    eid = _make_event(title="Followthrough Event")
    r = client.get(f"/events/{eid}")
    assert r.status_code == 200
    body = r.text
    assert f"/events/{eid}.ics" in body
    assert "Add to calendar" in body
    assert 'id="ev-share"' in body
    assert "Contact:" in body  # organizer info renders when contact fields exist


def test_permalink_omits_organizer_when_no_contact():
    eid = _make_event(title="No Organizer Event", contact=False)
    r = client.get(f"/events/{eid}")
    assert r.status_code == 200
    # Honest omission: no Contact line when the event has no organizer fields.
    assert "<strong>Contact:</strong>" not in r.text
