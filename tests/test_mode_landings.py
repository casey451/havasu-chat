"""Sandstone mode landings — Lake / Night / Family (01_UI_BUILD_GUIDE.md §4.10).

Each landing loads pre-themed (data-mode), sub-tiles navigate to REAL routes (a
category page or a /chat search — never a 404), and the hero shows only live
data or copy — never the prototype's mock counters.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.home import sandstone
from app.main import app

_MOCK_NUMBERS = ("12 happy hours", "6 kid events", "4 live music", "448.7", "280 places")


# C11: /lake no longer renders a mode landing — it 301-redirects to the Lake
# Life category (covered by tests/test_lake_redirect.py). Night/Family stay.
@pytest.mark.parametrize(
    ("path", "mode", "heading"),
    [
        ("/night", "night", "Where the night goes"),
        ("/family", "family", "Plenty to do with the kids"),
    ],
)
def test_mode_landing_renders_pretheme_and_real_links(path: str, mode: str, heading: str) -> None:
    with TestClient(app) as client:
        r = client.get(path)
    assert r.status_code == 200
    body = r.text
    # v4.5 PR-5: the Family/Night landings wear the standalone v4 shell — the
    # desert in-page mode-switcher + data-mode dark transformation are retired
    # (the v4 six-link header is the navigation; v4 has a single lake theme).
    assert heading in body
    assert 'data-theme="lake"' in body  # Lake Ink & Brass is the only theme now
    assert "/static/styles/lake_redesign.css" in body
    # Sub-tiles are navigation to real destinations only.
    assert "/categories/" in body or "/chat?q=" in body
    # Anti-confabulation: none of the prototype's mock counters.
    for mock in _MOCK_NUMBERS:
        assert mock not in body, f"{path} leaked mock counter: {mock}"


def test_night_landing_on_v4_shell_single_theme() -> None:
    """v4.5 PR-5: /night is on the v4 shell — one lake theme, no desert dark
    transformation (data-mode is gone)."""
    with TestClient(app) as client:
        r = client.get("/night")
    assert 'data-theme="lake"' in r.text
    assert 'data-mode="night"' not in r.text
    assert "/static/styles/desert_home.css" not in r.text


def test_mode_landing_data_contract() -> None:
    # ("lake" left _MODE_CONFIG 2026-07-02: /lake has 301'd to the category
    # page since IA v2, so its landing config/tiles/mini-conditions were dead.)
    with SessionLocal() as db:
        family = sandstone.mode_landing(db, "family")
        night = sandstone.mode_landing(db, "night")
    # Every landing ships exactly six navigation sub-tiles, each with a real url.
    assert len(family["tiles"]) == 6
    for tile in family["tiles"]:
        assert tile["url"].startswith(("/categories/", "/chat?q=", "/events-ui", "/calendar"))
    # Night/Family never show a fake counter (anti-confabulation §4.10).
    assert night["mini_conditions"] == []
    with SessionLocal() as db, pytest.raises(KeyError):
        sandstone.mode_landing(db, "lake")


def test_unknown_mode_raises() -> None:
    with SessionLocal() as db, pytest.raises(KeyError):
        sandstone.mode_landing(db, "bogus")


# -- WP-8: mode-page cross-links (7 / G-2) -----------------------------------


def test_night_and_family_link_to_events() -> None:
    """N-11: /night and /family surface a 'This week's events' link to /events-ui."""
    for path in ("/night", "/family"):
        with TestClient(app) as client:
            body = client.get(path).text
        assert "This week's events" in body
        assert 'href="/events-ui"' in body


def test_night_has_no_conditions_link() -> None:
    """C11 removed the served /lake hero (it now redirects to the Lake Life
    category), so the only remaining assertion here is the negative one: /night
    has no live mini-conditions and therefore must NOT carry the conditions
    deep-link. The lake mini-conditions DATA is still exercised by
    test_mode_landing_data_contract."""
    with TestClient(app) as client:
        night = client.get("/night").text
    assert "mini-cond--link" not in night
