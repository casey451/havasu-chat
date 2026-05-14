"""Phase 5 — npi_verify script (mocked NPI HTTP)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import npi_verify


def _fake_registry() -> list[dict]:
    return [
        {
            "number": "1234567890",
            "enumeration_type": "NPI-2",
            "basic": {
                "organization_name": "Desert Springs Medical Clinic",
                "status": "A",
            },
            "other_names": [],
        }
    ]


def test_npi_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(npi_verify, "fetch_npi_results_for_city", lambda *a, **k: _fake_registry())

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="npi-test-prov-1",
            provider_name="Desert Springs Medical Clinic",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="npi-test-prov-1",
            google_place_id="places/npi-test-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = npi_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="npi-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "npi_registry"
        assert prov.attributes and prov.attributes.get("npi_number") == "1234567890"
        assert prov.last_verified_at is not None


def test_npi_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(npi_verify, "fetch_npi_results_for_city", lambda *a, **k: _fake_registry())

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="npi-test-prov-2",
            provider_name="Unrelated Name XYZ",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="npi-test-prov-2",
            google_place_id="places/npi-test-2",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = npi_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0
    assert counts["skipped_no_match"] >= 1
