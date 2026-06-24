"""THEME feature-flag behaviour — Lake Ink & Brass redesign (Phase 0).

Guards the rollout switch: theme resolution precedence, the per-request
middleware (request.state + the QA cookie), that production stays **desert by
default** the entire build, and that the new lake base renders. Also pins the
preserved ``/lake`` -> ``/categories/on-the-water`` 301 so the redesign work
can't regress it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.theme import (
    FALLBACK_THEME,
    base_template_for,
    resolve_request_theme,
    theme_default,
)
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ── resolution precedence (pure) ────────────────────────────────────────────

def test_default_is_lake_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THEME_DEFAULT", raising=False)
    assert theme_default() == "lake" == FALLBACK_THEME


def test_env_default_can_flip_to_lake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEME_DEFAULT", "lake")
    assert theme_default() == "lake"


def test_env_default_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    # Desert was retired; anything non-lake normalizes to the lake default.
    monkeypatch.setenv("THEME_DEFAULT", "neon")
    assert theme_default() == "lake"


def test_query_overrides_cookie_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THEME_DEFAULT", raising=False)
    assert resolve_request_theme("lake", None) == "lake"  # query wins
    assert resolve_request_theme(None, "lake") == "lake"  # cookie next
    assert resolve_request_theme("LAKE", None) == "lake"  # case-insensitive
    assert resolve_request_theme("bogus", "lake") == "lake"  # bad query falls to cookie
    assert resolve_request_theme(None, None) == "lake"  # nothing -> lake default


def test_base_template_for() -> None:
    # Lake is the only theme — every input resolves to the lake base.
    assert base_template_for("lake") == "base_lake.html"
    assert base_template_for("desert") == "base_lake.html"
    assert base_template_for(None) == "base_lake.html"
    assert base_template_for("garbage") == "base_lake.html"


# ── middleware (request.state.theme + QA cookie) ────────────────────────────

def test_valid_query_theme_sets_persistent_cookie(client: TestClient) -> None:
    # The styleguide is DB-free, so it isolates the middleware cleanly.
    r = client.get("/lake-styleguide?theme=lake")
    set_cookie = r.headers.get("set-cookie") or ""
    assert "theme=lake" in set_cookie
    assert "Max-Age=2592000" in set_cookie
    assert "HttpOnly" in set_cookie


def test_no_query_theme_sets_no_cookie() -> None:
    c = TestClient(app)  # fresh cookie jar
    r = c.get("/lake-styleguide")
    assert r.headers.get("set-cookie") is None


def test_bogus_query_theme_is_ignored() -> None:
    c = TestClient(app)
    r = c.get("/lake-styleguide?theme=neon")
    assert r.headers.get("set-cookie") is None


# ── the lake base renders; desert stays the default surface ─────────────────

def test_styleguide_renders_on_lake_base(client: TestClient) -> None:
    r = client.get("/lake-styleguide")
    assert r.status_code == 200
    body = r.text
    assert 'data-theme="lake"' in body
    assert "/static/styles/lake.css" in body
    assert body.count("<h1") == 1


def test_lake_redirect_preserved() -> None:
    # The only previously-shipped "lake" behaviour; must survive the redesign.
    c = TestClient(app)
    r = c.get("/lake", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/on-the-water"
