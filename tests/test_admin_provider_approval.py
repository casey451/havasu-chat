"""Admin provider approval queue tests (draft + pending_review providers)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug
from app.main import app


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def admin_client():
    """TestClient authenticated via admin login (same as contributions tests)."""
    c = TestClient(app)
    c.cookies.clear()
    _login(c)
    return c


def _pending_provider(db, name: str = "Held Cafe") -> Provider:
    prov = Provider(
        provider_name=name,
        category="restaurant",
        slug=derive_provider_slug(db, name),
        source="go_lake_havasu",
        draft=True,
        pending_review=True,
        is_active=True,
    )
    db.add(prov)
    create_provider_and_entity(db, prov)
    db.commit()
    return prov


def test_pending_queue_lists_held_providers(admin_client, db_session) -> None:
    prov = _pending_provider(db_session, "Queue Visible Cafe")
    resp = admin_client.get("/admin/providers/pending")
    assert resp.status_code == 200
    assert "Queue Visible Cafe" in resp.text
    assert prov.id in resp.text


def test_approve_makes_provider_live(admin_client, db_session) -> None:
    prov = _pending_provider(db_session, "Approve Me Grill")
    pid = prov.id
    resp = admin_client.post(f"/admin/provider/{pid}/approve", follow_redirects=False)
    assert resp.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(Provider, pid)
    assert refreshed.draft is False
    assert refreshed.pending_review is False
    assert refreshed.is_active is True


def test_reject_deactivates_provider(admin_client, db_session) -> None:
    prov = _pending_provider(db_session, "Reject Me Bar")
    pid = prov.id
    resp = admin_client.post(f"/admin/provider/{pid}/reject", follow_redirects=False)
    assert resp.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(Provider, pid)
    assert refreshed.is_active is False
    assert refreshed.pending_review is False


def test_approve_missing_provider_404(admin_client) -> None:
    resp = admin_client.post("/admin/provider/nonexistent-id/approve", follow_redirects=False)
    assert resp.status_code == 404


def test_pending_requires_admin(db_session) -> None:
    """Unauthenticated request is redirected to admin login, not served."""
    anon = TestClient(app)
    resp = anon.get("/admin/providers/pending", follow_redirects=False)
    assert resp.status_code == 302  # unified guard status (2026-07-02)
    assert "/admin/login" in resp.headers.get("location", "")


def test_pending_count_helper(db_session) -> None:
    from app.admin.provider_approval import pending_provider_count

    before = pending_provider_count(db_session)
    _pending_provider(db_session, "Counted Cafe")
    assert pending_provider_count(db_session) == before + 1
