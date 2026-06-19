"""THEME feature flag — Lake Ink & Brass redesign rollout (Phase 0).

The whole redesign ships behind one switch so production looks unchanged
until a single coordinated flip. A request's theme is resolved in this
order (first hit wins):

1. ``?theme=`` query param (``lake`` | ``desert``) — QA override; also sets a
   cookie so the choice sticks while click-testing.
2. ``theme`` cookie — the persisted QA choice.
3. ``THEME_DEFAULT`` env var — the deployment default. **Stays ``desert``
   the entire build**; the flip sets it to ``lake``.
4. Hard fallback ``desert`` — so a missing/garbage env never dark-launches.

The resolved value is stamped on ``request.state.theme`` by
``ThemeMiddleware`` (app/main.py) and read directly in templates via
``request.state.theme``. Routes that serve both skins pick the base layout
with :func:`base_template_for`.

Read-at-call (not import-time) so tests can ``monkeypatch.setenv`` and see
the change without reimporting — mirrors the other env flags in this repo
(e.g. ``app/categories/taxonomy_overlay.py``).
"""

from __future__ import annotations

import os

from app.bootstrap_env import ensure_dotenv_loaded

#: Env var holding the deployment-wide default theme.
THEME_DEFAULT_ENV = "THEME_DEFAULT"
#: Cookie that persists a QA ``?theme=`` override.
THEME_COOKIE = "theme"
#: The themes the app knows how to render.
VALID_THEMES: frozenset[str] = frozenset({"desert", "lake"})
#: Used when nothing else resolves to a known theme.
FALLBACK_THEME = "desert"

_BASE_TEMPLATES = {"lake": "base_lake.html", "desert": "desert_base.html"}


def _normalize(value: str | None) -> str | None:
    """Lower/strip ``value`` and return it only if it's a known theme."""
    if not value:
        return None
    v = value.strip().lower()
    return v if v in VALID_THEMES else None


def theme_default() -> str:
    """The deployment default from ``THEME_DEFAULT`` (``desert`` if unset/bad)."""
    ensure_dotenv_loaded()
    return _normalize(os.environ.get(THEME_DEFAULT_ENV)) or FALLBACK_THEME


def resolve_request_theme(query_theme: str | None, cookie_theme: str | None) -> str:
    """Resolve the active theme from a request's query param + cookie.

    Pure function (no ``Request`` import) so it's trivially unit-testable.
    ``ThemeMiddleware`` feeds it ``request.query_params.get("theme")`` and
    ``request.cookies.get(THEME_COOKIE)``.
    """
    return _normalize(query_theme) or _normalize(cookie_theme) or theme_default()


def base_template_for(theme: str | None) -> str:
    """Base layout template name for ``theme`` (defaults to the desert base)."""
    return _BASE_TEMPLATES.get((theme or "").strip().lower(), "desert_base.html")
