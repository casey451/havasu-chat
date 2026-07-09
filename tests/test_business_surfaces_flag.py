"""BUSINESS_SURFACES_ENABLED — the single kill switch for every advertiser /
business-owner surface.

Both states are pinned so re-enabling the business side later is one config flip,
pre-verified here:

  * flag OFF (the consumer-launch state): zero business CTAs in the rendered HTML
    of home / category / provider / search, and the owner-facing routes (/portal,
    /portal/*, /sponsor, /advertise, /claim/*, /merchant/*) serve ONE "coming
    soon" stub — 200, noindex, contact mailto — instead of their real content.
  * flag ON (today's behavior): the "For Business" nav, the homepage claim card,
    the provider claim CTAs, and the live /portal + /sponsor pages all render.

The suite-wide default is ON (see tests/conftest.py) so the rest of the tests keep
asserting today's behavior; every test here sets the flag explicitly via
monkeypatch so it never depends on that default.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app

FLAG = "BUSINESS_SURFACES_ENABLED"

client = TestClient(app)

# Visible CTA text / link targets that ONLY appear on business-owner surfaces.
# None of these may survive in consumer-facing HTML while the flag is off.
_BIZ_MARKERS: tuple[str, ...] = (
    "For Business",
    'href="/portal',
    'href="/sponsor',
    "Own a Havasu business",
    "Claim your listing",
    "Claim &amp; manage",
    "Claim this listing",
    "Sponsor this category",
    "premium placement",
    "Advertise on Ask",
)


def _assert_no_biz_markers(html: str, where: str) -> None:
    hits = [m for m in _BIZ_MARKERS if m in html]
    assert not hits, f"business CTA(s) leaked into {where} with flag off: {hits}"


def _seed_claimable_provider() -> str:
    """A free, unverified, live listing → its /provider page shows the claim CTA
    when the flag is on. Rows are swept by the conftest source-cleanup fixture."""
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


# ── flag OFF — consumer pages carry zero business CTAs ─────────────────────────


def test_home_has_no_business_ctas_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    _assert_no_biz_markers(client.get("/home").text, "/home")


def test_category_has_no_sponsor_cta_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    _assert_no_biz_markers(client.get("/categories/eat-and-drink").text, "/categories/eat-and-drink")


def test_provider_page_hides_claim_cta_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _seed_claimable_provider()
    monkeypatch.setenv(FLAG, "false")
    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    _assert_no_biz_markers(r.text, f"/provider/{slug}")
    # The claim CTA's else-branch keeps a clean, non-link consumer line.
    assert "Listing kept fresh from public data." in r.text


def test_search_page_has_no_business_ctas_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    _assert_no_biz_markers(client.get("/search?q=coffee").text, "/search")


def test_header_and_footer_drop_for_business_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    body = client.get("/home").text
    assert "For Business" not in body
    # Footer trust line keeps its non-business phrases, no dead sponsor link.
    assert "Real public reviews" in body
    assert "Sponsored clearly labeled" not in body


# ── flag OFF — owner routes serve the "coming soon" stub, never a 404 ──────────

_OFF_ROUTES = (
    "/portal",
    "/portal/",
    "/portal/claim",
    "/portal/placements",  # normally login-walls; the stub answers first
    "/portal/creatives",
    "/sponsor",
    "/advertise",
    "/claim/anything-here",
    "/merchant/upgrade/anything-here",
)


@pytest.mark.parametrize("path", _OFF_ROUTES)
def test_business_routes_serve_coming_soon_when_off(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FLAG, "false")
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200, (path, r.status_code)
    body = r.text
    assert "coming soon" in body.lower(), path
    assert "hello@askhava.com" in body, path  # a real contact path, no wall
    assert "noindex" in body.lower(), path  # <meta robots>
    assert "noindex" in r.headers.get("x-robots-tag", "").lower(), path
    assert "For Business" not in body, path  # the stub's own chrome is clean too


def test_coming_soon_post_lands_softly_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "false")
    # A bookmarked POST (e.g. an old buy/claim form) must not 404/405.
    r = client.post("/portal/placements/new", follow_redirects=False)
    assert r.status_code == 200
    assert "coming soon" in r.text.lower()


def test_sitemap_omits_portal_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test the builder directly — the /sitemap-*.xml route is TTL-cached, so
    # asserting through HTTP would be order-dependent on a prior request's cache.
    monkeypatch.setenv(FLAG, "false")
    from app.seo.site_routes import _build_sitemap_pages_xml

    assert "/portal</loc>" not in _build_sitemap_pages_xml()


# ── flag ON — today's full behavior is intact (pre-verified re-enable) ─────────


def test_home_shows_claim_card_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    body = client.get("/home").text
    assert "Own a Havasu business" in body
    assert 'href="/portal/claim"' in body
    assert "For Business" in body  # nav link restored


def test_provider_page_shows_claim_cta_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    slug = _seed_claimable_provider()
    monkeypatch.setenv(FLAG, "true")
    body = client.get(f"/provider/{slug}").text
    assert "Claim this listing" in body or "Claim &amp; manage" in body


def test_portal_and_sponsor_are_live_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    portal = client.get("/portal", follow_redirects=False)
    assert portal.status_code == 200
    assert "coming soon" not in portal.text.lower()
    sponsor = client.get("/sponsor", follow_redirects=False)
    assert sponsor.status_code == 200
    assert "coming soon" not in sponsor.text.lower()


def test_advertise_redirects_to_sponsor_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    r = client.get("/advertise", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers.get("location", "").endswith("/sponsor")


def test_sitemap_lists_portal_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FLAG, "true")
    from app.seo.site_routes import _build_sitemap_pages_xml

    assert "/portal</loc>" in _build_sitemap_pages_xml()
