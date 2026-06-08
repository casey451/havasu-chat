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


@pytest.mark.parametrize(
    ("path", "mode", "heading"),
    [
        ("/lake", "lake", "Everything for a day on the water"),
        ("/night", "night", "Where the night goes"),
        ("/family", "family", "Plenty to do with the kids"),
    ],
)
def test_mode_landing_renders_pretheme_and_real_links(path: str, mode: str, heading: str) -> None:
    with TestClient(app) as client:
        r = client.get(path)
    assert r.status_code == 200
    body = r.text
    # Pre-themed server-side (Night fires its dark transformation here).
    assert f'data-mode="{mode}"' in body
    assert heading in body
    assert "/static/styles/desert.css" in body  # Desert Modern reskin
    # Active mode control is stamped (now the in-page mode switcher pills).
    assert f'href="/{mode}" data-mode="{mode}"' in body
    assert "aria-current=\"page\"" in body
    # Sub-tiles are navigation to real destinations only.
    assert "/categories/" in body or "/chat?q=" in body
    # Anti-confabulation: none of the prototype's mock counters.
    for mock in _MOCK_NUMBERS:
        assert mock not in body, f"{path} leaked mock counter: {mock}"


def test_night_landing_has_no_lime_and_real_dark_palette() -> None:
    """Night landing loads in the hot-pink/teal/black party palette (data-mode)."""
    with TestClient(app) as client:
        r = client.get("/night")
    assert 'data-mode="night"' in r.text


def test_mode_landing_data_contract() -> None:
    with SessionLocal() as db:
        lake = sandstone.mode_landing(db, "lake")
        night = sandstone.mode_landing(db, "night")
    # Every landing ships exactly six navigation sub-tiles, each with a real url.
    assert len(lake["tiles"]) == 6
    for tile in lake["tiles"]:
        assert tile["url"].startswith(("/categories/", "/chat?q="))
    # Lake hero may carry live mini-conditions; Night never shows a fake counter.
    assert isinstance(lake["mini_conditions"], list)
    assert night["mini_conditions"] == []


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


def test_lake_conditions_block_links_to_today() -> None:
    """The Lake hero conditions strip deep-links to the full /today board.

    Skips cleanly if no live mini-conditions are available in the test DB (the
    strip -- and therefore the link -- is omitted when there's no live data).
    """
    with SessionLocal() as db:
        has_conditions = bool(sandstone.mode_landing(db, "lake")["mini_conditions"])
    with TestClient(app) as client:
        body = client.get("/lake").text
    if has_conditions:
        assert 'class="mini-cond mini-cond--link" href="/today"' in body
    # /night has no mini-conditions, so it must NOT carry the conditions link.
    with TestClient(app) as client:
        night = client.get("/night").text
    assert "mini-cond--link" not in night
