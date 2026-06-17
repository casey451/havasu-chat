"""Tests for ``scripts/phase4b_misfile_recat.py`` (targeted 4-row re-file).

Loads the script via importlib (mirrors ``test_phase4_fitness_load.py``;
``sys.modules`` registration before exec so PEP 563 dataclass annotations resolve
on Py 3.13). Exercises the spec invariants + the name-rule safety contract, plus
``recat_listings`` against an in-memory DB — dry-run never writes; ``--apply``
repoints the primary EntityCategory link and sets ``Provider.category_id``.
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

from app.contrib.name_leaf_rules import leaf_for_name
from app.db.database import Base
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, EntityCategory, Provider

ROOT = Path(__file__).resolve().parents[1]

# Representative LIVE names for the 4 targets — each must (a) contain the spec's
# search term and (b) be routed to the spec's target leaf by the name rule. This
# locks the contract the prod dry-run relies on.
REPR_NAMES = {
    "seibukan": "Seibukan Karate-Do",
    "next generation mixed martial": "Next Generation Mixed Martial Arts",
    "women kravmaga": "Women KravMaga Self Defense for Women",
    "the dance center": "The Dance Center",
}


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "phase4b_misfile_recat.py"
    spec = importlib.util.spec_from_file_location("phase4b_misfile_recat", path)
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


# Source (wrong) leaves these rows currently sit on, + the two targets.
SRC = "kids-classes-and-camps"


def _cat_by_slug(mod) -> dict[str, int]:
    return {SRC: 20, mod.LEAF_MARTIAL: 30, mod.LEAF_DANCE: 31}


def _seed_leaves(db: Session, mod) -> None:
    _seed_leaf(db, SRC, 20)
    _seed_leaf(db, mod.LEAF_MARTIAL, 30)
    _seed_leaf(db, mod.LEAF_DANCE, 31)


# --------------------------- spec invariants --------------------------- #
def test_specs_are_well_formed(mod) -> None:
    assert len(mod.RECAT_SPECS) == 4
    assert {s.target_leaf for s in mod.RECAT_SPECS} <= {mod.LEAF_MARTIAL, mod.LEAF_DANCE}
    # Search terms are unique (no two specs collide on the same name fragment).
    assert len({s.name_contains for s in mod.RECAT_SPECS}) == 4


def test_name_rule_agrees_with_every_spec_target(mod) -> None:
    """The name rule (this slice's authority) must route each representative
    live name to the spec's declared target leaf, and the search term must be a
    substring of that name."""
    by_term = {s.name_contains: s for s in mod.RECAT_SPECS}
    assert set(by_term) == set(REPR_NAMES)
    for term, name in REPR_NAMES.items():
        assert term.lower() in name.lower()
        assert leaf_for_name(name) == by_term[term].target_leaf, name


# ------------------------------ RECAT ---------------------------------- #
def test_recat_moves_primary_link(mod, db) -> None:
    _seed_leaves(db, mod)
    prov = _seed_provider_on_leaf(db, REPR_NAMES["seibukan"], 20)
    db.commit()
    undo: list = []
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=undo)
    assert c["moved"] == 1
    assert c["no_match"] == 3  # the other three specs find nothing
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary is not None and primary.category_id == 30
    db.refresh(prov)
    assert prov.category_id == 30  # sustainability: survives re-scrape
    assert undo and undo[0]["op"] == "recat"
    assert undo[0]["provider_category_id"] == 20  # old value snapshotted for undo


def test_recat_moves_dance_row(mod, db) -> None:
    _seed_leaves(db, mod)
    prov = _seed_provider_on_leaf(db, REPR_NAMES["the dance center"], 20)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["moved"] == 1
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary is not None and primary.category_id == 31  # dance-studios


def test_recat_dry_run_writes_nothing(mod, db) -> None:
    _seed_leaves(db, mod)
    prov = _seed_provider_on_leaf(db, REPR_NAMES["seibukan"], 20)
    db.commit()
    c = mod.recat_listings(db, apply=False, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["would_move"] == 1 and c["moved"] == 0
    primary = db.scalar(
        select(EntityCategory)
        .where(EntityCategory.entity_id == prov.entity_id)
        .where(EntityCategory.is_primary.is_(True))
    )
    assert primary.category_id == 20  # untouched


def test_run_dry_run_asserts_no_writes(mod, db) -> None:
    _seed_leaves(db, mod)
    _seed_provider_on_leaf(db, REPR_NAMES["seibukan"], 20)
    db.commit()
    c = mod.run(db, apply=False)  # must not raise the internal "dry-run must not persist"
    assert c["moved"] == 0 and c["would_move"] == 1


def test_recat_unexpected_name_is_skipped(mod, db) -> None:
    # Matches the "seibukan" search term but the name rule does NOT route it to
    # martial-arts (no martial keyword), so it must be skipped, not guessed.
    _seed_leaves(db, mod)
    _seed_provider_on_leaf(db, "Seibukan Trading Company", 20)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["unexpected"] >= 1 and c["moved"] == 0


def test_recat_already_correct_is_skipped(mod, db) -> None:
    # Row already on the target leaf -> no move, reported already_correct.
    _seed_leaves(db, mod)
    _seed_provider_on_leaf(db, REPR_NAMES["seibukan"], 30)  # already on martial-arts
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["already_correct"] >= 1 and c["moved"] == 0


def test_recat_ambiguous_is_skipped(mod, db) -> None:
    _seed_leaves(db, mod)
    _seed_provider_on_leaf(db, "Seibukan Karate-Do", 20)
    _seed_provider_on_leaf(db, "Seibukan Karate-Do North", 20)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["ambiguous"] >= 1 and c["moved"] == 0


def test_kravmaga_term_is_disambiguated(mod, db) -> None:
    # The 2026-06-17 dry-run showed bare "kravmaga" matched a second business,
    # "Arizona Kravmaga". The narrowed "women kravmaga" term must move ONLY the
    # intended row and leave Arizona Kravmaga untouched (not ambiguous, not moved).
    _seed_leaves(db, mod)
    target = _seed_provider_on_leaf(db, REPR_NAMES["women kravmaga"], 20)
    other = _seed_provider_on_leaf(db, "Arizona Kravmaga", 20)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["ambiguous"] == 0
    db.refresh(target)
    db.refresh(other)
    assert target.category_id == 30  # moved to martial-arts
    assert other.category_id == 20  # left where it was


def test_recat_promotes_existing_target_link(mod, db) -> None:
    # Entity already has a (non-primary) link on the target leaf -> promote it,
    # demote the source primary, without creating a duplicate EntityCategory.
    _seed_leaves(db, mod)
    prov = _seed_provider_on_leaf(db, REPR_NAMES["seibukan"], 20)
    db.add(EntityCategory(entity_id=prov.entity_id, category_id=30, is_primary=False))
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["moved"] == 1
    ecs = list(db.scalars(
        select(EntityCategory).where(EntityCategory.entity_id == prov.entity_id)
    ).all())
    assert len(ecs) == 2  # no duplicate created
    primary = [ec for ec in ecs if ec.is_primary]
    assert len(primary) == 1 and primary[0].category_id == 30


def test_no_match_when_absent(mod, db) -> None:
    _seed_leaves(db, mod)
    db.commit()
    c = mod.recat_listings(db, apply=True, cat_by_slug=_cat_by_slug(mod), undo=[])
    assert c["no_match"] == 4 and c["moved"] == 0


def test_counter_is_a_counter(mod) -> None:
    assert isinstance(Counter(), Counter)  # sanity: import used
