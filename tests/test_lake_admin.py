"""Phase 6 — Lake Ink & Brass admin/portal skin.

The admin surface is three rendering families (inline-HTML _nav_shell pages, the
Jinja .d-admin templates, the CSS-var admin_portal). AdminLakeSkinMiddleware
injects lake_admin.css (+ noindex) into any /admin HTML response when the THEME
flag resolves to lake — so ONE check per family confirms the uniform reskin,
plus the desert default (no injection) and the non-admin / non-HTML guards.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.main import app


def _admin_client() -> TestClient:
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, sign_admin_cookie())
    return c


def test_desert_admin_is_default() -> None:
    b = _admin_client().get("/admin/jobs")
    assert b.status_code == 200
    assert "lake_admin.css" not in b.text  # desert admin untouched
    assert 'data-theme="lake"' not in b.text


def test_lake_admin_inline_html_page() -> None:
    # inline-HTML _nav_shell family (jobs)
    b = _admin_client().get("/admin/jobs?theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_admin.css" in b.text
    assert 'name="robots" content="noindex"' in b.text
    assert "</head>" in b.text  # injection point present, page intact


def test_lake_admin_portal_page() -> None:
    # CSS-var admin_portal family (dashboard) — already noindex; lake css still injected
    b = _admin_client().get("/admin/portal?theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_admin.css" in b.text


def test_lake_admin_jinja_template_page() -> None:
    # Jinja .d-admin family (sponsors inventory)
    b = _admin_client().get("/admin/sponsors?theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_admin.css" in b.text


def test_non_admin_html_not_reskinned() -> None:
    # the middleware is scoped to /admin — a public lake page is untouched by it
    b = TestClient(app).get("/home?theme=lake")
    assert b.status_code == 200
    assert "lake_admin.css" not in b.text
