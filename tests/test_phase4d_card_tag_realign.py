"""Tests for ``scripts/phase4d_card_tag_realign.py`` (card subtype chip realign).

importlib load + in-memory DB. Verifies the leaf->chip map is valid, that a
re-filed row's stale ``subcategory`` is set to the mapped chip (or blanked), that
dry-run writes nothing, and that the no-guess guards (no_match / not_on_leaf /
already_correct) fire.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories.subcategories import subcategory_by_slug
from app.db.database import Base
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider

ROOT = Path(__file__).resolve().parents[1]

# Leaf slug -> Category.id used across the tests.
LEAF_IDS = {
    "martial-arts": 30,
    "dance-studios": 31,
    "yoga-and-pilates": 32,
    "personal-training": 34,
    "nutrition-and-wellness": 35,
    "sporting-goods": 40,
}


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "phase4d_card_tag_realign.py"
    spec = importlib.util.spec_from_file_location("phase4d_card_tag_realign", path)
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


def _seed_leaves(db: Session) -> dict[str, int]:
    for slug, cid in LEAF_IDS.items():
        db.add(Category(id=cid, slug=slug, name=slug.title(), level=1, parent_id=1))
    db.flush()
    return dict(LEAF_IDS)


def _seed_provider(db: Session, name: str, leaf_id: int, subcat: str | None) -> Provider:
    p = Provider(
        provider_name=name,
        category="fitness_sports",
        is_active=True,
        draft=False,
        category_id=leaf_id,
        subcategory=subcat,
        slug=name.lower().replace(" ", "-"),
    )
    db.add(p)
    create_provider_and_entity(db, p)
    db.flush()
    return p


# ------------------------------ map -------------------------------------- #
def test_chip_map_is_valid(mod) -> None:
    mod._validate_chip_map()  # must not raise
    for leaf, chip in mod.LEAF_TO_CHIP.items():
        if chip is not None:
            assert subcategory_by_slug(chip) is not None, (leaf, chip)


def test_every_spec_leaf_has_a_chip_mapping(mod) -> None:
    assert {s.leaf for s in mod.REALIGN_SPECS} <= set(mod.LEAF_TO_CHIP)


# ----------------------------- realign ----------------------------------- #
def test_sets_martial_chip(mod, db) -> None:
    cat = _seed_leaves(db)
    prov = _seed_provider(db, "Seibukan Karate-Do", cat["martial-arts"], "kids-lessons")
    db.commit()
    undo: list = []
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=undo)
    assert c["set"] == 1
    db.refresh(prov)
    assert prov.subcategory == "martial-arts"
    assert undo and undo[0]["prior_subcategory"] == "kids-lessons"


def test_blanks_nutrition_chip(mod, db) -> None:
    cat = _seed_leaves(db)
    prov = _seed_provider(db, "Nutrition One", cat["nutrition-and-wellness"], "personal-training")
    db.commit()
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=[])
    assert c["set"] == 1
    db.refresh(prov)
    assert prov.subcategory is None  # blanked — no honest chip


def test_sets_biking_for_bike_shop(mod, db) -> None:
    cat = _seed_leaves(db)
    prov = _seed_provider(db, "Havasu Bike and Fitness", cat["sporting-goods"], "gyms")
    db.commit()
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=[])
    assert c["set"] == 1
    db.refresh(prov)
    assert prov.subcategory == "biking"


def test_dry_run_writes_nothing(mod, db) -> None:
    cat = _seed_leaves(db)
    prov = _seed_provider(db, "Seibukan Karate-Do", cat["martial-arts"], "kids-lessons")
    db.commit()
    c = mod.realign(db, apply=False, cat_by_slug=cat, undo=[])
    assert c["would_set"] == 1 and c["set"] == 0
    db.refresh(prov)
    assert prov.subcategory == "kids-lessons"  # untouched


def test_already_correct_skipped(mod, db) -> None:
    cat = _seed_leaves(db)
    _seed_provider(db, "Seibukan Karate-Do", cat["martial-arts"], "martial-arts")
    db.commit()
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=[])
    assert c["already_correct"] >= 1 and c["set"] == 0


def test_not_on_leaf_skipped(mod, db) -> None:
    # Name matches the martial-arts spec, but the row sits on dance -> skip.
    cat = _seed_leaves(db)
    _seed_provider(db, "Seibukan Karate-Do", cat["dance-studios"], "kids-lessons")
    db.commit()
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=[])
    assert c["not_on_leaf"] >= 1 and c["set"] == 0


def test_no_match_when_absent(mod, db) -> None:
    cat = _seed_leaves(db)
    db.commit()
    c = mod.realign(db, apply=True, cat_by_slug=cat, undo=[])
    assert c["no_match"] == len(mod.REALIGN_SPECS) and c["set"] == 0
