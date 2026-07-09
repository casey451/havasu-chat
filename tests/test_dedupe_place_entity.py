"""Tests for ``scripts/dedupe_place_entity.py`` (retire place-only dup entity)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Entity, EntityCategory, Provider

ROOT = Path(__file__).resolve().parents[1]
NAME = "Next Generation Mixed Martial Arts"
LEAF_ID = 30


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "dedupe_place_entity.py"
    spec = importlib.util.spec_from_file_location("dedupe_place_entity", path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_leaf(db: Session) -> None:
    db.add(Category(id=LEAF_ID, slug="martial-arts", name="Martial Arts", level=1, parent_id=1))
    db.flush()


def _seed_keeper(db: Session) -> Provider:
    p = Provider(provider_name=NAME, category="fitness_sports", is_active=True, draft=False,
                 category_id=LEAF_ID, slug="next-generation-mixed-martial-arts-2")
    db.add(p)
    create_provider_and_entity(db, p)
    db.flush()
    return p


def _seed_place_dup(db: Session, slug: str = "next-gen-place") -> Entity:
    e = Entity(entity_type="commercial", slug=slug, name=NAME, is_active=True)
    db.add(e)
    db.flush()
    db.add(EntityCategory(entity_id=e.id, category_id=LEAF_ID, is_primary=True))
    db.flush()
    return e


def test_dry_run_diagnoses_without_writing(mod, db) -> None:
    _seed_leaf(db)
    _seed_keeper(db)
    dup = _seed_place_dup(db)
    db.commit()
    c = mod.run(db, apply=False)
    assert c["would_deactivate"] == 1 and c["deactivated"] == 0
    db.refresh(dup)
    assert dup.is_active is True


def test_apply_deactivates_place_dup(mod, db) -> None:
    _seed_leaf(db)
    keeper = _seed_keeper(db)
    dup = _seed_place_dup(db)
    db.commit()
    undo: list = []
    c = mod.dedupe(db, apply=True, undo=undo)
    db.commit()
    assert c["deactivated"] == 1
    db.refresh(dup)
    assert dup.is_active is False
    # Keeper entity untouched.
    keeper_entity = db.get(Entity, keeper.entity_id)
    assert keeper_entity.is_active is True
    assert undo and undo[0]["op"] == "deactivate_entity"


def test_refuses_when_dup_has_references(mod, db, monkeypatch) -> None:
    _seed_leaf(db)
    _seed_keeper(db)
    dup = _seed_place_dup(db)
    db.commit()
    monkeypatch.setattr(mod, "_ref_counts", lambda _db, _eid: {"events": 1})
    c = mod.dedupe(db, apply=True, undo=[])
    assert c["has_references"] == 1 and c["deactivated"] == 0
    db.refresh(dup)
    assert dup.is_active is True  # untouched — references must be repointed first


def test_skips_when_no_provider_keeper(mod, db) -> None:
    # Two place-only entities, neither provider-backed -> no keeper, skip.
    _seed_leaf(db)
    _seed_place_dup(db, slug="p1")
    _seed_place_dup(db, slug="p2")
    db.commit()
    c = mod.dedupe(db, apply=True, undo=[])
    assert c["skipped"] == 1 and c["deactivated"] == 0


def test_skips_when_no_place_dup(mod, db) -> None:
    # Only the provider-backed keeper -> nothing to retire.
    _seed_leaf(db)
    _seed_keeper(db)
    db.commit()
    c = mod.dedupe(db, apply=True, undo=[])
    assert c["skipped"] == 1 and c["deactivated"] == 0


def test_leaf_missing_is_skipped(mod, db) -> None:
    c = mod.dedupe(db, apply=True, undo=[])  # no leaf seeded
    assert c["leaf_missing"] == 1 and c["deactivated"] == 0
