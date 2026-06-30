"""F2 (P0 revenue): the advertising Buy funnel must carry the chosen product all
the way through, never dumping the visitor on a context-free claim page.

Audit (2026-06-29): every "Buy →" and "Start advertising" linked to a bare
``/portal/placements/new``, which 303-redirects an unclaimed visitor to
``/portal/claim`` (the free claim page) with the selected product + price lost
and no way to resume. These tests pin that:

- the storefront Buy links encode which product was chosen;
- an anonymous Buy click preserves that product through the login redirect;
- a Buy click from someone with no claimed listing lands on a claim page that
  NAMES the product + price and offers a resume link (not a context-free page).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.portal.products import resolve_offer


def test_storefront_buy_links_encode_the_chosen_product() -> None:
    with TestClient(app) as client:
        body = client.get("/sponsor").text
    # Home rotating + page ad carry their type; category top spot carries its tier.
    assert "/portal/placements/new?placement_type=homepage_rotating" in body
    assert "/portal/placements/new?placement_type=page_ad" in body
    assert "placement_type=category_rank" in body and "rank_tier=1" in body


def test_anonymous_buy_preserves_offer_through_login() -> None:
    with TestClient(app) as client:
        r = client.get(
            "/portal/placements/new?placement_type=homepage_rotating",
            follow_redirects=False,
        )
    assert r.status_code == 303
    loc = r.headers.get("location", "")
    assert "/login" in loc
    # The offer survives in the post-login `next` target.
    assert "placement_type" in loc and "homepage_rotating" in loc


def test_resolve_offer_returns_label_and_price() -> None:
    with SessionLocal() as db:
        home = resolve_offer(db, "homepage_rotating")
        top = resolve_offer(db, "category_rank", 1)
        bogus = resolve_offer(db, "not_a_product")
    assert home is not None and home["label"] == "Home rotating spot"
    assert home["price_cents"] == 9900
    assert top is not None and top["rank_tier"] == 1 and top["price_cents"] == 17900
    assert bogus is None


def test_claim_page_names_product_and_offers_resume() -> None:
    with TestClient(app) as client:
        body = client.get("/portal/claim?placement_type=homepage_rotating").text
    assert "You're buying Home rotating spot" in body
    assert "$99" in body
    # A resume link back to the buy form with the same product.
    assert "/portal/placements/new?placement_type=homepage_rotating" in body


def test_claim_page_category_top_spot_with_tier() -> None:
    with TestClient(app) as client:
        body = client.get(
            "/portal/claim?placement_type=category_rank&rank_tier=1"
        ).text
    assert "You're buying Category top spot" in body
    assert "$179" in body
    assert "rank_tier=1" in body


def test_claim_page_generic_advertise_banner() -> None:
    with TestClient(app) as client:
        body = client.get("/portal/claim?advertise=1").text
    assert "You're setting up advertising" in body
    assert "/portal/placements/new" in body


def test_plain_claim_page_has_no_advertise_banner() -> None:
    with TestClient(app) as client:
        body = client.get("/portal/claim").text
    assert "You're buying" not in body
    assert "You're setting up advertising" not in body


def test_bogus_product_does_not_trigger_banner() -> None:
    # A junk placement_type is dropped — no banner, no resume link fabricated.
    with TestClient(app) as client:
        body = client.get("/portal/claim?placement_type=__nope__").text
    assert "You're buying" not in body
    assert "You're setting up advertising" not in body
