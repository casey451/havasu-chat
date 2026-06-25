"""Runtime feature flags for the home + calendar redesign (dark rollout).

The ``home_redesign`` flag gates the v4 homepage/calendar reskin. It ships OFF:
with the flag off, ``/home`` and ``/calendar`` render the existing Lake Ink &
Brass templates exactly as before, so merging to ``main`` while dark changes
nothing for users and rollback is instant (flip the env var off).

Resolution order (first hit wins), mirroring the repo's ``?theme=`` middleware
pattern so the redesign is reviewable on the real site without exposing it:

1. ``?home_redesign=1`` / ``?home_redesign=0`` query override (preview). A valid
   override is also persisted to the ``home_redesign`` cookie so a reviewer can
   click around the redesigned site without re-appending the param every hop.
2. the ``home_redesign`` cookie (set by a prior query override).
3. the ``HOME_REDESIGN`` environment variable (the go-live switch — Casey flips
   this on the Railway service when the Definition of Done is met).

Off by default everywhere. Nothing here flips the flag autonomously; the env var
is the single human go-live gate.
"""

from __future__ import annotations

import os

from fastapi import Request
from starlette.responses import Response

#: Cookie + query-param name; 30-day persistence for the preview override.
FLAG_NAME = "home_redesign"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60

_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no"}


def _env_default() -> bool:
    return (os.getenv("HOME_REDESIGN") or "").strip().lower() in _TRUE


def _query_override(request: Request) -> bool | None:
    raw = request.query_params.get(FLAG_NAME)
    if raw is None:
        return None
    val = raw.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    return None


def home_redesign_enabled(request: Request) -> bool:
    """True when the redesigned home/calendar should be served for this request.

    Query override > cookie > ``HOME_REDESIGN`` env (off by default).
    """
    override = _query_override(request)
    if override is not None:
        return override
    cookie = request.cookies.get(FLAG_NAME)
    if cookie is not None:
        cookie = cookie.strip().lower()
        if cookie in _TRUE:
            return True
        if cookie in _FALSE:
            return False
    return _env_default()


def apply_preview_cookie(request: Request, response: Response) -> None:
    """Persist a valid ``?home_redesign=`` preview override onto the response.

    No-op when the request carried no override, so normal traffic never gets a
    cookie. Keeps a reviewer's preview state sticky across navigation.
    """
    override = _query_override(request)
    if override is None:
        return
    response.set_cookie(
        FLAG_NAME,
        "1" if override else "0",
        max_age=_COOKIE_MAX_AGE,
        path="/",
        httponly=False,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
