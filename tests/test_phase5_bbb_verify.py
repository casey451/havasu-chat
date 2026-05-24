"""V1.5 wave-4 — bbb_verify script (mocked BBB accredited listing fetch)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import bbb_verify


def _fake_bbb_record() -> dict:
    return {
        "business_id": "1000018294",
        "business_name": "ABC Hardware",
        "accreditation_status": "Accredited",
        "rating": "A+",
        "profile_url": (
            "https://www.bbb.org/us/az/lake-havasu-city/profile/"
            "hardware-store/abc-hardware-1126-1000018294"
        ),
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


def test_bbb_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        bbb_verify,
        "fetch_bbb_businesses",
        lambda *a, **k: [_fake_bbb_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-test-prov-1", name="ABC Hardware")

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="bbb-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        payload = (prov.attributes or {}).get("bbb") or {}
        assert payload.get("business_id") == "1000018294"
        assert payload.get("match_score", 0) >= 86
        assert prov.last_verified_at is not None


def test_bbb_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        bbb_verify,
        "fetch_bbb_businesses",
        lambda *a, **k: [_fake_bbb_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-test-prov-2", name="Unrelated Shop XYZ")

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0
    assert counts["skipped_no_match"] >= 1


def test_bbb_verify_handles_case_mismatch(monkeypatch) -> None:
    registry = [
        {
            "business_id": "1000022222",
            "business_name": "ABC HARDWARE STORE",
            "accreditation_status": "Accredited",
        }
    ]
    monkeypatch.setattr(bbb_verify, "fetch_bbb_businesses", lambda *a, **k: registry)

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-case-test-1", name="Abc Hardware Store")

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1


def test_bbb_verify_no_match(monkeypatch) -> None:
    monkeypatch.setattr(bbb_verify, "fetch_bbb_businesses", lambda *a, **k: [])

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-nomatch-test-1", name="Joe's Tackle")

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_no_match"] >= 1
    assert counts["matched"] == 0


def test_bbb_verify_skips_already_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        bbb_verify,
        "fetch_bbb_businesses",
        lambda *a, **k: [_fake_bbb_record()],
    )

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-idem-test-1", name="ABC Hardware")

    with httpx.Client() as client:
        counts1 = bbb_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = bbb_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0


def test_bbb_verify_zero_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        bbb_verify,
        "fetch_bbb_businesses",
        lambda *a, **k: [_fake_bbb_record()],
    )

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=False, limit=0, client=client)

    assert counts["candidates"] == 0
    assert counts["matched"] == 0


def test_bbb_verify_captcha_soft_fail(monkeypatch) -> None:
    monkeypatch.setattr(bbb_verify, "fetch_bbb_businesses", lambda *a, **k: [])

    with SessionLocal() as db:
        _seed_shopping_provider(db, prov_id="bbb-softfail-test-1", name="ABC Hardware")

    with httpx.Client() as client:
        counts = bbb_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_no_match"] >= 1
    assert counts["matched"] == 0
