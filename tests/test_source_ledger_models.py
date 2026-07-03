"""Schema tests for the source-parity additions (PR B).

Covers the new Provider/Event columns, the two ledger tables, and that the two
new leaves are seeded under the correct departments.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect

from app.db.database import SessionLocal, engine
from app.db.models import (
    Entity,
    Event,
    Provider,
    SourceEvent,
    SourceListing,
)

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"

_MODULE_SEED = "_MODULE_SEED_SOURCE"


def test_new_columns_exist() -> None:
    cols = {c["name"] for c in inspect(engine).get_columns("providers")}
    assert {"region", "category_provenance"} <= cols
    ecols = {c["name"] for c in inspect(engine).get_columns("events")}
    assert {"category", "region"} <= ecols


def test_ledger_tables_exist() -> None:
    tables = set(inspect(engine).get_table_names())
    assert {"source_listings", "source_events"} <= tables


def test_provider_region_and_provenance_roundtrip() -> None:
    with SessionLocal() as db:
        ent = Entity(
            entity_type="commercial",
            slug=f"region-test-{uuid4().hex[:10]}",
            name="Region Test Co",
            source=_MODULE_SEED,
        )
        db.add(ent)
        db.flush()
        p = Provider(
            provider_name="Region Test Co",
            category="test",
            entity_id=ent.id,
            region="parker",
            category_provenance="source_crosswalk",
            source=_MODULE_SEED,
        )
        db.add(p)
        db.commit()
        got = db.get(Provider, p.id)
        assert got is not None
        assert got.region == "parker"
        assert got.category_provenance == "source_crosswalk"
        db.delete(got)
        db.delete(db.get(Entity, ent.id))
        db.commit()


def test_event_category_roundtrip() -> None:
    with SessionLocal() as db:
        ent = Entity(
            entity_type="event",
            slug=f"cat-test-{uuid4().hex[:10]}",
            name="Cat Test Event",
            source=_MODULE_SEED,
        )
        db.add(ent)
        db.flush()
        ev = Event(
            title="Cat Test Event",
            normalized_title="cat test event",
            date=date(2026, 7, 4),
            start_time=time(9, 0),
            location_name="Rotary Park",
            location_normalized="rotary park",
            description="x",
            entity_id=ent.id,
            category="festival",
            region="havasu-core",
            source=_MODULE_SEED,
        )
        db.add(ev)
        db.commit()
        got = db.get(Event, ev.id)
        assert got is not None
        assert got.category == "festival"
        assert got.region == "havasu-core"
        db.delete(got)
        db.delete(db.get(Entity, ent.id))
        db.commit()


def test_source_listing_and_event_insert() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        sl = SourceListing(
            source="go_lake_havasu",
            source_url="https://example.com/partner/acme",
            source_category="Charters",
            name="Acme Charters",
            region="havasu-core",
            mapped_leaf="boat-tours-and-charters",
            match_status="missing",
            first_seen=now,
            last_seen=now,
        )
        se = SourceEvent(
            source="river_scene",
            source_url="https://example.com/event/parade",
            source_category="festival",
            title="Parade",
            event_date=date(2026, 7, 4),
            region="havasu-core",
            mapped_category="festival",
            match_status="excluded",
            exclusion_reason="outside-service-area",
            first_seen=now,
            last_seen=now,
        )
        db.add_all([sl, se])
        db.commit()
        assert db.get(SourceListing, sl.id).mapped_leaf == "boat-tours-and-charters"
        assert db.get(SourceEvent, se.id).exclusion_reason == "outside-service-area"
        db.delete(db.get(SourceListing, sl.id))
        db.delete(db.get(SourceEvent, se.id))
        db.commit()


def test_new_leaves_seeded_under_correct_departments() -> None:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    assert "wildlife-and-nature" in data["outdoors-and-recreation"]["leaves"]
    assert "event-venues" in data["things-to-do-and-attractions"]["leaves"]
