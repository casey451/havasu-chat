"""V1.5 wave-3 — azcc_towing_verify script (mocked AZCC entity search fetch)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import azcc_towing_verify


def _fake_corp_record() -> dict:
    return {
        "corp_id": "12345678",
        "entity_name": "ABC Towing Service LLC",
        "status": "Active",
    }


def _seed_towing_provider(db, *, prov_id: str, name: str) -> Provider:
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


def test_azcc_towing_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: [_fake_corp_record()],
    )

    with SessionLocal() as db:
        _seed_towing_provider(db, prov_id="azcc-test-prov-1", name="ABC Towing Service")

    with httpx.Client() as client:
        counts = azcc_towing_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azcc-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        payload = (prov.attributes or {}).get("azcc") or {}
        assert payload.get("corp_id") == "12345678"
        assert payload.get("match_score", 0) >= 86
        assert prov.last_verified_at is not None


def test_azcc_towing_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: [_fake_corp_record()],
    )

    with SessionLocal() as db:
        _seed_towing_provider(db, prov_id="azcc-test-prov-2", name="XYZ Towing Co")

    with httpx.Client() as client:
        counts = azcc_towing_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azcc-test-prov-2").one()
        assert prov.verified is False


def test_azcc_towing_verify_handles_case_mismatch(monkeypatch) -> None:
    registry = [
        {"corp_id": "99887766", "entity_name": "Abc Towing Service LLC", "status": "Active"}
    ]
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: registry,
    )

    with SessionLocal() as db:
        _seed_towing_provider(db, prov_id="azcc-case-test-1", name="ABC TOWING SERVICE")

    with httpx.Client() as client:
        counts = azcc_towing_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1


def test_azcc_towing_verify_skips_non_towing_keyword(monkeypatch) -> None:
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: [_fake_corp_record()],
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="auto-rv-fuel").one()
        p = Provider(
            id="azcc-nontow-test-1",
            provider_name="Joe's Pet Grooming",
            category="auto-rv-fuel",
            category_id=cat.id,
            source="google_places",
            slug="azcc-nontow-test-1",
            google_place_id="places/azcc-nontow-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azcc_towing_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_not_towing"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azcc-nontow-test-1").one()
        assert prov.verified is False
        assert (prov.attributes or {}).get("azcc") is None


def test_azcc_towing_verify_skips_already_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: [_fake_corp_record()],
    )

    with SessionLocal() as db:
        _seed_towing_provider(db, prov_id="azcc-idem-test-1", name="ABC Towing Service")

    with httpx.Client() as client:
        counts1 = azcc_towing_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = azcc_towing_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0


def test_azcc_towing_verify_zero_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        azcc_towing_verify,
        "fetch_azcc_entity_search",
        lambda *a, **k: [_fake_corp_record()],
    )

    with httpx.Client() as client:
        counts = azcc_towing_verify.run_verify(dry_run=False, limit=0, client=client)

    assert counts["candidates"] == 0
    assert counts["matched"] == 0
