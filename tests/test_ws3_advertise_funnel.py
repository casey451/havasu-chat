"""WS3 — advertiser funnel & rate-card terminology regression.

The 2026-07-06 audit (B3) reported a broken ad funnel: a "blank" rate card, no
public prices, and paid "Claim this category" CTAs colliding with the free
listing-claim flow. On the current build `/sponsor` is already a public, priced
rate card; these tests pin the pieces this workstream fixes/keeps:

  * the unsold homepage marquee is a *house promo* (free-listing claim) with a
    small "Advertise" link — not a consumer-facing empty ad slot ("Your logo
    here" / "Ad space · Available");
  * paid category placement says "Sponsor" (the "Claim" verb is reserved for the
    free listing-ownership flow) — the category-page copy is covered in
    tests/test_leaf_pages.py;
  * the public rate card is viewable WITHOUT an account (WS3 acceptance:
    "a business owner can see every price without an account");
  * `/advertise` still reaches the rate card in one hop.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _get(path: str, *, follow: bool = True) -> tuple[int, str]:
    with TestClient(app) as client:
        r = client.get(path, follow_redirects=follow)
        return r.status_code, r.text


def test_home_unsold_marquee_is_house_promo_not_empty_ad_slot() -> None:
    status, b = _get("/home")
    assert status == 200
    # House promo: the free listing-claim CTA holds the unsold slot.
    assert 'href="/portal/claim"' in b
    assert "For local businesses" in b
    # A small, honest paid-advertising link remains discoverable.
    assert "marquee-alt" in b
    assert 'href="/sponsor"' in b
    # The consumer-facing empty-ad-slot framing (and the paid "Claim" verb) are gone.
    assert "Your logo here" not in b
    assert "Ad space · Available" not in b
    assert "Claim this spot" not in b


def test_sponsor_rate_card_is_public_without_login() -> None:
    status, b = _get("/sponsor", follow=False)
    # Public: 200, never a 3xx to /login — prices are visible without an account.
    assert status == 200
    # The three self-serve products render (labels from the STOREFRONT_OFFERS catalog).
    assert "Category top spot" in b
    assert "Category page ad" in b
    assert "Home rotating spot" in b
    # Honesty framing + the self-serve buy path.
    assert "no dark patterns" in b
    assert "/portal/placements/new" in b


def test_advertise_reaches_the_rate_card_in_one_hop() -> None:
    with TestClient(app) as client:
        r = client.get("/advertise", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/sponsor"
