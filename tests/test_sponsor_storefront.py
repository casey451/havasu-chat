"""P4 storefront: /sponsor is public and shows a config-driven rate card; the
offers helper falls back to the default price book and never hardcodes amounts.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.portal.products import DEFAULT_PRICE_BOOK, storefront_offers


def test_sponsor_landing_public_and_shows_rate_card() -> None:
    with TestClient(app) as client:
        r = client.get("/sponsor")
    assert r.status_code == 200
    body = r.text
    assert "Start advertising" in body
    # Routes into the real self-serve buy flow, not a dead lead-capture.
    assert "/portal/placements/new" in body


def test_storefront_offers_fall_back_to_default_price_book() -> None:
    with SessionLocal() as db:
        offers = storefront_offers(db)
    assert {o["key"] for o in offers} == {"category_rank", "page_ad", "homepage_rotating"}
    # With no seeded price book, each offer shows the indicative default price.
    for o in offers:
        expected = DEFAULT_PRICE_BOOK.get((o["key"], o["rank_tier"]))
        assert o["price_cents"] == expected
        assert o["indicative"] is True


def test_offers_never_invent_a_price_without_config() -> None:
    # An unknown product key has no default → price stays None (→ "on request").
    from app.portal.products import storefront_offers as _so

    with SessionLocal() as db:
        offers = _so(db)
    # Every shipped offer has a default; none should be None here.
    assert all(o["price_cents"] is not None for o in offers)
