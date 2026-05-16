"""Phase 5 — az_roc_verify script (mocked AZ ROC lookup)."""

from __future__ import annotations

import httpx

from app.contrib.az_roc_client import AzRocMatch
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from scripts import az_roc_verify


def test_az_roc_verify_marks_provider_and_name_cache() -> None:
    calls: list[str] = []

    def counting_lookup(client: httpx.Client, name: str) -> AzRocMatch | None:
        calls.append(name)
        if "AZROC1" in name:
            return AzRocMatch(
                license_number="ROC-99999",
                classification="CR-11",
                status="ACTIVE",
                raw=None,
            )
        if "AZCACHE" in name:
            return AzRocMatch(license_number="ROC-1", classification=None, status="ACTIVE", raw=None)
        return None

    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="home-property-services").one()
        p = Provider(
            id="az-roc-test-1",
            provider_name="AZROC1 Plumbing LLC",
            category="home-property-services",
            category_id=cat.id,
            source="google_places",
            slug="az-roc-test-1",
            google_place_id="places/az-roc-1",
            # Required: az_roc_verify._home_providers_query filters by
            # google_primary_category ∈ AZ_ROC_LICENSED_PRIMARY_TYPES
            # (added at 420f893). Without this, the query excludes the
            # fixture and run_verify returns 0 candidates.
            google_primary_category="plumber",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        for i in (1, 2):
            pid = f"az-roc-cache-{i}"
            p2 = Provider(
                id=pid,
                provider_name="AZCACHE Plumbing Co",
                category="home-property-services",
                category_id=cat.id,
                source="google_places",
                slug=f"az-roc-cache-slug-{i}",
                google_place_id=f"places/az-cache-{i}",
                google_primary_category="plumber",
            )
            db.add(p2)
            create_provider_and_entity(db, p2)
        db.commit()

    with httpx.Client() as client:
        counts = az_roc_verify.run_verify(dry_run=False, limit=20, client=client, lookup_fn=counting_lookup)

    assert counts["matched"] == 3
    assert len(calls) == 2

    with SessionLocal() as db:
        prov = db.query(Provider).filter_by(id="az-roc-test-1").one()
        assert prov.attributes and prov.attributes.get("az_roc", {}).get("license_number") == "ROC-99999"
        for pid in ("az-roc-cache-1", "az-roc-cache-2"):
            p3 = db.query(Provider).filter_by(id=pid).one()
            assert p3.attributes and p3.attributes.get("az_roc", {}).get("license_number") == "ROC-1"
