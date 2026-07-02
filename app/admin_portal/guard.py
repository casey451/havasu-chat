"""Admin gate for the portal — the ONE consolidated admin guard.

2026-07-02 (audit): this used to be a cookie-only copy, which bounced
legitimate role-admin users (accepted by /admin event moderation) to the login
page. It now delegates to :func:`app.admin.auth.admin_guard` — cookie OR
role="admin", 403 for logged-in non-admins.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.admin.auth import admin_guard


def guard(request: Request) -> RedirectResponse | None:
    """Return a redirect to the existing admin login when not authenticated."""
    return admin_guard(request)
