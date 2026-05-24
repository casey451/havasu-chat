"""Phase 6.5 — homepage Browse tiles + conditions strip."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.groups import themed_groups as tg
from app.home import browse_tiles
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


def test_home_returns_200(client: TestClient) -> None:
    r = client.get("/home")
    assert r.status_code == 200


def test_home_regression_search_bar_anchor(client: TestClient) -> None:
    r = client.get("/home")
    assert "<!-- search-bar-include -->" in r.text
    assert 'data-hava-search' in r.text
    assert "hava-search-input" in r.text


def test_home_snowbird_anchor_intact() -> None:
    text = Path("app/templates/home.html").read_text(encoding="utf-8")
    assert "<!-- snowbird-panel-include -->" in text
    assert "components/snowbird_panel.html" in text


def test_home_browse_section_anchors_and_heading(client: TestClient) -> None:
    r = client.get("/home")
    assert "<!-- themed-tiles-anchor -->" in r.text
    assert 'id="browse-heading"' in r.text
    assert "Browse" in r.text
    assert "themed-tiles-grid" in r.text


def test_home_eight_tiles_in_locked_order(client: TestClient) -> None:
    r = client.get("/home")
    positions: list[int] = []
    for _kind, slug, href in _EXPECTED_TILE_ORDER:
        idx = r.text.find(f'href="{href}"')
        assert idx >= 0, f"missing tile link {href}"
        positions.append(idx)
    assert positions == sorted(positions), "tile links appear out of order"


def test_home_tile_titles_present(client: TestClient) -> None:
    r = client.get("/home")
    for _kind, _slug, _href in _EXPECTED_TILE_ORDER:
        pass
    assert "Eat &amp; Drink" in r.text or "Eat & Drink" in r.text
    assert "Health &amp; Fitness" in r.text or "Health & Fitness" in r.text
    assert "On the Water" in r.text
    assert "Home &amp; Auto" in r.text or "Home & Auto" in r.text
    assert "Outdoors" in r.text
    assert "Lodging" in r.text
    assert "Public" in r.text


def test_home_conditions_strip_anchor_and_heading(client: TestClient) -> None:
    # Phase 8a: the placeholder section was replaced with the live conditions
    # strip include. The anchor comment + heading remain stable; the body now
    # renders tiles from cached upstream sources (with a fallback empty-state
    # message when no source has populated yet).
    r = client.get("/home")
    assert "<!-- conditions-strip-anchor -->" in r.text
    assert "Today in Havasu" in r.text
    assert 'id="conditions-strip"' in r.text
    assert 'data-poll-url="/api/conditions"' in r.text


def test_home_css_imports_phase65_components() -> None:
    css = Path("app/static/styles/home.css").read_text(encoding="utf-8")
    assert "components/themed_tile.css" in css
    assert "components/conditions_strip.css" in css


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
