"""Phase 8b — Layer 3 civic scraper unit tests (mocked HTML)."""

from __future__ import annotations

import pytest

from scripts.ingest.lhc_civic_scrape import (
    build_scraper_records,
    parse_airnav_html,
    parse_airport_city_html,
    parse_library_html,
    parse_transit_html,
)

LIBRARY_FIXTURE = """
<html><body>
<h1>Lake Havasu City Library</h1>
<p>Phone (928) 453-0718</p>
<p>Monday: 9:00 AM - 7:00 PM</p>
<p>Tuesday: 9:00 AM - 7:00 PM</p>
<p>Wednesday: 9:00 AM - 7:00 PM</p>
</body></html>
"""

TRANSIT_FIXTURE = """
<html><body>
<h1>Havasu Hopper Transit</h1>
<p>Route schedule and fares for public transit.</p>
<p>Call (928) 453-4141</p>
</body></html>
"""

AIRPORT_FIXTURE = """
<html><body>
<h1>Lake Havasu City Airport KHII</h1>
<p>General aviation airport serving the city.</p>
<p>(928) 764-3330</p>
</body></html>
"""

AIRNAV_FIXTURE = """
<html><body>
<h1>KHII / Lake Havasu City Airport</h1>
<p>Elevation: 783 ft</p>
</body></html>
"""


def test_parse_library_extracts_hours_and_phone() -> None:
    rec = parse_library_html(LIBRARY_FIXTURE)
    assert rec.name.startswith("Mohave County Library")
    assert rec.entity_type == "place"
    assert rec.sub_category == "library"
    assert rec.phone is not None
    assert "Monday" in (rec.hours_text or "")
    assert rec.parse_fallback is False


def test_parse_library_fallback_on_empty_html() -> None:
    rec = parse_library_html("")
    assert rec.parse_fallback is True
    assert rec.hours_text is not None


def test_parse_transit_returns_three_entities() -> None:
    rows = parse_transit_html(TRANSIT_FIXTURE)
    assert len(rows) == 3
    assert all(r.sub_category == "transit" for r in rows)
    assert any("Havasu Hopper Transit" == r.name for r in rows)


def test_parse_airport_city_html() -> None:
    rec = parse_airport_city_html(AIRPORT_FIXTURE)
    assert "KHII" in rec.name
    assert rec.sub_category == "airport"
    assert rec.parse_fallback is False


def test_parse_airnav_html_elevation() -> None:
    rec = parse_airnav_html(AIRNAV_FIXTURE)
    assert "783" in (rec.description or "")
    assert rec.website is not None


def test_build_scraper_records_mocks_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "library": LIBRARY_FIXTURE,
        "transit": TRANSIT_FIXTURE,
        "airport": AIRPORT_FIXTURE,
        "airnav": AIRNAV_FIXTURE,
    }

    def fake_fetch(url: str) -> str:
        if "mohavecountylibrary" in url:
            return pages["library"]
        if "lhcaz.gov/transit" in url:
            return pages["transit"]
        if "lhcaz.gov/government/airport" in url:
            return pages["airport"]
        if "airnav.com" in url:
            return pages["airnav"]
        return ""

    records = build_scraper_records(source="all", fetch_html=fake_fetch)
    assert len(records) >= 5
    sub_cats = {r.sub_category for r in records}
    assert "library" in sub_cats
    assert "transit" in sub_cats
    assert "airport" in sub_cats


def test_build_scraper_records_library_only() -> None:
    records = build_scraper_records(
        source="library",
        fetch_html=lambda _url: LIBRARY_FIXTURE,
    )
    assert len(records) == 1
    assert records[0].sub_category == "library"


def test_scraper_entity_shape_keys() -> None:
    rec = parse_library_html(LIBRARY_FIXTURE)
    assert rec.name
    assert rec.address
    assert rec.entity_type == "place"
