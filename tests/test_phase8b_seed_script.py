"""Phase 8b — Layer 5 seed script tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, select

from app.db.database import SessionLocal
from app.db.models import Category, ContactPoint, Entity, EntityCategory, Feature, Hours, Location
from scripts.ingest.lhc_civic_scrape import CivicEntityRecord, _cat13_id, upsert_civic_entity
from scripts.seed_cat13_civic import SEED_ENTITIES, run_seed


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _cleanup_seed_rows(db, names: list[str]) -> None:
    if not names:
        return
    ents = db.scalars(select(Entity).where(Entity.name.in_(names))).all()
    eids = [e.id for e in ents]
    if not eids:
        return
    db.execute(delete(ContactPoint).where(ContactPoint.entity_id.in_(eids)))
    db.execute(delete(Hours).where(Hours.entity_id.in_(eids)))
    db.execute(delete(Feature).where(Feature.entity_id.in_(eids)))
    db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(eids)))
    db.execute(delete(Location).where(Location.entity_id.in_(eids)))
    db.execute(delete(Entity).where(Entity.id.in_(eids)))
    db.commit()


def test_seed_entities_list_count() -> None:
    assert len(SEED_ENTITIES) >= 10


def test_upsert_insert_then_noop(db) -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"Phase8b Test Civic {suf}"
    addr = f"100 Test Blvd, Lake Havasu City, AZ 86403 {suf}"
    rec = CivicEntityRecord(
        name=name,
        address=addr,
        website="https://example.com/civic",
        sub_category="civic_org",
        source="test_phase8b",
    )
    cat_id = _cat13_id(db)
    try:
        assert upsert_civic_entity(db, rec, cat_id=cat_id) == "insert"
        db.commit()
        assert upsert_civic_entity(db, rec, cat_id=cat_id) == "noop"
        db.commit()
    finally:
        _cleanup_seed_rows(db, [name])


def test_upsert_idempotent_on_name_address(db) -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"Phase8b Idempotent {suf}"
    addr = f"200 Idempotent Rd, Lake Havasu City, AZ 86403 {suf}"
    rec = CivicEntityRecord(name=name, address=addr, source="test_phase8b")
    cat_id = _cat13_id(db)
    try:
        upsert_civic_entity(db, rec, cat_id=cat_id)
        db.commit()
        updated = CivicEntityRecord(
            name=name,
            address=addr,
            description="Updated description",
            source="test_phase8b",
        )
        action = upsert_civic_entity(db, updated, cat_id=cat_id)
        assert action == "update"
        db.commit()
        ent = db.scalars(select(Entity).where(func.lower(Entity.name) == name.lower())).one()
        assert ent.description == "Updated description"
    finally:
        _cleanup_seed_rows(db, [name])


def test_run_seed_dry_run_does_not_persist(db) -> None:
    before = db.scalars(
        select(func.count())
        .select_from(Entity)
        .join(EntityCategory)
        .join(Category)
        .where(Category.slug == "public-civic-resources", Entity.source == "seed_cat13_civic")
    ).one()
    stats = run_seed(dry_run=True)
    after = db.scalars(
        select(func.count())
        .select_from(Entity)
        .join(EntityCategory)
        .join(Category)
        .where(Category.slug == "public-civic-resources", Entity.source == "seed_cat13_civic")
    ).one()
    assert after == before
    assert stats["insert"] + stats["update"] + stats["noop"] == len(SEED_ENTITIES)


def test_seed_entity_has_website_contact(db) -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"Phase8b Portal {suf}"
    addr = f"300 Portal Ln, Lake Havasu City, AZ 86403 {suf}"
    rec = CivicEntityRecord(
        name=name,
        address=addr,
        website="https://portal.example.gov/pay",
        sub_category="payment_licensing",
        source="test_phase8b",
    )
    cat_id = _cat13_id(db)
    try:
        upsert_civic_entity(db, rec, cat_id=cat_id)
        db.commit()
        ent = db.scalars(select(Entity).where(Entity.name == name)).one()
        cp = db.scalars(
            select(ContactPoint).where(
                ContactPoint.entity_id == ent.id,
                ContactPoint.kind == "website",
            )
        ).one()
        assert "portal.example.gov" in cp.value
    finally:
        _cleanup_seed_rows(db, [name])
