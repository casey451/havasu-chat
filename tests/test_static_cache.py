"""Static-asset Cache-Control (UI build-out plan 1.9).

The ``/static`` mount previously shipped with *no* ``Cache-Control``: Starlette's
``StaticFiles`` sends ``ETag``/``Last-Modified`` validators but no ``max-age``,
so browsers revalidated every asset on every navigation. ``CachedStaticFiles``
(``app/main.py``) adds a freshness lifetime:

* bare requests              → ``public, max-age=300`` (short; self-heals)
* fingerprinted ``?v=...``   → ``public, max-age=31536000, immutable`` (1 year)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_bare_static_asset_gets_short_max_age(client: TestClient) -> None:
    """An un-fingerprinted asset gets a short, self-healing max-age."""
    r = client.get("/static/styles/lake.css")
    assert r.status_code == 200
    cc = r.headers.get("cache-control")
    assert cc == "public, max-age=300", cc


def test_fingerprinted_static_asset_is_immutable(client: TestClient) -> None:
    """A ``?v=`` fingerprinted URL is safe to cache for a year, immutably."""
    r = client.get("/static/styles/lake.css?v=ab12cd34")
    assert r.status_code == 200
    cc = r.headers.get("cache-control")
    assert cc == "public, max-age=31536000, immutable", cc


def test_unrelated_query_param_is_not_treated_as_fingerprint(client: TestClient) -> None:
    """Only a ``v`` key flips to immutable — a lookalike key must not.

    Guards the token parse against matching substrings like ``rev=`` or
    ``preview=`` (which contain ``v`` but are not the fingerprint key).
    """
    r = client.get("/static/styles/lake.css?rev=ab12cd34")
    assert r.status_code == 200
    cc = r.headers.get("cache-control")
    assert cc == "public, max-age=300", cc


def test_static_asset_still_carries_validators(client: TestClient) -> None:
    """Cache-Control is additive: the ETag/Last-Modified validators remain.

    The short bare-asset max-age relies on conditional revalidation to stay
    correct after it expires, so the validators must still be present.
    """
    r = client.get("/static/styles/lake.css")
    assert r.status_code == 200
    header_keys = {k.lower() for k in r.headers}
    assert "etag" in header_keys or "last-modified" in header_keys
