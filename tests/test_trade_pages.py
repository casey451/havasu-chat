"""SEO P2.1/P2.2 — dedicated home-services trade pages.

Covers: route resolution + 404s (unknown parent/trade, under-minimum trade),
trade provider filtering, the live-count title/H1, the canonical matrix
(self-canonical + promoted ``?trade=`` facet -> trade-page canonical +
unpromoted facet -> clean category canonical), JSON-LD (BreadcrumbList +
ItemList present, NO AggregateRating anywhere per DECISION D4), and sitemap
inclusion/exclusion across the thin-page gate.
"""

from __future__ import annotations

import json
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.categories.trades import (
    TRADE_PAGE_MIN_PROVIDERS,
    TRADE_PARENT_SLUG,
    TRADES,
    provider_matches_trade,
)
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app

_BASE = "https://hava.example.com"
_SOURCE = "test-trade-pages"

_CANON_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
_JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sitemap_cache() -> None:
    main_module._sitemap_cache.clear()
    yield
    main_module._sitemap_cache.clear()


def _seed_trade_provider(
    db, *, name: str, google_primary: str, rating: float = 4.5, reviews: int = 25
) -> Provider:
    slug = f"trade-test-{uuid4().hex[:10]}"
    ent = Entity(
        entity_type="commercial",
        slug=f"trade-ent-{uuid4().hex[:10]}",
        name=name,
        source=_SOURCE,
    )
    db.add(ent)
    db.flush()
    prov = Provider(
        provider_name=name,
        category="home_services",
        google_primary_category=google_primary,
        slug=slug,
        is_active=True,
        draft=False,
        source=_SOURCE,
        entity_id=ent.id,
        google_rating=rating,
        google_review_count=reviews,
    )
    db.add(prov)
    return prov


def _cleanup() -> None:
    from sqlalchemy import select

    with SessionLocal() as db:
        for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
            db.delete(prov)
        for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
            db.delete(ent)
        db.commit()


@pytest.fixture
def seeded_trades():
    """Seed plumbers at the gate, hvac above it, roofers below it.

    - plumbers: TRADE_PAGE_MIN_PROVIDERS providers (exactly at the gate)
    - hvac: gate + 1 providers
    - roofers: gate - 1 providers (below -> 404 / sitemap-excluded / unlinked)
    """
    with SessionLocal() as db:
        plumber_names = []
        for i in range(TRADE_PAGE_MIN_PROVIDERS):
            name = f"Plumb Co {i} {uuid4().hex[:6]}"
            _seed_trade_provider(db, name=name, google_primary="plumber")
            plumber_names.append(name)
        hvac_names = []
        for i in range(TRADE_PAGE_MIN_PROVIDERS + 1):
            name = f"Cool Air {i} {uuid4().hex[:6]}"
            _seed_trade_provider(db, name=name, google_primary="hvac_contractor")
            hvac_names.append(name)
        roofer_names = []
        for i in range(TRADE_PAGE_MIN_PROVIDERS - 1):
            name = f"Roof Co {i} {uuid4().hex[:6]}"
            _seed_trade_provider(db, name=name, google_primary="roofing_contractor")
            roofer_names.append(name)
        db.commit()
    try:
        yield {
            "plumbers": plumber_names,
            "hvac": hvac_names,
            "roofers": roofer_names,
        }
    finally:
        _cleanup()


def _jsonld_blocks(html: str) -> list[dict]:
    return [json.loads(m) for m in _JSONLD_RE.findall(html)]


# --- taxonomy / matcher unit checks -----------------------------------------


def test_ten_promoted_trades_under_home_property_services() -> None:
    assert TRADE_PARENT_SLUG == "home-property-services"
    assert sorted(TRADES) == sorted(
        [
            "plumbers",
            "hvac",
            "electricians",
            "handyman",
            "pool-service",
            "pest-control",
            "roofers",
            "garage-door",
            "landscapers",
            "cleaning",
        ]
    )


def test_provider_matches_trade_uses_curated_needles() -> None:
    plumber = Provider(
        provider_name="P",
        category="home_services",
        source=_SOURCE,
        google_primary_category="plumber",
    )
    # The plural URL slug matches the singular Google type via curated needles.
    assert provider_matches_trade(plumber, "plumbers") is True
    assert provider_matches_trade(plumber, "hvac") is False
    landscaper = Provider(
        provider_name="L",
        category="home_services",
        source=_SOURCE,
        google_primary_category="landscaping_service",
    )
    assert provider_matches_trade(landscaper, "landscapers") is True


def test_legacy_generic_trade_matching_preserved() -> None:
    """Unpromoted ?trade= values keep the old slug-derived needle behavior."""
    prov = Provider(
        provider_name="W",
        category="home_services",
        source=_SOURCE,
        google_primary_category="window_tinting_service",
    )
    assert provider_matches_trade(prov, "window-tinting") is True


def test_all_trade_intros_are_40_to_100_words() -> None:
    for trade in TRADES.values():
        n = len(trade.intro.split())
        assert 40 <= n <= 100, f"{trade.slug}: intro is {n} words"
        assert 4 <= len(trade.faqs) <= 6, f"{trade.slug}: {len(trade.faqs)} FAQs"


# --- route resolution + gate --------------------------------------------------


def test_trade_page_resolves_and_filters_to_trade(
    client: TestClient, seeded_trades: dict
) -> None:
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/plumbers")
    assert r.status_code == 200
    body = r.text
    for name in seeded_trades["plumbers"]:
        assert name in body
    # An hvac provider must NOT appear on the plumbers page.
    for name in seeded_trades["hvac"]:
        assert name not in body


