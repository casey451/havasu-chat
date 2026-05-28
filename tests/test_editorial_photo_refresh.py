"""Editorial photo refresh (items #7 + #8) — hero rotation + discover grid."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.home import queries_c
from app.home.router import _HERO_ROTATION, _pick_hero
from app.main import app

_SWAPPED_DISCOVER = {
    "Bridgewater Channel": "photo-IbBDRgpNkkQ",
    "Body Beach": "photo-ATGecbX--mU",
    "Site Six": "photo-J0tl4W-yUUI",
    "Lake Havasu State Park": "photo-rMS4YYBPOMY",
    "Cattail Cove": "photo-xDHsu-TnDbE",
    "Sara Park": "photo-3ZAKE8qVTK0",
}


@pytest.fixture(autouse=True)
def _reset_curated_cache() -> None:
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


def test_pick_hero_is_deterministic_for_pinned_date() -> None:
    """Same calendar day always yields the same hero photo."""
    pinned = datetime(2026, 6, 1, 15, 30)
    first = _pick_hero(pinned)
    second = _pick_hero(datetime(2026, 6, 1, 8, 0))

    assert first["id"] == second["id"]
    assert first["url"] == second["url"]
    assert first["id"] == "photo-QS-aTbuoJFc"
    assert first["photographer"] == "Spencer Davis"
    assert first["profile_url"] == "https://unsplash.com/@spencerdavis"
    assert first["url"].endswith("?w=1800&q=85&auto=format&fit=crop")


def test_hero_rotation_has_vetted_pool() -> None:
    assert 4 <= len(_HERO_ROTATION) <= 16
    for entry in _HERO_ROTATION:
        assert entry["id"].startswith("photo-")
        assert entry["photographer"]
        assert entry["profile_url"].startswith("https://unsplash.com/@")


def test_discover_grid_swapped_cards_have_new_photos_and_attribution() -> None:
    cards = queries_c.discover_grid()
    assert len(cards) == 10

    by_name = {c["name"]: c for c in cards}
    for name, photo_id in _SWAPPED_DISCOVER.items():
        card = by_name[name]
        assert photo_id in card["image_url"]
        attr = card["image_attribution"]
        assert attr is not None
        assert attr["photographer"]
        assert attr["profile_url"].startswith("https://unsplash.com/@")


def test_home_renders_photo_attribution() -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert 'class="c-hero-attribution"' in r.text
    assert "Photo:" in r.text
    assert 'class="c-card-attribution"' in r.text
    assert "rel=\"noopener nofollow\"" in r.text
    assert "Jonathan Varghese" in r.text
    assert "Susan Weber" in r.text
