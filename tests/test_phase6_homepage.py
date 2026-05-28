"""Phase 6.5 — homepage Browse tiles (unit tests; /home is home_c.html)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.groups import themed_groups as tg
from app.home import browse_tiles
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


def test_home_returns_200_serves_home_c(client: TestClient) -> None:
    r = client.get("/home")
    assert r.status_code == 200
    assert "home_c.css" in r.text
    assert 'class="home-c"' in r.text


def test_home_query_redesign_param_still_serves_home_c(client: TestClient) -> None:
    for qs in ("", "?redesign=0", "?redesign=1"):
        r = client.get(f"/home{qs}")
        assert r.status_code == 200
        assert "home_c.css" in r.text


def test_browse_tile_specs_match_themed_groups_dict() -> None:
    group_slugs = {s.slug for s in browse_tiles.browse_tile_specs() if s.kind == "group"}
    assert group_slugs == set(tg.THEMED_GROUPS.keys())


def test_build_browse_tiles_count_labels_match_db() -> None:
    with SessionLocal() as db:
        tiles = browse_tiles.build_browse_tiles(db)
    assert len(tiles) == 9
    with SessionLocal() as db:
        for tile, (kind, slug, _href) in zip(tiles, _EXPECTED_TILE_ORDER, strict=True):
            assert tile["tile_kind"] == kind
            assert tile["tile_slug"] == slug
            if kind == "group":
                cats = tg.get_categories_for_group(slug)
                raw = browse_tiles.count_entities_for_category_slugs(db, cats)
            else:
                raw = browse_tiles.count_entities_for_category_slugs(db, [slug])
            assert tile["tile_count"] == browse_tiles.format_tile_count_label(raw)
            assert tile["tile_count_raw"] == raw


def test_format_tile_count_cap() -> None:
    assert browse_tiles.format_tile_count_label(199) == "199 businesses"
    assert browse_tiles.format_tile_count_label(200) == "200+ businesses"
    assert browse_tiles.format_tile_count_label(500) == "200+ businesses"


def test_themed_tile_partial_exists() -> None:
    path = Path("app/templates/components/themed_tile.html")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "themed-tile" in text
    assert "tile.tile_title" in text
