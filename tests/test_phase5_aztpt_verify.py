"""V1.5 wave-4 — aztpt_verify script (mocked AZ TPT license search fetch)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import aztpt_verify


def _fake_tpt_record() -> dict:
    return {
        "tpt_license_number": "12345678",
        "business_name": "Desert Market LLC",
        "business_status": "Valid",
    }


def _seed_shopping_provider(db, *, prov_id: str, name: str) -> Provider:
    cat = db.query(Category).filter_by(slug="shopping-essentials").one()
    p = Provider(
        id=prov_id,
        provider_name=name,
        category="shopping-essentials",
        category_id=cat.id,
        source="google_places",
        slug=prov_id,
        google_place_id=f"places/{prov_id}",
    )
    db.add(p)
    create_provider_and_entity(db, p)
    db.commit()
    return p


def test_aztpt_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        aztpt_verify,
        "fetch_aztpt_license_search",
        lambda *a, **k: [_fake_tpt_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-test-prov-1", name="Desert Market")

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="aztpt-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        payload = (prov.attributes or {}).get("aztpt") or {}
        assert payload.get("tpt_license_number") == "12345678"
        assert payload.get("match_score", 0) >= 86
        assert prov.last_verified_at is not None


def test_aztpt_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        aztpt_verify,
        "fetch_aztpt_license_search",
        lambda *a, **k: [_fake_tpt_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-test-prov-2", name="Unrelated Shop XYZ")

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="aztpt-test-prov-2").one()
        assert prov.verified is False


def test_aztpt_verify_handles_case_mismatch(monkeypatch) -> None:
    registry = [
        {
            "tpt_license_number": "87654321",
            "business_name": "DESERT MARKET LLC",
            "business_status": "Valid",
        }
    ]
    monkeypatch.setattr(
        aztpt_verify,
        "fetch_aztpt_license_search",
        lambda *a, **k: registry,
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-case-test-1", name="Desert Market")

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1


def test_aztpt_verify_no_match(monkeypatch) -> None:
    monkeypatch.setattr(aztpt_verify, "fetch_aztpt_license_search", lambda *a, **k: [])

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-nomatch-test-1", name="Joe's Tackle")

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_no_match"] >= 1
    assert counts["matched"] == 0


def test_aztpt_verify_skips_already_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        aztpt_verify,
        "fetch_aztpt_license_search",
        lambda *a, **k: [_fake_tpt_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-idem-test-1", name="Desert Market")

    with httpx.Client() as client:
        counts1 = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0


def test_aztpt_verify_zero_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        aztpt_verify,
        "fetch_aztpt_license_search",
        lambda *a, **k: [_fake_tpt_record()],
    )

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=False, limit=0, client=client)

    assert counts["candidates"] == 0
    assert counts["matched"] == 0


def test_aztpt_verify_captcha_soft_fail(monkeypatch) -> None:
    monkeypatch.setattr(aztpt_verify, "fetch_aztpt_license_search", lambda *a, **k: [])

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="aztpt-softfail-test-1", name="Desert Market")

    with httpx.Client() as client:
        counts = aztpt_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_no_match"] >= 1
    assert counts["matched"] == 0
