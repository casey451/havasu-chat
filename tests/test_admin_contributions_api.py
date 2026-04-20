"""Tests for admin JSON contribution routes (Phase 5.1)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def test_post_contributions_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "x",
            "source": "operator_backfill",
        },
    )
    assert r.status_code == 401


def test_post_contributions_with_auth(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "API auth row",
            "source": "operator_backfill",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["submission_name"] == "API auth row"
    assert body["status"] == "pending"


def test_post_invalid_entity_type(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "not_valid",
            "submission_name": "x",
            "source": "operator_backfill",
        },
    )
    assert r.status_code == 422


def test_post_provider_without_url(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "provider",
            "submission_name": "No URL",
            "source": "operator_backfill",
        },
    )
    assert r.status_code == 422


def test_get_list_and_filters(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "filter list marker",
            "source": "operator_backfill",
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    lst = client.get("/admin/contributions?limit=100")
    assert lst.status_code == 200
    ids = {row["id"] for row in lst.json()}
    assert cid in ids
    by_status = client.get("/admin/contributions?status=pending&limit=200")
    assert by_status.status_code == 200
    assert cid in {row["id"] for row in by_status.json()}


def test_get_by_id_and_404(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "single fetch",
            "source": "operator_backfill",
        },
    )
    cid = r.json()["id"]
    g = client.get(f"/admin/contributions/{cid}")
    assert g.status_code == 200
    assert g.json()["id"] == cid
    miss = client.get("/admin/contributions/999999999")
    assert miss.status_code == 404


def test_patch_status(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "patch target",
            "source": "operator_backfill",
        },
    )
    cid = r.json()["id"]
    p = client.patch(
        f"/admin/contributions/{cid}/status",
        json={"status": "approved", "review_notes": "lgtm"},
    )
    assert p.status_code == 200
    assert p.json()["status"] == "approved"
    assert p.json()["review_notes"] == "lgtm"
    assert p.json()["reviewed_at"] is not None


def test_patch_rejected_requires_reason(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.post(
        "/admin/contributions",
        json={
            "entity_type": "tip",
            "submission_name": "reject probe",
            "source": "operator_backfill",
        },
    )
    cid = r.json()["id"]
    bad = client.patch(
        f"/admin/contributions/{cid}/status",
        json={"status": "rejected"},
    )
    assert bad.status_code == 422
    ok = client.patch(
        f"/admin/contributions/{cid}/status",
        json={"status": "rejected", "rejection_reason": "spam"},
    )
    assert ok.status_code == 200
    assert ok.json()["rejection_reason"] == "spam"
