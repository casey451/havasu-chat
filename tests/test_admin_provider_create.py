"""Slice 45 — admin direct-create provider UI."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


def _login_admin(client: TestClient) -> None:
    """Set a valid signed admin cookie on the client."""
    client.cookies.set(COOKIE_NAME, sign_admin_cookie())


def test_admin_provider_new_form_requires_login() -> None:
    client = TestClient(app)
    resp = client.get("/admin/providers/new", follow_redirects=False)
    assert resp.status_code in (302, 303), "unauthenticated GET should redirect"


def test_admin_provider_new_form_renders_when_logged_in() -> None:
    client = TestClient(app)
    _login_admin(client)
    resp = client.get("/admin/providers/new")
    assert resp.status_code == 200
    assert "<form" in resp.text
    assert 'action="/admin/providers"' in resp.text


def test_admin_provider_create_happy_path() -> None:
    client = TestClient(app)
    _login_admin(client)
    resp = client.post(
        "/admin/providers",
        data={
            "provider_name": "Test Provider Slice 45",
            "category": "test_category",
            "address": "123 Test St",
            "phone": "(928) 555-1234",
            "hours": "Mon-Fri 9am-5pm",
            "website": "https://example.com",
            "description": "A provider created by Slice 45 tests.",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, (
        f"expected 303 redirect, got {resp.status_code}: {resp.text[:200]}"
    )
    assert resp.headers["location"] == "/admin"

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name == "Test Provider Slice 45")
            .all()
        )
        assert len(rows) == 1
        p = rows[0]
        assert p.category == "test_category"
        assert p.is_active is True
        assert p.verified is True
        assert p.source == "admin"
        # Cleanup so re-runs don't accumulate.
        db.delete(p)
        db.commit()


def test_admin_provider_create_rejects_missing_name() -> None:
    client = TestClient(app)
    _login_admin(client)
    resp = client.post(
        "/admin/providers",
        data={"provider_name": "", "category": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Name is required" in resp.text


def test_admin_provider_create_rejects_missing_category() -> None:
    client = TestClient(app)
    _login_admin(client)
    resp = client.post(
        "/admin/providers",
        data={"provider_name": "Some Provider", "category": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Category is required" in resp.text


def test_admin_provider_create_requires_login() -> None:
    client = TestClient(app)
    resp = client.post(
        "/admin/providers",
        data={"provider_name": "X", "category": "y"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), "unauthenticated POST should redirect"
