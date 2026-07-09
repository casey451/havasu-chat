"""/map category-scope tab labels are sourced from the canonical department
labels (Phase 3.2, FIX_SPEC_2026-06-23).

The map scope SLUGS are the legacy tier-1 ids (markers API untouched), but the
displayed tab labels now come from ``display_labels.map_scope_label`` so a
category reads IDENTICALLY on /map, the directory, and the home grid. This
replaced a hand-kept map-only label set that had drifted ("Lake Life" vs
"Lake & Boating", "Outdoors & Recreation" vs "Things to Do").

Note: the THEMED-group tabs are separate (``group_label``) and still carry their
own names (e.g. the "Lake Life" themed group), so those strings can legitimately
appear elsewhere on the page — these assertions target the category-scope labels.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_map_category_scope_labels_match_directory() -> None:
    body = client.get("/map").text
    # Jinja autoescapes the ampersand, so assert the rendered ``&amp;`` form.
    for label in (
        "Eat &amp; Drink",
        "Lake &amp; Boating",        # on-the-water (was "Lake Life" on the map)
        "Things to Do",              # outdoors-parks-trails (was "Outdoors & Recreation")
        "Fitness &amp; Classes",     # classes-sports-recreation (was "Fitness, Sports & Classes")
        "Health &amp; Medical",
        "City &amp; Government",     # public-civic-resources (was "Community & Civic")
        "Pets &amp; Vets",
        "Home Services",
        "Auto &amp; Boat Service",   # auto-rv-fuel (was "Auto, RV & Fuel")
        "Places to Stay",            # lodging-vacation-rentals (was "Lodging")
    ):
        assert label in body, label


def test_map_no_stale_category_scope_labels() -> None:
    body = client.get("/map").text
    # The pre-unification map-only labels and retired canonical names must be
    # gone from the category-scope tabs. (NOT "Lake Life" — that's the themed
    # group's own label, which legitimately remains.)
    for stale in (
        "Outdoors &amp; Recreation",
        "Community &amp; Civic",
        "Shopping &amp; Retail",
        "Fitness, Sports &amp; Classes",
        "Auto, RV &amp; Fuel",
        "Auto, RV &amp; Marine",
        "Fitness &amp; Wellness",
        "Health, Wellness &amp; Care",
        "Outdoors, Parks &amp; Trails",
        "Public &amp; Civic Resources",
        "Shopping, Grocery &amp; Essentials",
        "Lodging &amp; Vacation Rentals",
    ):
        assert stale not in body, stale


def test_map_still_renders() -> None:
    r = client.get("/map")
    assert r.status_code == 200
    # Scope slugs unchanged — a known category scope still drives the map.
    assert "auto-rv-fuel" in r.text
