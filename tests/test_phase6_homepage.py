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


def test_home_returns_200_serves_desert(client: TestClient) -> None:
    # Desert Modern reskin: /home extends desert_base (desert.css).
    r = client.get("/home")
    assert r.status_code == 200
    assert "/static/styles/desert.css" in r.text
    assert 'data-mode="ask"' in r.text


def test_home_calendar_param_still_serves_desert(client: TestClient) -> None:
    for qs in ("", "?cal=2026-07", "?cal=2025-12"):
        r = client.get(f"/home{qs}")
        assert r.status_code == 200
        assert "/static/styles/desert.css" in r.text


def test_home_has_single_search_box_no_quicklinks(client: TestClient) -> None:
    """Workstream E: one search box wired to /chat, the four quick-action chips
    removed, and the input set up for the rotating placeholder."""
    r = client.get("/home")
    assert r.status_code == 200
    # Exactly one hero search form, posting to the 3-tier /chat backend.
    assert r.text.count('id="home-ask-form"') == 1
    assert 'action="/chat"' in r.text
    # The .quicklinks chip row is gone.
    assert 'class="quicklinks"' not in r.text
    # Input ready for the rotating placeholder (autocomplete off so the browser
    # dropdown doesn't fight it) and the seed script is present.
    assert 'autocomplete="off"' in r.text
    assert "setInterval(rotate" in r.text


def test_themed_tile_partial_exists() -> None:
    path = Path("app/templates/components/themed_tile.html")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "themed-tile" in text
    assert "tile.tile_title" in text
