"""Tests for the machine-to-machine Facebook-scraper ingest API (Phase A).

Mirrors tests/test_admin_contributions_api.py style (TestClient(app) against the
isolated session SQLite DB from conftest.py).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Contribution
from app.main import app

_TOKEN = "test-ingest-token-123"


@pytest.fixture
def client() -> TestClient:
    os.environ["INGEST_API_TOKEN"] = _TOKEN
    return TestClient(app)


def _payload(**over: object) -> dict:
    base: dict = {
        "entity_type": "event",
        "submission_name": "Taco Tuesday @ Test Cantina",
        "submission_url": "https://facebook.com/testcantina/posts/123",
        "source_url": "https://facebook.com/testcantina",
        "submission_notes": "Half-price tacos, $3 margs, 4-7pm",
    }
    base.update(over)
    return base


def test_requires_token(client: TestClient) -> None:
    r = client.post("/api/ingest/contribution", json=_payload())
    assert r.status_code == 401


def test_rejects_wrong_token(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/contribution",
        headers={"Authorization": "Bearer not-the-token"},
        json=_payload(),
    )
    assert r.status_code == 401


def test_queues_with_valid_token(client: TestClient) -> None:
    r = client.post(
        "/api/ingest/contribution",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json=_payload(submission_url="https://facebook.com/unique-venue/posts/1"),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "queued"
    with SessionLocal() as db:
        row = db.get(Contribution, body["id"])
        assert row is not None
        assert row.source == "facebook_scrape"
        assert row.status == "pending"


def test_duplicate_url_is_idempotent(client: TestClient) -> None:
    url = "https://facebook.com/dupe-venue/posts/9"
    headers = {"Authorization": f"Bearer {_TOKEN}"}
    r1 = client.post("/api/ingest/contribution", headers=headers, json=_payload(submission_url=url))
    assert r1.status_code == 201
    r2 = client.post("/api/ingest/contribution", headers=headers, json=_payload(submission_url=url))
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


def test_source_cannot_be_spoofed(client: TestClient) -> None:
    """Even if the caller sends a different source, the server forces facebook_scrape."""
    r = client.post(
        "/api/ingest/contribution",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json=_payload(
            submission_url="https://facebook.com/spoof-venue/posts/1",
            source="operator_backfill",
        ),
    )
    assert r.status_code == 201
    with SessionLocal() as db:
        row = db.get(Contribution, r.json()["id"])
        assert row is not None
        assert row.source == "facebook_scrape"
