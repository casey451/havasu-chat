"""Tests for ``build_business_list`` (CLUSTER-02 / business_list component)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.chat.component_builders import build_business_list


def _rows(*providers: dict) -> list[dict]:
    return [{"type": "provider", **p} for p in providers]


def test_build_business_list_sorts_by_rating_desc() -> None:
    rows = _rows(
        {"name": "Low Rated", "slug": "low", "google_rating": 3.2},
        {"name": "Top Rated", "slug": "top", "google_rating": 4.9},
        {"name": "Mid Rated", "slug": "mid", "google_rating": 4.1},
    )
    data = build_business_list(rows, category="plumber", total_count=3)
    assert data["items"][0]["name"] == "Top Rated"
    assert data["items"][1]["name"] == "Mid Rated"
    assert data["items"][2]["name"] == "Low Rated"


def test_build_business_list_phone_and_maps_links() -> None:
    rows = _rows(
        {
            "name": "Acme Plumbing",
            "slug": "acme-plumbing",
            "phone": "(480) 409-0746",
            "address": "1234 Pine Rd, Lake Havasu City",
            "google_rating": 4.7,
            "google_review_count": 38,
        }
    )
    data = build_business_list(rows, category="plumber", total_count=1)
    item = data["items"][0]
    assert item["url"] == "/provider/acme-plumbing"
    assert item["phone"] == "(480) 409-0746"
    assert item["phone_raw"] == "4804090746"
    assert "google.com/maps/search" in item["directions_url"]
    assert "1234%20Pine%20Rd" in item["directions_url"]


def test_build_business_list_open_status_from_structured_hours(monkeypatch) -> None:
    monday = datetime(2026, 5, 25, 14, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr("app.chat.component_builders.now_lake_havasu", lambda: monday)
    rows = _rows(
        {
            "name": "Open Shop",
            "slug": "open-shop",
            "hours_structured": {"monday": [{"open": "09:00", "close": "17:00"}]},
        }
    )
    data = build_business_list(
        rows,
        category="electrician",
        total_count=1,
    )
    item = data["items"][0]
    assert item["status"] == "open"
    assert "Open" in (item.get("status_text") or "")


def test_build_business_list_marks_spotlight_row(monkeypatch) -> None:
    fixed = datetime(2026, 5, 28, 12, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr("app.chat.component_builders.now_lake_havasu", lambda: fixed)
    rows = _rows(
        {
            "name": "Sponsored Plumber",
            "slug": "sponsored-plumber",
            "tier": "spotlight",
            "sponsored_until": fixed + timedelta(days=7),
            "google_rating": 4.5,
        },
        {
            "name": "Organic Plumber",
            "slug": "organic-plumber",
            "tier": "free",
            "sponsored_until": None,
            "google_rating": 4.7,
        },
    )
    data = build_business_list(rows, category="plumber", total_count=2)
    by_name = {it["name"]: it for it in data["items"]}
    assert by_name["Sponsored Plumber"].get("spotlight") is True
    assert "spotlight" not in by_name["Organic Plumber"]


def test_build_business_list_rotates_spotlight_to_top(monkeypatch) -> None:
    """Spotlight row lands at items[0] even when organic rating would rank it lower.

    Organic rows preserve rating-desc ordering in the remaining slots.
    BUILD.md step 7.5 phase B. Mockup: mockups/07-business-answer.html:511.
    """
    fixed = datetime(2026, 5, 28, 12, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr("app.chat.component_builders.now_lake_havasu", lambda: fixed)
    rows = _rows(
        {
            "name": "Top Organic",
            "slug": "top-organic",
            "tier": "free",
            "google_rating": 4.9,
        },
        {
            "name": "Mid Organic",
            "slug": "mid-organic",
            "tier": "free",
            "google_rating": 4.5,
        },
        {
            "name": "Sponsored Pick",
            "slug": "sponsored-pick",
            "tier": "spotlight",
            "sponsored_until": fixed + timedelta(days=30),
            "google_rating": 3.0,
        },
    )
    data = build_business_list(rows, category="plumber", total_count=3)
    names = [it["name"] for it in data["items"]]
    assert names == ["Sponsored Pick", "Top Organic", "Mid Organic"]
    assert data["items"][0].get("spotlight") is True
    # Disclosure still emitted (Phase A behavior, preserved).
    assert data.get("disclosure") is True


def test_build_business_list_emits_disclosure_when_spotlight_present(
    monkeypatch,
) -> None:
    fixed = datetime(2026, 5, 28, 12, 0, tzinfo=ZoneInfo("America/Phoenix"))
    monkeypatch.setattr("app.chat.component_builders.now_lake_havasu", lambda: fixed)
    spotlight_row = {
        "name": "Spot Pros",
        "slug": "spot-pros",
        "tier": "spotlight",
        "sponsored_until": fixed + timedelta(days=7),
        "google_rating": 4.5,
    }
    organic_row = {
        "name": "Free Plumber",
        "slug": "free-plumber",
        "tier": "free",
        "sponsored_until": None,
        "google_rating": 4.0,
    }
    with_spotlight = build_business_list(
        _rows(spotlight_row, organic_row), category="plumber", total_count=2
    )
    assert with_spotlight["disclosure"] is True

    organic_only = build_business_list(
        _rows(organic_row), category="plumber", total_count=1
    )
    assert "disclosure" not in organic_only


def test_build_business_list_caps_at_five() -> None:
    rows = _rows(*[{"name": f"Shop {i}", "slug": f"shop-{i}"} for i in range(12)])
    data = build_business_list(rows, category="mechanic", total_count=12)
    assert len(data["items"]) == 5
    assert data["total_count"] == 12


def test_build_business_list_strips_pipe_marketing_tail_from_name() -> None:
    """CLUSTER-08 name hygiene.

    Provider rows from Google Places sometimes carry vendor marketing copy
    after a pipe character (e.g. "Havasu Hills Apartment Homes | An
    AllThrive 365 Affordable Housing Property"). The chat business_list
    payload must carry the clean prefix only so the front-end renderer
    never has to know about this.
    """
    rows = _rows(
        {
            "name": "Foo | Bar Marketing Copy",
            "slug": "foo",
            "google_rating": 4.5,
        },
        {
            "name": "Havasu Hills Apartment Homes | An AllThrive 365 Property",
            "slug": "havasu-hills",
            "google_rating": 4.2,
        },
    )
    data = build_business_list(rows, category="apartment", total_count=2)
    names = [it["name"] for it in data["items"]]
    assert "Foo" in names
    assert "Havasu Hills Apartment Homes" in names
    # Sanity: no pipe leaked through into the payload at all.
    for item in data["items"]:
        assert "|" not in item["name"]


def test_render_business_listing_with_component() -> None:
    from app.chat import tier2_business_shortcut as shortcut

    rows = _rows(
        {
            "name": "Pipe Pros",
            "slug": "pipe-pros",
            "phone": "928-555-0100",
            "address": "100 Main St",
            "google_rating": 4.8,
        }
    )
    out = shortcut.render_business_listing_with_component(rows, "plumber")
    assert out is not None
    voice, comp = out
    assert "plumbers" in voice.lower()
    assert comp["items"][0]["url"] == "/provider/pipe-pros"


def test_tier2_handler_populates_component_meta() -> None:
    from unittest.mock import patch

    from app.chat.tier2_handler import try_tier2_with_usage

    rows = _rows(
        {
            "name": "Pipe Pros",
            "slug": "pipe-pros",
            "phone": "928-555-0100",
            "address": "100 Main St",
            "google_rating": 4.8,
        }
    )
    component_meta: dict = {}
    with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows):
        text, total, _, _ = try_tier2_with_usage(
            "find a plumber", component_meta=component_meta
        )
    assert text is not None
    assert total == 0
    assert component_meta.get("type") == "business_list"
    assert component_meta["data"]["items"][0]["name"] == "Pipe Pros"
