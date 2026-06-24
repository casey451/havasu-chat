"""Phase 5d — Lake Ink & Brass full-page /map.

The reskin is chrome-only: the page renders on an empty DB (markers load later
via /api/map_data), so the route is exercised with TestClient. The critical
assertions are that EVERY map JS hook survives the reskin (the Leaflet/cluster
CDN, map.js + boat_mode.js, #map-container, the data-map-* attributes, and the
scope tabs) — plus the flag-swap, desert default, single-h1, and a11y.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


def test_lake_map_preserves_all_js_wiring() -> None:
    b = TestClient(app).get("/map?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_map.css" in b
    assert "/static/styles/components/map_view.css" in b  # shared layout kept
    # map JS wiring — all must survive the reskin untouched
    assert 'id="map-container"' in b
    assert 'data-map-scope=' in b
    assert 'data-map-default-expanded="true"' in b
    assert "data-map-toggle" in b
    assert "data-map-scope-tab" in b  # scope tabs
    assert "/static/js/map.js" in b and "/static/js/boat_mode.js" in b
    assert "leaflet" in b.lower()  # Leaflet + markercluster CDN
    # chrome + structure
    assert "The <em>map.</em>" in b
    assert b.count("<h1") == 1
    assert not _a11y(b)
