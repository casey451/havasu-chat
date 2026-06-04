"""WP-1 shell smoke tests.

Covers the new ``lake_light_base.html`` shell, the migrated Lake Light page
templates, the new static trust pages (/about, /help, /contact), the shared
nav/footer partials, and the CSS-level a11y/type contracts (skip-link,
:focus-visible, prefers-reduced-motion, the six-tab bottom-nav grid).

Two render paths are used:
  * Templates needing no app context are rendered directly through a Jinja
    ``Environment`` (mirrors the per-router ``Jinja2Templates`` setup) -- this
    avoids standing up auth/DB just to assert shell structure.
  * Routes with no auth requirement (/about, /help, /contact, /map, 404) are
    hit through ``TestClient`` so we also exercise registration.

Substring assertions follow the existing test_a11y_smoke / test_category_pages
style -- a cheap tripwire, not a DOM parse.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader

from app.home.static_pages import router as static_pages_router

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATES_DIR = _ROOT / "app" / "templates"
_LL_CSS = _ROOT / "app" / "static" / "styles" / "lake_light.css"
_SAND_CSS = _ROOT / "app" / "static" / "styles" / "sandstone.css"
_SAND_JS = _ROOT / "app" / "static" / "js" / "sandstone.js"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    env.globals["plausible_domain"] = None
    env.filters["clean_name"] = lambda s: s
    return env


def _render(name: str, **ctx: object) -> str:
    return _env().get_template(name).render(**ctx)


# Template -> minimal render context for the utility-shell pages.
_UTILITY_PAGES: dict[str, dict] = {
    "today.html": {"fields": [], "any_available": False, "local_time_label": "6 PM"},
    "login.html": {},
    "login_check_email.html": {"email": "a@b.com"},
    "login_expired.html": {},
    "account.html": {"user": {"email": "a@b.com"}},
    "account_favorites.html": {"user": {"email": "a@b.com"}, "favorites": []},
    "account_alerts.html": {"user": {"email": "a@b.com"}, "active_types": [], "saved": False},
    "claim_form.html": {"entity": {"name": "Foo", "slug": "foo"}},
    "claim_status.html": {"entity": {"name": "Foo", "slug": "foo"}, "claim": {"status": "pending"}},
    "claim_submitted.html": {"entity": {"name": "Foo", "slug": "foo"}},
    "not_found.html": {},
    "privacy_doc.html": {"head_title": "Privacy -- Hava", "body": "<h1>Privacy</h1><p>x</p>"},
    "about.html": {},
    "help.html": {},
    "contact.html": {},
    "categories_index.html": {
        "today_label": "Sunday, May 24",
        "now_label": "6:14 PM",
        "categories": [],
    },
}


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_has_one_h1(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert html.count("<h1") == 1, f"{name} must have exactly one <h1>"


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_has_skip_link_and_main(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert 'class="ll-skip-link" href="#main"' in html
    assert 'id="main"' in html


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_has_bottom_nav_and_topbar(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert 'class="ll-bottom-nav"' in html
    assert "ll-desktop-topbar" in html
    # Six fixed tabs (DL-2).
    for label in ("Home", "Events", "Ask", "Explore", "Map", "Saved"):
        assert f">{label}<" in html or f'aria-label="{label}"' in html


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_doctype_is_first(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert html.lstrip().lower().startswith("<!doctype html>"), f"{name} leaked text before doctype"


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_drops_legacy_fonts(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert "Playfair" not in html
    assert "Poppins" not in html
    assert "Fraunces" in html and "Figtree" in html


# ---- active_tab correctness (C10 / the today=home, login/claim=saved bugs) ----


def test_today_lights_home_tab() -> None:
    html = _render("today.html", **_UTILITY_PAGES["today.html"])
    assert '<a class="is-active" href="/home">Home</a>' in html


@pytest.mark.parametrize(
    "name",
    ["login.html", "login_check_email.html", "login_expired.html",
     "claim_form.html", "claim_status.html", "claim_submitted.html",
     "not_found.html", "privacy_doc.html", "about.html", "help.html", "contact.html"],
)
def test_non_nav_pages_light_no_tab(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert "is-active" not in html, f"{name} should not light any bottom-nav tab"


@pytest.mark.parametrize("name", ["account.html", "account_favorites.html", "account_alerts.html"])
def test_account_pages_light_saved_tab(name: str) -> None:
    html = _render(name, **_UTILITY_PAGES[name])
    assert '<a class="is-active" href="/account/favorites">Saved</a>' in html


def test_categories_index_lights_explore_tab() -> None:
    html = _render("categories_index.html", **_UTILITY_PAGES["categories_index.html"])
    assert '<a class="is-active" href="/categories">Explore</a>' in html


# ---- shared footer: DL-19 tagline + DL-18 trust links + report mailto ----


def test_footer_has_tagline_and_trust_links() -> None:
    html = _render("about.html")
    assert "Honest. Local. Built in Lake Havasu." in html
    for href in ('href="/about"', 'href="/help"', 'href="/contact"', 'href="/privacy"', 'href="/terms"'):
        assert href in html
    assert "Report wrong info" in html
    assert "mailto:hello@havasuchat.com" in html


# ---- header search (DL-6 Wave 1: GET -> /chat?q=) ----


def test_desktop_topbar_search_posts_to_search() -> None:
    # DL-6 phase 2 (WP-11): the header search now posts to the /search results
    # page; chat is the secondary "Ask Hava instead" CTA (/chat?q=).
    html = _render("about.html")
    assert 'action="/search" method="get"' in html
    assert 'name="q"' in html


# ---- static pages register and render through the app router ----


def test_static_pages_router_serves_trust_pages() -> None:
    app = FastAPI()
    app.include_router(static_pages_router)
    client = TestClient(app)
    for path in ("/about", "/help", "/contact"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.text.count("<h1") == 1
        assert 'class="ll-skip-link"' in resp.text


# ---- CSS-level contracts ----


def test_lake_light_css_shell_contracts() -> None:
    css = _LL_CSS.read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(6, 1fr)" in css  # six-tab bottom nav
    assert ".ll-skip-link" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".ll-utility-footer-tagline" in css
    # DL-2 boundary: topbar/bottom-nav swap at 900px.
    assert "@media (min-width: 900px)" in css


def test_sandstone_css_shell_contracts() -> None:
    css = _SAND_CSS.read_text(encoding="utf-8")
    assert ".ll-bottom-nav" in css  # bottom nav styled on sandstone pages too
    assert "grid-template-columns:repeat(6,1fr)" in css
    assert ".ll-skip-link" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".header-search" in css
    assert ".stale-badge" in css


def test_sandstone_js_uses_disclosure_not_mode_cycle_noop() -> None:
    js = _SAND_JS.read_text(encoding="utf-8")
    assert "nav-drawer" in js  # hamburger opens a real menu
    assert "data-mode-cycle" not in js  # old no-op glyph behavior removed
    assert "aria-controls" not in js or "mega" in js  # disclosure wiring


# ---- sandstone shell template (header search, mega disclosure, no role=menu) ----


def test_sandstone_base_shell_structure() -> None:
    html = _render(
        "sandstone_base.html",
        mega_columns=[
            {"heading": "Eat & Drink", "links": [{"label": "Eat & Drink", "url": "/categories/eat-drink"}]},
            {"heading": "Services", "links": [
                {"label": "Home", "url": "/categories/home-property-services"},
                {"label": "Auto", "url": "/categories/auto-rv-fuel"},
            ]},
        ],
        primary_nav=[{"label": "Eat & Drink", "url": "/categories/eat-drink"}],
        utility_chips=[],
    )
    assert 'class="ll-skip-link" href="#main"' in html
    # Mega-menu is a plain disclosure: aria-controls + hidden, no ARIA menu roles.
    assert 'aria-controls="mega"' in html
    assert 'role="menu"' not in html
    assert 'role="menuitem"' not in html
    # Single-child column collapses to a bare link.
    assert "mm-bare" in html
    # Final "All categories ->" link to /categories.
    assert "mm-all" in html and 'href="/categories"' in html
    # Header search present in the sandstone header (DL-6 phase 2 / WP-11:
    # posts to the /search results page, not chat).
    assert 'action="/search" method="get"' in html
    # Bottom-nav included on sandstone pages too (DL-2).
    assert 'class="ll-bottom-nav"' in html
    # Hamburger opens a real drawer (aria-controls), not a mode-cycle no-op.
    assert 'aria-controls="nav-drawer"' in html
    assert "data-mode-cycle" not in html


def test_sandstone_ribbon_stale_badge_replaces_middot() -> None:
    html = _render(
        "sandstone_base.html",
        utility_chips=[
            {"icon": "G", "value": "$3.99", "label": "Gas", "href": "/gas",
             "is_stale": True, "detail": "x"},
        ],
        mega_columns=[],
        primary_nav=[],
    )
    assert "stale-badge" in html
    assert ">Stale<" in html
