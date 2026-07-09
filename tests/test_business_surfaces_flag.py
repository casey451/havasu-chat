"""CLAIM_SURFACES_ENABLED (free) + ADS_ENABLED (paid) — the two-tier business gate.

The business side splits into a free claim tier and a paid ads tier so they launch
independently. Every state is pinned so flipping a tier is a pre-verified config
change:

  * LAUNCH (claim on, ads off): the free claim flow is fully live — "For Business"
    nav, homepage claim card (WITHOUT the "premium placement" advertise line),
    provider claim CTAs, and the real /portal + /portal/claim + /claim flow with
    ZERO paid-product mentions. Paid surfaces stay hidden — /sponsor + /advertise +
    the buy routes serve an advertising-specific "coming soon" stub, category
    sponsor cards are gone, and the "Sponsored clearly labeled" footer line drops.
  * FUTURE (both on): today's full behavior — advertise line, sponsor cards, the
    live /sponsor rate card, the login-gated buy routes, the footer trust line.
  * OFF (claim off): the whole business side falls back to the generic stub.

The suite-wide default is BOTH ON (see tests/conftest.py) so the rest of the tests
keep asserting full behavior; every test here sets the two flags explicitly.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app

CLAIM = "CLAIM_SURFACES_ENABLED"
ADS = "ADS_ENABLED"

client = TestClient(app)

# Text / link targets that only appear on the PAID (ads) surfaces.
_ADS_MARKERS: tuple[str, ...] = (
    'href="/sponsor"',
    "Sponsor this category",
    "premium placement",
    "Advertise on Ask",
    "Sponsored clearly labeled",
    'href="/portal/placements"',
)
# Substrings (lowercased) that must NEVER appear in the free claim flow while ads
# are off — the flow must read as free-only.
_PAID_IN_CLAIM_FLOW: tuple[str, ...] = (
    "advertis",
    "sponsored",
    "/portal/placements",
    "premium",
    "paid slot",
    "rate card",
)


def _set(monkeypatch: pytest.MonkeyPatch, *, claim: bool, ads: bool) -> None:
    monkeypatch.setenv(CLAIM, "true" if claim else "false")
    monkeypatch.setenv(ADS, "true" if ads else "false")


def _assert_no_ads_markers(html: str, where: str) -> None:
    hits = [m for m in _ADS_MARKERS if m in html]
    assert not hits, f"paid/ads CTA(s) leaked into {where} with ads off: {hits}"


def _seed_claimable_provider() -> str:
    """A free, unverified, live listing → its /provider page shows the claim CTA
    when claim is on. Rows are swept by the conftest source-cleanup fixture."""
    suf = uuid.uuid4().hex[:8]
    slug = f"biz-flag-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Flag Test Biz {suf}",
                category="home_services",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,  # + free tier → show_claim_cta is True
                source="test-biz-flag",
            )
        )
        db.commit()
    return slug


# ── flag defaults (unset env) ─────────────────────────────────────────────────


def test_flag_defaults_are_claim_on_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.feature_flags import ads_enabled, claim_surfaces_enabled

    monkeypatch.delenv(CLAIM, raising=False)
    monkeypatch.delenv(ADS, raising=False)
    assert claim_surfaces_enabled() is True  # free tier ships on
    assert ads_enabled() is False  # paid tier ships off


# ── LAUNCH state: claim on, ads off ───────────────────────────────────────────


def test_home_shows_claim_card_without_advertise_line(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    body = client.get("/home").text
    assert "Own a Havasu business" in body  # claim card restored
    assert 'href="/portal/claim"' in body
    assert "For Business" in body  # nav restored
    _assert_no_ads_markers(body, "/home")  # but no advertise line / sponsor links


def test_provider_shows_claim_cta_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _seed_claimable_provider()
    _set(monkeypatch, claim=True, ads=False)
    body = client.get(f"/provider/{slug}").text
    assert "Claim this listing" in body or "Claim &amp; manage" in body
    _assert_no_ads_markers(body, f"/provider/{slug}")


def test_footer_has_claim_links_no_advertise_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    body = client.get("/home").text
    assert 'href="/portal">For Business' in body
    assert 'href="/portal/claim">Claim your listing' in body
    assert "Real public reviews" in body
    assert "Sponsored clearly labeled" not in body  # no ads → no trust line
    assert 'href="/sponsor"' not in body  # no Advertise link


def test_category_has_no_sponsor_card_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    _assert_no_ads_markers(client.get("/categories/eat-and-drink").text, "/categories/eat-and-drink")


def test_portal_landing_is_live_and_paid_free_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    r = client.get("/portal", follow_redirects=False)
    assert r.status_code == 200
    low = r.text.lower()
    assert "coming soon" not in low  # the real claim landing, not the stub
    assert "Claim your listing" in r.text
    leaked = [m for m in _PAID_IN_CLAIM_FLOW if m in low]
    assert not leaked, f"paid mentions leaked into /portal with ads off: {leaked}"


def test_portal_claim_is_live_and_paid_free_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    # Even the advertise-funnel entry (?advertise=1) must not surface paid copy.
    r = client.get("/portal/claim?advertise=1", follow_redirects=False)
    assert r.status_code == 200
    low = r.text.lower()
    assert "coming soon" not in low
    assert "claim-search-q" in r.text  # the real find-your-listing search
    assert "you're setting up advertising" not in low
    leaked = [m for m in _PAID_IN_CLAIM_FLOW if m in low]
    assert not leaked, f"paid mentions leaked into /portal/claim with ads off: {leaked}"


def test_claim_slug_enters_real_signin_flow_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    # Not the stub: the real per-listing claim login-gates to magic-link sign-in.
    r = client.get("/claim/some-slug", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


def test_sitemap_lists_portal_when_claim_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    from app.seo.site_routes import _build_sitemap_pages_xml

    assert "/portal</loc>" in _build_sitemap_pages_xml()


# ── LAUNCH state: paid routes serve the ADS "coming soon" stub ─────────────────

_ADS_ROUTES = (
    "/sponsor",
    "/advertise",
    "/portal/placements",
    "/portal/placements/new",
    "/portal/creatives",
    "/merchant/upgrade/x",
)


@pytest.mark.parametrize("path", _ADS_ROUTES)
def test_ads_routes_serve_advertising_coming_soon(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set(monkeypatch, claim=True, ads=False)
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200, (path, r.status_code)
    low = r.text.lower()
    assert "coming soon" in low, path
    assert "advertising" in low, path  # ads-specific copy, not the generic stub
    assert "noindex" in r.headers.get("x-robots-tag", "").lower(), path
    # Ads stub points owners at the free claim flow (claim is on).
    assert 'href="/portal/claim"' in r.text, path


def test_ads_buy_post_lands_softly_ads_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=False)
    r = client.post("/portal/placements/new", follow_redirects=False)
    assert r.status_code == 200
    assert "coming soon" in r.text.lower()


# ── FUTURE state: both on → today's full behavior ─────────────────────────────


def test_home_shows_advertise_line_when_ads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=True)
    body = client.get("/home").text
    assert "Own a Havasu business" in body
    assert "premium placement" in body  # advertise line back
    assert 'href="/sponsor"' in body


def test_footer_and_sponsor_live_when_ads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=True)
    home = client.get("/home").text
    assert "Sponsored clearly labeled" in home  # trust line back
    assert 'href="/sponsor">Advertise' in home
    sponsor = client.get("/sponsor", follow_redirects=False)
    assert sponsor.status_code == 200
    assert "coming soon" not in sponsor.text.lower()  # the real rate card


def test_portal_shows_advertise_door_when_ads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=True)
    body = client.get("/portal", follow_redirects=False).text
    assert "coming soon" not in body.lower()
    assert 'href="/portal/placements"' in body  # the Advertise door


def test_buy_route_is_login_gated_when_ads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=True)
    r = client.get("/portal/placements", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


def test_advertise_redirects_to_sponsor_when_ads_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=True, ads=True)
    r = client.get("/advertise", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers.get("location", "").endswith("/sponsor")


# ── OFF state: claim off → whole business side falls back to the generic stub ──


def test_portal_serves_generic_stub_when_claim_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=False, ads=False)
    r = client.get("/portal", follow_redirects=False)
    assert r.status_code == 200
    low = r.text.lower()
    assert "coming soon" in low
    assert "business tools" in low  # generic copy, not the advertising stub


def test_home_hides_all_business_when_claim_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=False, ads=False)
    body = client.get("/home").text
    assert "For Business" not in body
    assert "Own a Havasu business" not in body
    _assert_no_ads_markers(body, "/home (claim off)")


def test_sitemap_omits_portal_when_claim_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, claim=False, ads=False)
    from app.seo.site_routes import _build_sitemap_pages_xml

    assert "/portal</loc>" not in _build_sitemap_pages_xml()
