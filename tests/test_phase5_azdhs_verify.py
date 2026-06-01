"""V1.5 wave-1 — azdhs_verify script (mocked AZDHS FeatureServer fetch)."""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import azdhs_verify


def _fake_registry() -> list[dict]:
    """One ArcGIS feature ``attributes`` dict shape (geometry stripped per
    the client's ``returnGeometry=false`` default)."""
    return [
        {
            "FACILITY_NAME": "Hilltop Learning Center",
            "LICENSE_NUMBER": "CDC-8407",
            "FACID": "FAC-001",
            "TYPE": "Child Care Center",
            "LICENSE_TYPE": "Child Care Group",
            "OPERATION_STATUS": "Active",
            "license_expiration": None,
            "License_Effective": None,
            "Capacity": "120",
            "CAPACITY_INT": 120,
            "Telephone": "928-555-0123",
            "ADDRESS": "123 Acoma Blvd S",
            "CITY": "Lake Havasu City",
            "ZIP": "86403",
            "N_ADDRESS": "123 ACOMA BLVD S",
            "N_CITY": "LAKE HAVASU CITY",
            "N_COUNTY": "MOHAVE COUNTY",
            "N_ZIP": "86403",
            "N_FULLADDR": "123 ACOMA BLVD S, LAKE HAVASU CITY, AZ 86403",
            "N_LAT": 34.4839,
            "N_LON": -114.3225,
            "RUN_DATE": 1740614400000,  # ArcGIS epoch-ms
        }
    ]


def test_azdhs_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        azdhs_verify, "fetch_azdhs_childcare_for_county", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="azdhs-test-prov-1",
            provider_name="Hilltop Learning Center",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="azdhs-test-prov-1",
            google_place_id="places/azdhs-test-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azdhs_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azdhs-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        assert prov.attributes
        payload = prov.attributes.get("azdhs")
        assert isinstance(payload, dict)
        assert payload.get("LICENSE_NUMBER") == "CDC-8407"
        assert payload.get("CAPACITY_INT") == 120
        assert payload.get("OPERATION_STATUS") == "Active"
        assert payload.get("match_score", 0) >= 86
        assert prov.last_verified_at is not None


def test_azdhs_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        azdhs_verify, "fetch_azdhs_childcare_for_county", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="azdhs-test-prov-2",
            provider_name="Unrelated Provider Name XYZ",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="azdhs-test-prov-2",
            google_place_id="places/azdhs-test-2",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azdhs_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0
    assert counts["skipped_no_match"] >= 1


def test_azdhs_verify_handles_case_mismatch(monkeypatch) -> None:
    """Provider name in Title Case vs AZDHS entry in ALL CAPS still matches.

    Regression guard parallel to the NPI ``test_npi_verify_handles_case_mismatch``
    one (Phase 5.4 §3 fix #1: ``processor=utils.default_process``). AZDHS
    FACILITY_NAME values mix casing; the verifier must be case-insensitive.
    """
    registry = [
        {
            "FACILITY_NAME": "REDEMPTION KIDS DAY CARE",
            "LICENSE_NUMBER": "CDC-99999",
            "OPERATION_STATUS": "Active",
            "Capacity": "54",
            "CAPACITY_INT": 54,
            "N_COUNTY": "MOHAVE COUNTY",
        }
    ]
    monkeypatch.setattr(azdhs_verify, "fetch_azdhs_childcare_for_county", lambda *a, **k: registry)

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="azdhs-case-test-1",
            provider_name="Redemption Kids Day Care",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="azdhs-case-test-1",
            google_place_id="places/azdhs-case-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azdhs_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1, (
        "Regression of the rapidfuzz 3.x case-sensitivity fix. "
        "Pre-fix this case-only-differing pair scored ~25; post-fix it should score "
        "~100 and match. Check scripts/azdhs_verify._best_azdhs_match passes "
        "processor=utils.default_process to fuzz.token_sort_ratio."
    )

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azdhs-case-test-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        payload = (prov.attributes or {}).get("azdhs") or {}
        assert payload.get("LICENSE_NUMBER") == "CDC-99999"


def test_azdhs_verify_skips_already_verified(monkeypatch) -> None:
    """Idempotency guard: a provider already stamped with
    ``verification_method='azdhs_childcare'`` AND an attributes['azdhs']
    LICENSE_NUMBER should land in ``skipped_already``, not ``matched``,
    on the second run."""
    monkeypatch.setattr(
        azdhs_verify, "fetch_azdhs_childcare_for_county", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="health-wellness-care").one()
        p = Provider(
            id="azdhs-idem-test-1",
            provider_name="Hilltop Learning Center",
            category="health-wellness-care",
            category_id=cat.id,
            source="google_places",
            slug="azdhs-idem-test-1",
            google_place_id="places/azdhs-idem-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts1 = azdhs_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = azdhs_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0
