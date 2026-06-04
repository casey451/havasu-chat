"""Tests for scripts/import_schedule_hunt_entities.py.

The classification logic (``build_plan`` + helpers) is pure and tested without a
DB. One end-to-end test exercises ``apply_plan`` against the isolated session DB
from conftest.py and cleans up after itself.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import ContactPoint, Entity, EntityCategory, Location
from scripts.import_schedule_hunt_entities import (
    _SOURCE_TAG,
    CsvVenue,
    ExistingEntity,
    apply_plan,
    best_match,
    build_plan,
    category_slug_for,
    has_hash_suffix,
    normalize_name,
    strip_hash_suffix,
)

# --- pure helpers -------------------------------------------------------


def test_hash_suffix_detection() -> None:
    assert has_hash_suffix("Bridge City Combat 3f9a2b1c")
    assert has_hash_suffix("Bridge City Combat-9c8d7e6f")
    # Real names must not be flagged.
    assert not has_hash_suffix("Iron Age Gym")
    assert not has_hash_suffix("Anytime Fitness")
    assert not has_hash_suffix("CrossFit 928")  # too short to be a hash
    assert not has_hash_suffix("Decade Studio")  # hex letters but no digit


def test_strip_hash_suffix() -> None:
    assert strip_hash_suffix("Bridge City Combat 3f9a2b1c") == "Bridge City Combat"
    assert strip_hash_suffix("Iron Age Gym") == "Iron Age Gym"


def test_normalize_and_best_match() -> None:
    assert normalize_name("Fiore's Endorphin Factory") == "fiore endorphin factory"
    # Possessive + punctuation variants still match.
    assert best_match("Fiore's Endorphin Factory", ["Fiores Endorphin Factory"]) == (
        "Fiores Endorphin Factory"
    )
    # Distinct businesses do not match.
    assert best_match("Iron Age Gym", ["Planet Fitness", "Anytime Fitness"]) is None


def test_category_mapping() -> None:
    assert category_slug_for("gym") == "classes-sports-recreation"
    assert category_slug_for("martial arts/MMA") == "classes-sports-recreation"
    assert category_slug_for("scuba school") == "on-the-water"
    assert category_slug_for("library programs") == "public-civic-resources"
    assert category_slug_for("youth baseball") == "classes-sports-recreation"
    assert category_slug_for("dog training") == "pets"
    assert category_slug_for("something unmapped") is None


# --- classification -----------------------------------------------------


def test_build_plan_classifies_all_buckets() -> None:
    venues = [
        CsvVenue("Iron Age Gym", "gym", "http://ironagegym.com", "", "1880 Commander Dr"),
        CsvVenue("Bridge City Combat", "martial arts/MMA", "", "https://fb.com/bcc", "2143 McCulloch"),
        CsvVenue("Brand New Yoga Studio", "yoga", "", "", "100 Main St"),
    ]
    existing = [
        # A real entity that the first venue should match -> "already in DB".
        ExistingEntity(id="e-iron", name="Iron Age Gym", source="seed", is_active=True),
        # A hash-suffixed fixture shadowing a real CSV business -> keep & fix.
        ExistingEntity(id="e-bcc1", name="Bridge City Combat 3f9a2b1c", source="test-tier2", is_active=True),
        # A test-source fixture that shadows nothing -> quarantine.
        ExistingEntity(id="e-junk", name="Zzz Placeholder Co", source="test-seed", is_active=True),
    ]
    plan = build_plan(venues, existing)

    new_names = {p.venue.name for p in plan.new}
    assert "Brand New Yoga Studio" in new_names
    # Bridge City Combat is real but only exists as fixtures -> proposed new.
    assert "Bridge City Combat" in new_names
    # Iron Age Gym already exists -> not new.
    assert "Iron Age Gym" not in new_names
    assert any(csv == "Iron Age Gym" for csv, _ in plan.existing_matches)

    quarantined_ids = {e.id for e in plan.quarantine}
    keepfix_ids = {e.id for e, _ in plan.keep_fix}
    assert "e-bcc1" in keepfix_ids  # shadows Bridge City Combat
    assert "e-junk" in quarantined_ids
    assert "e-bcc1" not in quarantined_ids  # never both


def test_new_proposals_have_unique_slugs() -> None:
    venues = [
        CsvVenue("Studio A", "yoga", "", "", ""),
        CsvVenue("Studio A", "pilates", "", "", ""),  # duplicate name
    ]
    plan = build_plan(venues, existing=[])
    slugs = [p.slug for p in plan.new]
    assert len(slugs) == len(set(slugs))  # no collisions within the batch


# --- apply (end-to-end against the test DB) -----------------------------


@pytest.fixture
def _cleanup_import() -> None:
    yield
    with SessionLocal() as db:
        ids = [e.id for e in db.query(Entity.id).filter(Entity.source == _SOURCE_TAG)]
        # Order matters: satellites reference entity_id.
        for table in (Location, ContactPoint, EntityCategory):
            db.execute(delete(table).where(table.entity_id.in_(ids)))
        db.execute(delete(Entity).where(Entity.source == _SOURCE_TAG))
        db.execute(delete(Entity).where(Entity.id == "fixture-quarantine-me"))
        db.commit()


def test_apply_creates_entity_with_satellites_and_quarantines(_cleanup_import: None) -> None:
    with SessionLocal() as db:
        db.add(
            Entity(
                id="fixture-quarantine-me",
                entity_type="commercial",
                slug="fixture-quarantine-me",
                name="Lonely Test Fixture",
                source="test-seed",
                is_active=True,
            )
        )
        db.commit()

    venues = [CsvVenue("Zzq Unique Venue", "gym", "http://example.com", "https://fb.com/zzq", "5 Lake Ave")]
    with SessionLocal() as db:
        from scripts.import_schedule_hunt_entities import load_existing

        plan = build_plan(venues, load_existing(db))
        assert len(plan.new) == 1
        assert any(e.id == "fixture-quarantine-me" for e in plan.quarantine)
        apply_plan(db, plan)

    with SessionLocal() as db:
        ent = db.query(Entity).filter(Entity.source == _SOURCE_TAG).one()
        assert ent.name == "Zzq Unique Venue"
        loc = db.query(Location).filter(Location.entity_id == ent.id).one()
        assert loc.city == "Lake Havasu City"
        kinds = {c.kind for c in db.query(ContactPoint).filter(ContactPoint.entity_id == ent.id)}
        assert {"website", "facebook"} <= kinds
        # gym -> health category attached.
        assert db.query(EntityCategory).filter(EntityCategory.entity_id == ent.id).count() == 1
        # Fixture got deactivated, not deleted.
        fixture = db.get(Entity, "fixture-quarantine-me")
        assert fixture is not None and fixture.is_active is False
