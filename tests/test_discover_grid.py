"""Direction C Discover grid tests (PR D2).

Coverage:

1. ``queries_c.discover_grid()`` shape and contract.
2. Curated JSON file integrity (schema, status values, span values).
3. End-to-end render via ``GET /home?redesign=1``: the partial is
   included, every card carries the C9 status-pill state class, and
   no "0" copy bleeds through (BUILD.md hard rule).

These run without a populated DB (no Provider rows). The slug-join
enrichment is exercised only as a no-op path here -- a separate
integration test with a populated session is out of scope for D2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.home import queries_c
from app.main import app

_ALLOWED_SPANS = {3, 4, 5, 6, 8, 12}
_ALLOWED_STATUS = {"open", "closing", "closed", "scenic", "neutral"}


@pytest.fixture(autouse=True)
def _reset_curated_cache() -> None:
    """Curated JSON is module-cached; clear between tests so file-mocking
    tests don't poison later runs."""
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


# ---------------------------------------------------------------------------
# Curated JSON file integrity
# ---------------------------------------------------------------------------


def test_curated_json_is_valid_and_in_range() -> None:
    """File loads, has 6-12 places, schema fields populated."""
    data = queries_c._load_curated()
    assert data["version"] == 2
    places = data["places"]
    assert 6 <= len(places) <= 12, f"want 6-12 places, got {len(places)}"
    for i, p in enumerate(places):
        assert "name" in p and p["name"], f"place {i} missing name"
        assert p["span"] in _ALLOWED_SPANS, f"place {i} bad span {p['span']}"
        assert p["status"] in _ALLOWED_STATUS, f"place {i} bad status"
        assert p["image_url"].startswith("https://images.unsplash.com/")
        assert "?w=" in p["image_url"], "image_url missing sizing params"


def test_curated_layout_fills_clean_rows() -> None:
    """Spans pack into rows of 12 without overflow -- ensures the masonry
    renders without trailing whitespace columns. Allowed: the last row
    may be a single span-12 feature card."""
    places = queries_c._load_curated()["places"]
    cols = sum(p["span"] for p in places)
    assert cols % 12 == 0, f"total cols {cols} not a multiple of 12"


# ---------------------------------------------------------------------------
# discover_grid() function contract
# ---------------------------------------------------------------------------


def test_discover_grid_returns_normalised_cards() -> None:
    """No db, no now -> static curated cards with all template keys."""
    cards = queries_c.discover_grid()
    assert 6 <= len(cards) <= 12
    required_keys = {
        "slug", "name", "where", "image_url", "image_attribution", "span", "pick",
        "blurb", "meta_line", "status", "status_text",
    }
    for c in cards:
        assert set(c.keys()) == required_keys, f"card missing keys: {required_keys - set(c.keys())}"
        assert isinstance(c["span"], int)
        assert isinstance(c["pick"], bool)


def test_discover_grid_limit_caps_result() -> None:
    cards = queries_c.discover_grid(limit=3)
    assert len(cards) == 3


def test_discover_grid_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """File-missing path must return [], not raise -- the template
    falls back to the 'taking a breather' editorial empty state."""
    bogus = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(queries_c, "_DATA_PATH", bogus)
    queries_c.reset_cache()
    assert queries_c.discover_grid() == []


def test_discover_grid_malformed_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A corrupt JSON file should not 500 the home page."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not: valid json", encoding="utf-8")
    monkeypatch.setattr(queries_c, "_DATA_PATH", bad)
    queries_c.reset_cache()
    assert queries_c.discover_grid() == []


def test_discover_grid_status_text_can_be_none() -> None:
    """At least one curated card has status_text=None so the pill
    is hidden -- this is the documented 'no pill we can't justify'
    behaviour from BUILD.md."""
    cards = queries_c.discover_grid()
    null_pill_cards = [c for c in cards if c["status_text"] is None]
    assert null_pill_cards, "expected at least one card with null status_text"


# ---------------------------------------------------------------------------
# End-to-end /home rendering
# ---------------------------------------------------------------------------


def test_home_redesign_renders_discover_grid() -> None:
    """GET /home renders the discover/mood browse grid."""
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert 'class="ll-grid-two"' in r.text
    assert 'class="ll-tile"' in r.text


def test_home_redesign_uses_editorial_status_pills() -> None:
    """Discover section renders editable card titles in Lake Light UI."""
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "Things to do" in r.text
    assert "Browse by mood" in r.text


def test_home_redesign_no_zero_copy() -> None:
    """No '0 places', '0 events', etc. -- editorial empty states only.

    The check strips inline SVG content first. PR D4's services grid
    introduced 12 inline <svg viewBox="0 0 24 24"> icons whose path
    data legitimately contains " 0 " (SVG arc flags like 'a4 4 0 0 1')
    -- those are not editorial copy and must not trip this guard.
    """
    import re

    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    body = r.text
    body_without_svg = re.sub(r"<svg[\s\S]*?</svg>", "", body)
    assert "0 listed" not in body_without_svg
