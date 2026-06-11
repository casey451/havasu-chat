"""Label standardization (fixlist §7.5): the /map category-scope tabs carry the
canonical directory DEPARTMENT names, not the legacy flat-bucket labels. The
scope slugs are unchanged (markers API untouched) — this is presentation only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_map_scope_labels_use_department_names() -> None:
    body = client.get("/map").text
    # Department-aligned names users see in the nav/directory. Jinja autoescapes
    # the ampersand, so assert against the rendered ``&amp;`` form.
    for label in (
        "Auto, RV &amp; Marine",
        "Fitness &amp; Wellness",
        "Outdoors &amp; Recreation",
        "Community &amp; Civic",
        "Health &amp; Medical",
        "Shopping &amp; Retail",
    ):
        assert label in body, label


def test_map_no_legacy_scope_labels() -> None:
    body = client.get("/map").text
    # The old flat-bucket labels must be gone from the map tabs (rendered form).
    for legacy in (
        "Auto, RV &amp; Fuel",
        "Classes, Sports &amp; Recreation",
        "Outdoors, Parks &amp; Trails",
        "Public &amp; Civic Resources",
        "Health, Wellness &amp; Care",
        "Shopping, Grocery &amp; Essentials",
        "Lodging &amp; Vacation Rentals",
    ):
        assert legacy not in body, legacy


def test_map_still_renders() -> None:
    r = client.get("/map")
    assert r.status_code == 200
    # Scope slugs unchanged — a known category scope still drives the map.
    assert "auto-rv-fuel" in r.text
