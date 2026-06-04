"""Tests for the admin Jobs portal — model, store, API, and HTML page.

TestClient(app) against the isolated session SQLite DB from conftest.py. The
admin endpoints use the session cookie (``/admin/login``); the worker endpoints
use the machine-ingest bearer token (``INGEST_API_TOKEN``).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.jobs_store import claim_next_job, create_job
from app.db.models import Job
from app.main import app

_TOKEN = "test-ingest-token-jobs"


@pytest.fixture(autouse=True)
def _clean_jobs() -> None:
    """Each test starts with an empty jobs table so claim-ordering is deterministic."""
    with SessionLocal() as db:
        db.execute(delete(Job))
        db.commit()
    yield


@pytest.fixture
def client() -> TestClient:
    os.environ["INGEST_API_TOKEN"] = _TOKEN
    return TestClient(app)


def _auth() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


# --- admin-session auth on admin routes ---------------------------------


def test_post_jobs_requires_admin(client: TestClient) -> None:
    client.cookies.clear()
    r = client.post("/api/admin/jobs", json={"job_type": "schedule_hunt"})
    assert r.status_code == 401


def test_get_jobs_requires_admin(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/api/admin/jobs")
    assert r.status_code == 401


def test_admin_jobs_page_requires_login(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/jobs", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/admin/login"


# --- create + history ---------------------------------------------------


def test_create_job_queued(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/admin/jobs", json={"job_type": "schedule_hunt", "params": {"x": 1}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_type"] == "schedule_hunt"
    assert body["params"] == {"x": 1}
    assert body["requested_by"] == "admin"


def test_create_job_unknown_type_422(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/admin/jobs", json={"job_type": "not_a_real_type"})
    assert r.status_code == 422


def test_create_discovery_audit_job(client: TestClient) -> None:
    """Kickoff addition 1a: the 5th job type is accepted and routes to cowork."""
    _login(client)
    r = client.post("/api/admin/jobs", json={"job_type": "discovery_audit"})
    assert r.status_code == 201
    assert r.json()["job_type"] == "discovery_audit"


def test_history_lists_newest_first(client: TestClient) -> None:
    _login(client)
    client.post("/api/admin/jobs", json={"job_type": "schedule_hunt"})
    client.post("/api/admin/jobs", json={"job_type": "publish_approved"})
    r = client.get("/api/admin/jobs?limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert rows[0]["job_type"] == "publish_approved"  # newest first


# --- worker claim (lifecycle + auth + routing) --------------------------


def test_pending_requires_token(client: TestClient) -> None:
    r = client.get("/api/ingest/jobs/pending?worker=cowork")
    assert r.status_code == 401


def test_pending_unknown_worker_422(client: TestClient) -> None:
    r = client.get("/api/ingest/jobs/pending?worker=martians", headers=_auth())
    assert r.status_code == 422


def test_claim_marks_job_claimed(client: TestClient) -> None:
    _login(client)
    created = client.post("/api/admin/jobs", json={"job_type": "fb_capture_sweep"}).json()
    r = client.get("/api/ingest/jobs/pending?worker=openclaw", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == created["id"]
    assert body["status"] == "claimed"
    assert body["claimed_by"] == "openclaw"
    assert body["claimed_at"] is not None


def test_empty_queue_returns_204(client: TestClient) -> None:
    r = client.get("/api/ingest/jobs/pending?worker=cowork", headers=_auth())
    assert r.status_code == 204
    assert r.content == b""


def test_worker_type_map_routing(client: TestClient) -> None:
    """OpenClaw only sees fb_capture_sweep; Cowork sees the other four."""
    _login(client)
    client.post("/api/admin/jobs", json={"job_type": "fb_capture_sweep"})
    client.post("/api/admin/jobs", json={"job_type": "schedule_hunt"})

    # OpenClaw must not pick up the schedule_hunt job.
    r = client.get("/api/ingest/jobs/pending?worker=openclaw", headers=_auth())
    assert r.json()["job_type"] == "fb_capture_sweep"
    # No more openclaw work remains.
    assert client.get("/api/ingest/jobs/pending?worker=openclaw", headers=_auth()).status_code == 204
    # Cowork gets the schedule_hunt job.
    r = client.get("/api/ingest/jobs/pending?worker=cowork", headers=_auth())
    assert r.json()["job_type"] == "schedule_hunt"


def test_double_claim_does_not_hand_out_same_job(client: TestClient) -> None:
    """Two polls of the same queued job: one wins, the next sees an empty queue."""
    _login(client)
    client.post("/api/admin/jobs", json={"job_type": "fb_capture_sweep"})
    first = client.get("/api/ingest/jobs/pending?worker=openclaw", headers=_auth())
    second = client.get("/api/ingest/jobs/pending?worker=openclaw", headers=_auth())
    assert first.status_code == 200
    assert second.status_code == 204


# --- worker patch (finish) ----------------------------------------------


def test_patch_running_then_done(client: TestClient) -> None:
    _login(client)
    created = client.post("/api/admin/jobs", json={"job_type": "capture_review"}).json()
    jid = created["id"]
    r = client.patch(f"/api/ingest/jobs/{jid}", headers=_auth(), json={"status": "running"})
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["finished_at"] is None
    r = client.patch(
        f"/api/ingest/jobs/{jid}",
        headers=_auth(),
        json={"status": "done", "result_summary": "12 venues reviewed"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["result_summary"] == "12 venues reviewed"
    assert body["finished_at"] is not None


def test_patch_invalid_status_422(client: TestClient) -> None:
    _login(client)
    created = client.post("/api/admin/jobs", json={"job_type": "schedule_hunt"}).json()
    r = client.patch(
        f"/api/ingest/jobs/{created['id']}", headers=_auth(), json={"status": "queued"}
    )
    assert r.status_code == 422


def test_patch_missing_job_404(client: TestClient) -> None:
    r = client.patch("/api/ingest/jobs/nope", headers=_auth(), json={"status": "done"})
    assert r.status_code == 404


def test_patch_requires_token(client: TestClient) -> None:
    r = client.patch("/api/ingest/jobs/whatever", json={"status": "done"})
    assert r.status_code == 401


# --- store-level atomic claim -------------------------------------------


def test_store_claim_is_fifo_and_single_use() -> None:
    with SessionLocal() as db:
        a = create_job(db, "schedule_hunt")
        create_job(db, "publish_approved")
        # Oldest queued cowork job comes out first.
        first = claim_next_job(db, "cowork")
        assert first is not None and first.id == a.id
        assert first.status == "claimed"
        second = claim_next_job(db, "cowork")
        assert second is not None and second.id != a.id
        # Nothing left.
        assert claim_next_job(db, "cowork") is None


def test_store_unknown_worker_returns_none() -> None:
    with SessionLocal() as db:
        create_job(db, "schedule_hunt")
        assert claim_next_job(db, "nobody") is None


# --- admin Jobs HTML page -----------------------------------------------


def test_jobs_page_renders_buttons(client: TestClient) -> None:
    _login(client)
    r = client.get("/admin/jobs")
    assert r.status_code == 200
    for label in (
        "Hunt schedules (websites)",
        "Capture Facebook (OpenClaw)",
        "Review captures",
        "Publish approved",
        "Discovery audit (find new venues)",
    ):
        assert label in r.text


def test_jobs_page_button_queues_and_disables(client: TestClient) -> None:
    _login(client)
    r = client.post(
        "/admin/jobs/create", data={"job_type": "schedule_hunt"}, follow_redirects=False
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        rows = db.query(Job).filter(Job.job_type == "schedule_hunt").all()
        assert len(rows) == 1
    # The button for an in-flight type is disabled on the next render.
    page = client.get("/admin/jobs").text
    assert "disabled" in page
