"""Full-page map view (/map → map_c.html) tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_map_view_returns_200_with_container_and_leaflet() -> None:
    with TestClient(app) as client:
        r = client.get("/map")
    assert r.status_code == 200
    # Map host that map.js mounts onto.
    assert 'id="map-container"' in r.text
    # map.js + data-map-scope wiring.
    assert "/static/js/map.js" in r.text
    assert "data-map-scope" in r.text
    # Leaflet CDN assets (same tags as category_landing.html).
    assert "leaflet/1.9.4/leaflet.min.css" in r.text
    assert "leaflet/1.9.4/leaflet.min.js" in r.text
    assert "leaflet.markercluster/1.5.3/leaflet.markercluster.min.js" in r.text
    # Lake Light chrome.
    assert "/static/styles/lake_light.css" in r.text
    assert 'class="ll-page map-page"' in r.text
    # Full-page map stylesheet.
    assert "/static/styles/components/map_view.css" in r.text


def test_map_view_default_scope_is_a_themed_group() -> None:
    with TestClient(app) as client:
        r = client.get("/map")
    assert r.status_code == 200
    # Default scope tab is the first themed group.
    assert 'data-map-scope="eat-drink-group"' in r.text
    # Scope selector exposes both themed groups and tier-1 categories.
    assert 'data-scope-slug="on-the-water-group"' in r.text
    assert 'data-scope-slug="eat-drink"' in r.text


def test_map_view_honors_scope_query_param() -> None:
    with TestClient(app) as client:
        r = client.get("/map?scope=on-the-water")
    assert r.status_code == 200
    assert 'data-map-scope="on-the-water"' in r.text


def test_map_view_rejects_unknown_scope_falls_back_to_default() -> None:
    with TestClient(app) as client:
        r = client.get("/map?scope=not-a-real-scope")
    assert r.status_code == 200
    # Unknown scope falls back to the default themed group.
    assert 'data-map-scope="eat-drink-group"' in r.text


def test_bottom_nav_has_map_link() -> None:
    with TestClient(app) as client:
        r = client.get("/map")
    assert 'href="/map"' in r.text
