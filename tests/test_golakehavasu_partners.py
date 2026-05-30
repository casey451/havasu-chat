"""golakehavasu partner directory -- sitemap + listing parse + payload map."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.contrib.golakehavasu import SITEMAP_INDEX_URL
from app.contrib.golakehavasu_partners import (
    fetch_and_parse_partner,
    fetch_partner_sitemap_urls,
    partner_to_entity_payload,
)

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
    assert payload.category_slug == "things-to-do"
    assert payload.lat == pytest.approx(34.4682917)
    assert payload.website == "http://www.lobster3ways.com"


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
