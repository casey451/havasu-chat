"""Phase 2A.2 — auth routes, session middleware, rate limits."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth.dependencies import require_admin, require_user
from app.auth.routes import _safe_next
from app.auth.session import COOKIE_NAME, sign_session_cookie, verify_session_cookie
from app.db.database import SessionLocal
from app.db.models import AuthSession, MagicLinkToken, User
from app.main import app as _fastapi_app  # noqa: F401 — load app graph first


@pytest.fixture(autouse=True)
def _clear_last_seen_debounce() -> None:
    import app.auth.session as session_mod

    session_mod._LAST_SEEN_MONO.clear()
    yield
    session_mod._LAST_SEEN_MONO.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(_fastapi_app)


def _capture_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    tokens: list[str] = []

    def _fake(email: str, tok: str, *, next_path: str | None = None) -> None:
        tokens.append(tok)

    monkeypatch.setattr("app.auth.routes.send_magic_link", _fake)
    return tokens


def _bare_request() -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_get_login_renders_form_and_preserves_next(client: TestClient) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert "Email me a link" in r.text
    r2 = client.get("/login?next=%2Ffoo%2Fbar")
    assert r2.status_code == 200
    assert 'name="next"' in r2.text
    assert "/foo/bar" in r2.text


def test_request_link_valid_creates_token_and_check_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"u-{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/request-link", data={"email": email})
    assert r.status_code == 200
    assert "Check your email" in r.text
    assert email in r.text
    assert len(toks) == 1
    with SessionLocal() as db:
        n = (
            db.query(MagicLinkToken)
            .filter(MagicLinkToken.email == email)
            .count()
        )
        assert n == 1


def test_request_link_send_failure_still_shows_check_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("simulated send failure")

    monkeypatch.setattr("app.auth.routes.send_magic_link", _boom)
    email = f"fail-{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/request-link", data={"email": email})
    assert r.status_code == 200
    assert "Check your email" in r.text
    assert email in r.text


def test_request_link_invalid_email_400(client: TestClient) -> None:
    r = client.post("/api/auth/request-link", data={"email": "not-an-email"})
    assert r.status_code == 400
    assert "valid email" in r.text


def test_request_link_email_rate_limit_silent_sixth_no_new_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_send(monkeypatch)
    email = f"rate-{uuid4().hex[:8]}@example.com"
    for _ in range(5):
        r = client.post("/api/auth/request-link", data={"email": email})
        assert r.status_code == 200
        assert "Check your email" in r.text
    with SessionLocal() as db:
        before = (
            db.query(MagicLinkToken)
            .filter(MagicLinkToken.email == email)
            .count()
        )
    r6 = client.post("/api/auth/request-link", data={"email": email})
    assert r6.status_code == 200
    assert "Check your email" in r6.text
    with SessionLocal() as db:
        after = (
            db.query(MagicLinkToken)
            .filter(MagicLinkToken.email == email)
            .count()
        )
    assert before == 5 == after


def test_callback_valid_creates_user_session_sets_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"new-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    tok = toks[0]
    r = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/account"
    assert COOKIE_NAME in r.cookies
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).one()
        assert u.role == "end_user"
        s = db.query(AuthSession).filter(AuthSession.user_id == u.id).one()
        assert s.id
    r2 = client.get("/account", follow_redirects=False)
    assert r2.status_code == 200
    assert email in r2.text


def test_callback_existing_user_updates_last_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"exist-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)
    with SessionLocal() as db:
        u1 = db.query(User).filter(User.email == email).one()
        t1 = u1.last_login_at
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[1]}", follow_redirects=False)
    with SessionLocal() as db:
        u2 = db.query(User).filter(User.email == email).one()
        t2 = u2.last_login_at
    assert u1.id == u2.id
    assert t2 is not None and (t1 is None or t2 >= t1)


def test_callback_expired_token_no_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.auth.routes.send_magic_link", lambda *a, **k: None)
    email = f"exp-{uuid4().hex[:8]}@example.com"
    plain = "known-plaintext-token"
    from app.auth.email_helpers import hash_token

    h = hash_token(plain)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        db.add(
            MagicLinkToken(
                email=email,
                token_hash=h,
                expires_at=past,
            )
        )
        db.commit()
    r = client.get(f"/auth/callback?token={plain}")
    assert r.status_code == 400
    assert "expired" in r.text.lower() or "already been used" in r.text
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == email).count() == 0


def test_callback_consumed_token_second_hit_expired_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"dbl-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    tok = toks[0]
    assert (
        client.get(f"/auth/callback?token={tok}", follow_redirects=False).status_code
        == 303
    )
    r2 = client.get(f"/auth/callback?token={tok}", follow_redirects=False)
    assert r2.status_code == 400


def test_callback_invalid_unknown_token_expired_page(client: TestClient) -> None:
    r = client.get("/auth/callback?token=totally-unknown-token-value")
    assert r.status_code == 400


def test_logout_deletes_session_and_clears_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"out-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)
    with SessionLocal() as db:
        sid = db.query(AuthSession).join(User).filter(User.email == email).one().id
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/"
    with SessionLocal() as db:
        assert db.get(AuthSession, sid) is None


def test_logout_anonymous_redirects_home(client: TestClient) -> None:
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/"


def test_middleware_expired_session_anonymous(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"exps-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)
    with SessionLocal() as db:
        s = db.query(AuthSession).join(User).filter(User.email == email).one()
        s.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.add(s)
        db.commit()
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in (r.headers.get("location") or "")


def test_middleware_invalid_signature_cookie_anonymous(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, "not-a-valid-signature", path="/")
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 303


def test_middleware_no_cookie_anonymous(client: TestClient) -> None:
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 303


def test_middleware_signed_missing_row_clears_cookie(client: TestClient) -> None:
    ghost_id = str(uuid4())
    signed = sign_session_cookie(ghost_id)
    assert verify_session_cookie(signed) == ghost_id
    client.cookies.set(COOKIE_NAME, signed, path="/")
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 303
    set_cookie = r.headers.get("set-cookie") or ""
    assert COOKIE_NAME in set_cookie.lower()


def test_last_seen_debounced_second_request_within_window(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    toks = _capture_send(monkeypatch)
    email = f"ls-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)
    with SessionLocal() as db:
        sid = db.query(AuthSession).join(User).filter(User.email == email).one().id

    monkeypatch.setattr("app.auth.session.time.monotonic", lambda: 1.0)
    client.get("/account")
    with SessionLocal() as db:
        t1 = db.get(AuthSession, sid).last_seen_at
    client.get("/account")
    with SessionLocal() as db:
        t2 = db.get(AuthSession, sid).last_seen_at
    assert t1 == t2


def test_require_user_raises_when_anonymous() -> None:
    req = _bare_request()
    with pytest.raises(HTTPException) as ei:
        require_user(req)
    assert ei.value.status_code == 401


def test_require_admin_forbidden_for_end_user() -> None:
    with SessionLocal() as db:
        u = User(email=f"eu-{uuid4().hex[:8]}@example.com", role="end_user")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.expunge(u)
    req = _bare_request()
    req.state.current_user = u
    with pytest.raises(HTTPException) as ei:
        require_admin(req)
    assert ei.value.status_code == 403


def test_safe_next_rejects_open_redirect_and_callback_ignores_evil_next(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _safe_next("https://evil.com") is None
    assert _safe_next("//evil.com/path") is None
    assert _safe_next("/nice/../../../etc/passwd") is None
    assert _safe_next("/ok/path") == "/ok/path"
    toks = _capture_send(monkeypatch)
    email = f"nxt-{uuid4().hex[:8]}@example.com"
    client.post("/api/auth/request-link", data={"email": email})
    tok = toks[0]
    r = client.get(
        f"/auth/callback?token={tok}&next=https%3A%2F%2Fevil.com",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers.get("location") == "/account"
