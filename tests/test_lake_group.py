"""Deferred follow-up — Lake themed-group landing (/group/{slug}).

A chrome reskin of the most JS-heavy page (Leaflet + boat_mode + search_bar +
map + category_filters + the shared hava_card stream). Renders on an empty DB
(empty stream + sparse banner), so the route is exercised with TestClient. The
critical assertions: every JS hook + the pinned group-accent body class survive
the reskin, plus flag-swap, desert default, single-h1, and a11y.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app

_GROUP = "/group/on-the-water-group"


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


def test_lake_group_landing_preserves_wiring() -> None:
    r = TestClient(app).get(f"{_GROUP}?theme=lake")
    assert r.status_code == 200
    assert 'data-theme="lake"' in r.text
    assert "/static/styles/lake_redesign.css" in r.text  # v4.6 PR-1: v4 shell
    assert "/static/styles/components/hava_card.css" in r.text  # shared card sheet kept
    assert "group-accent-" in r.text  # body-accent hook pinned by test_phase6_themed_groups
    # JS wiring — all must survive the reskin
    assert 'id="map-container"' in r.text
    assert "data-hava-search" in r.text
    assert "data-map-toggle" in r.text
    assert "data-map-scope=" in r.text
    for js in ("boat_mode.js", "search_bar.js", "map.js", "category_filters.js"):
        assert f"/static/js/{js}" in r.text
    assert "leaflet" in r.text.lower()  # Leaflet + markercluster CDN
    assert r.text.count("<h1") == 1
    assert not _a11y(r.text)
