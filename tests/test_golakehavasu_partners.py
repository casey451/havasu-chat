"""golakehavasu partner directory -- sitemap + listing parse + payload map."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.contrib.golakehavasu import SITEMAP_INDEX_URL
from app.contrib.golakehavasu_partners import (
    CVB_PRIMARY_CATEGORY_TO_LEGACY,
    CVB_PRIMARY_CATEGORY_TO_SLUG,
    fetch_and_parse_partner,
    fetch_partner_sitemap_urls,
    map_cvb_category,
    map_cvb_legacy_category,
    partner_to_entity_payload,
)
from app.contrib.ingest_base import EntityPayload
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug
from scripts.golakehavasu_partners_load import (
    FUZZY_NAME_THRESHOLD,
    _contact_match,
    _fuzzy_geo_match,
    _norm_phone,
    _provider_to_payload,
)


@pytest.fixture
def db_session():
    """Transactional session for the fuzzy-match tests; rolled back after each."""
    with SessionLocal() as session:
        yield session
        session.rollback()


FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"
PARTNERS_SITEMAP_URL = (
    "https://www.golakehavasu.com/sitemaps-1-section-partnerDirectory-1-sitemap-p1.xml"
)
LOBSTER_URL = "https://www.golakehavasu.com/directory/lobster-3-ways/"
HEAT_URL = "https://www.golakehavasu.com/directory/heat-hotel-resorts/"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_polite_sleep():
    with patch("app.contrib.golakehavasu._sleep_polite"):
        yield


def _mock_client() -> httpx.Client:
    routes = {
        SITEMAP_INDEX_URL: _fixture("golakehavasu_sitemap_index.xml"),
        PARTNERS_SITEMAP_URL: _fixture("golakehavasu_partners_sitemap.xml"),
        LOBSTER_URL: _fixture("golakehavasu_partner_detail.html"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url))
        if body is None:
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_partner_sitemap_urls_follows_partner_children() -> None:
    with _mock_client() as client:
        urls = fetch_partner_sitemap_urls(client=client)
    assert urls == [LOBSTER_URL, HEAT_URL]


def test_parse_partner_listing() -> None:
    with _mock_client() as client:
        listing = fetch_and_parse_partner(LOBSTER_URL, client=client)
    assert listing is not None
    assert listing.name == "Lobster 3 Ways"
    assert listing.address == "201 Swanson Ave, Lake Havasu City, AZ 86403"
    assert listing.phone == "(702) 787-9568"
    assert listing.website == "http://www.lobster3ways.com"
    assert listing.lat == pytest.approx(34.4682917)
    assert listing.lng == pytest.approx(-114.3421794)
    assert listing.description and "lobster" in listing.description.lower()


def test_partner_to_entity_payload_source_and_category() -> None:
    with _mock_client() as client:
        listing = fetch_and_parse_partner(LOBSTER_URL, client=client)
    assert listing is not None
    payload = partner_to_entity_payload(listing, category_slug="things-to-do")
    assert payload.source == "go_lake_havasu"
    assert payload.entity_type == "place"
    # Lobster 3 Ways is data-dms-category-name="Restaurant/Bar" -> eat-drink,
    # which overrides the passed default of things-to-do (Task C).
    assert payload.category_slug == "eat-drink"
    # Dual-write: the legacy Provider.category string is also set, and it is a
    # value the legacy CATEGORY_FILTERS["eat-drink"] tuple contains.
    assert payload.legacy_category == "restaurant"
    assert payload.lat == pytest.approx(34.4682917)
    assert payload.website == "http://www.lobster3ways.com"


# --- Task C: per-listing category parse + CVB->Hava mapping -----------------
def test_parse_partner_reads_primary_category() -> None:
    with _mock_client() as client:
        listing = fetch_and_parse_partner(LOBSTER_URL, client=client)
    assert listing is not None
    assert listing.category == "Restaurant/Bar"


def test_map_cvb_category_known_and_case_insensitive() -> None:
    assert map_cvb_category("Restaurant/Bar") == "eat-drink"
    assert map_cvb_category("  restaurant/bar  ") == "eat-drink"
    assert map_cvb_category("Lodging") == "lodging-vacation-rentals"
    assert map_cvb_category("Resorts") == "lodging-vacation-rentals"
    assert map_cvb_category("Boating") == "on-the-water"
    assert map_cvb_category("Golf") == "classes-sports-recreation"
    assert map_cvb_category("Shopping") == "shopping-essentials"


def test_map_cvb_legacy_category_known_and_case_insensitive() -> None:
    assert map_cvb_legacy_category("Restaurant/Bar") == "restaurant"
    assert map_cvb_legacy_category("  restaurant/bar  ") == "restaurant"
    assert map_cvb_legacy_category("Lodging") == "lodging"
    assert map_cvb_legacy_category("Resorts") == "lodging"
    assert map_cvb_legacy_category("Boating") == "boat_rental"
    assert map_cvb_legacy_category("Shopping") == "retail"
    assert map_cvb_legacy_category("Events") == "event_venue"


def test_map_cvb_legacy_category_unmapped_returns_none() -> None:
    # Attractions / Guided Tour are now mapped (see attractions test above);
    # only genuinely ambiguous / geographic categories remain unmapped.
    for unmapped in ("Rentals", "Transportation", "Kingman", "Misc", "", None):
        assert map_cvb_legacy_category(unmapped) is None


def test_cvb_legacy_values_are_accepted_by_category_filters() -> None:
    """Every legacy string we write must be matchable by at least one legacy
    category-page route (app/categories/queries.py CATEGORY_FILTERS)."""
    from app.categories.queries import CATEGORY_FILTERS

    accepted = {s for slugs in CATEGORY_FILTERS.values() for s in slugs}
    # event_venue is an Events label not present in CATEGORY_FILTERS (events are
    # a separate surface), so exclude it from this page-route assertion.
    page_routed = set(CVB_PRIMARY_CATEGORY_TO_LEGACY.values()) - {"event_venue"}
    assert page_routed <= accepted, page_routed - accepted


def test_map_cvb_category_attractions_family_tours() -> None:
    # Attractions / family-fun / tours / entertainment have no dedicated Tier-1
    # category, so they map to the closest seeded bucket (classes-sports-
    # recreation) and route to the attractions legacy page via the legacy string.
    assert map_cvb_category("Attractions") == "classes-sports-recreation"
    assert map_cvb_category("Family-Fun") == "classes-sports-recreation"
    assert map_cvb_category("Family Fun") == "classes-sports-recreation"
    assert map_cvb_category("Guided Tour") == "classes-sports-recreation"
    assert map_cvb_category("Entertainment") == "classes-sports-recreation"
    assert map_cvb_legacy_category("Attractions") == "entertainment_attractions"
    assert map_cvb_legacy_category("Guided Tour") == "tourism"


def test_map_cvb_category_unmapped_returns_none() -> None:
    # Genuinely ambiguous or geographic CVB categories stay unmapped so the
    # loader falls back to its --category-slug default.
    for unmapped in ("Rentals", "Transportation", "Kingman", "Misc", "", None):
        assert map_cvb_category(unmapped) is None


def test_partner_to_entity_payload_falls_back_when_unmapped() -> None:
    from app.contrib.golakehavasu_partners import PartnerListing

    listing = PartnerListing(
        name="Some Rental Co",
        url="https://www.golakehavasu.com/directory/some-rental-co/",
        address=None,
        lat=None,
        lng=None,
        phone=None,
        website=None,
        description=None,
        category="Rentals",  # genuinely ambiguous -> not in the confident map
    )
    payload = partner_to_entity_payload(listing, category_slug="things-to-do")
    assert payload.category_slug == "things-to-do"


def test_cvb_category_map_values_are_known_tier1_slugs() -> None:
    valid = {
        "eat-drink",
        "on-the-water",
        "home-property-services",
        "health-wellness-care",
        "auto-rv-fuel",
        "shopping-essentials",
        "events",
        "outdoors-parks-trails",
        "classes-sports-recreation",
        "lodging-vacation-rentals",
        "pets",
        "public-civic-resources",
    }
    assert set(CVB_PRIMARY_CATEGORY_TO_SLUG.values()) <= valid


def test_norm_web_idempotency_key() -> None:
    from scripts.golakehavasu_partners_load import _norm_web

    assert _norm_web("https://www.Lobster3Ways.com/") == "lobster3ways.com"
    assert _norm_web("http://lobster3ways.com") == "lobster3ways.com"
    assert _norm_web("https://www.lobster3ways.com") == _norm_web("http://lobster3ways.com/")
    assert _norm_web(None) is None
    assert _norm_web("   ") is None


def test_pick_canonical_prefers_live_over_draft() -> None:
    from app.db.models import Provider
    from scripts.golakehavasu_partners_load import _pick_canonical

    draft = Provider(
        provider_name="X", category="things-to-do", slug="x-draft", draft=True, is_active=False
    )
    live = Provider(
        provider_name="X", category="things-to-do", slug="x-live", draft=False, is_active=True
    )
    assert _pick_canonical([draft, live]) is live
    assert _pick_canonical([draft]) is draft


# --- Task A: fuzzy-name-at-geo merge ----------------------------------------
# Lake Havasu City civic-center-ish anchor used as the shared coordinate.
_LAT = 34.4839
_LNG = -114.3225


def _fuzzy_payload(
    name: str,
    *,
    lat: float | None = _LAT,
    lng: float | None = _LNG,
) -> EntityPayload:
    return EntityPayload(
        name=name,
        entity_type="place",
        source="go_lake_havasu",
        lat=lat,
        lng=lng,
        category_slug="things-to-do",
    )


def _google_provider(
    session,
    name: str,
    *,
    lat: float = _LAT,
    lng: float = _LNG,
    website: str | None = None,
    phone: str | None = None,
) -> Provider:
    """Create a Google-backed Provider (+ Entity + Location via dual-write).

    Mirrors tests/test_ingest_reconciler.py: the before_flush hook promotes the
    Provider to an Entity and a Location carrying ``google_place_id``, which is
    exactly what ``_fuzzy_geo_match`` queries.
    """
    prov = Provider(
        provider_name=name,
        category="eat-drink",
        slug=derive_provider_slug(session, name),
        source="google_places",
        google_place_id=f"ChIJ-{uuid.uuid4().hex[:16]}",
        lat=lat,
        lng=lng,
        website=website,
        phone=phone,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.flush()
    return prov


def test_fuzzy_geo_match_merges_close_name_at_geo(db_session) -> None:
    # token_sort_ratio("london bridge resort and spa",
    #                  "london bridge resort & spa") ~= 92 (>= 88 floor).
    prov = _google_provider(db_session, "London Bridge Resort & Spa")
    payload = _fuzzy_payload("London Bridge Resort and Spa")
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) == prov.entity_id


def test_fuzzy_geo_match_below_threshold_returns_none(db_session) -> None:
    _google_provider(db_session, "London Bridge Resort & Spa")
    payload = _fuzzy_payload("Joe's Tacos")  # nothing in common -> low ratio
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) is None


def test_fuzzy_geo_match_outside_radius_returns_none(db_session) -> None:
    # Strong name match but ~1.1 km away (0.01 deg lat) -> beyond 50m radius.
    _google_provider(db_session, "London Bridge Resort & Spa", lat=_LAT + 0.01)
    payload = _fuzzy_payload("London Bridge Resort and Spa")
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) is None


def test_fuzzy_geo_match_multiple_candidates_returns_none(db_session) -> None:
    # Two distinct Google entities at the same point both clear the floor
    # (one exact at 100, one ~92) -> ambiguous -> stay pending.
    _google_provider(db_session, "Lake Havasu Marina")
    _google_provider(db_session, "Lake Havasu Marina Co")
    payload = _fuzzy_payload("Lake Havasu Marina")
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) is None


def test_fuzzy_geo_match_ignores_non_google_rows(db_session) -> None:
    # Nearby, name-matching provider but NO google_place_id -> not a candidate.
    prov = Provider(
        provider_name="London Bridge Resort & Spa",
        category="lodging-vacation-rentals",
        slug=derive_provider_slug(db_session, "London Bridge Resort OSM"),
        source="osm",
        google_place_id=None,
        lat=_LAT,
        lng=_LNG,
        draft=False,
        is_active=True,
    )
    db_session.add(prov)
    create_provider_and_entity(db_session, prov)
    db_session.flush()
    payload = _fuzzy_payload("London Bridge Resort and Spa")
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) is None


def test_fuzzy_geo_match_requires_payload_coords(db_session) -> None:
    _google_provider(db_session, "London Bridge Resort & Spa")
    payload = _fuzzy_payload("London Bridge Resort and Spa", lat=None, lng=None)
    assert _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD) is None


def test_provider_to_payload_maps_fields() -> None:
    prov = Provider(
        provider_name="X Cafe",
        category="eat-drink",
        slug="x-cafe",
        lat=_LAT,
        lng=_LNG,
        address="1 Main St",
        phone="555-0000",
        website="http://x.example",
        description="desc",
    )
    payload = _provider_to_payload(prov)
    assert payload.name == "X Cafe"
    assert payload.source == "go_lake_havasu"
    assert payload.lat == _LAT and payload.lng == _LNG
    assert payload.category_slug == "eat-drink"
    assert payload.google_place_id is None


def test_norm_phone_variants() -> None:
    assert _norm_phone("(702) 787-9568") == "7027879568"
    assert _norm_phone("+1 702-787-9568") == "7027879568"
    assert _norm_phone("1.702.787.9568") == "7027879568"
    assert _norm_phone("787-9568") is None
    assert _norm_phone(None) is None


def test_contact_match_on_website_ignores_geo(db_session) -> None:
    prov = _google_provider(
        db_session, "Lobster 3 Ways Food Truck", website="http://www.lobster3ways.com"
    )
    payload = EntityPayload(
        name="Lobster 3 Ways",
        entity_type="place",
        source="go_lake_havasu",
        lat=None,
        lng=None,
        website="https://lobster3ways.com/",
        category_slug="eat-drink",
    )
    assert _contact_match(db_session, payload) == prov.entity_id


def test_contact_match_on_phone(db_session) -> None:
    prov = _google_provider(db_session, "Barley Brothers Brewery", phone="(928) 505-7837")
    payload = EntityPayload(
        name="Barley Brothers Restaurant & Brewery",
        entity_type="place",
        source="go_lake_havasu",
        phone="928-505-7837",
        category_slug="eat-drink",
    )
    assert _contact_match(db_session, payload) == prov.entity_id


def test_contact_match_ambiguous_website_returns_none(db_session) -> None:
    _google_provider(db_session, "Plaza Unit A", website="http://sharedplaza.com")
    _google_provider(db_session, "Plaza Unit B", website="http://sharedplaza.com")
    payload = EntityPayload(
        name="Plaza Tenant",
        entity_type="place",
        source="go_lake_havasu",
        website="http://sharedplaza.com",
        category_slug="eat-drink",
    )
    assert _contact_match(db_session, payload) is None


def test_contact_match_no_contact_fields_returns_none(db_session) -> None:
    _google_provider(db_session, "Some Place", website="http://example.com")
    payload = EntityPayload(name="Some Place", entity_type="place", source="go_lake_havasu")
    assert _contact_match(db_session, payload) is None


def test_contact_match_ignores_non_google_rows(db_session) -> None:
    prov = Provider(
        provider_name="OSM Cafe",
        category="eat-drink",
        slug=derive_provider_slug(db_session, "OSM Cafe"),
        source="osm",
        google_place_id=None,
        website="http://osmcafe.com",
        draft=False,
        is_active=True,
    )
    db_session.add(prov)
    create_provider_and_entity(db_session, prov)
    db_session.flush()
    payload = EntityPayload(
        name="OSM Cafe",
        entity_type="place",
        source="go_lake_havasu",
        website="http://osmcafe.com",
        category_slug="eat-drink",
    )
    assert _contact_match(db_session, payload) is None


# --- in-batch idempotency (regression for the same-source 0.0m self-dups) ----
def test_ingest_partners_dedupes_same_name_within_one_run(monkeypatch) -> None:
    """Two partner URLs for the SAME business in one run yield ONE row.

    The CVB sitemap lists some businesses under multiple URLs; the loader's
    idempotency snapshot was built once before the payload loop, so the second
    payload could not see the row the first had just inserted and inserted a
    duplicate -- and geo could not catch it because both carried the
    visitor-center coords (0.0m apart). _register_cvb closes that window. This
    is the source of the 58 same-source geo+name self-dups the cross-source
    audit surfaced.
    """
    import scripts.golakehavasu_partners_load as loader
    from app.contrib.golakehavasu_partners import PartnerListing

    name = "Multiurl Self Dup ZZZ"

    def _make_listing(url: str) -> PartnerListing:
        # Isolated coords: visitor-center lat/lng sits among many Google rows and
        # the first payload lands in ambiguous reconcile (inserted_pending), which
        # would mask the _register_cvb same-run dedup this test targets.
        return PartnerListing(
            name=name,
            url=url,
            address="1 Pier Rd, Lake Havasu City, AZ 86403",
            lat=34.5123,
            lng=-114.3789,
            phone="(928) 555-0142",
            website="http://multiurl-selfdup.example",
            description="desc",
            category="Restaurant/Bar",
        )

    # Same listing served from two distinct partner URLs (the real sitemap shape).
    monkeypatch.setattr(loader, "fetch_partner_sitemap_urls", lambda **k: ["u1", "u2"])
    monkeypatch.setattr(loader, "fetch_and_parse_partner", lambda url, **k: _make_listing(url))

    def _cleanup() -> None:
        # ingest_partners commits internally (no rollback harness), so remove the
        # rows it created -- providers AND their entities -- to keep the DB clean
        # and stop a prior run's leftovers from poisoning the snapshot.
        from app.db.models import Entity

        with SessionLocal() as session:
            provs = session.scalars(select(Provider).where(Provider.provider_name == name)).all()
            ent_ids = [p.entity_id for p in provs if p.entity_id]
            for p in provs:
                session.delete(p)
            session.flush()
            for ent in session.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all():
                session.delete(ent)
            session.commit()

    _cleanup()  # clear any leftovers from an earlier failed run
    try:
        counts = loader.ingest_partners(category_slug="eat-drink", dry_run=False, limit=None)

        assert counts["inserted"] == 1
        assert counts["idempotent_updated"] == 1
        assert counts["retired_duplicates"] == 0

        with SessionLocal() as session:
            rows = session.scalars(select(Provider).where(Provider.provider_name == name)).all()
            assert len(rows) == 1
    finally:
        _cleanup()


# --- reactivate-or-skip: heal hidden CVB rows still present in the sitemap ----
# Isolated coords (no other rows near them) so the heal path is exercised via the
# CVB name/website idempotency match, never an incidental geo reconcile.
_REACT_LAT = 34.9512
_REACT_LNG = -114.9123


def _seed_cvb_provider(
    name: str,
    *,
    website: str | None,
    is_active: bool,
    draft: bool,
    description: str | None = None,
    lat: float = _REACT_LAT,
    lng: float = _REACT_LNG,
) -> str:
    """Commit a ``go_lake_havasu`` Provider (+ Entity via dual-write), then drop
    it into the requested hidden state.

    Created active-then-hidden so the Entity always exists -- exactly how the
    real Cabana/Captain-Bob rows became inactive after a prior deactivation,
    rather than never having been promoted.
    """
    with SessionLocal() as session:
        prov = Provider(
            provider_name=name,
            category="uncategorized",
            slug=derive_provider_slug(session, name),
            source="go_lake_havasu",
            website=website,
            description=description,
            lat=lat,
            lng=lng,
            is_active=True,
            draft=False,
        )
        session.add(prov)
        create_provider_and_entity(session, prov)
        session.flush()
        prov.is_active = is_active
        prov.draft = draft
        session.commit()
        return prov.id


def _cleanup_providers_named(name: str) -> None:
    """Remove every Provider (and its Entity) with this name -- ingest_partners
    commits internally, so clean explicitly before and after each run."""
    from app.db.models import Entity

    with SessionLocal() as session:
        provs = session.scalars(select(Provider).where(Provider.provider_name == name)).all()
        ent_ids = [p.entity_id for p in provs if p.entity_id]
        for p in provs:
            session.delete(p)
        session.flush()
        for ent in session.scalars(select(Entity).where(Entity.id.in_(ent_ids))).all():
            session.delete(ent)
        session.commit()


def _mock_single_listing(monkeypatch, *, name: str, website: str | None, category: str) -> None:
    import scripts.golakehavasu_partners_load as loader
    from app.contrib.golakehavasu_partners import PartnerListing

    listing = PartnerListing(
        name=name,
        url="https://www.golakehavasu.com/directory/heal-test/",
        address="1 Pier Rd, Lake Havasu City, AZ 86403",
        lat=_REACT_LAT,
        lng=_REACT_LNG,
        phone=None,
        website=website,
        description="desc",
        category=category,
    )
    monkeypatch.setattr(loader, "fetch_partner_sitemap_urls", lambda **k: ["u1"])
    monkeypatch.setattr(loader, "fetch_and_parse_partner", lambda url, **k: listing)


def test_ingest_partners_reactivates_hidden_partner_without_live_twin(monkeypatch) -> None:
    """A still-listed partner whose only CVB row is hidden gets SURFACED.

    Regression for the Cabana Boat Rentals no-op: the idempotency snapshot keys
    on name/website regardless of is_active/draft, so the loader matched the
    inactive row, filled gaps, and left it invisible (counted as
    idempotent_updated, "work done"). With no live twin, the heal reactivates the
    surviving canonical instead of silently skipping it.
    """
    import scripts.golakehavasu_partners_load as loader

    name = "Hidden Reactivate NoTwin ZZZ"
    _cleanup_providers_named(name)
    pid = _seed_cvb_provider(
        name, website="http://hidden-notwin.example", is_active=False, draft=False
    )
    try:
        _mock_single_listing(
            monkeypatch, name=name, website="http://hidden-notwin.example", category="Boating"
        )
        counts = loader.ingest_partners(category_slug="things-to-do", dry_run=False, limit=None)

        assert counts["reactivated"] == 1
        assert counts["skipped_reactivate_live_twin"] == 0
        assert counts["idempotent_updated"] == 1
        assert counts["inserted"] == 0

        with SessionLocal() as session:
            prov = session.get(Provider, pid)
            assert prov is not None
            assert prov.is_active is True
            assert prov.draft is False
    finally:
        _cleanup_providers_named(name)


def test_ingest_partners_skips_reactivation_when_live_twin_exists(monkeypatch) -> None:
    """A hidden CVB row is NOT resurrected when a live twin already represents it.

    The 16 'dormant duplicate' partners (a hidden CVB row beside an active Google
    Places row) must stay as-is: reactivating the CVB row would mint a visible
    duplicate next to the Google listing. Heal must detect the live twin and skip.
    """
    import scripts.golakehavasu_partners_load as loader

    name = "Hidden With Twin ZZZ"
    _cleanup_providers_named(name)
    cvb_pid = _seed_cvb_provider(name, website=None, is_active=False, draft=False)
    with SessionLocal() as session:
        twin = _google_provider(session, name)  # active, non-draft, google_places
        session.commit()
        twin_id = twin.id
    try:
        _mock_single_listing(monkeypatch, name=name, website=None, category="Boating")
        counts = loader.ingest_partners(category_slug="things-to-do", dry_run=False, limit=None)

        assert counts["skipped_reactivate_live_twin"] == 1
        assert counts["reactivated"] == 0
        assert counts["idempotent_updated"] == 1

        with SessionLocal() as session:
            cvb = session.get(Provider, cvb_pid)
            twin = session.get(Provider, twin_id)
            assert cvb is not None and cvb.is_active is False  # stayed hidden
            assert twin is not None and twin.is_active is True
            # no new duplicate row minted: still exactly the seeded CVB + twin
            rows = session.scalars(select(Provider).where(Provider.provider_name == name)).all()
            assert len(rows) == 2
    finally:
        _cleanup_providers_named(name)


# --- reconcile-dormant: fold hidden CVB rows onto their confident live twin ----
def test_reconcile_dormant_merges_inactive_row_onto_contact_twin() -> None:
    """A hidden CVB row with a confident (shared-website) Google twin folds: its
    enrichment lifts onto the twin, CVB provenance is recorded, and the dormant
    row is left retired. This is the cleanup for the 16 'dormant duplicate'
    partners the audit found.
    """
    import scripts.golakehavasu_partners_load as loader
    from app.db.models import Entity

    cvb_name = "Dormant CVB Contact ZZZ"
    twin_name = "Dormant Twin Google ZZZ"
    shared_web = "http://dormant-twin.example"
    _cleanup_providers_named(cvb_name)
    _cleanup_providers_named(twin_name)
    cvb_pid = _seed_cvb_provider(
        cvb_name, website=shared_web, is_active=False, draft=False, description="CVB blurb"
    )
    with SessionLocal() as session:
        twin = _google_provider(session, twin_name, website=shared_web)
        session.commit()
        twin_id = twin.id
        twin_ent_id = twin.entity_id
    try:
        counts = loader.reconcile_dormant(dry_run=False, limit=None)

        assert counts["merged"] == 1
        assert counts["merged_contact"] == 1
        assert counts["retired"] == 0  # already inactive -> not re-retired
        assert counts["left_alone"] == 0

        with SessionLocal() as session:
            cvb = session.get(Provider, cvb_pid)
            twin = session.get(Provider, twin_id)
            assert cvb is not None and cvb.is_active is False  # stays retired
            assert cvb.pending_review is False
            assert twin is not None and twin.is_active is True
            assert twin.description == "CVB blurb"  # gap lifted from the CVB row
            ent = session.get(Entity, twin_ent_id)
            assert ent is not None and "go_lake_havasu" in (ent.source or "")
    finally:
        _cleanup_providers_named(cvb_name)
        _cleanup_providers_named(twin_name)


def test_reconcile_dormant_leaves_twinless_row_untouched() -> None:
    """A hidden CVB row with NO confident twin is left alone -- those are the
    genuinely-invisible partners the ingest reactivation path surfaces instead;
    reconcile-dormant must not retire-merge them into nothing.
    """
    import scripts.golakehavasu_partners_load as loader

    name = "Dormant NoTwin ZZZ"
    _cleanup_providers_named(name)
    pid = _seed_cvb_provider(
        name,
        website="http://dormant-notwin-unique.example",
        is_active=False,
        draft=False,
        lat=35.5012,  # far from any seeded Google row -> no fuzzy-geo twin either
        lng=-115.5012,
    )
    try:
        counts = loader.reconcile_dormant(dry_run=False, limit=None)

        assert counts["merged"] == 0
        assert counts["left_alone"] == 1

        with SessionLocal() as session:
            prov = session.get(Provider, pid)
            assert prov is not None and prov.is_active is False
    finally:
        _cleanup_providers_named(name)


def test_reconcile_dormant_dry_run_does_not_write() -> None:
    """--dry-run computes the fold plan but persists nothing (the gate Casey runs
    before the real prod pass)."""
    import scripts.golakehavasu_partners_load as loader

    cvb_name = "Dormant DryRun CVB ZZZ"
    twin_name = "Dormant DryRun Twin ZZZ"
    shared_web = "http://dormant-dryrun.example"
    _cleanup_providers_named(cvb_name)
    _cleanup_providers_named(twin_name)
    _seed_cvb_provider(
        cvb_name, website=shared_web, is_active=False, draft=False, description="CVB blurb"
    )
    with SessionLocal() as session:
        twin = _google_provider(session, twin_name, website=shared_web)
        session.commit()
        twin_id = twin.id
    try:
        counts = loader.reconcile_dormant(dry_run=True, limit=None)

        assert counts["merged"] == 1  # planned...
        with SessionLocal() as session:
            twin = session.get(Provider, twin_id)
            assert twin is not None and twin.description is None  # ...but not written
    finally:
        _cleanup_providers_named(cvb_name)
        _cleanup_providers_named(twin_name)
