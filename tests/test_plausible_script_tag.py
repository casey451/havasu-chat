"""Q5 — Plausible analytics script tag injection.

Tests the env-gated ``_partials/plausible.html`` include + the
``register_template_globals`` registrar in ``app.core.provider_name``.

Subtle gotcha (documented in the task spec): the ``plausible_domain``
Jinja global is set at app-import time, so a plain ``monkeypatch.setenv``
inside a test won't propagate into the already-constructed ``templates``
instances. To force a refresh, we set the env var and then re-invoke
``register_template_globals`` against each ``templates`` instance the
under-test routes use. The registrar re-reads ``os.getenv`` on every
call (by design) so this round-trips cleanly.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.category_pages import templates as category_pages_templates
from app.core.provider_name import register_template_globals
from app.home.chat_route import templates as chat_templates
from app.home.router import templates as home_templates
from app.main import app
from app.main import templates as main_templates

_SCRIPT_FRAGMENT = "plausible.io/js/script"


# All ``Jinja2Templates`` instances that render an HTML page exercised by
# the tests below. Refreshing every one keeps each test self-contained: a
# test that flips PLAUSIBLE_DOMAIN on or off doesn't leak global state
# into a sibling test that hits a different route.
_TEMPLATE_INSTANCES = (
    main_templates,
    home_templates,
    chat_templates,
    category_pages_templates,
)


def _refresh_globals_against_all_templates() -> None:
    for t in _TEMPLATE_INSTANCES:
        register_template_globals(t)


def test_plausible_script_absent_when_env_unset(monkeypatch) -> None:
    """With ``PLAUSIBLE_DOMAIN`` unset, no Plausible script tag is rendered.

    Covers the local-dev no-op posture: the env var is intentionally
    absent in development so the page never loads the script and never
    requires a cookie banner.
    """
    monkeypatch.delenv("PLAUSIBLE_DOMAIN", raising=False)
    _refresh_globals_against_all_templates()

    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert _SCRIPT_FRAGMENT not in body
    # Sanity: we actually rendered an HTML page (not an early redirect /
    # error swallowing the assertion).
    assert "<head>" in body.lower() or "<head " in body.lower()


def test_plausible_script_present_when_env_set(monkeypatch) -> None:
    """With ``PLAUSIBLE_DOMAIN=havachat.com``, the script tag renders with
    the domain wired through and the outbound-links variant URL.
    """
    monkeypatch.setenv("PLAUSIBLE_DOMAIN", "havachat.com")
    _refresh_globals_against_all_templates()

    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert _SCRIPT_FRAGMENT in body
    assert 'data-domain="havachat.com"' in body
    # The outbound-links variant of the script is what we ship — it
    # auto-tracks external link clicks alongside pageviews.
    assert "script.outbound-links.js" in body


def test_plausible_script_renders_on_chat_page(monkeypatch) -> None:
    """``/chat`` uses a different ``Jinja2Templates`` instance than ``/home``.

    Regression guard for the "one registrar per Jinja2Templates site"
    wiring — if a future PR adds a new instance and forgets the registrar
    call, this test will start failing once that route is exercised here.
    """
    monkeypatch.setenv("PLAUSIBLE_DOMAIN", "havachat.com")
    _refresh_globals_against_all_templates()

    client = TestClient(app)
    resp = client.get("/chat")
    assert resp.status_code == 200
    body = resp.text
    assert _SCRIPT_FRAGMENT in body
    assert 'data-domain="havachat.com"' in body


def test_plausible_domain_strips_whitespace(monkeypatch) -> None:
    """Trailing whitespace from a Railway env var must not leak into the
    rendered ``data-domain`` attribute. ``register_template_globals``
    strips on read.
    """
    monkeypatch.setenv("PLAUSIBLE_DOMAIN", "  havachat.com  ")
    _refresh_globals_against_all_templates()

    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert 'data-domain="havachat.com"' in body
    # No accidental leading/trailing space inside the attribute value.
    assert 'data-domain=" ' not in body
    assert 'data-domain="havachat.com "' not in body


def test_plausible_empty_env_var_is_treated_as_unset(monkeypatch) -> None:
    """Empty / whitespace-only ``PLAUSIBLE_DOMAIN`` must not emit the script
    (the global coerces to ``None``). Otherwise a misconfigured deploy
    would render an empty ``data-domain=""`` attribute.
    """
    monkeypatch.setenv("PLAUSIBLE_DOMAIN", "   ")
    _refresh_globals_against_all_templates()

    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    assert _SCRIPT_FRAGMENT not in resp.text