def test_trade_page_title_and_h1_carry_live_count(
    client: TestClient, seeded_trades: dict
) -> None:
    n = len(seeded_trades["hvac"])
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/hvac")
    assert r.status_code == 200
    title = f"{n} Best HVAC Companies in Lake Havasu City, AZ — Ask Hava"
    assert f"<title>{title}</title>" in r.text
    assert f"<h1>{n} Best HVAC Companies in Lake Havasu City, AZ</h1>" in r.text


def test_trade_page_has_intro_faq_and_breadcrumb(
    client: TestClient, seeded_trades: dict
) -> None:
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/plumbers")
    assert r.status_code == 200
    body = r.text
    assert 'class="trade-intro"' in body
    intro_first_sentence = TRADES["plumbers"].intro.split(".")[0]
    assert intro_first_sentence in body
    # FAQ block: 4–6 truthful templated Q&As.
    n_faq = body.count('class="faq-item"')
    assert 4 <= n_faq <= 6
    # Breadcrumb: Home › parent category › trade.
    assert f'<a href="/categories/{TRADE_PARENT_SLUG}">' in body
    assert "Plumbers" in body


def test_unknown_trade_404s(client: TestClient, seeded_trades: dict) -> None:
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/dog-walkers")
    assert r.status_code == 404


def test_unknown_parent_404s(client: TestClient, seeded_trades: dict) -> None:
    r = client.get("/categories/eat-drink/plumbers")
    assert r.status_code == 404


def test_under_minimum_trade_404s(client: TestClient, seeded_trades: dict) -> None:
    """Thin-page gate: roofers is seeded below TRADE_PAGE_MIN_PROVIDERS."""
    assert len(seeded_trades["roofers"]) < TRADE_PAGE_MIN_PROVIDERS
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/roofers")
    assert r.status_code == 404


# --- canonicals (P1.5 interplay) ----------------------------------------------


def test_trade_page_self_canonical(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/plumbers")
    assert r.status_code == 200
    assert _CANON_RE.findall(r.text) == [
        f"{_BASE}/categories/{TRADE_PARENT_SLUG}/plumbers"
    ]


def test_promoted_trade_facet_canonicalizes_to_trade_page(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}?trade=plumbers")
    assert r.status_code == 200
    assert _CANON_RE.findall(r.text) == [
        f"{_BASE}/categories/{TRADE_PARENT_SLUG}/plumbers"
    ]


def test_unpromoted_trade_facet_keeps_clean_category_canonical(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}?trade=window-tinting")
    assert r.status_code == 200
    assert _CANON_RE.findall(r.text) == [f"{_BASE}/categories/{TRADE_PARENT_SLUG}"]


def test_under_minimum_promoted_facet_keeps_clean_category_canonical(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A promoted trade that fails the gate must not canonicalize to a 404."""
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}?trade=roofers")
    assert r.status_code == 200
    assert _CANON_RE.findall(r.text) == [f"{_BASE}/categories/{TRADE_PARENT_SLUG}"]


def test_other_category_pages_canonical_unchanged(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-parent categories keep the existing clean-URL canonical behavior."""
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get("/categories/eat-drink?cuisine=mexican")
    assert r.status_code == 200
    assert _CANON_RE.findall(r.text) == [f"{_BASE}/categories/eat-drink"]


def test_parent_page_links_only_gate_clearing_trades(
    client: TestClient, seeded_trades: dict
) -> None:
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}")
    assert r.status_code == 200
    body = r.text
    assert f'href="/categories/{TRADE_PARENT_SLUG}/plumbers"' in body
    assert f'href="/categories/{TRADE_PARENT_SLUG}/hvac"' in body
    # Under-minimum trade is never linked.
    assert f'href="/categories/{TRADE_PARENT_SLUG}/roofers"' not in body


# --- JSON-LD (DECISION D4) ------------------------------------------------------


def test_trade_page_jsonld_breadcrumb_itemlist_no_aggregate_rating(
    client: TestClient, seeded_trades: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASE_URL", _BASE)
    r = client.get(f"/categories/{TRADE_PARENT_SLUG}/hvac")
    assert r.status_code == 200
    body = r.text
    blocks = _jsonld_blocks(body)
    types = {b.get("@type") for b in blocks}
    assert "BreadcrumbList" in types
    assert "ItemList" in types
    crumb = next(b for b in blocks if b["@type"] == "BreadcrumbList")
    items = crumb["itemListElement"]
    assert [it["position"] for it in items] == [1, 2, 3]
    assert items[2]["item"] == f"{_BASE}/categories/{TRADE_PARENT_SLUG}/hvac"
    ilist = next(b for b in blocks if b["@type"] == "ItemList")
    assert ilist["numberOfItems"] == len(seeded_trades["hvac"])
    assert len(ilist["itemListElement"]) == len(seeded_trades["hvac"])
    for entry in ilist["itemListElement"]:
        assert entry["url"].startswith(f"{_BASE}/provider/")
    # DECISION D4: no self-serving AggregateRating structured data ANYWHERE on
    # the page. Visible star ratings in the cards stay (asserted below).
    assert "AggregateRating" not in body
    assert "aggregateRating" not in body
    assert 'class="stars"' in body


# --- sitemap gate ----------------------------------------------------------------


def test_sitemap_includes_qualifying_trades_excludes_thin_ones(
    client: TestClient, seeded_trades: dict
) -> None:
    r = client.get("/sitemap-pages.xml")
    assert r.status_code == 200
    xml = r.text
    base = main_module._base_url()
    assert f"{base}/categories/{TRADE_PARENT_SLUG}/plumbers" in xml
    assert f"{base}/categories/{TRADE_PARENT_SLUG}/hvac" in xml
    assert f"{base}/categories/{TRADE_PARENT_SLUG}/roofers" not in xml
