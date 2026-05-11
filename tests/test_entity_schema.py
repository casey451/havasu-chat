"""Phase 1A — ENTITY schema shape + ORM wiring (additive migration only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine
from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_PROGRAM,
    ENTITY_TYPES,
    is_valid_entity_type,
)
from app.db.models import (
    Category,
    ContactPoint,
    Entity,
    EntityCategory,
    Hours,
    Location,
)

_ENTITY_EXTENSION_TABLES = (
    "entity_categories",
    "locations",
    "hours",
    "seasonal_hours",
    "contact_points",
    "features",
    "offerings",
    "service_areas",
    "schedules",
    "source_evidence",
    "sponsorship_slots",
)


def _now() -> datetime:
    return datetime.now(UTC)


def test_entities_table_exists_after_migration() -> None:
    """entities exists with expected columns (names + rough SQLite kinds)."""
    insp = inspect(engine)
    assert insp.has_table("entities")
    cols = {c["name"]: c for c in insp.get_columns("entities")}
    assert set(cols) >= {
        "id",
        "entity_type",
        "slug",
        "name",
        "description",
        "last_verified_at",
        "source",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert cols["entity_type"]["nullable"] is False
    assert cols["slug"]["nullable"] is False


def test_entity_type_column_nullable_false() -> None:
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("entities")}
    assert cols["entity_type"]["nullable"] is False


def test_entity_slug_unique() -> None:
    suf = uuid.uuid4().hex[:8]
    slug = f"dup-slug-{suf}"
    now = _now()
    with SessionLocal() as db:
        db.add(
            Entity(
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="First",
                source="test",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        db.add(
            Entity(
                entity_type=ENTITY_TYPE_COMMERCIAL,
                slug=slug,
                name="Second",
                source="test",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("table_name", _ENTITY_EXTENSION_TABLES)
def test_entity_extension_tables_exist(table_name: str) -> None:
    insp = inspect(engine)
    assert insp.has_table(table_name)


def test_entity_category_unique_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        cat = db.query(Category).filter_by(slug="pets").one()
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"ec-uq-{suf}",
            name="EC UQ",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()

        db.add(
            EntityCategory(
                entity_id=e.id,
                category_id=cat.id,
                is_primary=True,
                created_at=now,
            )
        )
        db.flush()
        db.add(
            EntityCategory(
                entity_id=e.id,
                category_id=cat.id,
                is_primary=False,
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_location_one_to_one_with_entity() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"loc-uq-{suf}",
            name="Loc UQ",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        db.add(
            Location(
                entity_id=e.id,
                address="123 Main",
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        db.add(
            Location(
                entity_id=e.id,
                address="456 Other",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_contact_point_polymorphic_kinds() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"cp-kinds-{suf}",
            name="Contact kinds",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        for kind, val in (
            ("phone", "555-0100"),
            ("email", "a@example.com"),
            ("website", "https://example.com"),
            ("facebook", "https://facebook.com/x"),
        ):
            db.add(
                ContactPoint(
                    entity_id=e.id,
                    kind=kind,
                    value=val,
                    created_at=now,
                )
            )
        db.commit()


def test_sponsor_entity_type_column_exists() -> None:
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("sponsors")}
    assert "entity_type" in cols
    assert cols["entity_type"]["nullable"] is True


def test_entity_relationships_navigable() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"rel-{suf}",
            name="Rel test",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        db.add(
            Location(
                entity_id=e.id,
                city="Lake Havasu City",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Hours(
                entity_id=e.id,
                day_of_week=0,
                opens_at=time(9, 0),
                closes_at=time(17, 0),
                created_at=now,
            )
        )
        db.add(
            Hours(
                entity_id=e.id,
                day_of_week=1,
                opens_at=time(10, 0),
                closes_at=time(18, 0),
                created_at=now,
            )
        )
        db.add(
            ContactPoint(
                entity_id=e.id,
                kind="phone",
                value="555-0199",
                created_at=now,
            )
        )
        db.commit()
        eid = e.id

    with SessionLocal() as db:
        loaded = db.get(Entity, eid)
        assert loaded is not None
        db.refresh(loaded, ["location", "hours", "contact_points"])
        assert loaded.location is not None
        assert loaded.location.city == "Lake Havasu City"
        assert len(loaded.hours) == 2
        assert len(loaded.contact_points) == 1


def test_entity_cascade_delete() -> None:
    """SQLite enforces ON DELETE CASCADE only when foreign_keys pragma is on."""
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"cascade-{suf}",
            name="Cascade",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        db.add(
            Location(
                entity_id=e.id,
                address="1 Cascade Way",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Hours(
                entity_id=e.id,
                day_of_week=2,
                opens_at=time(8, 0),
                closes_at=time(12, 0),
                created_at=now,
            )
        )
        db.add(
            ContactPoint(
                entity_id=e.id,
                kind="email",
                value="cascade@example.com",
                created_at=now,
            )
        )
        db.commit()
        eid = e.id

    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        ent = db.get(Entity, eid)
        assert ent is not None
        db.delete(ent)
        db.commit()

    with SessionLocal() as db:
        assert db.get(Entity, eid) is None
        assert db.query(Location).filter_by(entity_id=eid).count() == 0
        assert db.query(Hours).filter_by(entity_id=eid).count() == 0
        assert db.query(ContactPoint).filter_by(entity_id=eid).count() == 0

    # PRAGMA foreign_keys=ON is per SQLite connection; pooling can hand the same
    # connection to later tests and break suites that rely on FK checks being off
    # for deletes (e.g. chat_logs teardown). Drop pooled connections after this test.
    engine.dispose()


def test_entity_type_constants() -> None:
    assert ENTITY_TYPES == frozenset(
        {
            ENTITY_TYPE_COMMERCIAL,
            ENTITY_TYPE_PLACE,
            ENTITY_TYPE_EVENT,
            ENTITY_TYPE_PROGRAM,
        }
    )
    assert len(ENTITY_TYPES) == 4
    assert is_valid_entity_type("commercial") is True
    assert is_valid_entity_type("not-a-type") is False
