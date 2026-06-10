"""Fail-closed auth secrets in production (T1.3) + admin cookie SameSite=Strict (T1.5).

In production (``RAILWAY_ENVIRONMENT`` set) the app must refuse the well-known
``changeme`` default for the admin password and must require a distinct
``HAVA_SESSION_SECRET`` rather than silently signing user sessions with the
admin password. Locally / in tests (``RAILWAY_ENVIRONMENT`` unset) behavior is
unchanged so the suite stays green.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.admin import auth as admin_auth
from app.auth import session as session_mod
from app.main import app

# --- T1.3: admin password fail-closed -------------------------------------


def test_admin_password_local_default_when_not_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert admin_auth._admin_password_from_env() == "changeme"


def test_admin_password_prod_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        admin_auth._admin_password_from_env()


def test_admin_password_prod_changeme_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "changeme")
    with pytest.raises(RuntimeError):
        admin_auth._admin_password_from_env()


def test_admin_password_prod_set_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-strong-admin-pw")
    assert admin_auth._admin_password_from_env() == "a-strong-admin-pw"


# --- T1.3: session secret fail-closed + decoupled from admin password ------


def test_session_secret_local_falls_back_to_admin_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("HAVA_SESSION_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert session_mod._session_secret() == "changeme"


def test_session_secret_prod_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("HAVA_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="HAVA_SESSION_SECRET"):
        session_mod._session_secret()


def test_session_secret_prod_does_not_fall_back_to_admin_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Even with a perfectly valid admin password set, prod must require its own
    # distinct secret rather than reusing the admin password.
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-strong-admin-pw")
    monkeypatch.delenv("HAVA_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        session_mod._session_secret()


def test_session_secret_prod_changeme_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("HAVA_SESSION_SECRET", "changeme")
    with pytest.raises(RuntimeError):
        session_mod._session_secret()


def test_session_secret_prod_set_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("HAVA_SESSION_SECRET", "distinct-strong-secret")
    assert session_mod._session_secret() == "distinct-strong-secret"


# --- T1.5: admin cookie carries SameSite=Strict ----------------------------


def test_admin_login_sets_samesite_strict_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)  # local default "changeme"
    with TestClient(app) as client:
        r = client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    set_cookie = (r.headers.get("set-cookie") or "").lower()
    assert "admin_session=" in set_cookie
    assert "samesite=strict" in set_cookie


def test_admin_login_wrong_password_no_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with TestClient(app) as client:
        r = client.post(
            "/admin/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )
    assert r.status_code == 401
    assert "admin_session=" not in (r.headers.get("set-cookie") or "")


# --- SEC-1: admin cookie carries Secure in prod (both login surfaces) ------


def _cookie_attrs(response) -> set[str]:
    """Lower-cased Set-Cookie attribute names/flags (value-bearing attrs keep
    only the name), so flag checks can't false-positive on the cookie value."""
    raw = response.headers.get("set-cookie") or ""
    return {part.strip().split("=")[0].lower() for part in raw.split(";")}


def _prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-strong-admin-pw")
    monkeypatch.setenv("HAVA_SESSION_SECRET", "distinct-strong-secret")


def test_admin_login_cookie_secure_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    _prod_env(monkeypatch)
    with TestClient(app) as client:
        r = client.post(
            "/admin/login",
            data={"password": "a-strong-admin-pw"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    attrs = _cookie_attrs(r)
    assert "secure" in attrs
    assert "httponly" in attrs


def test_admin_login_cookie_not_secure_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with TestClient(app) as client:
        r = client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    assert "secure" not in _cookie_attrs(r)


def test_v1_admin_login_cookie_strict_and_secure_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prod_env(monkeypatch)
    with TestClient(app) as client:
        r = client.post(
            "/api/admin/login",
            data={"email": "admin@example.com", "password": "a-strong-admin-pw"},
        )
    assert r.status_code == 200
    set_cookie = (r.headers.get("set-cookie") or "").lower()
    assert "admin_session=" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "secure" in _cookie_attrs(r)


def test_v1_admin_login_cookie_samesite_strict_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with TestClient(app) as client:
        r = client.post(
            "/api/admin/login",
            data={"email": "admin@example.com", "password": "changeme"},
        )
    assert r.status_code == 200
    set_cookie = (r.headers.get("set-cookie") or "").lower()
    assert "samesite=strict" in set_cookie
    assert "secure" not in _cookie_attrs(r)
