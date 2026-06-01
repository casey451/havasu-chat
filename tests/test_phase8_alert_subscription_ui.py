"""Phase 8a — /account/alerts subscription UI."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import AlertSubscription, User
from app.main import app


def _capture_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    toks: list[str] = []

    def _fake(email: str, tok: str, *, next_path: str | None = None) -> None:
        toks.append(tok)

    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _fake)
    return toks


def _login_email(client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    toks = _capture_send(monkeypatch)
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_account_alerts_requires_login(client: TestClient) -> None:
    r = client.get("/account/alerts", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_account_alerts_save_subscription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = f"alerts-{uuid4().hex[:8]}@example.com"
    _login_email(client, monkeypatch, email)

    r = client.post(
        "/account/alerts",
        data={"heat_advisory": "1", "aqi_alert": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.email == email)).first()
        assert user is not None
        subs = list(
            db.scalars(select(AlertSubscription).where(AlertSubscription.user_id == user.id)).all()
        )
        types = {s.alert_type for s in subs}
        assert "heat_advisory" in types
        assert "aqi_alert" in types
