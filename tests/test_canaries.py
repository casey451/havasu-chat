"""A4: canary listings — off-site detection + exclusion from counts/sitemap."""

from __future__ import annotations

from uuid import uuid4

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.monitoring.canaries import CANARIES, CANARY_SOURCE, canary_phrases
from app.monitoring.canary_scanner import (
    find_canary_hits,
    format_canary_report,
    scan_for_leaks,
)

# ---------------------------------------------------------------------------
# Off-site scanner (pure core — no network)
# ---------------------------------------------------------------------------


def test_find_canary_hits_detects_phrase_whitespace_insensitive() -> None:
    phrase = CANARIES[0].unique_phrase
    # Simulate a scraped copy: re-wrapped lines + doubled spaces + extra markup text.
    page = f"<p>Welcome.</p>  {phrase.replace(' ', '   ')}\n\nCall us today."
    hits = find_canary_hits(page, "https://havasu.info/biz")
    assert len(hits) == 1
    assert hits[0].canary_slug == CANARIES[0].slug
    assert hits[0].url == "https://havasu.info/biz"


def test_find_canary_hits_no_false_positive() -> None:
    page = "An ordinary directory page about Lake Havasu businesses and events."
    assert find_canary_hits(page, "https://havasu.info/") == []


def test_scan_for_leaks_uses_injected_fetcher() -> None:
    leaking = {"https://havasu.info/": CANARIES[1].unique_phrase, "https://other/": "clean"}
    hits = scan_for_leaks(
        ("https://havasu.info/", "https://other/"),
        fetcher=lambda url: leaking.get(url, ""),
    )
    assert len(hits) == 1
    assert hits[0].url == "https://havasu.info/"
    assert hits[0].canary_slug == CANARIES[1].slug


def test_scan_for_leaks_clean_when_nothing_matches() -> None:
    hits = scan_for_leaks(("https://havasu.info/",), fetcher=lambda url: "nothing here")
    assert hits == []
    subject, _ = format_canary_report(hits)
    assert "no copies" in subject.lower()


def test_format_report_flags_hits() -> None:
    hits = scan_for_leaks(("https://havasu.info/",), fetcher=lambda url: canary_phrases()[0])
    subject, body = format_canary_report(hits)
    assert "canary copy detected" in subject.lower()
    assert CANARIES[0].name in body


# ---------------------------------------------------------------------------
# Exclusion from counts + sitemap
# ---------------------------------------------------------------------------


def _mk_provider(db, *, primary_category: str, source: str) -> str:
    ent = Entity(
        entity_type="commercial",
        slug=f"canary-test-ent-{uuid4().hex[:8]}",
        name="Canary Test Entity",
        source=source,
    )
    db.add(ent)
    db.flush()
    prov = Provider(
        provider_name="Canary Test Provider",
        category="x",
        primary_category=primary_category,
        slug=f"canary-test-{uuid4().hex[:8]}",
        is_active=True,
        draft=False,
        source=source,
        entity_id=ent.id,
    )
    db.add(prov)
    db.flush()
    return prov.slug


def test_canary_not_counted_in_category_listing_count() -> None:
    from app.categories.queries import category_listing_count

    cat = f"test-canary-cat-{uuid4().hex[:6]}"
    with SessionLocal() as db:
        assert category_listing_count(db, {cat}) == 0  # isolated, made-up category
        _mk_provider(db, primary_category=cat, source="test-canary-real")
        _mk_provider(db, primary_category=cat, source=CANARY_SOURCE)
        db.commit()
    with SessionLocal() as db:
        # Only the real provider counts; the canary is excluded.
        assert category_listing_count(db, {cat}) == 1


def test_canary_excluded_from_provider_sitemap() -> None:
    from app import main as main_module

    with SessionLocal() as db:
        real_slug = _mk_provider(db, primary_category="x", source="test-canary-real")
        canary_slug = _mk_provider(db, primary_category="x", source=CANARY_SOURCE)
        db.commit()
    main_module._sitemap_cache.clear()
    xml = main_module._build_sitemap_providers_xml()
    main_module._sitemap_cache.clear()
    assert f"/provider/{real_slug}" in xml
    assert f"/provider/{canary_slug}" not in xml
