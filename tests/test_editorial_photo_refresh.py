"""Editorial imagery — configurable hero, clean fallbacks, event date blocks.

Rewritten for P0 Task 3. The previous version of this file *enshrined the bug*:
it asserted that the discover cards carried ``photo-<page-slug>`` Unsplash URLs
(e.g. ``photo-IbBDRgpNkkQ``) — which are not valid ``images.unsplash.com`` asset
URLs and 404 on the live site — and the hero test only checked the id started
with ``photo-``. These tests now assert the fixes instead.
"""

from __future__ import annotations

import re

import pytest

from app.home import queries_c

# (the configurable-hero + event-accent + window-feed helpers were pre-v4
# home_lake builders, deleted 2026-07-02 with the flag collapse)

# Real Unsplash CDN asset URLs look like ``photo-<digits>-<hex>``; the page-slug
# form (``photo-IbBDRgpNkkQ``) is not a CDN asset and 404s.
_VALID_UNSPLASH = re.compile(r"images\.unsplash\.com/photo-\d{6,}-")


@pytest.fixture(autouse=True)
def _reset_curated_cache() -> None:
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


# --- configurable hero ------------------------------------------------------




# --- no broken / reused fallback imagery ------------------------------------


def test_discover_cards_have_no_invalid_unsplash_urls() -> None:
    """Regression: a curated card's image is either a valid CDN asset URL or
    None (which falls back to a per-card gradient + name, never a reused photo)."""
    for card in queries_c.discover_grid():
        url = card["image_url"]
        if url and "images.unsplash.com" in url:
            assert _VALID_UNSPLASH.search(url), f"invalid Unsplash URL on {card['name']}: {url}"


def test_previously_broken_scenic_cards_now_fall_back_cleanly() -> None:
    by_name = {c["name"]: c for c in queries_c.discover_grid()}
    for name in ("Body Beach", "Site Six", "Sara Park", "Cattail Cove"):
        assert by_name[name]["image_url"] is None


# --- image-optional event cards (date block is the hero) --------------------



