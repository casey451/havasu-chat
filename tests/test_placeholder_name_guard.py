"""T1.3 — placeholder-name ingest guard (2026-07-06).

Bare geographies, lead-gen funnels, and CMS template stubs are not real
businesses. ``is_placeholder_name`` flags them and ``decide_ingest`` skips them
(no insert, no reactivation) so a re-scrape can't keep minting junk rows. The
guard is deliberately tight — a real business must never be rejected.
"""

from __future__ import annotations

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_suppression import is_placeholder_name


def test_placeholder_names_are_flagged() -> None:
    for name in (
        "Lake Havasu City",
        "lake havasu city",
        "Lake Havasu",
        "My Website Store",
        "Get Free Solar Estimate",
        "get-free-solar-estimate",  # slug form folds to the same normalized name
        "Kids Activities Studio",
        "Get A Free Roofing Quote",
        "Free Estimate",
        "Coming Soon",
    ):
        assert is_placeholder_name(name), name


def test_real_businesses_are_not_flagged() -> None:
    for name in (
        "Lake Havasu City Aquatic Center",  # bare-city is EXACT-match only
        "Lake Havasu Golf Club",
        "My Website Store & Cafe",  # not the bare CMS stub
        "Free Spirit Boat Rentals",  # 'free' as a real brand word
        "Havasu Solar Solutions",
        "Estimate Masters Drywall",
        "",
        None,  # type: ignore[arg-type]
    ):
        assert not is_placeholder_name(name), name


def test_decide_ingest_skips_a_placeholder_payload() -> None:
    # decide_ingest short-circuits on the guard BEFORE any DB reconcile, so we can
    # pass db=None: a placeholder name must never reach reconcile_hit.
    from app.contrib.scraper_ingest import decide_ingest

    payload = EntityPayload(
        name="Get Free Solar Estimate",
        entity_type="place",
        lat=None,
        lng=None,
        address=None,
        phone=None,
        website="https://www.ownwatts.com/contact/",
        description=None,
        category_slug="home-property-services",
        legacy_category="home_services",
        google_place_id=None,
        source="google_places",
    )
    decision = decide_ingest(None, payload)  # type: ignore[arg-type]
    assert decision.action == "skip"
    assert decision.existing_id is None
    assert "placeholder" in (decision.reason or "")
