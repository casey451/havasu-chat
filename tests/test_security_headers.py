"""Security headers middleware (v48 launch hardening)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_SECURITY_HEADERS = (
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)


def test_home_response_has_security_headers(client: TestClient) -> None:
    """The editorial /home route is HTML; it MUST carry the baseline headers."""
    r = client.get("/home")
    # /home routes through the templates layer; whatever it returns (200 or
    # a non-error redirect), the middleware should have layered headers on.
    assert r.status_code < 500
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    perm = r.headers.get("permissions-policy") or ""
    assert "geolocation=()" in perm
    assert "microphone=()" in perm
    assert "camera=()" in perm


def test_robots_txt_has_security_headers(client: TestClient) -> None:
    """robots.txt is not an /api/ path; middleware should still apply."""
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"


def test_health_endpoint_skips_security_headers(client: TestClient) -> None:
    """Railway health probes don't need the HTML hardening headers."""
    r = client.get("/health")
    assert r.status_code == 200
    for header in _SECURITY_HEADERS:
        assert header not in {k.lower() for k in r.headers}, f"/health should not carry {header}"


def test_api_routes_skip_security_headers(client: TestClient) -> None:
    """JSON API endpoints (anything under /api/) should not have these headers.

    Hitting a real /api/ route that's available without auth is brittle, so
    we ping a path that is guaranteed to land in the FastAPI router under
    /api/ — even a 404 / 405 response flows through the middleware.
    """
    r = client.get("/api/__security_headers_probe__")
    # Whatever the status, the middleware should have skipped this path.
    for header in _SECURITY_HEADERS:
        assert header not in {k.lower() for k in r.headers}, f"/api/* should not carry {header}"


def test_http_request_omits_hsts(client: TestClient) -> None:
    """TestClient defaults to http://; HSTS must NOT be set on plain HTTP."""
    r = client.get("/home")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


def test_https_request_includes_hsts(client: TestClient) -> None:
    """When the scheme is https, HSTS should be present."""
    r = client.get("https://testserver/home")
    assert r.headers.get("strict-transport-security", "").startswith("max-age=63072000")
    assert "includeSubDomains" in (r.headers.get("strict-transport-security") or "")
