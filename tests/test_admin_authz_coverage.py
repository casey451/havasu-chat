"""Regression: every /admin* route rejects an unauthenticated request (audit L3).

Admin authorization is enforced by a hand-copied first-line `_guard(request)` /
`_admin_guard(request)` call inside each handler, not by a router-level
dependency. That's correct everywhere today, but a future handler that forgets
the two guard lines would be silently world-accessible. This test fails if any
`/admin` or `/api/admin` route returns 200 without an admin cookie — turning the
convention into an enforced invariant.

If a genuinely public admin route is added later, add it to `_PUBLIC_ALLOWLIST`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.main import app

client = TestClient(app)

# Genuinely public routes under the /admin* prefixes (the login surface).
_PUBLIC_ALLOWLIST: set[tuple[str, str]] = {
    ("/admin/login", "GET"),
    ("/admin/login", "POST"),
    ("/api/admin/login", "POST"),
}

# Acceptable outcomes for an unauthenticated request (i.e. the privileged action
# did NOT execute): redirect-to-login, explicit auth error, body-validation that
# ran before the in-handler guard, or a path-param miss before the guard.
_REJECTED = {301, 302, 303, 307, 308, 401, 403, 404, 422}


def _admin_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for r in app.routes:
        if not isinstance(r, Route):
            continue
        if not (r.path.startswith("/admin") or r.path.startswith("/api/admin")):
            continue
        for method in sorted(r.methods or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.append((r.path, method))
    return routes


def _concrete(path: str) -> str:
    # Substitute a dummy value for any {param}; the guard runs first, so the
    # value is never used before the auth check.
    return "/".join("1" if s.startswith("{") and s.endswith("}") else s for s in path.split("/"))


@pytest.mark.parametrize("path,method", _admin_routes())
def test_admin_route_requires_auth(path: str, method: str) -> None:
    if (path, method) in _PUBLIC_ALLOWLIST:
        pytest.skip("public admin route")
    url = _concrete(path)
    resp = client.request(method, url, follow_redirects=False)
    assert resp.status_code != 200, (
        f"{method} {url} returned 200 with NO admin cookie — missing guard?"
    )
    assert resp.status_code in _REJECTED, (
        f"{method} {url} returned unexpected {resp.status_code} without auth "
        f"(expected one of {sorted(_REJECTED)})"
    )
