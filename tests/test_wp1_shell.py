"""WP-1 shell smoke tests.

Covers the site shell (``desert_base.html`` since the Desert Modern reskin;
the Lake Light and Sandstone shells it replaced are deleted), the utility
page templates, the static trust pages (/about, /help, /contact), and the
CSS-level a11y/type contracts (skip-link, :focus-visible,
prefers-reduced-motion, the six-tab bottom-nav).

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
_DESERT_CSS = _ROOT / "app" / "static" / "styles" / "desert.css"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    env.globals["plausible_domain"] = None
    # 1.9b: desert_base + the utility pages now reference static_url() for the
    # fingerprinted /static cache. This bare render env predates that global, so
    # mirror the app's Jinja registration (provider_name.register_template_globals)
    # for just static_url -- leaving canonical_url undefined keeps the SEO/og
    # block guarded-off as before, so unrelated shell assertions are unchanged.
    from app.core.static_assets import static_url

    env.globals["static_url"] = static_url
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
    # Skin-agnostic during the Desert Modern migration: both shells must ship a
    # skip-link targeting #main (lake light: .ll-skip-link, desert: .d-skip).
    html = _render(name, **_UTILITY_PAGES[name])
    assert (
        'class="ll-skip-link" href="#main"' in html
        or 'class="d-skip" href="#main"' in html
    )
    assert 'id="main"' in html


@pytest.mark.parametrize("name", sorted(_UTILITY_PAGES))
def test_migrated_page_has_bottom_nav_and_topbar(name: str) -> None:
    # Skin-agnostic: lake light (.ll-bottom-nav / .ll-desktop-topbar) or
    # Desert Modern (.d-bottomnav / .d-header) — the chrome contract is the
    # same: a desktop header plus the fixed six-tab mobile nav.
    html = _render(name, **_UTILITY_PAGES[name])
    assert 'class="ll-bottom-nav"' in html or 'class="d-bottomnav"' in html
    assert "ll-desktop-topbar" in html or 'class="d-header"' in html
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
    # Each skin ships exactly one sanctioned font pair: lake light
    # (Fraunces/Figtree) or Desert Modern (Bricolage Grotesque/Space Grotesk).
    assert ("Fraunces" in html and "Figtree" in html) or (
        "Bricolage+Grotesque" in html and "Space+Grotesk" in html
    )


# ---- active_tab correctness (C10 / the today=home, login/claim=saved bugs) ----


def test_today_lights_home_tab() -> None:
    # Desert Modern bottom nav marks the lit tab with class "on" +
    # aria-current="page" (was class "is-active" in the lake light shell).
    html = _render("today.html", **_UTILITY_PAGES["today.html"])
    assert 'aria-current="page" href="/home"' in html


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
    # Desert Modern bottom nav marks the lit tab with class "on" +
    # aria-current="page" (was class "is-active" in the lake light shell).
    html = _render(name, **_UTILITY_PAGES[name])
    assert 'aria-current="page" href="/account/favorites"' in html


def test_categories_index_lights_explore_tab() -> None:
    # Desert Modern bottom nav marks the lit tab with class "on" +
    # aria-current="page" (was class "is-active" in the lake light shell).
    html = _render("categories_index.html", **_UTILITY_PAGES["categories_index.html"])
    assert 'aria-current="page" href="/categories"' in html


# ---- shared footer: DL-19 tagline + DL-18 trust links + report mailto ----


def test_footer_has_tagline_and_trust_links() -> None:
    # The Desert Modern footer keeps the credo but wraps the accent phrase in a
    # <span> ("Honest. Local. <span>Built in Lake Havasu.</span>"), so match
    # the two halves rather than the single contiguous string.
    html = _render("about.html")
    assert "Honest. Local." in html
    assert "Built in Lake Havasu." in html
    for href in ('href="/about"', 'href="/help"', 'href="/contact"', 'href="/privacy"', 'href="/terms"'):
        assert href in html
    assert "Report wrong info" in html
    assert "mailto:hello@askhava.com" in html


# ---- static pages register and render through the app router ----


def test_static_pages_router_serves_trust_pages() -> None:
    app = FastAPI()
    app.include_router(static_pages_router)
    client = TestClient(app)
    for path in ("/about", "/help", "/contact"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.text.count("<h1") == 1
        # Skip-link survives the Desert Modern reskin (class renamed to d-skip).
        assert 'class="ll-skip-link"' in resp.text or 'class="d-skip"' in resp.text


# ---- CSS-level contracts ----


def test_desert_css_shell_contracts() -> None:
    css = _DESERT_CSS.read_text(encoding="utf-8")
    flat = css.replace(" ", "")
    assert ":focus-visible{outline:" in flat  # visible keyboard focus, global rule
    assert "@media(prefers-reduced-motion:reduce)" in flat
    assert ".d-skip" in css
    assert ".d-bottomnav" in css


# ---- desert shell template (mega disclosure, drawer, no role=menu) ----


def test_desert_base_shell_structure() -> None:
    html = _render(
        "desert_base.html",
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
    assert 'class="d-skip" href="#main"' in html
    # Mega-menu is a plain disclosure: aria-controls + hidden, no ARIA menu roles.
    assert 'aria-controls="d-mega"' in html
    assert "hidden" in html
    assert 'role="menu"' not in html
    assert 'role="menuitem"' not in html
    # Single-child column collapses to a bare link.
    assert "d-mm-bare" in html
    # Final "All categories ->" link to /categories.
    assert "d-mm-all" in html and 'href="/categories"' in html
    # Six-tab mobile bottom nav present.
    assert 'class="d-bottomnav"' in html
    # Hamburger opens a real drawer (aria-controls), not a mode-cycle no-op.
    assert 'aria-controls="d-drawer"' in html
    assert "data-mode-cycle" not in html


def test_desert_conditions_strip_stale_badge() -> None:
    html = _render(
        "desert_base.html",
        utility_chips=[
            {"icon": "G", "value": "$3.99", "label": "Gas", "href": "/gas",
             "is_stale": True, "detail": "x"},
        ],
        mega_columns=[],
        primary_nav=[],
    )
    assert "d-stale" in html
    assert ">Stale<" in html
