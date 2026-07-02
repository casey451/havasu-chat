"""Admin "Missing time" review queue (Item 2): surface TBD-time events and let a
human set the real start time off the flyer, reusing the existing edit endpoint."""

from __future__ import annotations

import os
import uuid
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.main import app

_DAY = date(2099, 8, 3)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


# The DB column is NOT NULL, so a time-unknown event is stored as the 00:00
# midnight sentinel (the aggregator-ingest fallback) — is_time_tbd treats a bare
# midnight start with no real end as "Time TBD" (see app/events/time_labels.py).
_TBD = time(0, 0)


def _add_event(*, title: str, start: time, source: str, url: str = "") -> str:
    with SessionLocal() as db:
        ev = Event(
            title=title, normalized_title=title.lower(), date=_DAY,
            start_time=start, end_time=None, location_name="Rotary Park",
            location_normalized="rotary park", description="x",
            event_url="https://example.com/e", source_url=url, tags=[],
            status="live", source=source, verified=True, is_recurring=False,
        )
        db.add(ev)
        db.commit()
        return ev.id


def _cleanup(ids: list[str]) -> None:
    with SessionLocal() as db:
        ents = [e.entity_id for e in db.query(Event).filter(Event.id.in_(ids)).all()]
        db.execute(delete(Event).where(Event.id.in_(ids)))
        if ents:
            db.execute(delete(Entity).where(Entity.id.in_(ents)))
        db.commit()


def test_missing_times_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/events/missing-times", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_missing_times_lists_tbd_and_save_drops_it(client: TestClient) -> None:
    s = uuid.uuid4().hex[:6]
    tbd_title = f"ZZ Kids Fishing {s}"        # no start time -> "Time TBD"
    timed_title = f"ZZ Concert {s}"           # has a real time -> not listed
    ids = [
        _add_event(title=tbd_title, start=_TBD, source="parks_rec_flyers",
                   url="https://example.com/flyer.jpg"),
        _add_event(title=timed_title, start=time(19, 0), source="allevents"),
    ]
    try:
        client.cookies.clear()
        _login(client)

        r = client.get("/admin/events/missing-times")
        assert r.status_code == 200
        assert tbd_title in r.text
        assert timed_title not in r.text
        # Vision source is flagged and links to the flyer + the locking edit form.
        assert "https://example.com/flyer.jpg" in r.text
        assert f"/admin/events/{ids[0]}/edit?lock=1" in r.text

        # The locking edit form pre-checks operator_override.
        form = client.get(f"/admin/events/{ids[0]}/edit?lock=1")
        assert form.status_code == 200
        assert 'name="operator_override" value="1" checked' in form.text

        # Setting the time via the existing edit endpoint, with the lock on.
        save = client.post(
            f"/admin/events/{ids[0]}/edit",
            data={
                "title": tbd_title, "date": _DAY.isoformat(),
                "start_time": "10:00", "end_time": "12:00",
                "operator_override": "1",
            },
            follow_redirects=False,
        )
        assert save.status_code == 303

        with SessionLocal() as db:
            ev = db.get(Event, ids[0])
            assert ev.start_time == time(10, 0)
            assert ev.end_time == time(12, 0)
            assert ev.operator_override is True

        # It now drops off the Missing-time queue.
        r2 = client.get("/admin/events/missing-times")
        assert tbd_title not in r2.text
    finally:
        _cleanup(ids)


def test_missing_times_includes_pending_review(client: TestClient) -> None:
    # Regression (audit 2026-07-01): the queue filtered on a nonexistent
    # status "pending", so pending_review events with TBD times never
    # surfaced. The vocabulary is live/pending_review (ck_events_status).
    s = uuid.uuid4().hex[:6]
    pending_title = f"ZZ Pending Flyer {s}"
    ids = [_add_event(title=pending_title, start=_TBD, source="parks_rec_flyers")]
    with SessionLocal() as db:
        db.query(Event).filter(Event.id == ids[0]).update({"status": "pending_review"})
        db.commit()
    try:
        client.cookies.clear()
        _login(client)
        r = client.get("/admin/events/missing-times")
        assert r.status_code == 200
        assert pending_title in r.text
    finally:
        _cleanup(ids)


def test_edit_save_rejects_malformed_datetime_without_500(client: TestClient) -> None:
    # Malformed date/time on a direct POST must re-render with a flash, not 500,
    # and must not modify the row.
    s = uuid.uuid4().hex[:6]
    title = f"ZZ BadDate {s}"
    ids = [_add_event(title=title, start=time(19, 0), source="allevents")]
    try:
        client.cookies.clear()
        _login(client)
        save = client.post(
            f"/admin/events/{ids[0]}/edit",
            data={"title": title, "date": "not-a-date", "start_time": "19:00"},
            follow_redirects=False,
        )
        assert save.status_code == 303
        assert "flash=bad_datetime" in save.headers.get("location", "")
        with SessionLocal() as db:
            ev = db.get(Event, ids[0])
            assert ev.date == _DAY  # unchanged
        form = client.get(f"/admin/events/{ids[0]}/edit?flash=bad_datetime")
        assert "Not saved" in form.text
    finally:
        _cleanup(ids)


def test_flyer_link_neutralizes_javascript_scheme() -> None:
    # safe_href regression: scraped source URLs must not reach an admin href
    # with a javascript:/data: scheme (html.escape alone doesn't stop them).
    from app.admin.events_html import _missing_time_row_html

    ev = Event(
        title="ZZ Evil", normalized_title="zz evil", date=_DAY,
        start_time=_TBD, end_time=None, location_name="x",
        location_normalized="x", description="x",
        event_url="", source_url="javascript:alert(1)", tags=[],
        status="live", source="allevents", verified=True, is_recurring=False,
    )
    row_html = _missing_time_row_html(ev)
    assert 'href="javascript:' not in row_html
    assert 'href="#"' in row_html


def test_missing_times_source_filter(client: TestClient) -> None:
    s = uuid.uuid4().hex[:6]
    vis = f"ZZ Flyer Event {s}"
    other = f"ZZ Aggregator Event {s}"
    ids = [
        _add_event(title=vis, start=_TBD, source="parks_rec_flyers"),
        _add_event(title=other, start=_TBD, source="allevents"),
    ]
    try:
        client.cookies.clear()
        _login(client)
        r = client.get("/admin/events/missing-times?source=parks_rec_flyers")
        assert r.status_code == 200
        assert vis in r.text
        assert other not in r.text
    finally:
        _cleanup(ids)
