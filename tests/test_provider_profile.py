"""Tests for /provider/<slug> route + view-model + template (directory pivot V1).

Tests #1-12 cover the route + view-model layer (Phase A).
Tests #13-18 cover template rendering + timezone-aware open-status (Phase B).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app
from app.providers import queries, view_models


def _make_provider(**overrides) -> Provider:
    """Construct a Provider with sensible test defaults. ``slug`` is
    auto-assigned by the model insert listener when omitted."""
    suf = uuid.uuid4().hex[:8]
    defaults: dict = {
        "provider_name": f"Acme Plumbing {suf}",
        "category": "home_services",
        "verified": True,
        "draft": False,
        "is_active": True,
        "pending_review": False,
        "source": "test-provider-profile",
    }
    defaults.update(overrides)
    return Provider(**defaults)


# --- #1-3: route status codes ---


def test_route_returns_200_for_valid_slug() -> None:
    with SessionLocal() as db:
        p = _make_provider()
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200


def test_route_returns_404_for_unknown_slug() -> None:
    with TestClient(app) as client:
        r = client.get("/provider/no-such-slug-12345")
    assert r.status_code == 404


def test_route_returns_404_for_inactive_provider() -> None:
    with SessionLocal() as db:
        p = _make_provider(is_active=False)
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 404


# --- #4-7: freshness bands ---


def test_view_model_freshness_fresh_band() -> None:
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(last_verified_at=now - timedelta(days=1))
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db, now=now)
    assert vm.freshness_band == "fresh"
    assert vm.freshness_copy.startswith("Last verified ")


def test_view_model_freshness_aging_band() -> None:
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(last_verified_at=now - timedelta(days=120))
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db, now=now)
    assert vm.freshness_band == "aging"
    assert vm.freshness_copy == "Verification may be outdated"


def test_view_model_freshness_stale_band() -> None:
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(last_verified_at=now - timedelta(days=200))
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db, now=now)
    assert vm.freshness_band == "stale"
    assert vm.freshness_copy == "Business information may have changed"


def test_view_model_freshness_none_band() -> None:
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(last_verified_at=None)
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db, now=now)
    assert vm.freshness_band == "none"
    assert vm.freshness_copy == ""


# --- #8: data-inconsistency edge case ---


def test_view_model_data_inconsistency_flag() -> None:
    """tier=sponsored AND sponsored_until in future AND verified=False
    surfaces a structural-data warning (UX spec §9)."""
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(
            tier="sponsored",
            sponsored_until=(now + timedelta(days=30)).replace(tzinfo=None),
            verified=False,
        )
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db, now=now)
    assert vm.is_sponsored is True
    assert vm.verified is False
    assert vm.data_inconsistency_flag is True


# --- #9: Ask Hava prefill URL ---


def test_view_model_ask_hava_url_prefilled() -> None:
    with SessionLocal() as db:
        p = _make_provider(provider_name="Acme Plumbing")
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db)
    # quote() encodes spaces as %20 (not "+").
    assert vm.ask_hava_url.startswith("/chat?q=")
    assert "Tell%20me%20about%20Acme%20Plumbing" in vm.ask_hava_url
    assert "Lake%20Havasu%20City" in vm.ask_hava_url


# --- #10: hero photo priority ---


def test_view_model_hero_pin_wins_over_google_photo() -> None:
    pinned = "https://example.com/pinned-hero.jpg"
    with SessionLocal() as db:
        p = _make_provider(
            attributes={"hero_pin_photo_url": pinned},
            google_photo_refs=[
                "https://example.com/google-1.jpg",
                "https://example.com/google-2.jpg",
            ],
        )
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db)
    assert vm.hero_photo_url == pinned


# --- #11-12: service-area-only default + override ---


def test_view_model_service_area_only_default_for_no_google_place_id() -> None:
    """No google_place_id + no explicit attr → service_area_only defaults to True."""
    with SessionLocal() as db:
        p = _make_provider(google_place_id=None, attributes=None)
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db)
    assert vm.service_area_only is True
    assert vm.address is None


def test_view_model_service_area_only_override() -> None:
    """Explicit attributes.service_area_only=True wins even when google_place_id is set."""
    with SessionLocal() as db:
        p = _make_provider(
            google_place_id="ChIJ_xxx_test_place_id",
            address="123 Test Lane, Lake Havasu City, AZ",
            attributes={"service_area_only": True, "service_area": ["86403", "86404"]},
        )
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db)
    assert vm.service_area_only is True
    assert vm.address is None
    assert vm.service_area == ["86403", "86404"]


# --- #13-14: Hava's pick badge ---


def test_template_renders_hava_pick_badge_when_featured() -> None:
    with SessionLocal() as db:
        p = _make_provider(featured=True)
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert "Featured Local" in r.text


def test_template_omits_hava_pick_badge_when_not_featured() -> None:
    with SessionLocal() as db:
        p = _make_provider(featured=False)
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert "Featured Local" not in r.text


# --- #15: sponsor disclosure word ---


def test_template_renders_sponsor_disclosure_when_sponsored() -> None:
    now = now_lake_havasu()
    with SessionLocal() as db:
        p = _make_provider(
            tier="sponsored",
            sponsored_until=(now + timedelta(days=30)).replace(tzinfo=None),
            verified=True,
        )
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert "Featured Local" in r.text


# --- #16-17: claim + upgrade CTAs ---


def test_template_renders_claim_cta_for_free_unclaimed() -> None:
    """tier=free + verified=False → claim CTA visible (UX spec §8 + §10)."""
    with SessionLocal() as db:
        p = _make_provider(tier="free", verified=False)
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert "Claim this listing" in r.text


def test_template_renders_upgrade_cta_for_claimed_not_sponsored() -> None:
    """verified=True + tier!=sponsored keeps the unlocked profile experience."""
    with SessionLocal() as db:
        p = _make_provider(tier="free", verified=True)
        db.add(p)
        db.commit()
        slug = p.slug

    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert "Local offer" in r.text


# --- #18: timezone-aware is_open_now ---


def test_open_status_respects_lake_havasu_timezone() -> None:
    """Pin is_open_now against a known hours_structured + injected now in
    America/Phoenix. Tuesday 10:00 AM local should be inside an 08:00-17:00
    Tuesday span and read as Open. Tuesday 19:00 should read as Closed.
    """
    hours = {
        "monday": [{"open": "08:00", "close": "17:00"}],
        "tuesday": [{"open": "08:00", "close": "17:00"}],
        "wednesday": [{"open": "08:00", "close": "17:00"}],
        "thursday": [{"open": "08:00", "close": "17:00"}],
        "friday": [{"open": "08:00", "close": "17:00"}],
        "saturday": [],
        "sunday": [],
    }
    p = Provider(
        provider_name="Hours Test Co",
        category="home_services",
        hours_structured=hours,
        verified=True,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-provider-profile",
    )

    # Tuesday 2026-05-12 10:00 AM in America/Phoenix.
    tuesday_morning = datetime(2026, 5, 12, 10, 0, tzinfo=LAKE_HAVASU_TZ)
    assert tuesday_morning.weekday() == 1  # 0=Monday, 1=Tuesday — guards the fixture.
    is_open, copy = queries.is_open_now(p, now=tuesday_morning)
    assert is_open is True
    assert copy is not None
    assert "Open now" in copy
    assert "5 PM" in copy

    # Tuesday 2026-05-12 19:00 — after the 17:00 close.
    tuesday_evening = datetime(2026, 5, 12, 19, 0, tzinfo=LAKE_HAVASU_TZ)
    is_open_pm, copy_pm = queries.is_open_now(p, now=tuesday_evening)
    assert is_open_pm is False
    assert copy_pm is not None
