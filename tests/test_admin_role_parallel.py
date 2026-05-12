"""Phase 2A.3 — admin _guard: cookie path + role=admin parallel + end_user 403."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.session import COOKIE_NAME, SESSION_LIFETIME_SECONDS, sign_session_cookie
from app.db.database import SessionLocal
from app.db.models import AuthSession, User
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_admin_claims_cookie_session_still_works(client: TestClient) -> None:
    c = client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert c.status_code == 303
    r = client.get("/admin/claims")
    assert r.status_code == 200


def test_admin_claims_role_admin_without_admin_cookie(
    client: TestClient,
) -> None:
    suf = uuid4().hex[:8]
    email = f"admrole-{suf}@example.com"

    now_a = datetime.now(timezone.utc)
    with SessionLocal() as db:
        u = User(email=email, role="admin")
        db.add(u)
        db.flush()
        sid_row = AuthSession(
            user_id=u.id,
            expires_at=now_a + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(sid_row)
        db.flush()
        uid = u.id
        sid = sid_row.id
        db.commit()
    try:
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, sign_session_cookie(sid), path="/")
        r = client.get("/admin/claims")
        assert r.status_code == 200
    finally:
        with SessionLocal() as db:
            db.query(AuthSession).filter_by(user_id=uid).delete()
            db.query(User).filter_by(id=uid).delete()
            db.commit()


def test_admin_claims_end_user_session_forbidden(client: TestClient) -> None:
    suf = uuid4().hex[:8]
    email = f"euadm-{suf}@example.com"

    now_a = datetime.now(timezone.utc)
    with SessionLocal() as db:
        u = User(email=email, role="end_user")
        db.add(u)
        db.flush()
        sid_row = AuthSession(
            user_id=u.id,
            expires_at=now_a + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(sid_row)
        db.flush()
        uid = u.id
        sid = sid_row.id
        db.commit()
    try:
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, sign_session_cookie(sid), path="/")
        r = client.get("/admin/claims", follow_redirects=False)
        assert r.status_code == 403
    finally:
        with SessionLocal() as db:
            db.query(AuthSession).filter_by(user_id=uid).delete()
            db.query(User).filter_by(id=uid).delete()
            db.commit()
