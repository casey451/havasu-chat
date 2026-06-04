"""Group E business/community scrapers (source-expansion #19-24). No live HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contrib import (
    chamber_directory,
    downtown_lhc,
    food_inspections,
    p2c_bulletin,
    reddit_havasu,
    zillow_research,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ----- food_inspections (#19) ----------------------------------------------


def test_food_discover_pdf_links() -> None:
    html = (FIXTURES / "food_inspections" / "index.html").read_text(encoding="utf-8")
    links = food_inspections.discover_pdf_links(html)
    assert len(links) == 2
    assert all("food-safety-inspections_" in link for link in links)
    assert links[0].startswith("https://www.mohave.gov/")


def test_food_parse_rows_filters_to_lake_havasu() -> None:
    rows = [
        ["Establishment", "Address", "City", "Inspection Date", "Result"],
        ["Joe's Diner", "100 Main St", "Lake Havasu City", "2026-04-10", "Pass"],
        ["Phoenix Grill", "200 Central Ave", "Phoenix", "2026-04-11", "Pass"],
        ["Lakeside Cafe", "300 Lake Ave", "Lake Havasu City", "2026-04-12", "Conditional"],
        ["", "", "", "", ""],
    ]
    records = food_inspections.parse_inspection_rows(rows)
    names = [r.establishment for r in records]
    assert names == ["Joe's Diner", "Lakeside Cafe"]  # Phoenix filtered, blank skipped
    assert records[0].inspection_date is not None
    assert records[0].name_slug == "joe-s-diner"


# ----- chamber_directory (#20) ---------------------------------------------


def test_chamber_parse_listing() -> None:
    html = (FIXTURES / "chamber" / "listing_a.html").read_text(encoding="utf-8")
    members = chamber_directory.parse_member_listing(html)
    assert len(members) == 2
    acme = members[0]
    assert acme.name == "Acme Plumbing LLC"
    assert acme.url.endswith("/member/acme-plumbing/")
    assert "Acoma" in (acme.address or "")
    assert acme.enrichment_signal()["chamber_member"] is True


# ----- reddit_havasu (#21) -------------------------------------------------


def test_reddit_parse_listing_snippet_and_mentions() -> None:
    payload = json.loads((FIXTURES / "reddit" / "new.json").read_text(encoding="utf-8"))
    posts = reddit_havasu.parse_listing(payload)
    assert len(posts) == 2
    first = posts[0]
    assert first.permalink.startswith("https://www.reddit.com/")
    assert first.snippet and "Avalon Auto" in first.snippet
    # Business mentions piped via mention_scanner.
    assert any("Avalon" in m for m in first.mentions)
    # Second post has empty selftext -> no snippet.
    assert posts[1].snippet is None


# ----- downtown_lhc (#22) --------------------------------------------------


def test_downtown_member_links_dedup_and_skip_events() -> None:
    html = (FIXTURES / "downtown" / "directory.html").read_text(encoding="utf-8")
    links = downtown_lhc.parse_member_links(html)
    assert len(links) == 2  # dupe collapsed, /events/ excluded
    assert all("/member/" in link for link in links)


def test_downtown_member_detail() -> None:
    html = (FIXTURES / "downtown" / "member.html").read_text(encoding="utf-8")
    member = downtown_lhc.parse_member_detail(html, "https://downtownlakehavasu.com/member/the-tap-room/")
    assert member is not None
    assert member.name == "The Tap Room"
    assert member.website == "https://thetaproomlhc.com"
    assert member.enrichment_signal()["downtown_member"] is True


# ----- zillow_research (#23) -----------------------------------------------


def test_zillow_parse_csv_latest_value() -> None:
    csv_text = (FIXTURES / "zillow" / "zhvi_city.csv").read_text(encoding="utf-8")
    stats = zillow_research.parse_csv(csv_text, metric="ZHVI")
    assert len(stats) == 1  # only Lake Havasu City kept
    s = stats[0]
    assert s.region_name == "Lake Havasu City"
    # 2026-04-30 is blank -> latest non-empty is 2026-03-31.
    assert s.latest_date == "2026-03-31"
    assert s.latest_value == 420500.0
    payload = zillow_research.build_cache_payload(stats)
    assert payload["attribution"] == "Zillow Research"
    assert payload["stats"][0]["value"] == 420500.0


# ----- p2c_bulletin (#24) --------------------------------------------------


def test_p2c_parse_bulletin_defensive() -> None:
    payload = {
        "data": [
            {"Type": "Arrest", "Date": "2026-06-04", "Description": "DUI on London Bridge Rd"},
            {"type": "incident", "DateTime": "2026-06-04 02:00", "description": "Noise complaint"},
        ]
    }
    entries = p2c_bulletin.parse_bulletin(payload)
    assert len(entries) == 2
    assert entries[0].entry_type == "Arrest"
    assert "DUI" in (entries[0].description or "")


# ----- CLI -----------------------------------------------------------------


def test_business_cli_apply_guarded() -> None:
    import scripts.business_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--source", "chamber", "--apply"])
    assert exc.value.code == 2
