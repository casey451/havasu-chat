"""Tests for the A.3 taxonomy apply (seed + remap scripts).

Uses an isolated in-memory SQLite engine per test so seeding 126 categories
never leaks into the shared session test DB.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import Category, Entity, EntityCategory

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


seed_taxonomy = _load("seed_taxonomy")
apply_taxonomy_remap = _load("apply_taxonomy_remap")


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# --- pure classification -----------------------------------------------------


def test_normalize_leaf_strips_annotation() -> None:
    assert apply_taxonomy_remap.normalize_leaf("Shuttles & Transportation [NEW]") == (
        "Shuttles & Transportation"
    )
    assert apply_taxonomy_remap.normalize_leaf("Restaurants") == "Restaurants"


def test_classify_actions() -> None:
    c = apply_taxonomy_remap.classify
    assert c("Eat & Drink", "Restaurants", "google_type") == "assign"
    # Workstream C: PARK flag in the leaf, and the EXCLUDE/TEST departments.
    assert c("Lodging", "Vacation Rental — PARK [C]", "name_keyword") == "deactivate"
    assert c("(EXCLUDE — residential)", "(not a real listing)", "name_keyword") == (
        "deactivate"
    )
    assert c("(TEST/SEED — EXCLUDE)", "(not a real listing)", "seed_exclude") == (
        "deactivate"
    )
    # The 13 unresolved.
    assert c("(needs review)", "(needs review)", "unresolved") == "skip_review"
    assert c("Pets", "(needs review)", "provider_subcat") == "skip_review"


# --- seed_taxonomy -----------------------------------------------------------

_MINI_SEED = {
    "eat-and-drink": {
        "name": "Eat & Drink",
        "sort": 0,
        "leaves": {
            "restaurants": {"name": "Restaurants", "count": 10, "gate_ok": True},
            "bars-and-breweries": {"name": "Bars & Breweries", "count": 5},
        },
    },
    "lodging": {
        "name": "Lodging",
        "sort": 1,
        "leaves": {"hotels-and-motels": {"name": "Hotels & Motels", "count": 8}},
    },
}


def _write_seed(tmp_path: Path) -> Path:
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(_MINI_SEED), encoding="utf-8")
    return p


def test_seed_taxonomy_dry_run_writes_nothing(db: Session, tmp_path: Path) -> None:
    seed_taxonomy.run(apply=False, seed_path=_write_seed(tmp_path), session=db)
    assert db.query(Category).count() == 0


def test_seed_taxonomy_apply_builds_tree_idempotently(
    db: Session, tmp_path: Path
) -> None:
    seed_path = _write_seed(tmp_path)
    counts = seed_taxonomy.run(apply=True, confirm=True, seed_path=seed_path, session=db)
    assert counts["dept_insert"] == 2
    assert counts["leaf_insert"] == 3
    depts = db.query(Category).filter(Category.level == 0).all()
    leaves = db.query(Category).filter(Category.level == 1).all()
    assert len(depts) == 2 and len(leaves) == 3
    eat = db.query(Category).filter(Category.slug == "eat-and-drink").one()
    assert all(leaf.parent_id == eat.id for leaf in eat.children)

    # Re-run is idempotent: no new rows, everything "unchanged".
    counts2 = seed_taxonomy.run(apply=True, confirm=True, seed_path=seed_path, session=db)
    assert counts2["dept_insert"] == 0 and counts2["leaf_insert"] == 0
    assert db.query(Category).count() == 5


def test_seed_taxonomy_apply_requires_confirm(db: Session, tmp_path: Path) -> None:
    seed_taxonomy.run(apply=True, confirm=False, seed_path=_write_seed(tmp_path), session=db)
    assert db.query(Category).count() == 0


# --- apply_taxonomy_remap end-to-end ----------------------------------------


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    p = tmp_path / "remap.csv"
    cols = [
        "entity_id", "name", "google_type", "signal", "confidence",
        "proposed_department", "proposed_leaf",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return p


def _seed_and_entities(db: Session, tmp_path: Path) -> dict[str, str]:
    seed_taxonomy.run(apply=True, confirm=True, seed_path=_write_seed(tmp_path), session=db)
    restaurants = db.query(Category).filter(Category.slug == "restaurants").one()
    bars = db.query(Category).filter(Category.slug == "bars-and-breweries").one()

    # e_move: currently primary=bars, should move to restaurants.
    e_move = Entity(entity_type="commercial", slug="e-move", name="Mover")
    # e_same: already primary=restaurants -> unchanged.
    e_same = Entity(entity_type="commercial", slug="e-same", name="Stayer")
    # e_park: a PARK [C] row -> deactivate.
    e_park = Entity(entity_type="commercial", slug="e-park", name="Parker")
    db.add_all([e_move, e_same, e_park])
    db.flush()
    db.add_all([
        EntityCategory(entity_id=e_move.id, category_id=bars.id, is_primary=True),
        EntityCategory(entity_id=e_same.id, category_id=restaurants.id, is_primary=True),
    ])
    db.commit()
    return {
        "move": e_move.id,
        "same": e_same.id,
        "park": e_park.id,
        "restaurants_id": restaurants.id,
        "bars_id": bars.id,
    }


def test_remap_dry_run_writes_nothing(db: Session, tmp_path: Path) -> None:
    ids = _seed_and_entities(db, tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"entity_id": ids["move"], "signal": "google_type",
         "proposed_department": "Eat & Drink", "proposed_leaf": "Restaurants"},
    ])
    counts = apply_taxonomy_remap.run(
        apply=False, csv_path=csv_path, seed_path=_write_seed(tmp_path), session=db
    )
    assert counts["assign"] == 1
    # Primary unchanged on disk (still bars).
    prim = db.query(EntityCategory).filter(
        EntityCategory.entity_id == ids["move"], EntityCategory.is_primary.is_(True)
    ).one()
    assert prim.category_id == ids["bars_id"]


def test_remap_apply_reassigns_and_deactivates(db: Session, tmp_path: Path) -> None:
    ids = _seed_and_entities(db, tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"entity_id": ids["move"], "signal": "google_type",
         "proposed_department": "Eat & Drink", "proposed_leaf": "Restaurants"},
        {"entity_id": ids["same"], "signal": "google_type",
         "proposed_department": "Eat & Drink", "proposed_leaf": "Restaurants"},
        {"entity_id": ids["park"], "signal": "name_keyword",
         "proposed_department": "Lodging", "proposed_leaf": "Vacation Rental — PARK [C]"},
    ])
    counts = apply_taxonomy_remap.run(
        apply=True, confirm=True, csv_path=csv_path,
        seed_path=_write_seed(tmp_path), snapshot_dir=tmp_path, session=db,
    )
    assert counts["assign"] == 2
    assert counts["deactivate"] == 1
    assert counts["primaries_changed"] == 1  # only e_move changed; e_same unchanged
    assert counts["deactivated"] == 1

    # e_move primary is now restaurants, old bars primary cleared.
    primaries = db.query(EntityCategory).filter(
        EntityCategory.entity_id == ids["move"], EntityCategory.is_primary.is_(True)
    ).all()
    assert len(primaries) == 1 and primaries[0].category_id == ids["restaurants_id"]
    # e_park deactivated.
    assert db.get(Entity, ids["park"]).is_active is False
    # e_same untouched and still active.
    assert db.get(Entity, ids["same"]).is_active is True


def test_remap_department_filter_scopes_the_run(db: Session, tmp_path: Path) -> None:
    """B3 (spec §7 step 2): --department drops other departments' rows, so a
    stray row in a hand-built phase CSV can never leak into a phase apply."""
    ids = _seed_and_entities(db, tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"entity_id": ids["move"], "signal": "google_type",
         "proposed_department": "Eat & Drink", "proposed_leaf": "Restaurants"},
        # Stray row from another department — must be filtered OUT.
        {"entity_id": ids["park"], "signal": "name_keyword",
         "proposed_department": "Lodging", "proposed_leaf": "Vacation Rental — PARK [C]"},
    ])
    counts = apply_taxonomy_remap.run(
        apply=True, confirm=True, csv_path=csv_path,
        seed_path=_write_seed(tmp_path), snapshot_dir=tmp_path, session=db,
        department="Eat & Drink",
    )
    assert counts["csv_rows"] == 1  # the Lodging row never entered the plan
    assert counts["assign"] == 1
    assert counts.get("deactivate", 0) == 0
    # The stray row's entity is untouched.
    assert db.get(Entity, ids["park"]).is_active is True
    # And the in-scope move landed.
    prim = db.query(EntityCategory).filter(
        EntityCategory.entity_id == ids["move"], EntityCategory.is_primary.is_(True)
    ).one()
    assert prim.category_id == ids["restaurants_id"]


def test_remap_apply_requires_confirm(db: Session, tmp_path: Path) -> None:
    ids = _seed_and_entities(db, tmp_path)
    csv_path = _write_csv(tmp_path, [
        {"entity_id": ids["move"], "signal": "google_type",
         "proposed_department": "Eat & Drink", "proposed_leaf": "Restaurants"},
    ])
    apply_taxonomy_remap.run(
        apply=True, confirm=False, csv_path=csv_path,
        seed_path=_write_seed(tmp_path), session=db,
    )
    prim = db.query(EntityCategory).filter(
        EntityCategory.entity_id == ids["move"], EntityCategory.is_primary.is_(True)
    ).one()
    assert prim.category_id == ids["bars_id"]  # unchanged
