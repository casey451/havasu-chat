"""Label standardization (fixlist §7.5): the /map category-scope tabs carry the
canonical directory DEPARTMENT names, not the legacy flat-bucket labels. The
scope slugs are unchanged (markers API untouched) — this is presentation only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_map_scope_labels_use_department_names() -> None:
    body = client.get("/map").text
    # Department-aligned names users see in the nav/directory.
    for label in (
        "Auto, RV & Marine",
        "Fitness & Wellness",
        "Outdoors & Recreation",
        "Community & Civic",
        "Health & Medical",
        "Shopping & Retail",
    ):
        assert label in body, label


def test_map_no_legacy_scope_labels() -> None:
    body = client.get("/map").text
    # The old flat-bucket labels must be gone from the map tabs.
    for legacy in (
        "Auto, RV & Fuel",
        "Classes, Sports & Recreation",
        "Outdoors, Parks & Trails",
        "Public & Civic Resources",
        "Health, Wellness & Care",
        "Shopping, Grocery & Essentials",
        "Lodging & Vacation Rentals",
    ):
        assert legacy not in body, legacy


def test_map_still_renders() -> None:
    r = client.get("/map")
    assert r.status_code == 200
    # Scope slugs unchanged — a known category scope still drives the map.
    assert "auto-rv-fuel" in r.text
