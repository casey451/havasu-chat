"""Tests for /provider/<slug> route + view-model (directory pivot V1).

Phase A (this file): tests #1-12 cover the route + view-model layer.
Phase B will add tests #13-18 for template rendering.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app
from app.providers import view_models


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
            google_photo_refs=["https://example.com/google-1.jpg", "https://example.com/google-2.jpg"],
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
