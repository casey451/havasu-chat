"""Home-page feature flags.

Single source of truth for any rollout switch that gates *redesign-era*
home structure (the §B layout swap, Marquee partial, Supporters wall,
self-hosted fonts, and the C13 a11y polish).

The flag is intentionally minimal: an env var with a per-request query
override. No DB, no admin UI, no per-user targeting -- those are heavier
solutions and the redesign cut is bounded enough to live without them.

Truthy values for ``HOME_REDESIGN`` (case-insensitive): ``1 true yes on``.
Anything else (including unset) reads as off.

The ``?redesign=1`` / ``?redesign=0`` query string overrides the env var
on a per-request basis so staff can preview either side in production
without flipping the env. The override accepts the same truthy/falsy
vocabulary as the env var.

See ``outputs/boot_prompt_ui_redesign_session.md`` and the PR 1 dispatch
for the rollout plan.
"""

from __future__ import annotations

import os
from typing import Optional

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _parse_bool(raw: str | None) -> bool | None:
    """Return True/False for a truthy/falsy token, None when unrecognised.

    None is the *unset* signal so callers can compose env + override
    (override wins when present).
    """
    if raw is None:
        return None
    v = raw.strip().lower()
    if not v:
        return None
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    return None


def home_redesign_env_default() -> bool:
    """Read the ``HOME_REDESIGN`` env var. Off when unset or unrecognised."""
    return _parse_bool(os.environ.get("HOME_REDESIGN")) is True


def home_redesign_enabled(query_override: Optional[str] = None) -> bool:
    """Resolve the final on/off for a given request.

    ``query_override`` is the raw value of the ``redesign`` query string
    param (or ``None`` when absent). When present and parseable as
    truthy/falsy, it wins over the env default. When present but
    unparseable (e.g. ``?redesign=maybe``), it is ignored and the env
    default applies.
    """
    override = _parse_bool(query_override)
    if override is not None:
        return override
    return home_redesign_env_default()
