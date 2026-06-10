"""Admin gate for the portal — reuses the existing /admin cookie.

Same pattern as ``app.admin.router._guard``: routes call ``guard(request)``
and return the redirect when it is not None. Once the portal is wired,
the existing ``/admin/login`` session works here with no extra setup.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.admin.auth import COOKIE_NAME, verify_admin_cookie


def guard(request: Request) -> RedirectResponse | None:
    """Return a redirect to the existing admin login when not authenticated."""
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=303)
