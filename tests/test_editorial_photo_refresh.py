"""Editorial imagery — configurable hero, clean fallbacks, event date blocks.

Rewritten for P0 Task 3. The previous version of this file *enshrined the bug*:
it asserted that the discover cards carried ``photo-<page-slug>`` Unsplash URLs
(e.g. ``photo-IbBDRgpNkkQ``) — which are not valid ``images.unsplash.com`` asset
URLs and 404 on the live site — and the hero test only checked the id started
with ``photo-``. These tests now assert the fixes instead.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.home import queries_c
from app.home.router import (
    _DEFAULT_HERO_ASSET,
    _event_accent,
    _events_for_window,
    _hero_context,
)
from app.main import app

# Real Unsplash CDN asset URLs look like ``photo-<digits>-<hex>``; the page-slug
# form (``photo-IbBDRgpNkkQ``) is not a CDN asset and 404s.
_VALID_UNSPLASH = re.compile(r"images\.unsplash\.com/photo-\d{6,}-")


@pytest.fixture(autouse=True)
def _reset_curated_cache() -> None:
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


# --- configurable hero ------------------------------------------------------


def test_hero_defaults_to_bundled_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_HERO_IMAGE_URL", raising=False)
    ctx = _hero_context()
    assert ctx["url"] == _DEFAULT_HERO_ASSET
    assert ctx["attribution"] is None


def test_hero_env_override_with_attribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_HERO_IMAGE_URL", "/static/img/custom-hero.jpg")
    monkeypatch.setenv("HOME_HERO_CREDIT", "Jane Doe")
    monkeypatch.setenv("HOME_HERO_CREDIT_URL", "https://unsplash.com/@jane")
    ctx = _hero_context()
    assert ctx["url"] == "/static/img/custom-hero.jpg"
    assert ctx["attribution"] == {
        "photographer": "Jane Doe",
        "profile_url": "https://unsplash.com/@jane",
    }


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


def test_event_accent_maps_tags_to_category_color() -> None:
    assert _event_accent(["aquatics"]) == ("Water", "#2f7d9a")
    assert _event_accent(["Live Music"])[0] == "Music"
    assert _event_accent(["food", "market"])[0] == "Food"
    assert _event_accent(None) == ("Event", "#3f5c4b")


def test_events_window_carries_category_accent() -> None:
    ids: list[str] = []
    with SessionLocal() as db:
        ev = Event(
            title=f"Lap Swim {uuid.uuid4().hex[:6]}",
            normalized_title="lap swim",
            date=now_lake_havasu().date(),
            start_time=datetime(2026, 6, 1, 9, 0).time(),
            location_name="Aquatic Center",
            location_normalized="aquatic center",
            description="swim",
            event_url="https://example.com/e",
            tags=["aquatics"],
            status="live",
            source="test-imagery",
            verified=True,
        )
        db.add(ev)
        db.commit()
        ids.append(ev.entity_id)
        now = now_lake_havasu()
        items = _events_for_window(
            db, start_day=now, end_day=now, limit=20
        )
    try:
        mine = [i for i in items if i["title"].startswith("Lap Swim")]
        assert mine, "seeded event not in window"
        assert mine[0]["category_label"] == "Water"
        assert mine[0]["accent_color"] == "#2f7d9a"
        assert mine[0]["image_url"] is None  # date block is the hero
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ids)))
            db.commit()


def test_home_renders_sandstone_text_hero(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Sandstone home uses an editorial *text* hero (no background photo).

    The configurable-photo hero was a Lake Light feature; the locked prototype's
    home leads with a centered Fraunces headline + single search. The hero
    composer (``_hero_context``) keeps its own unit test above for reuse on the
    mode-landing heroes (step 5).
    """
    monkeypatch.delenv("HOME_HERO_IMAGE_URL", raising=False)
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert 'class="hero wrap"' in r.text
    assert "What's the plan on" in r.text
