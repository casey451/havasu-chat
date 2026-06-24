"""Theme resolution — Lake is the one and only theme.

The Lake Ink & Brass redesign shipped behind a ``?theme=``/``THEME_DEFAULT``
switch during its dark rollout; after the 2026-06-19 flip Lake became the prod
default, and on 2026-06-24 (Casey-approved) the legacy **desert** lineage was
deleted. ``lake`` is now the only valid theme, so every request resolves to it —
``?theme=desert``, a stale ``desert`` cookie, or ``THEME_DEFAULT=desert`` all
normalize away and fall back to ``lake``. (This is why deleting desert removed
the instant ``THEME_DEFAULT=desert`` rollback: there is nothing to roll back to.)

The resolved value is stamped on ``request.state.theme`` by ``ThemeMiddleware``
(app/main.py) and read in templates (``data-theme``). The function signatures are
kept so the middleware + tests need no churn; they just always yield ``lake``.
"""

from __future__ import annotations

#: Cookie that persisted the QA ``?theme=`` override (now inert — always lake).
THEME_COOKIE = "theme"
#: Env var that held the deployment default (now inert — desert was deleted).
THEME_DEFAULT_ENV = "THEME_DEFAULT"
#: The only theme the app renders.
FALLBACK_THEME = "lake"
#: The themes the app knows how to render (Lake only).
VALID_THEMES: frozenset[str] = frozenset({"lake"})

_BASE_TEMPLATES = {"lake": "base_lake.html"}


def _normalize(value: str | None) -> str | None:
    """Lower/strip ``value`` and return it only if it's a known theme (lake)."""
    if not value:
        return None
    v = value.strip().lower()
    return v if v in VALID_THEMES else None


def theme_default() -> str:
    """The deployment default theme — always ``lake`` (desert was retired)."""
    return FALLBACK_THEME


def resolve_request_theme(query_theme: str | None, cookie_theme: str | None) -> str:
    """Resolve the active theme — always ``lake``.

    Kept as a function (and still consulting the inputs) so ``ThemeMiddleware``
    and the existing tests are unchanged; a non-lake query/cookie normalizes to
    None and falls through to the lake default.
    """
    return _normalize(query_theme) or _normalize(cookie_theme) or theme_default()


def base_template_for(theme: str | None) -> str:
    """Base layout template name — always the Lake base."""
    return _BASE_TEMPLATES.get((theme or "").strip().lower(), "base_lake.html")
