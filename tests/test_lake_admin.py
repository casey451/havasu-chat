"""Phase 6 — Lake Ink & Brass admin/portal skin.

The admin surface is three rendering families (inline-HTML _nav_shell pages, the
Jinja .d-admin templates, the CSS-var admin_portal). AdminLakeSkinMiddleware
injects lake_admin.css (+ noindex) into any /admin HTML response when the THEME
flag resolves to lake — so ONE check per family confirms the uniform reskin,
plus the desert default (no injection) and the non-admin / non-HTML guards.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_pkg
from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.main import app

_LAKE_ADMIN_CSS = Path(app_pkg.__file__).parent / "static" / "styles" / "lake_admin.css"


def _admin_client() -> TestClient:
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, sign_admin_cookie())
    return c


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


def test_lake_admin_css_recolors_nav_tabs_and_sort_links() -> None:
    """The inline _nav_shell dashboard hard-codes Bootstrap blue for its .tabs
    pills + .sort-opt links; lake_admin.css must override them with lake tokens
    (never raw blue). Guards the desert/lake hybrid regression in the admin skin."""
    css = _LAKE_ADMIN_CSS.read_text(encoding="utf-8")
    # strip comments so the checks reflect actual declarations, not prose
    css_rules = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    compact = "".join(css_rules.split())
    assert ".tabsa.active{" in compact  # active-tab override present
    assert ".sort-opt{" in compact and ".sort-opt-active{" in compact
    assert "--la-brass" in css_rules  # recoloured with lake tokens
    # no Bootstrap-blue literals in the actual declarations
    for blue in ("#0d6efd", "#0a58ca", "#e7f1ff"):
        assert blue not in css_rules.lower()


def test_lake_dashboard_skin_injected_after_inline_blue() -> None:
    """The fix relies on source order: the page ships its own blue inline <style>,
    then AdminLakeSkinMiddleware appends lake_admin.css before </head>, so the lake
    rules win at matching specificity. Assert the skin link follows the inline blue."""
    b = _admin_client().get("/admin?tab=queue&theme=lake")
    assert b.status_code == 200
    html = b.text
    inline_blue = html.find("#0d6efd")  # the page's own inline .tabs a.active blue
    skin = html.find("/static/styles/lake_admin.css")
    assert inline_blue != -1, "expected the inline blue dashboard <style> to still ship"
    assert skin != -1, "expected lake_admin.css to be injected"
    assert skin > inline_blue, "lake_admin.css must be injected AFTER the inline blue to win"
