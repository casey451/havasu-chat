"""Phase 8b — cat-13 entity shapes and sub-category coverage."""

from __future__ import annotations

from scripts.ingest.lhc_civic_scrape import build_scraper_records
from scripts.seed_cat13_civic import SEED_ENTITIES

# Master plan Phase 8 sub-categories (8 buckets)
REQUIRED_SUB_CATEGORIES = frozenset({
    "library",
    "transit",
    "visitor_info",
    "utility",
    "airport",
    "senior_resource",
    "payment_licensing",
    "civic_org",
})


def test_all_seed_entities_use_place_type() -> None:
    for rec in SEED_ENTITIES:
        assert rec.entity_type == "place", rec.name


def test_scraper_entities_use_place_type() -> None:
    records = build_scraper_records(
        source="all",
        fetch_html=lambda _url: "<html><body>Monday: 9-5 route airport KHII</body></html>",
    )
    assert records
    for rec in records:
        assert rec.entity_type == "place", rec.name


def test_combined_sub_categories_cover_master_plan_buckets() -> None:
    scraper = build_scraper_records(
        source="all",
        fetch_html=lambda _url: "<html><body>Monday schedule route airport KHII Lake Havasu</body></html>",
    )
    subs = {r.sub_category for r in scraper if r.sub_category}
    subs |= {r.sub_category for r in SEED_ENTITIES if r.sub_category}
    assert REQUIRED_SUB_CATEGORIES <= subs


def test_seed_includes_chamber_and_visitor_bureau() -> None:
    names = {r.name for r in SEED_ENTITIES}
    assert any("Chamber" in n for n in names)
    assert any("Visitor" in n for n in names)


def test_seed_includes_utility_and_payment_portals() -> None:
    subs = [r.sub_category for r in SEED_ENTITIES]
    assert subs.count("utility") >= 3
    assert subs.count("payment_licensing") >= 2


def test_scraper_includes_library_and_transit() -> None:
    records = build_scraper_records(
        source="all",
        fetch_html=lambda _url: "<html><body>Monday: 9-5 Havasu Hopper route schedule airport KHII</body></html>",
    )
    subs = {r.sub_category for r in records}
    assert "library" in subs
    assert "transit" in subs
    assert "airport" in subs
