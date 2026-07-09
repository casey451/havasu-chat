"""Admin portal smoke tests (moved from app/admin_portal/smoke_test.py at wiring).

Builds a throwaway FastAPI app with the portal router and an in-memory
SQLite DB, then exercises every GET page and the role-change write path.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.admin_portal.audit_models import PortalBase
from app.admin_portal.router import portal_router
from app.db.database import get_db
from app.db.models import Base, User


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    PortalBase.metadata.create_all(engine)  # audit table present -> audited path exercised
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(portal_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with Session() as db:
        db.add(User(email="casey@example.com", role="end_user"))
        db.commit()

    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, sign_admin_cookie())
    yield c


PAGES = (
    "/admin/portal",
    "/admin/portal/traffic",
    "/admin/portal/traffic?window=7d",
    "/admin/portal/search",
    "/admin/portal/search?window=all",
    "/admin/portal/placements",
    "/admin/portal/feedback",
    "/admin/portal/feedback?status=resolved",
    "/admin/portal/moderation",
    "/admin/portal/addresses",
    "/admin/portal/users",
    "/admin/portal/chat",
    "/admin/portal/chat?days=30",
    "/admin/portal/ops",
    "/admin/portal/audit",
)


@pytest.mark.parametrize("path", PAGES)
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text[:300]


def test_unauthenticated_redirects_to_login(client):
    client.cookies.delete(COOKIE_NAME)
    resp = client.get("/admin/portal", follow_redirects=False)
    # 302 since the 2026-07-02 guard consolidation (the classic /admin guard's
    # status; the portal copy used 303).
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin/login"


def test_role_change_writes_audit(client):
    users_page = client.get("/admin/portal/users")
    assert "casey@example.com" in users_page.text

    # Find the user id via the detail link, then promote to merchant.
    import re

    match = re.search(r"/admin/portal/users/([0-9a-f-]{36})", users_page.text)
    assert match, "user detail link not found"
    user_id = match.group(1)

    resp = client.post(f"/admin/portal/users/{user_id}/role", data={"role": "merchant"})
    assert resp.status_code == 200  # after redirect

    audit = client.get("/admin/portal/audit")
    assert "user.role_change" in audit.text


def test_wired_app_serves_portal_unauthenticated_redirect():
    """The REAL app (not the throwaway) now registers the portal router."""
    from app.main import app as real_app

    with TestClient(real_app) as c:
        resp = c.get("/admin/portal", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin/login"


def test_address_flags_queue_lists_and_dismisses(client):
    """WS-4 flag queue: a city-repeat row surfaces, 'Mark OK' persists the
    dismissal (Provider.attributes), and the row stops surfacing."""
    from app.db.models import Entity, Location, Provider

    # Seed through the SAME override session factory the app uses.
    app_obj = client.app
    override = app_obj.dependency_overrides[get_db]
    db = next(override())
    ent = Entity(entity_type="provider", slug="flagged-biz", name="Flagged Biz")
    db.add(ent)
    db.flush()
    db.add(
        Location(
            entity_id=ent.id,
            address="123 Main St, Lake Havasu City, AZ 86403, Lake Havasu City",
        )
    )
    prov = Provider(
        provider_name="Flagged Biz",
        category="services",
        slug="flagged-biz",
        entity_id=ent.id,
        draft=False,
        is_active=True,
    )
    db.add(prov)
    db.commit()
    provider_id = prov.id

    page = client.get("/admin/portal/addresses")
    assert page.status_code == 200
    assert "Flagged Biz" in page.text
    assert "city_repeat" in page.text

    resp = client.post(f"/admin/portal/addresses/{provider_id}/dismiss")
    assert resp.status_code == 200  # after redirect

    page = client.get("/admin/portal/addresses")
    assert "Flagged Biz" not in page.text

    # Dismissal persisted on the provider's attributes bag + audited.
    db2 = next(override())
    refreshed = db2.get(Provider, provider_id)
    assert (refreshed.attributes or {}).get("address_flag_dismissed") is True
    audit = client.get("/admin/portal/audit")
    assert "address_flag_dismissed" in audit.text
