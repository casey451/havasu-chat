"""Tests for the schedule-hunt auto-publish loop: policy + ingest trigger + batch.

TestClient(app) against the isolated session SQLite DB. The kill-switch
``SCHEDULE_HUNT_AUTOPUBLISH`` is toggled per-test via monkeypatch (the policy
reads env at call time). Each test seeds its own Entity and cleans up.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.contrib import autopublish_policy as pol
from app.db.database import SessionLocal
from app.db.models import (
    ContactPoint,
    Contribution,
    Entity,
    Offering,
    Schedule,
    SourceEvidence,
)
from app.main import app

_TOKEN = "test-ingest-token-autopub"

_RECORD = {
    "title": "Morning Bootcamp",
    "description": "High-intensity outdoor bootcamp for all fitness levels.",
    "schedule_days": ["tuesday", "thursday"],
    "schedule_start_time": "06:00",
    "schedule_end_time": "07:00",
    "location_name": "Iron Age Gym",
    "provider_name": "Iron Age Gym",
    "cost": "$10",
}


@pytest.fixture
def client() -> TestClient:
    os.environ["INGEST_API_TOKEN"] = _TOKEN
    return TestClient(app)


def _auth() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _seed_entity(name: str = "Iron Age Gym") -> str:
    eid = str(uuid4())
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type="commercial",
                slug=f"ap-{eid[:8]}",
                name=name,
                source="test-autopub",
                is_active=True,
            )
        )
        db.commit()
    return eid


def _cleanup(eid: str) -> None:
    with SessionLocal() as db:
        for tbl in (Offering, Schedule, ContactPoint, SourceEvidence):
            for r in db.query(tbl).filter(tbl.entity_id == eid):
                db.delete(r)
        for c in db.query(Contribution).filter(Contribution.target_entity_id == eid):
            db.delete(c)
        e = db.get(Entity, eid)
        if e:
            db.delete(e)
        db.commit()


def _payload(eid: str, **over: object) -> dict:
    base: dict = {
        "entity_type": "program",
        "submission_name": "Iron Age Gym",
        "confidence": 0.95,
        "target_entity_id": eid,
        "proposed_record": dict(_RECORD),
    }
    base.update(over)
    return base


# --- policy unit --------------------------------------------------------


def test_enabled_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH", raising=False)
    assert pol.autopublish_enabled() is False
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH", "1")
    assert pol.autopublish_enabled() is True


def test_threshold_default_and_clamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD", raising=False)
    assert pol.autopublish_threshold() == 0.85
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD", "0.7")
    assert pol.autopublish_threshold() == 0.7
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD", "5")
    assert pol.autopublish_threshold() == 1.0


def test_meets_confidence_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH_THRESHOLD", raising=False)
    ok = Contribution(entity_type="program", submission_name="x", confidence=0.9, proposed_record={"a": 1})
    assert pol.meets_confidence_bar(ok) is True
    low = Contribution(entity_type="program", submission_name="x", confidence=0.5, proposed_record={"a": 1})
    assert pol.meets_confidence_bar(low) is False
    not_prog = Contribution(entity_type="event", submission_name="x", confidence=0.9, proposed_record={"a": 1})
    assert pol.meets_confidence_bar(not_prog) is False
    no_record = Contribution(entity_type="program", submission_name="x", confidence=0.9, proposed_record=None)
    assert pol.meets_confidence_bar(no_record) is False


# --- ingest auto-publish trigger ----------------------------------------


def test_ingest_autopublishes_when_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH", "1")
    eid = _seed_entity()
    try:
        r = client.post("/api/ingest/contribution", headers=_auth(), json=_payload(eid))
        assert r.status_code in (200, 201)
        body = r.json()
        assert body["status"] == "published"
        assert body["entity_id"] == eid
        with SessionLocal() as db:
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 1
            assert db.query(Offering).filter(Offering.entity_id == eid).count() == 1
    finally:
        _cleanup(eid)


def test_ingest_queues_when_disabled_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH", raising=False)
    eid = _seed_entity()
    try:
        r = client.post("/api/ingest/contribution", headers=_auth(), json=_payload(eid))
        body = r.json()
        assert body["status"] == "queued"
        with SessionLocal() as db:
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 0
    finally:
        _cleanup(eid)


def test_ingest_queues_low_confidence(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH", "1")
    eid = _seed_entity()
    try:
        r = client.post(
            "/api/ingest/contribution", headers=_auth(), json=_payload(eid, confidence=0.4)
        )
        assert r.json()["status"] == "queued"
        with SessionLocal() as db:
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 0
    finally:
        _cleanup(eid)


def test_ingest_queues_when_no_entity_match(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH", "1")
    # high confidence but target does not exist and name won't reconcile
    payload = {
        "entity_type": "program",
        "submission_name": "Ghost Studio No Match 9Z",
        "confidence": 0.99,
        "target_entity_id": "nope-missing",
        "proposed_record": dict(_RECORD),
    }
    r = client.post("/api/ingest/contribution", headers=_auth(), json=payload)
    body = r.json()
    assert body["status"] == "queued"
    with SessionLocal() as db:
        c = db.get(Contribution, body["id"])
        assert c.status == "pending"
        db.delete(c)
        db.commit()


# --- batch publish endpoint ---------------------------------------------


def test_publish_endpoint_requires_token(client: TestClient) -> None:
    r = client.post("/api/ingest/publish", json={})
    assert r.status_code == 401


def test_publish_dry_run_writes_nothing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH", raising=False)  # disabled
    eid = _seed_entity()
    try:
        # Queue a high-confidence pending row (disabled, so it stays pending).
        cid = client.post("/api/ingest/contribution", headers=_auth(), json=_payload(eid)).json()["id"]
        r = client.post("/api/ingest/publish", headers=_auth(), json={"dry_run": True})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert cid in body["would_publish_ids"]
        with SessionLocal() as db:
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 0  # no write
    finally:
        _cleanup(eid)


def test_publish_batch_respects_gate_and_is_idempotent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SCHEDULE_HUNT_AUTOPUBLISH", raising=False)
    eid = _seed_entity()
    try:
        cid = client.post("/api/ingest/contribution", headers=_auth(), json=_payload(eid)).json()["id"]
        # Gate off → publishes nothing.
        r = client.post("/api/ingest/publish", headers=_auth(), json={"contribution_ids": [cid]})
        assert r.json()["published"] == 0
        # Gate on → publishes it.
        monkeypatch.setenv("SCHEDULE_HUNT_AUTOPUBLISH", "1")
        r = client.post("/api/ingest/publish", headers=_auth(), json={"contribution_ids": [cid]})
        assert r.json()["published"] == 1
        # Idempotent second call.
        r = client.post("/api/ingest/publish", headers=_auth(), json={"contribution_ids": [cid]})
        assert r.json()["published"] == 0
        with SessionLocal() as db:
            assert db.query(Schedule).filter(Schedule.entity_id == eid).count() == 1
    finally:
        _cleanup(eid)
