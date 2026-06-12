"""Label standardization (fixlist §7.5) + 2026-06-12 taxonomy reconciliation.

The /map category-scope tabs carry one canonical label per slug. Three slugs
were unified on 2026-06-12 so their map tab now matches ``CATEGORY_LABELS``:
``auto-rv-fuel`` → "Auto, RV & Fuel" (was "… & Marine"), ``classes-sports-
recreation`` → "Fitness, Sports & Classes" (was "Fitness & Wellness"), and
``health-wellness-care`` → "Health & Medical". The remaining tabs still carry
the shorter 15-department directory names pending the B3 rebuild. Scope slugs
are unchanged (markers API untouched) — this is presentation only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_map_scope_labels_present() -> None:
    body = client.get("/map").text
    # Jinja autoescapes the ampersand, so assert the rendered ``&amp;`` form.
    for label in (
        "Auto, RV &amp; Fuel",            # reconciled 2026-06-12 (was "… & Marine")
        "Fitness, Sports &amp; Classes",  # reconciled 2026-06-12 (was "Fitness & Wellness")
        "Health &amp; Medical",           # canonical + map now agree
        "Outdoors &amp; Recreation",      # still the directory dept name (pending B3)
        "Community &amp; Civic",
        "Shopping &amp; Retail",
    ):
        assert label in body, label


def test_map_no_stale_scope_labels() -> None:
    body = client.get("/map").text
    # Pre-reconciliation map labels and the now-retired canonical labels must be
    # gone from the map tabs; the diverging canonical labels for the not-yet-
    # unified rows are still not shown on the map (the map uses dept names there).
    for stale in (
        "Auto, RV &amp; Marine",             # old map label, replaced
        "Fitness &amp; Wellness",            # old map label, replaced
        "Classes, Sports &amp; Recreation",  # retired canonical (renamed)
        "Health, Wellness &amp; Care",       # retired canonical (renamed)
        "Outdoors, Parks &amp; Trails",      # canonical for a still-diverging row
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
