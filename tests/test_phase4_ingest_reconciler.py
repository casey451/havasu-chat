"""Phase 4.3 — cross-layer ingest reconciler."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import (
    GEO_PROXIMITY_THRESHOLD_M,
    SOURCE_PRIORITY,
    _compute_merge_fields,
    haversine_m,
    reconcile_hit,
    slugify,
)
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Entity, Location, Provider


def test_haversine_identical_zero() -> None:
    assert haversine_m(34.5, -114.35, 34.5, -114.35) == pytest.approx(0.0, abs=0.01)


def test_haversine_one_degree_latitude() -> None:
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_000.0, rel=0.02)


def test_slugify_english_village() -> None:
    assert slugify("English Village") == "english-village"


def test_slugify_lake_havasu_aquatic_park() -> None:
    assert slugify("Lake Havasu Aquatic Park!") == "lake-havasu-aquatic-park"


def test_slugify_unicode() -> None:
    s = slugify("東京 公園")
    assert s and "-" in s


def test_reconcile_empty_db_insert() -> None:
    with SessionLocal() as db:
        payload = EntityPayload(
            name="Lonely Place",
            entity_type="place",
            lat=34.5,
            lng=-114.35,
            google_place_id="places/abc",
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "insert"


def test_reconcile_google_place_id_update() -> None:
    entity_id: str | None = None
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-1",
            provider_name="Match By PID",
            category="retail",
            source="google_places",
            slug="match-by-pid-rec-1",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        loc = db.scalars(select(Location).where(Location.entity_id == p.entity_id)).first()
        assert loc is not None
        loc.google_place_id = "places/xyz"
        entity_id = p.entity_id
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Updated Name",
            entity_type="place",
            lat=34.6,
            lng=-114.36,
            google_place_id="places/xyz",
            description="New desc",
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "update"
        assert r.existing_id == entity_id
        assert r.merge_fields == {}


def test_reconcile_geo_and_name_update() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-geo",
            provider_name="Geo Match Park",
            category="retail",
            source="osm",
            slug="geo-match-park-rec",
            lat=34.5000,
            lng=-114.3500,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Geo Match Park",
            entity_type="place",
            lat=34.5002,
            lng=-114.3502,
            google_place_id=None,
            source="google_places",
            description="From Google",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "update"
        assert r.merge_fields is not None
        assert "name" in r.merge_fields


def test_reconcile_geo_name_mismatch_ambiguous() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-near",
            provider_name="Alpha Site",
            category="retail",
            source="osm",
            slug="alpha-site-rec",
            lat=34.5000,
            lng=-114.3500,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Different Name",
            entity_type="place",
            lat=34.5001,
            lng=-114.3501,
            google_place_id=None,
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "ambiguous"
        assert "name" in (r.reason or "").lower() or "geo" in (r.reason or "").lower()


def test_reconcile_far_but_same_name_ambiguous() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-far",
            provider_name="Duplicate Name X",
            category="retail",
            source="osm",
            slug="duplicate-name-x-rec",
            lat=34.40,
            lng=-114.50,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Duplicate Name X",
            entity_type="place",
            lat=34.55,
            lng=-114.32,
            google_place_id=None,
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "ambiguous"


def test_reconcile_skips_geo_when_payload_missing_coords() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-nogeo",
            provider_name="No Geo Payload",
            category="retail",
            source="osm",
            slug="no-geo-payload-rec",
            lat=34.5,
            lng=-114.35,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Unrelated",
            entity_type="place",
            lat=None,
            lng=None,
            google_place_id=None,
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "insert"


def test_reconcile_skips_strategy1_without_google_place_id() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-nopid",
            provider_name="No PID Entity",
            category="retail",
            source="osm",
            slug="no-pid-entity-rec",
            lat=34.5,
            lng=-114.35,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="No PID Entity",
            entity_type="place",
            lat=34.5001,
            lng=-114.3501,
            google_place_id=None,
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "update"


def test_compute_merge_fields_operator_empty() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-op",
            provider_name="Op Row",
            category="retail",
            source="operator",
            slug="op-row-rec",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        payload = EntityPayload(
            name="Other",
            entity_type="place",
            source="google_places",
            description="Try",
        )
        m = _compute_merge_fields(db, p.entity_id, payload)
        assert m == {}


def test_compute_merge_fields_google_over_osm() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-go",
            provider_name="Osm Name",
            category="retail",
            source="osm",
            slug="osm-name-rec",
            description="Old",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        ent.source = "osm"
        payload = EntityPayload(
            name="Google Name",
            entity_type="place",
            source="google_places",
            description="GDesc",
        )
        m = _compute_merge_fields(db, p.entity_id, payload)
        assert m["name"] == "Google Name"
        assert m["description"] == "GDesc"
        assert "google_places" in m["source"]


def test_compute_merge_fields_osm_over_google_fill_description_only() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-og",
            provider_name="Google Held",
            category="retail",
            source="google_places",
            slug="google-held-rec",
            description="Has desc",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        ent.source = "google_places"
        ent.description = "Has desc"
        payload = EntityPayload(
            name="Ignored",
            entity_type="place",
            source="osm",
            description="OSM tries",
        )
        m = _compute_merge_fields(db, p.entity_id, payload)
        assert m == {}


def test_compute_merge_fields_osm_fills_missing_description() -> None:
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-og2",
            provider_name="Google Held 2",
            category="retail",
            source="google_places",
            slug="google-held-2-rec",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        ent.source = "google_places"
        ent.description = None
        payload = EntityPayload(
            name="Ignored",
            entity_type="place",
            source="osm",
            description="Filled by osm",
        )
        m = _compute_merge_fields(db, p.entity_id, payload)
        assert m == {"description": "Filled by osm"}


def test_idempotency_same_google_payload_twice() -> None:
    entity_id: str | None = None
    with SessionLocal() as db:
        p = Provider(
            id="rec-prov-idem",
            provider_name="Idem Pub",
            category="retail",
            source="google_places",
            slug="idem-pub-rec",
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        loc = db.scalars(select(Location).where(Location.entity_id == p.entity_id)).first()
        assert loc is not None
        loc.google_place_id = "places/idemp"
        entity_id = p.entity_id
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Idem Pub",
            entity_type="place",
            source="google_places",
            google_place_id="places/idemp",
        )
        r1 = reconcile_hit(db, payload)
        assert r1.action == "update"
        assert entity_id is not None
        assert _compute_merge_fields(db, entity_id, payload) == {}


def test_geo_proximity_constant() -> None:
    assert GEO_PROXIMITY_THRESHOLD_M == 50.0


def test_source_priority_ordering() -> None:
    assert SOURCE_PRIORITY["operator"] < SOURCE_PRIORITY["google_places"]
    assert SOURCE_PRIORITY["google_places"] < SOURCE_PRIORITY["osm"]
    assert SOURCE_PRIORITY["osm"] < SOURCE_PRIORITY["lhc_open_data"]
    assert SOURCE_PRIORITY["az_roc"] == SOURCE_PRIORITY["lhc_open_data"]
    assert SOURCE_PRIORITY["npi_registry"] == SOURCE_PRIORITY["usapickleball"]
    assert SOURCE_PRIORITY["pdga"] == SOURCE_PRIORITY["usapickleball"]


def test_reconcile_hit_does_not_add_pending_objects() -> None:
    with SessionLocal() as db:
        before = len(db.new)
        payload = EntityPayload(name="Ghost", entity_type="place", source="osm")
        reconcile_hit(db, payload)
        assert len(db.new) == before


def test_reconciler_subprocess_import_chain() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "from app.contrib.ingest_reconciler import reconcile_hit  # noqa: F401\n"
        "import json\n"
        "print(json.dumps({'ok': True}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
        env={**os.environ, "AUTH_DEV_MODE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_multiple_geo_name_matches_ambiguous() -> None:
    from uuid import uuid4

    u = uuid4().hex[:8]
    with SessionLocal() as db:
        for i, slug_s in enumerate([f"dup-a-{u}", f"dup-b-{u}"]):
            pid = f"rec-dup-{u}-{i}"
            p = Provider(
                id=pid,
                provider_name="Twin Park",
                category="retail",
                source="osm",
                slug=slug_s,
                lat=34.5000 + i * 0.00001,
                lng=-114.3500,
            )
            db.add(p)
            create_provider_and_entity(db, p)
        db.commit()

    with SessionLocal() as db:
        payload = EntityPayload(
            name="Twin Park",
            entity_type="place",
            lat=34.5000,
            lng=-114.3500,
            google_place_id=None,
            source="google_places",
        )
        r = reconcile_hit(db, payload)
        assert r.action == "ambiguous"
