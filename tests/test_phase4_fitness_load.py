"""Tests for ``scripts/phase4_fitness_load.py`` (Phase 4 fitness adds + recat).

Loads the script via importlib (mirrors ``test_phase5_event_link_repoint.py``;
``sys.modules`` registration before exec so PEP 563 dataclass annotations resolve
on Py 3.13). Exercises the pure spec invariants plus the core ``add_listings`` /
``recat_listings`` against an in-memory DB with a fake Places fetcher — dry-run
never writes; ``--apply`` files an add onto the right leaf and repoints a recat's
primary EntityCategory link.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, EntityCategory, Provider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "phase4_fitness_load.py"
    spec = importlib.util.spec_from_file_location("phase4_fitness_load", path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m  # register before exec for dataclass annotation resolution
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


def _seed_leaf(db: Session, slug: str, cid: int) -> Category:
    cat = Category(id=cid, slug=slug, name=slug.replace("-", " ").title(), level=1, parent_id=1)
    db.add(cat)
    db.flush()
    return cat


def _seed_provider_on_leaf(db: Session, name: str, leaf_id: int) -> Provider:
    """Create a Provider+Entity whose PRIMARY EntityCategory is ``leaf_id``."""
    p = Provider(provider_name=name, category="fitness_sports", is_active=True, draft=False,
                 category_id=leaf_id, slug=name.lower().replace(" ", "-"))
    db.add(p)
    create_provider_and_entity(db, p)
    db.flush()
    return p


def _fake_row(name: str, place_id: str, zip_code: str = "86406") -> dict:
    return {
        "place_id": place_id,
        "display_name": name,
        "formatted_address": f"123 Main St, Lake Havasu City, AZ {zip_code}",
        "zip": zip_code,
        "phone": "(928) 555-0100",
        "website": "https://example.com",
        "primary_type": "gym",
        "types": ["gym"],
        "lat": 34.48,
        "lng": -114.32,
        "rating": 4.9,
        "review_count": 42,
        "review_snippets": [],
        "photo_refs": [],
        "regular_opening_hours": None,
        "_first_seen_domain": "fitness_sports",
    }


# --------------------------- spec invariants --------------------------- #
def test_add_specs_target_known_leaves(mod) -> None:
    valid = {mod.LEAF_MARTIAL, mod.LEAF_DANCE, mod.LEAF_PT}
    assert {s.leaf for s in mod.ADD_SPECS} <= valid
    # Post-dry-run: only Four Dragons is a genuine add; the rest became re-files.
    assert len(mod.ADD_SPECS) == 1


def test_recat_specs_are_well_formed(mod) -> None:
    # No move is a no-op (source != target when a target exists).
    for s in mod.RECAT_SPECS:
        if s.to_leaf is not None:
            assert s.from_leaf != s.to_leaf, s.name_contains
    # Exactly the three no-target rows are flagged.
    assert sum(1 for s in mod.RECAT_SPECS if s.to_leaf is None) == 3
    # Every resolved target is a real fitness/shopping leaf.
    targets = {s.to_leaf for s in mod.RECAT_SPECS if s.to_leaf is not None}
    assert targets <= {mod.LEAF_MARTIAL, mod.LEAF_DANCE, mod.LEAF_PT, mod.LEAF_YOGA,
                       mod.LEAF_NUTRITION, mod.LEAF_SPORTING}


# ------------------------------- ADD ----------------------------------- #
# The single live ADD_SPEC is Four Dragons -> martial-arts; the fake fetcher must
# return a name containing "four dragons" or the script's name-match guard skips it.
_FD = "Four Dragons Martial Arts"


def test_add_dry_run_writes_nothing(mod, db) -> None:
    _seed_leaf(db, mod.LEAF_MARTIAL, 30)
    db.commit()
    cat_by_slug = {mod.LEAF_MARTIAL: 30}
    undo: list = []
    fetch = lambda q, e: _fake_row(_FD, "PID_FD")  # noqa: E731
    c = mod.add_listings(db, apply=False, fetch=fetch, cat_by_slug=cat_by_slug, undo=undo)
    assert c["would_add"] >= 1 and c["added"] == 0
    assert db.scalar(select(Provider).where(Provider.provider_name == _FD)) is None


def test_add_apply_files_onto_leaf(mod, db) -> None:
    _seed_leaf(db, mod.LEAF_MARTIAL, 30)
    db.commit()
    cat_by_slug = {mod.LEAF_MARTIAL: 30}
    undo: list = []
    fetch = lambda q, e: _fake_row(_FD, "PID_FD")  # noqa: E731
    c = mod.add_listings(db, apply=True, fetch=fetch, cat_by_slug=cat_by_slug, undo=undo)
    assert c["added"] == 1
    prov = db.scalar(select(Provider).where(Provider.provider_name == _FD))
    assert prov is not None and prov.google_place_id == "PID_FD"
    # Primary EntityCategory link is the target leaf — what the leaf page filters on.
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary is not None and primary.category_id == 30
    assert undo and undo[0]["op"] == "add"


def test_add_skips_duplicate_place_id(mod, db) -> None:
    _seed_leaf(db, mod.LEAF_MARTIAL, 30)
    fetch = lambda q, e: _fake_row(_FD, "PID_FD")  # noqa: E731
    mod.add_listings(db, apply=True, fetch=fetch, cat_by_slug={mod.LEAF_MARTIAL: 30}, undo=[])
    db.commit()
    c = mod.add_listings(db, apply=True, fetch=fetch, cat_by_slug={mod.LEAF_MARTIAL: 30}, undo=[])
    assert c["already_present"] >= 1 and c["added"] == 0


def test_add_skips_non_lhc_zip(mod, db) -> None:
    _seed_leaf(db, mod.LEAF_MARTIAL, 30)
    db.commit()
    fetch = lambda q, e: _fake_row(_FD, "PID_X", zip_code="90210")  # noqa: E731
    c = mod.add_listings(db, apply=True, fetch=fetch, cat_by_slug={mod.LEAF_MARTIAL: 30}, undo=[])
    assert c["non_lhc"] >= 1 and c["added"] == 0


# ------------------------------ RECAT ---------------------------------- #
def test_recat_moves_primary_link(mod, db) -> None:
    gyms = _seed_leaf(db, mod.LEAF_GYMS, 10)
    yoga = _seed_leaf(db, mod.LEAF_YOGA, 11)
    prov = _seed_provider_on_leaf(db, "Pilates of Lake Havasu", gyms.id)
    db.commit()
    cat_by_slug = {mod.LEAF_GYMS: 10, mod.LEAF_YOGA: 11}
    undo: list = []
    c = mod.recat_listings(db, apply=True, cat_by_slug=cat_by_slug, undo=undo)
    assert c["moved"] == 1
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary is not None and primary.category_id == yoga.id
    # Sustainability: Provider.category_id must also move so the re-scrape's
    # preserve-and-ensure logic keeps the row on the new leaf.
    db.refresh(prov)
    assert prov.category_id == yoga.id
    assert undo and undo[0]["op"] == "recat"
    assert undo[0]["provider_category_id"] == gyms.id  # old value snapshotted for undo


def test_recat_dry_run_writes_nothing(mod, db) -> None:
    gyms = _seed_leaf(db, mod.LEAF_GYMS, 10)
    _seed_leaf(db, mod.LEAF_YOGA, 11)
    prov = _seed_provider_on_leaf(db, "Pilates of Lake Havasu", gyms.id)
    db.commit()
    c = mod.recat_listings(db, apply=False, cat_by_slug={mod.LEAF_GYMS: 10, mod.LEAF_YOGA: 11},
                           undo=[])
    assert c["would_move"] == 1 and c["moved"] == 0
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary.category_id == gyms.id  # untouched


def test_recat_unexpected_source_is_skipped(mod, db) -> None:
    # Provider's primary link is on yoga, but the spec expects it on gyms.
    _seed_leaf(db, mod.LEAF_GYMS, 10)
    yoga = _seed_leaf(db, mod.LEAF_YOGA, 11)
    _seed_provider_on_leaf(db, "Pilates of Lake Havasu", yoga.id)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug={mod.LEAF_GYMS: 10, mod.LEAF_YOGA: 11},
                           undo=[])
    assert c["unexpected_state"] >= 1 and c["moved"] == 0


def test_recat_promotes_existing_target_link(mod, db) -> None:
    # Entity already has a (non-primary) link on the target leaf -> promote it,
    # demote the source primary, without creating a duplicate EntityCategory.
    gyms = _seed_leaf(db, mod.LEAF_GYMS, 10)
    yoga = _seed_leaf(db, mod.LEAF_YOGA, 11)
    prov = _seed_provider_on_leaf(db, "Pilates of Lake Havasu", gyms.id)
    db.add(EntityCategory(entity_id=prov.entity_id, category_id=yoga.id, is_primary=False))
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug={mod.LEAF_GYMS: 10, mod.LEAF_YOGA: 11},
                           undo=[])
    assert c["moved"] == 1
    ecs = list(db.scalars(
        select(EntityCategory).where(EntityCategory.entity_id == prov.entity_id)
    ).all())
    assert len(ecs) == 2  # no duplicate created
    primary = [ec for ec in ecs if ec.is_primary]
    assert len(primary) == 1 and primary[0].category_id == yoga.id


def test_no_target_rows_are_flagged_not_moved(mod, db) -> None:
    _seed_leaf(db, mod.LEAF_GYMS, 10)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug={mod.LEAF_GYMS: 10}, undo=[])
    assert c["flagged_no_target"] == 3 and c["moved"] == 0


def test_counter_is_a_counter(mod) -> None:
    assert isinstance(Counter(), Counter)  # sanity: import used
