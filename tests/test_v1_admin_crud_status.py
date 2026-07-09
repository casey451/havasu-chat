"""v1 admin CRUD event-status hygiene (audit 2026-07-01).

The events table enforces ck_events_status
('draft','live','cancelled','expired','pending_review','deleted','duplicate').
DELETE used to write "hidden" — an IntegrityError -> 500 on prod Postgres —
and PATCH/POST accepted any status string unvalidated. Statuses are now
validated at the API boundary and soft-delete writes "deleted".
"""

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

_DAY = date(2099, 9, 14)


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303
    return c


def _add_event(title: str) -> str:
    with SessionLocal() as db:
        ev = Event(
            title=title, normalized_title=title.lower(), date=_DAY,
            start_time=time(19, 0), end_time=None, location_name="Rotary Park",
            location_normalized="rotary park", description="x",
            event_url="https://example.com/e", tags=[],
            status="live", source="manual", verified=True, is_recurring=False,
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


def test_delete_soft_deletes_with_check_safe_status(client: TestClient) -> None:
    eid = _add_event(f"ZZ CRUD Delete {uuid.uuid4().hex[:6]}")
    try:
        r = client.delete(f"/api/admin/events/{eid}")
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"
        with SessionLocal() as db:
            assert db.get(Event, eid).status == "deleted"
    finally:
        _cleanup([eid])


def test_patch_rejects_status_outside_check_vocabulary(client: TestClient) -> None:
    eid = _add_event(f"ZZ CRUD Patch {uuid.uuid4().hex[:6]}")
    try:
        r = client.patch(f"/api/admin/events/{eid}", json={"status": "hidden"})
        assert r.status_code == 422
        with SessionLocal() as db:
            assert db.get(Event, eid).status == "live"  # unchanged
        ok = client.patch(f"/api/admin/events/{eid}", json={"status": "cancelled"})
        assert ok.status_code == 200
        with SessionLocal() as db:
            assert db.get(Event, eid).status == "cancelled"
    finally:
        _cleanup([eid])


def test_list_events_total_reflects_full_count_not_page(client: TestClient) -> None:
    ids = [_add_event(f"ZZ CRUD Count {uuid.uuid4().hex[:6]}-{n}") for n in range(3)]
    try:
        r = client.get("/api/admin/events", params={"limit": 1, "status": "live"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1
        assert body["total"] >= 3  # the real filtered count, not len(page)
    finally:
        _cleanup(ids)
