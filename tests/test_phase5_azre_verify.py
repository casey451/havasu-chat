"""V1.5 wave-1 — azre_verify script (mocked LHC vacation-rentals MapService fetch).

Pattern mirrors the AZDHS sibling test verbatim except match-key is
``Provider.address`` not ``Provider.provider_name`` (vacation rentals
identify by address, not by business name).
"""

from __future__ import annotations

import httpx

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import azre_verify


def _fake_registry() -> list[dict]:
    """One ArcGIS feature ``attributes`` dict shape (geometry stripped per
    the client's ``returnGeometry=false`` default). PII contact fields
    intentionally omitted to mirror what :func:`_azre_payload` actually
    persists (the verifier never reads contact fields)."""
    return [
        {
            "ObjectID": 1,
            "Status": "M",
            "Score": 100.0,
            "Match_addr": "2851 SARATOGA AVE",
            "USER_Parcel_Number": "108-22-174",
            "USER_FormattedAddress": "2851 SARATOGA AVE ",
            "USER_Business_State": "AZ",
            "USER_Business_Postal": "86406",
            "BusinessCity": "Lake Havasu City",
            "AccountNumber": None,
        }
    ]


def test_azre_verify_updates_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        azre_verify, "fetch_azre_lhc_vacation_rentals", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="lodging-vacation-rentals").one()
        p = Provider(
            id="azre-test-prov-1",
            provider_name="Saratoga Cove Vacation Rental",
            address="2851 Saratoga Ave",  # mixed case + missing trailing whitespace
            category="lodging-vacation-rentals",
            category_id=cat.id,
            source="google_places",
            slug="azre-test-prov-1",
            google_place_id="places/azre-test-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azre_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azre-test-prov-1").one()
        assert prov.verified is True
        assert prov.verification_method == "scraper"
        assert prov.attributes
        payload = prov.attributes.get("azre_lhc")
        assert isinstance(payload, dict)
        assert payload.get("USER_Parcel_Number") == "108-22-174"
        assert payload.get("USER_FormattedAddress", "").strip() == "2851 SARATOGA AVE"
        assert payload.get("Status") == "M"
        assert payload.get("match_score", 0) >= 86
        # PII boundary: emergency-contact fields must NOT have leaked into
        # attributes. The fake_registry doesn't include them so this is
        # belt-and-suspenders, but the assertion locks the contract.
        assert "USER_Emergency_Contact" not in payload
        assert "USER_Emergency_Contact_Phone" not in payload
        assert "USER_Emergency_Contact_Email" not in payload
        assert prov.last_verified_at is not None


def test_azre_verify_dry_run_no_writes(monkeypatch) -> None:
    monkeypatch.setattr(
        azre_verify, "fetch_azre_lhc_vacation_rentals", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="lodging-vacation-rentals").one()
        p = Provider(
            id="azre-test-prov-2",
            provider_name="Some Other Vacation Rental",
            address="9999 Nonexistent Lane",  # won't fuzzy-match the fake registry
            category="lodging-vacation-rentals",
            category_id=cat.id,
            source="google_places",
            slug="azre-test-prov-2",
            google_place_id="places/azre-test-2",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azre_verify.run_verify(dry_run=True, limit=10, client=client)

    assert counts["matched"] == 0
    assert counts["skipped_no_match"] >= 1


def test_azre_verify_handles_address_case_mismatch(monkeypatch) -> None:
    """Provider address in Title Case vs registry in ALL CAPS still matches.

    Parallel to NPI + AZDHS case-sensitivity regression guards. LHC City
    geocoder normalizes addresses to ALL CAPS in ``Match_addr`` and most
    ``USER_FormattedAddress`` rows; catalog providers come from Google
    Places typically in Title Case ("2500 Hacienda Dr"). The verifier
    must be case-insensitive.
    """
    registry = [
        {
            "ObjectID": 42,
            "Status": "M",
            "Match_addr": "2500 HACIENDA DR",
            "USER_Parcel_Number": "104-31-264",
            "USER_FormattedAddress": "2500 HACIENDA DR ",
            "USER_Business_State": "AZ",
            "USER_Business_Postal": "86403",
            "BusinessCity": "Lake Havasu City",
        }
    ]
    monkeypatch.setattr(azre_verify, "fetch_azre_lhc_vacation_rentals", lambda *a, **k: registry)

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="lodging-vacation-rentals").one()
        p = Provider(
            id="azre-case-test-1",
            provider_name="Hacienda Lakeside Rental",
            address="2500 Hacienda Dr",
            category="lodging-vacation-rentals",
            category_id=cat.id,
            source="google_places",
            slug="azre-case-test-1",
            google_place_id="places/azre-case-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azre_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["matched"] >= 1, (
        "Regression of the rapidfuzz 3.x case-sensitivity fix on AZRE. "
        "Check scripts/azre_verify._best_azre_match passes "
        "processor=utils.default_process to fuzz.token_sort_ratio."
    )

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azre-case-test-1").one()
        assert prov.verified is True
        payload = (prov.attributes or {}).get("azre_lhc") or {}
        assert payload.get("USER_Parcel_Number") == "104-31-264"


def test_azre_verify_skips_providers_without_address(monkeypatch) -> None:
    """Vacation-rental providers in the catalog without an ``address``
    field cannot be address-matched. They should land in
    ``skipped_no_address``, not ``skipped_no_match``, so operators can
    distinguish "missing data on our side" from "missing in registry."
    """
    monkeypatch.setattr(
        azre_verify, "fetch_azre_lhc_vacation_rentals", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="lodging-vacation-rentals").one()
        p = Provider(
            id="azre-noaddr-test-1",
            provider_name="Address-less Rental",
            address=None,
            category="lodging-vacation-rentals",
            category_id=cat.id,
            source="google_places",
            slug="azre-noaddr-test-1",
            google_place_id="places/azre-noaddr-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts = azre_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts["skipped_no_address"] >= 1

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="azre-noaddr-test-1").one()
        # Provider was untouched by the verifier.
        assert prov.verified is False
        assert prov.verification_method is None
        assert (prov.attributes or {}).get("azre_lhc") is None


def test_azre_verify_skips_already_verified(monkeypatch) -> None:
    """Idempotency guard parallel to AZDHS's: a provider already stamped
    with attributes['azre_lhc']['USER_Parcel_Number'] lands in
    skipped_already, not matched, on the second run."""
    monkeypatch.setattr(
        azre_verify, "fetch_azre_lhc_vacation_rentals", lambda *a, **k: _fake_registry()
    )

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="lodging-vacation-rentals").one()
        p = Provider(
            id="azre-idem-test-1",
            provider_name="Saratoga Cove Rental",
            address="2851 Saratoga Ave",
            category="lodging-vacation-rentals",
            category_id=cat.id,
            source="google_places",
            slug="azre-idem-test-1",
            google_place_id="places/azre-idem-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with httpx.Client() as client:
        counts1 = azre_verify.run_verify(dry_run=False, limit=10, client=client)
        counts2 = azre_verify.run_verify(dry_run=False, limit=10, client=client)

    assert counts1["matched"] >= 1
    assert counts2["skipped_already"] >= 1
    assert counts2["matched"] == 0
