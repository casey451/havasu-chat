"""Tests for the screenshot capture bridge (image inbox) API.

Mirrors tests/test_ingest_api.py: TestClient(app) against the isolated session
SQLite DB from conftest.py. ``upload_bytes`` is monkeypatched so no real R2
call happens.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import ScrapeCapture
from app.main import app

_TOKEN = "test-ingest-token-123"
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    os.environ["INGEST_API_TOKEN"] = _TOKEN

    def _fake_upload(key: str, content: bytes, content_type: str) -> str:
        return f"https://pub-test.r2.dev/{key}"

    # Patch the symbol as imported into the captures route module.
    monkeypatch.setattr("app.api.routes.captures.upload_bytes", _fake_upload)
    return TestClient(app)


def _auth() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


# --- auth ---------------------------------------------------------------


def test_post_requires_token(client: TestClient) -> None:
    r = client.post("/api/ingest/capture", data={"source_url": "https://fb.com/x"})
    assert r.status_code == 401


def test_get_requires_token(client: TestClient) -> None:
    r = client.get("/api/ingest/captures")
    assert r.status_code == 401


def test_patch_requires_token(client: TestClient) -> None:
    r = client.patch("/api/ingest/captures/nope", json={"status": "reviewed"})
    assert r.status_code == 401


def test_bad_token_rejected(client: TestClient) -> None:
    r = client.get("/api/ingest/captures", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


# --- POST ---------------------------------------------------------------


def test_post_with_image(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={
            "business_name": "Test Cantina",
            "source_url": "https://facebook.com/testcantina/posts/1",
            "captured_at": "2026-06-03T12:00:00",
            "notes": "looks like a taco special",
        },
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "new"
    assert body["image_url"]
    with SessionLocal() as db:
        row = db.get(ScrapeCapture, body["id"])
        assert row is not None
        assert row.status == "new"
        assert row.image_url
        assert row.image_key
        assert row.business_name == "Test Cantina"


def test_post_without_image_is_flagged(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={
            "source_url": "https://facebook.com/blocked-page",
            "notes": "page blocked, no FB page found",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "flagged"
    assert body["image_url"] is None
    with SessionLocal() as db:
        row = db.get(ScrapeCapture, body["id"])
        assert row is not None
        assert row.status == "flagged"
        assert row.image_url is None
        assert row.notes == "page blocked, no FB page found"


def test_post_bad_captured_at_is_422(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"source_url": "https://fb.com/x", "captured_at": "not-a-date"},
    )
    assert r.status_code == 422


# --- GET ----------------------------------------------------------------


def test_get_returns_new_rows(client: TestClient) -> None:
    src = "https://facebook.com/get-test/posts/77"
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"source_url": src},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    assert r.status_code == 201
    created_id = r.json()["id"]

    r = client.get("/api/ingest/captures", headers=_auth(), params={"status": "new"})
    assert r.status_code == 200
    rows = r.json()
    assert any(row["id"] == created_id and row["source_url"] == src for row in rows)
    assert all(row["status"] == "new" for row in rows)


# --- PATCH --------------------------------------------------------------


def test_patch_updates_status(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"source_url": "https://facebook.com/patch-test"},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    capture_id = r.json()["id"]

    r = client.patch(
        f"/api/ingest/captures/{capture_id}",
        headers=_auth(),
        json={"status": "reviewed"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "reviewed"
    with SessionLocal() as db:
        row = db.get(ScrapeCapture, capture_id)
        assert row is not None
        assert row.status == "reviewed"


def test_patch_invalid_status_is_422(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"source_url": "https://facebook.com/patch-bad"},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    capture_id = r.json()["id"]

    r = client.patch(
        f"/api/ingest/captures/{capture_id}",
        headers=_auth(),
        json={"status": "published"},
    )
    assert r.status_code == 422


def test_patch_missing_id_is_404(client: TestClient) -> None:
    r = client.patch(
        "/api/ingest/captures/does-not-exist",
        headers=_auth(),
        json={"status": "discarded"},
    )
    assert r.status_code == 404


# --- PATCH rename (kickoff addition 1b) ---------------------------------


def test_patch_renames_business_name(client: TestClient) -> None:
    """A review pass can fix a mislabeled capture's name without touching status."""
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"business_name": "Wrong Name", "source_url": "https://facebook.com/rename-test"},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    capture_id = r.json()["id"]

    r = client.patch(
        f"/api/ingest/captures/{capture_id}",
        headers=_auth(),
        json={"business_name": "Flying X Saloon"},
    )
    assert r.status_code == 200
    assert r.json()["business_name"] == "Flying X Saloon"
    with SessionLocal() as db:
        row = db.get(ScrapeCapture, capture_id)
        assert row is not None
        assert row.business_name == "Flying X Saloon"
        assert row.status == "new"  # untouched


def test_patch_rename_and_status_together(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"business_name": "The Ofice", "source_url": "https://facebook.com/rename-both"},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    capture_id = r.json()["id"]

    r = client.patch(
        f"/api/ingest/captures/{capture_id}",
        headers=_auth(),
        json={"business_name": "The Office", "status": "reviewed"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["business_name"] == "The Office"
    assert body["status"] == "reviewed"


def test_patch_empty_body_is_422(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/capture",
        headers=_auth(),
        data={"source_url": "https://facebook.com/empty-patch"},
        files={"image": ("shot.png", _TINY_PNG, "image/png")},
    )
    capture_id = r.json()["id"]

    r = client.patch(f"/api/ingest/captures/{capture_id}", headers=_auth(), json={})
    assert r.status_code == 422
