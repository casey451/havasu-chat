"""Phase 6.5 — homepage Browse tiles (unit tests; /home is home_c.html)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_EXPECTED_TILE_ORDER: tuple[tuple[str, str, str], ...] = (
    ("group", "eat-drink-group", "/group/eat-drink-group"),
    ("group", "health-fitness-group", "/group/health-fitness-group"),
    ("group", "on-the-water-group", "/group/on-the-water-group"),
    ("group", "home-auto-group", "/group/home-auto-group"),
    ("group", "things-to-do-group", "/group/things-to-do-group"),
    ("category", "events", "/category/events"),
    ("category", "outdoors-parks-trails", "/category/outdoors-parks-trails"),
    ("category", "lodging-vacation-rentals", "/category/lodging-vacation-rentals"),
    ("category", "public-civic-resources", "/category/public-civic-resources"),
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_home_returns_200_serves_sandstone(client: TestClient) -> None:
    r = client.get("/home")
    assert r.status_code == 200
    assert "/static/styles/sandstone.css" in r.text
    assert 'data-mode="ask"' in r.text


def test_home_calendar_param_still_serves_sandstone(client: TestClient) -> None:
    for qs in ("", "?cal=2026-07", "?cal=2025-12"):
        r = client.get(f"/home{qs}")
        assert r.status_code == 200
        assert "/static/styles/sandstone.css" in r.text


def test_themed_tile_partial_exists() -> None:
    path = Path("app/templates/components/themed_tile.html")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "themed-tile" in text
    assert "tile.tile_title" in text
