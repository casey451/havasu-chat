"""Phase 5 — osm_overpass_load script."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from app.contrib.ingest_reconciler import ReconcileResult
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from app.db.seed_helpers import derive_provider_slug
from scripts.osm_overpass_load import ingest_rows


def test_osm_overpass_load_filters_wrapper_elements(tmp_path: Path) -> None:
    wrapper = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 34.5,
                "lon": -114.35,
                "tags": {"leisure": "marina", "name": "A"},
            },
            {"type": "node", "id": 2, "lat": 34.51, "lon": -114.36, "tags": {"natural": "tree"}},
        ]
    }
    p = tmp_path / "osm.jsonl"
    p.write_text(json.dumps(wrapper) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows, tag="leisure", value="marina", category_slug="on-the-water", dry_run=True
    )
    assert counts["elements_seen"] == 1
    assert counts["payloads_ready"] == 1


def test_osm_overpass_load_inserts_provider(tmp_path: Path) -> None:
    uid = uuid.uuid4().hex[:10]
    name = f"OSM Test Marina {uid}"
    row = {
        "type": "node",
        "id": 4242,
        "lat": 34.101,
        "lon": -113.801,
        "tags": {"leisure": "marina", "name": name},
    }
    p = tmp_path / "osm2.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )
    assert counts["inserted"] == 1

    with SessionLocal() as db:
        q = select(Provider).where(Provider.provider_name == name)
        prov = db.scalars(q).first()
        assert prov is not None
        assert prov.source == "osm"
        assert prov.verified is False
        assert prov.google_place_id is None
        assert prov.tier == "free"


def _seed_google_like_provider(
    *,
    uid: str,
    phone: str | None,
    website: str | None,
    address: str | None,
    description: str | None,
) -> tuple[str, str, float, float, str]:
    """Returns ``entity_id``, venue ``name``, ``lat``, ``lng``, ``google_place_id``."""
    name = f"OSM Pri Marina {uid}"
    lat, lng = 34.472, -114.348
    google_place_id = f"ChIJseed_{uid}"
    with SessionLocal() as session:
        cat_id = session.scalars(select(Category.id).where(Category.slug == "on-the-water")).first()
        slug = derive_provider_slug(session, name)
        prov = Provider(
            provider_name=name,
            category="on-the-water",
            category_id=cat_id,
            address=address,
            phone=phone,
            website=website,
            description=description,
            google_place_id=google_place_id,
            lat=lat,
            lng=lng,
            zip="86403",
            slug=slug,
            source="google_places",
            enrichment_version="places_test_v1",
            last_google_scraped_at=None,
            is_active=True,
            verified=True,
            draft=False,
            pending_review=False,
            tier="premium",
        )
        session.add(prov)
        create_provider_and_entity(session, prov)
        session.commit()
        eid = prov.entity_id
        assert eid is not None
    return eid, name, lat, lng, google_place_id


@patch("app.contrib.scraper_ingest.reconcile_hit")
def test_osm_reconcile_update_preserves_identity_and_populated_contact(
    mock_rec, tmp_path: Path
) -> None:
    uid = uuid.uuid4().hex[:10]
    entity_id, name, lat, lng, google_place_id = _seed_google_like_provider(
        uid=uid,
        phone="555-GOOGLE",
        website="https://google.example/p",
        address="100 Google Way",
        description="From Google",
    )
    mock_rec.return_value = ReconcileResult(
        action="update",
        existing_id=entity_id,
        merge_fields={},
    )
    row = {
        "type": "node",
        "id": 9001,
        "lat": lat,
        "lon": lng,
        "tags": {
            "leisure": "marina",
            "name": name,
            "phone": "+19285559999",
            "website": "https://osm-would-clobber.example",
            "addr:full": "OSM Full Address Would Clobber",
        },
    }
    p = tmp_path / "upd1.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )
    assert counts["updated"] == 1
    assert counts["inserted"] == 0

    with SessionLocal() as db:
        prov = db.scalars(select(Provider).where(Provider.entity_id == entity_id)).one()
        assert prov.verified is True
        assert prov.google_place_id == google_place_id
        assert prov.source == "google_places"
        assert prov.tier == "premium"
        assert prov.enrichment_version == "places_test_v1"
        assert prov.zip == "86403"
        assert prov.category == "on-the-water"
        assert prov.phone == "555-GOOGLE"
        assert prov.website == "https://google.example/p"
        assert prov.address == "100 Google Way"
        assert prov.description == "From Google"


@patch("app.contrib.scraper_ingest.reconcile_hit")
def test_osm_reconcile_update_fills_empty_contact_fields(mock_rec, tmp_path: Path) -> None:
    uid = uuid.uuid4().hex[:10]
    entity_id, name, lat, lng, google_place_id = _seed_google_like_provider(
        uid=uid,
        phone=None,
        website=None,
        address=None,
        description=None,
    )
    mock_rec.return_value = ReconcileResult(
        action="update",
        existing_id=entity_id,
        merge_fields={},
    )
    row = {
        "type": "node",
        "id": 9002,
        "lat": lat,
        "lon": lng,
        "tags": {
            "leisure": "marina",
            "name": name,
            "phone": "+19285551111",
            "website": "https://osm-fill.example",
            "addr:full": "200 OSM Street",
            "description": "Filled from OSM tags",
        },
    }
    p = tmp_path / "upd2.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )
    assert counts["updated"] == 1

    with SessionLocal() as db:
        prov = db.scalars(select(Provider).where(Provider.entity_id == entity_id)).one()
        assert prov.phone == "+19285551111"
        assert prov.website == "https://osm-fill.example"
        assert prov.address == "200 OSM Street"
        assert prov.description == "Filled from OSM tags"
        assert prov.source == "google_places"
        assert prov.google_place_id == google_place_id


@patch("app.contrib.scraper_ingest.reconcile_hit")
def test_osm_reconcile_ambiguous_holds_for_review(mock_rec, tmp_path: Path) -> None:
    # Funnel-adoption behavior change: an ambiguous reconcile no longer DROPS the
    # OSM element. It now lands HELD (draft + pending_review) via decide_ingest's
    # should_hide, so the row is captured for the admin review queue but hidden
    # from users (every consumption query filters draft=False).
    uid = uuid.uuid4().hex[:10]
    name = f"OSM Ambiguous Marina {uid}"
    mock_rec.return_value = ReconcileResult(
        action="ambiguous",
        existing_id="some-other-entity",
        reason="geo within 50m but name differs",
    )
    row = {
        "type": "node",
        "id": 9100,
        "lat": 34.461,
        "lon": -114.341,
        "tags": {"leisure": "marina", "name": name},
    }
    p = tmp_path / "amb.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )
    assert counts["inserted_pending"] == 1
    assert counts["inserted"] == 0

    with SessionLocal() as db:
        prov = db.scalars(select(Provider).where(Provider.provider_name == name)).one()
        assert prov.draft is True
        assert prov.pending_review is True
        assert prov.source == "osm"
        # Cleanup: this test writes a real row (not in the update path).
        eid = prov.entity_id
        db.delete(prov)
        if eid:
            from app.db.models import Entity

            ent = db.get(Entity, eid)
            if ent is not None:
                db.delete(ent)
        db.commit()


@patch("app.contrib.scraper_ingest.reconcile_hit")
def test_osm_reconcile_update_fills_empty_string_contact_fields(mock_rec, tmp_path: Path) -> None:
    uid = uuid.uuid4().hex[:10]
    entity_id, name, lat, lng, _gpid = _seed_google_like_provider(
        uid=uid,
        phone="",
        website="",
        address="",
        description="",
    )
    mock_rec.return_value = ReconcileResult(
        action="update",
        existing_id=entity_id,
        merge_fields={},
    )
    row = {
        "type": "node",
        "id": 9003,
        "lat": lat,
        "lon": lng,
        "tags": {
            "leisure": "marina",
            "name": name,
            "phone": "+19285552222",
            "addr:full": "Empty-string gap fill",
        },
    }
    p = tmp_path / "upd3.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    ingest_rows(
        rows,
        tag="leisure",
        value="marina",
        category_slug="on-the-water",
        dry_run=False,
    )

    with SessionLocal() as db:
        prov = db.scalars(select(Provider).where(Provider.entity_id == entity_id)).one()
        assert prov.phone == "+19285552222"
        assert prov.address == "Empty-string gap fill"
