"""SEC-2: strict per-IP rate limit on both admin login routes.

The suite runs with ``RATE_LIMIT_DISABLED=1`` (tests/conftest.py), which the
limiter reads once at construction — so these tests flip ``limiter.enabled``
back on for their own duration (monkeypatch restores it) and reset the
in-memory storage around each test so buckets never leak across tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture
def _enabled_limiter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    yield
    limiter.reset()


def test_admin_login_rate_limited_429(_enabled_limiter) -> None:
    with TestClient(app) as client:
        for _ in range(5):
            r = client.post(
                "/admin/login",
                data={"password": "wrong"},
                follow_redirects=False,
            )
            assert r.status_code == 401
        r6 = client.post(
            "/admin/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )
    assert r6.status_code == 429


def test_v1_admin_login_rate_limited_429(_enabled_limiter) -> None:
    with TestClient(app) as client:
        for _ in range(5):
            r = client.post(
                "/api/admin/login",
                data={"email": "x@example.com", "password": "wrong"},
            )
            assert r.status_code == 401
        r6 = client.post(
            "/api/admin/login",
            data={"email": "x@example.com", "password": "wrong"},
        )
    assert r6.status_code == 429


def test_admin_login_correct_password_not_blocked_under_limit(_enabled_limiter) -> None:
    """The limit must leave room for a legitimate login (not lock on first try)."""
    with TestClient(app) as client:
        r = client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
    assert r.status_code == 303
