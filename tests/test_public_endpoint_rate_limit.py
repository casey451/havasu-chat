"""A2: per-IP rate limits on the public read + JSON scrape surface.

The wide-open scrape targets (provider profiles, category/leaf pages, and the
``conditions``/``gas``/``map_data``/``events.ics`` JSON+feed endpoints) now carry
``@limiter.limit`` with env-tunable budgets (``PUBLIC_HTML_RATE_LIMIT`` /
``PUBLIC_API_RATE_LIMIT``, see ``app/core/rate_limit.py``).

The suite runs with ``RATE_LIMIT_DISABLED=1`` (tests/conftest.py), which the
limiter reads once at construction — so these tests flip ``limiter.enabled`` back
on, pin a tiny per-IP budget via the env knobs (the limit callables re-read env
each request), and reset the in-memory storage around each test so buckets never
leak. ``TestClient`` keys every request to the same client IP, so one bucket is
shared across the loop.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture
def _tiny_limits(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PUBLIC_API_RATE_LIMIT", "2/minute")
    monkeypatch.setenv("PUBLIC_HTML_RATE_LIMIT", "2/minute")
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    yield
    limiter.reset()


def test_json_api_rate_limited_429(_tiny_limits) -> None:
    """The third hit to a JSON endpoint past a 2/min bucket returns 429."""
    with TestClient(app) as client:
        assert client.get("/api/conditions").status_code != 429
        assert client.get("/api/conditions").status_code != 429
        blocked = client.get("/api/conditions")
    assert blocked.status_code == 429
    assert "message" in blocked.json()


def test_calendar_feed_rate_limited_429(_tiny_limits) -> None:
    """The bulk iCal feed is a cheap full-dataset pull — it must be capped too."""
    with TestClient(app) as client:
        assert client.get("/events.ics").status_code != 429
        assert client.get("/events.ics").status_code != 429
        blocked = client.get("/events.ics")
    assert blocked.status_code == 429


def test_html_listing_rate_limited_429(_tiny_limits) -> None:
    """An HTML listing page past its 2/min bucket returns 429."""
    with TestClient(app) as client:
        assert client.get("/categories").status_code != 429
        assert client.get("/categories").status_code != 429
        blocked = client.get("/categories")
    assert blocked.status_code == 429


def test_rate_limit_disabled_never_blocks() -> None:
    """Suite default (RATE_LIMIT_DISABLED=1 -> limiter.enabled=False): the bypass
    must let every request through, no matter how many — so the test gate and an
    emergency prod disable both keep working."""
    assert limiter.enabled is False
    with TestClient(app) as client:
        for _ in range(6):
            assert client.get("/api/conditions").status_code != 429
