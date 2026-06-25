"""Admin broken-links review-list tests (link sentinel)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.admin.link_health_html import confirmed_broken_count
from app.db.database import SessionLocal
from app.db.models import LinkHealth
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


_URL = "https://broken-admin-test.example/dead"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    with SessionLocal() as db:
        db.execute(delete(LinkHealth).where(LinkHealth.url.like("https://%-admin-test.example/%")))
        db.commit()


def _make(url: str, *, confirmed: bool) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            LinkHealth(
                url=url,
                kind="provider_website",
                entity_id="pX",
                label="Dead Co",
                category="broken",
                http_status=404,
                detail="HTTP 404",
                consecutive_failures=3,
                first_checked_at=now,
                last_checked_at=now,
                confirmed_broken=confirmed,
            )
        )
        db.commit()


def test_requires_admin_auth(client: TestClient) -> None:
    r = client.get("/admin/link-health", follow_redirects=False)
    assert r.status_code == 302 and "/admin/login" in r.headers["location"]


def test_lists_confirmed_broken(client: TestClient) -> None:
    _make(_URL, confirmed=True)
    _login(client)
    r = client.get("/admin/link-health")
    assert r.status_code == 200
    assert _URL in r.text and "Dead Co" in r.text and "HTTP 404" in r.text


def test_hides_unconfirmed(client: TestClient) -> None:
    _make("https://maybe-admin-test.example/x", confirmed=False)
    _login(client)
    r = client.get("/admin/link-health")
    assert r.status_code == 200
    assert "maybe-admin-test.example" not in r.text


def test_confirmed_broken_count() -> None:
    _make(_URL, confirmed=True)
    with SessionLocal() as db:
        assert confirmed_broken_count(db) >= 1
