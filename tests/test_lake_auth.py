"""Phase 4a — Lake Ink & Brass auth + account surfaces.

/login renders on an empty DB so it goes through the real route (TestClient).
The check-email / expired / account / favorites / alerts pages are auth-gated or
need a session, so their templates are rendered directly with sample context
(the established Phase-3 pattern). Every page is asserted noindex, structurally
WCAG-clean (_A11yChecker), single-h1, and carrying its real form contract.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.auth.routes import _tname
from app.auth.routes import templates as _auth_templates
from app.main import app


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _render(name: str, path: str, **ctx: object) -> str:
    return _auth_templates.env.get_template(name).render(request=_req(path), **ctx)


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


class _FakeUser:
    email = "you@example.com"


# ── _tname route wiring ─────────────────────────────────────────────────────

def test_tname_always_selects_lake() -> None:
    # Lake is the only theme — _tname always maps to the lake variant.
    req = _req("/login")
    assert _tname(req, "login.html") == "login_lake.html"
    assert _tname(req, "account_favorites.html") == "account_favorites_lake.html"
    lake_req = _req("/login")
    lake_req.state.theme = "lake"
    assert _tname(lake_req, "login.html") == "login_lake.html"


# ── /login (full route) ─────────────────────────────────────────────────────

def test_lake_login_form() -> None:
    b = TestClient(app).get("/login?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b
    assert 'name="robots" content="noindex"' in b
    assert 'action="/api/auth/request-link"' in b
    assert 'name="email"' in b and 'id="email"' in b  # programmatically labeled
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── check-email / expired (direct render) ───────────────────────────────────

def test_lake_check_email() -> None:
    b = _render("login_check_email_lake.html", "/api/auth/request-link",
                email="you@example.com", next_path=None)
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert "you@example.com" in b
    assert b.count('action="/api/auth/request-link"') == 1  # resend form
    assert 'href="/login"' in b  # use a different email
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_login_expired() -> None:
    b = _render("login_expired_lake.html", "/auth/callback")
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert 'href="/login"' in b and 'href="/home"' in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── account hub / favorites / alerts (direct render) ────────────────────────

def test_lake_account_hub() -> None:
    b = _render("account_lake.html", "/account", user=_FakeUser())
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert "you@example.com" in b
    assert 'action="/logout"' in b  # logout POST preserved
    assert 'href="/account/favorites"' in b and 'href="/account/alerts"' in b
    assert 'aria-current="page"' in b  # account nav active state
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_favorites_empty_and_populated() -> None:
    empty = _render("account_favorites_lake.html", "/account/favorites",
                    user=_FakeUser(), favorites=[])
    assert "No saved listings yet" in empty
    assert empty.count("<h1") == 1
    assert not _a11y(empty)

    full = _render("account_favorites_lake.html", "/account/favorites",
                   user=_FakeUser(), favorites=[
                       {"name": "Barley Brothers", "href": "/provider/barley-bros"},
                       {"name": "Riverside Lawn", "href": None},
                   ])
    assert 'href="/provider/barley-bros"' in full  # favouritable row links out
    assert "Riverside Lawn" in full  # non-favouritable row still shows
    assert full.count("<h1") == 1
    assert not _a11y(full)


def test_lake_alerts_form() -> None:
    b = _render("account_alerts_lake.html", "/account/alerts",
                user=_FakeUser(), active_types={"heat_advisory"},
                alert_types=["heat_advisory", "aqi_alert", "lake_hazard"],
                event_traffic_deferred="event_traffic", saved=True)
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert 'action="/account/alerts"' in b
    # every real checkbox + the snooze field present
    for field in ("heat_advisory", "aqi_alert", "lake_hazard", "snooze_until"):
        assert f'name="{field}"' in b
    assert "checked" in b  # heat_advisory pre-checked from active_types
    assert "Preferences saved." in b  # saved=True banner
    assert b.count("<h1") == 1
    assert not _a11y(b)

    unsaved = _render("account_alerts_lake.html", "/account/alerts",
                      user=_FakeUser(), active_types=set(),
                      alert_types=["heat_advisory", "aqi_alert", "lake_hazard"],
                      event_traffic_deferred="event_traffic", saved=False)
    assert "Preferences saved." not in unsaved
    assert not _a11y(unsaved)
