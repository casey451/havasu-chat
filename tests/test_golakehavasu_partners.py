"""golakehavasu partner directory -- sitemap + listing parse + payload map."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

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
    for unmapped in ("Attractions", "Rentals", "Guided Tour", "Kingman", "", None):
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


def test_map_cvb_category_unmapped_returns_none() -> None:
    # Catch-all / ambiguous / geographic CVB categories are intentionally
    # unmapped so the loader falls back to its --category-slug default.
    for unmapped in ("Attractions", "Rentals", "Guided Tour", "Transportation",
                     "Kingman", "Family-Fun", "Misc", "", None):
        assert map_cvb_category(unmapped) is None


def test_partner_to_entity_payload_falls_back_when_unmapped() -> None:
    from app.contrib.golakehavasu_partners import PartnerListing

    listing = PartnerListing(
        name="Some Tour Co",
        url="https://www.golakehavasu.com/directory/some-tour-co/",
        address=None,
        lat=None,
        lng=None,
        phone=None,
        website=None,
        description=None,
        category="Guided Tour",  # not in the confident map
    )
    payload = partner_to_entity_payload(listing, category_slug="things-to-do")
    assert payload.category_slug == "things-to-do"


def test_cvb_category_map_values_are_known_tier1_slugs() -> None:
    valid = {
        "eat-drink", "on-the-water", "home-property-services",
        "health-wellness-care", "auto-rv-fuel", "shopping-essentials",
        "events", "outdoors-parks-trails", "classes-sports-recreation",
        "lodging-vacation-rentals", "pets", "public-civic-resources",
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
    assert (
        _fuzzy_geo_match(db_session, payload, threshold=FUZZY_NAME_THRESHOLD)
        == prov.entity_id
    )


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
    payload = EntityPayload(
        name="Some Place", entity_type="place", source="go_lake_havasu"
    )
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
