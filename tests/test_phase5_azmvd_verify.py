"""V1.5 wave-3 — azmvd_verify script (mocked Valid Dealer Report fetch)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import azmvd_verify


def _fake_registry() -> list[dict]:
    return [
        {
            "dealer_number": "L00099999",
            "business_name": "Lake Havasu Auto Sales",
            "doing_business_as": "",
            "dealership_license_status": "Active",
            "license_type": "Used Motor Vehicle Dealer",
            "city": "Lake Havasu City",
            "state": "AZ",
            "zip": "86403",
            "street_address": "123 Test Blvd",
        }
    ]


def _seed_dealer_provider(db, *, prov_id: str, name: str) -> Provider:
    cat = db.query(Category).filter_by(slug="auto-rv-fuel").one()
    p = Provider(
        id=prov_id,
        provider_name=name,
        category="auto-rv-fuel",
        category_id=cat.id,
        source="google_places",
        slug=prov_id,
        google_place_id=f"places/{prov_id}",
    )
    db.add(p)
    create_provider_and_entity(db, p)
    db.commit()
    return p


def test_azmvd_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", lambda *a, **k: _fake_registry())

    with SessionLocal() as db:
        _seed_dealer_provider(db, prov_id="azmvd-test-prov-1", name="Lake Havasu Auto Sales")

    with httpx.Client() as client:
        counts = azmvd_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azmvd-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        payload = (prov.attributes or {}).get("azmvd") or {}
        assert payload.get("dealer_number") == "L00099999"
        assert payload.get("dealer_type") == "Used Motor Vehicle Dealer"
        assert payload.get("match_score", 0) >= 86
        assert prov.last_verified_at is not None


def test_azmvd_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", lambda *a, **k: _fake_registry())

    with SessionLocal() as db:
        _seed_dealer_provider(db, prov_id="azmvd-test-prov-2", name="Unrelated Dealer Name XYZ")

    with httpx.Client() as client:
        counts = azmvd_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0
    assert counts["skipped_no_match"] >= 1


def test_azmvd_verify_handles_case_mismatch(monkeypatch) -> None:
    registry = [
        {
            "dealer_number": "L00088888",
            "business_name": "LAKE HAVASU AUTO SALES",
            "dealership_license_status": "Active",
            "license_type": "Used Motor Vehicle Dealer",
            "city": "LAKE HAVASU CITY",
        }
    ]
    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", lambda *a, **k: registry)

    with SessionLocal() as db:
        _seed_dealer_provider(db, prov_id="azmvd-case-test-1", name="Lake Havasu Auto Sales")

    with httpx.Client() as client:
        counts = azmvd_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1


def test_azmvd_verify_skips_non_dealer_keyword(monkeypatch) -> None:
    fetch_called = {"n": 0}

    def _fetch(*a, **k):
        fetch_called["n"] += 1
        return _fake_registry()

    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", _fetch)

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="auto-rv-fuel").one()
        p = Provider(
            id="azmvd-nodealer-test-1",
            provider_name="Joe's Plumbing",
            category="auto-rv-fuel",
            category_id=cat.id,
            source="google_places",
            slug="azmvd-nodealer-test-1",
            google_place_id="places/azmvd-nodealer-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azmvd_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_not_dealer"] >= 1
    assert fetch_called["n"] == 1


def test_azmvd_verify_skips_already_verified(monkeypatch) -> None:
    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", lambda *a, **k: _fake_registry())

    with SessionLocal() as db:
        _seed_dealer_provider(db, prov_id="azmvd-idem-test-1", name="Lake Havasu Auto Sales")

    with httpx.Client() as client:
        counts1 = azmvd_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = azmvd_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0


def test_azmvd_verify_zero_candidates(monkeypatch) -> None:
    monkeypatch.setattr(azmvd_verify, "fetch_azmvd_dealers", lambda *a, **k: _fake_registry())

    with httpx.Client() as client:
        counts = azmvd_verify.run_verify(dry_run=False, limit=0, client=client)

    assert counts["candidates"] == 0
    assert counts["matched"] == 0
