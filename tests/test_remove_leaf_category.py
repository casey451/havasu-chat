"""Tests for ``scripts/remove_leaf_category.py`` (gated empty-leaf delete)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import Category, Entity, EntityCategory

ROOT = Path(__file__).resolve().parents[1]
SLUG = "swim-and-aquatics"


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "remove_leaf_category.py"
    spec = importlib.util.spec_from_file_location("remove_leaf_category", path)
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


def _seed_leaf(db: Session, cid: int = 99) -> Category:
    db.add(Category(id=6, slug="fitness-and-wellness", name="Fitness", level=0))
    leaf = Category(id=cid, slug=SLUG, name="Swim & Aquatics", level=1, parent_id=6, sort_order=6)
    db.add(leaf)
    db.flush()
    return leaf


def test_deletes_empty_leaf(mod, db) -> None:
    _seed_leaf(db)
    db.commit()
    undo: list = []
    c = mod.remove_leaves(db, apply=True, undo=undo)
    assert c["deleted"] == 1
    assert db.scalar(select(Category).where(Category.slug == SLUG)) is None
    assert undo and undo[0]["op"] == "delete_category" and undo[0]["slug"] == SLUG


def test_dry_run_deletes_nothing(mod, db) -> None:
    _seed_leaf(db)
    db.commit()
    c = mod.remove_leaves(db, apply=False, undo=[])
    assert c["would_delete"] == 1 and c["deleted"] == 0
    assert db.scalar(select(Category).where(Category.slug == SLUG)) is not None


def test_refuses_when_leaf_has_listings(mod, db) -> None:
    leaf = _seed_leaf(db)
    ent = Entity(entity_type="commercial", slug="e1", name="A Swim Co")
    db.add(ent)
    db.flush()
    db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    db.commit()
    c = mod.remove_leaves(db, apply=True, undo=[])
    assert c["not_empty"] == 1 and c["deleted"] == 0
    assert db.scalar(select(Category).where(Category.slug == SLUG)) is not None


def test_refuses_when_leaf_has_children(mod, db) -> None:
    leaf = _seed_leaf(db)
    db.add(Category(slug="child", name="Child", level=2, parent_id=leaf.id))
    db.commit()
    c = mod.remove_leaves(db, apply=True, undo=[])
    assert c["not_empty"] == 1 and c["deleted"] == 0


def test_not_found_is_noop(mod, db) -> None:
    db.add(Category(id=6, slug="fitness-and-wellness", name="Fitness", level=0))
    db.commit()
    c = mod.remove_leaves(db, apply=True, undo=[])
    assert c["not_found"] == 1 and c["deleted"] == 0
