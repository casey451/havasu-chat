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
    "/admin/portal/moderation",
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
    assert resp.status_code == 303
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
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/login"
