"""Phase 3b — the Lake Ink & Brass business profile (/provider/{slug}).

The highest-SEO-value page, so the focus is the full LocalBusiness JSON-LD
(address + geo + openingHoursSpecification + aggregateRating) + BreadcrumbList,
plus the rendered bindings and a11y. The live route needs a seeded provider, so
the rich template is rendered directly with a sample ProviderProfileVM.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.main import app
from app.providers.router import templates as _prof_templates


def _fake_request(path: str = "/provider/mudshark") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _vm(**over) -> SimpleNamespace:
    base = dict(
        provider_name="Mudshark Brewery", category_label="Eat & Drink",
        category_url="/categories/eat-and-drink", slug="mudshark", district="Uptown",
        verified=True, last_verified_at=None, verification_method_copy="Verified by Hava",
        freshness_band="", freshness_copy="Checked 2 days ago",
        is_sponsored=True, is_featured=False, sponsor_disclosure_label="Sponsored",
        data_inconsistency_flag=False, google_rating=4.7, google_review_count=312,
        google_review_snippets=[{"text": "Best patio in town when it finally cools off, the ale and a pepperoni are done.", "author": "Dana R.", "rating": 5, "publish_time": "2026-06-16"}],
        call_phone="19285550142", call_phone_display="(928) 555-0142",
        directions_url="https://maps.google.com/?q=x&query_place_id=ABC", website_url="https://mudshark.example",
        ask_hava_url="/chat", hero_photo_url="https://img.example/h.jpg",
        gallery_photo_urls=["https://img.example/g1.jpg", "https://img.example/g2.jpg"],
        description="Lake Havasu's original craft brewery — wood-fired pizza and a patio.",
        service_chips=["Patio", "Live music"], service_area=[], service_area_only=False,
        address="210 Swanson Ave",
        postal_address={"street": "210 Swanson Ave", "city": "Lake Havasu City", "state": "AZ", "zip": "86403", "lat": 34.48, "lng": -114.32},
        hours_structured={d: [{"open": "11:00", "close": "22:00"}] for d in ("monday", "tuesday", "wednesday", "thursday")} | {"friday": [{"open": "11:00", "close": "00:00"}], "saturday": [{"open": "11:00", "close": "00:00"}], "sunday": []},
        hours_freetext=None, is_open_now=True, open_status_copy="Open until 10 PM",
        seasonal_hours_active_season=None, seasonal_hours_active_rows=None, season_status_copy=None,
        class_schedule=[], class_schedule_as_of=None,
        show_claim_cta=False, show_upgrade_cta=False, viewer_is_owner=False,
        claim_url="/claim/mudshark", upgrade_url="/upgrade/mudshark",
        district_chip_name=None, district_chip_url=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _render(vm: SimpleNamespace) -> str:
    return _prof_templates.env.get_template("provider_profile_lake.html").render(
        request=_fake_request(), vm=vm, disclosure_word="Sponsored",
        current_user_id="", favorite_entity_id="", is_favorited=False,
        parent_org=None, department_children=None, other_locations=None, nearby_providers=None,
    )


def _ld_blocks(html: str) -> list[dict]:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_profile_renders_core_bindings() -> None:
    h = _render(_vm())
    assert 'data-theme="lake"' in h
    assert "/static/styles/lake_redesign.css" in h
    assert h.count("<h1") == 1
    assert "Mudshark Brewery" in h
    # v4.5 PR-5: rating renders as an inline SVG star icon + number (no ★ glyph).
    assert 'class="star"' in h and "4.7" in h and "(312 reviews)" in h
    assert "Open until 10 PM" in h
    assert "(928) 555-0142" in h
    assert "Best patio in town" in h  # review snippet
    assert "Sponsored" in h  # disclosure tag
    assert "210 Swanson Ave" in h  # address


def test_profile_map_is_a_link_button_not_a_fake_map() -> None:
    """F14: the "View on the map" element is an obvious link button (pin glyph +
    label), not a faux embedded-map panel."""
    h = _render(_vm())
    assert '<a class="pmap"' in h
    assert "View on the map" in h
    assert "<svg" in h.split('class="pmap"')[1][:400]  # pin icon inside the link
    # The old faux-map gradient panel markup is gone.
    assert "linear-gradient(160deg,#dbe6ec" not in h


def test_profile_gallery_class_tracks_photo_count() -> None:
    """F14: the hero gallery carries a pg-N count class so the CSS can fill the
    frame for sparse photo sets (a single photo no longer leaves a blue half)."""
    # Default vm = 1 hero + 2 gallery = 3 photos.
    assert 'class="pgallery pg-3"' in _render(_vm())
    # One photo only (the amalaya-yoga case the audit hit).
    assert 'class="pgallery pg-1"' in _render(_vm(gallery_photo_urls=[]))
    # Five+ photos keep the full mosaic (capped at 5).
    five = _render(_vm(gallery_photo_urls=[f"https://img.example/g{i}.jpg" for i in range(6)]))
    assert 'class="pgallery pg-5"' in five
    # v4.5 PR-5: no photos -> NO image block at all (real photo or nothing; the
    # old monogram-art fallback is retired, §0 guardrail 3).
    _no_photos = _render(_vm(hero_photo_url=None, gallery_photo_urls=[]))
    assert "pgallery" not in _no_photos


def test_profile_localbusiness_jsonld_is_full() -> None:
    blocks = _ld_blocks(_render(_vm()))
    lb = next(b for b in blocks if b.get("@type") == "LocalBusiness")
    assert lb["name"] == "Mudshark Brewery"
    assert lb["address"]["streetAddress"] == "210 Swanson Ave"
    assert lb["address"]["addressRegion"] == "AZ"
    assert lb["geo"]["latitude"] == 34.48 and lb["geo"]["longitude"] == -114.32
    assert lb["aggregateRating"]["ratingValue"] == 4.7
    assert lb["aggregateRating"]["reviewCount"] == 312
    ohs = lb["openingHoursSpecification"]
    assert isinstance(ohs, list) and len(ohs) >= 5
    assert {"@type": "OpeningHoursSpecification", "dayOfWeek": "Monday", "opens": "11:00", "closes": "22:00"} in ohs


def test_profile_breadcrumb_jsonld() -> None:
    blocks = _ld_blocks(_render(_vm()))
    bc = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    names = [it["name"] for it in bc["itemListElement"]]
    assert names == ["Ask Hava", "Eat & Drink", "Mudshark Brewery"]


def test_profile_no_aggregate_rating_when_few_reviews() -> None:
    blocks = _ld_blocks(_render(_vm(google_review_count=1)))
    lb = next(b for b in blocks if b.get("@type") == "LocalBusiness")
    assert lb["aggregateRating"] is None  # under the 3-review threshold


def test_profile_claim_cta_variant() -> None:
    h = _render(_vm(show_claim_cta=True, website_url=None))
    assert "Claim this listing" in h
    assert "Claim &amp; manage it" in h or "Claim this listing →" in h


def test_profile_about_without_description_leads_with_factual_line() -> None:
    """v4.6 PR-0.2: a provider with no description of their own gets a short
    factual About line (name · category · address), NOT the auto-built disclaimer
    as the lead. The disclaimer becomes a .gasnote footnote by the suggest control."""
    h = _render(_vm(description=None, address="210 Swanson Ave"))
    about = h.split('class="pabout">', 1)[1].split("</p>", 1)[0]
    assert not about.lstrip().startswith("This listing is auto-built")
    assert "Mudshark Brewery" in about
    assert "Eat &amp; Drink" in about or "Eat & Drink" in about
    assert "210 Swanson Ave" in about
    # The disclaimer still appears, but as a small footnote next to suggest-an-edit.
    assert 'class="pautonote"' in h
    assert "auto-built from trusted public data" in h


def test_profile_about_with_description_has_no_autobuilt_footnote() -> None:
    """When the provider has its own description, the auto-built footnote is absent."""
    h = _render(_vm())  # default vm has a real description
    assert "auto-built from trusted public data" not in h
    assert "original craft brewery" in h


def test_profile_about_service_area_only_uses_area() -> None:
    """A service-area-only provider (no street address) falls back to the area."""
    h = _render(_vm(description=None, address=None, service_area_only=True,
                    service_area=["Lake Havasu City"], postal_address=None))
    about = h.split('class="pabout">', 1)[1].split("</p>", 1)[0]
    assert not about.lstrip().startswith("This listing is auto-built")
    assert "Lake Havasu City" in about


def test_profile_structural_a11y() -> None:
    for vm in (_vm(), _vm(show_claim_cta=True), _vm(hero_photo_url=None, gallery_photo_urls=[], service_area_only=True, service_area=["Lake Havasu City"], postal_address=None, address=None)):
        checker = _A11yChecker()
        checker.feed(_render(vm))
        issues = checker.finish()
        assert not issues, "; ".join(sorted(set(issues)))
