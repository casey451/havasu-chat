"""Guards for the 2026-06-20 search-coverage backfill scripts.

* ``plan_leaf_action`` is pure (no DB) — lock the insert/noop/abort decisions.
* ``create_missing_service_leaves.run`` is all-or-nothing: a single ABORT writes
  NOTHING (no partial seed), and a clean plan writes every leaf in one commit.
* ``seed_service_businesses.upsert`` relies on the catalog dual-write hook to set
  ``Provider.entity_id`` (non-nullable) — assert a committed draft has one, so a
  hook regression can never let the gated ``--commit`` crash with an
  IntegrityError.

Each test runs against an isolated throwaway sqlite engine (never prod / the
shared test DB), built fresh per test in ``iso_session``.
"""

from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.create_missing_service_leaves_2026_06_20 as leaves
import scripts.seed_service_businesses_2026_06_20 as seed
from app.db.models import Base, Category, Entity, Provider


@pytest.fixture
def iso_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'iso.db'}")
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    db = Sess()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_departments(db) -> None:
    """One level-0 Category per department the leaf list parents under."""
    depts = {dept for _slug, _name, dept in leaves.LEAVES_TO_CREATE}
    for i, dept in enumerate(sorted(depts)):
        db.add(Category(slug=dept, name=dept.replace("-", " ").title(), level=0, sort_order=i))
    db.commit()


# --- plan_leaf_action (pure) ----------------------------------------------


def _cats(dept="home-and-property-services", dept_id=10) -> dict[str, dict]:
    return {dept: {"id": dept_id, "level": 0, "parent_id": None}}


def test_plan_insert_when_missing() -> None:
    action, _ = leaves.plan_leaf_action("painting", "Painting", "home-and-property-services", _cats())
    assert action == "insert"


def test_plan_noop_when_already_correct_leaf() -> None:
    cats = _cats()
    cats["painting"] = {"id": 99, "level": 1, "parent_id": 10}
    action, _ = leaves.plan_leaf_action("painting", "Painting", "home-and-property-services", cats)
    assert action == "noop"


def test_plan_abort_when_department_missing() -> None:
    action, msg = leaves.plan_leaf_action("painting", "Painting", "home-and-property-services", {})
    assert action == "abort"
    assert "home-and-property-services" in msg


def test_plan_abort_when_leaf_exists_at_wrong_level() -> None:
    cats = _cats()
    cats["painting"] = {"id": 99, "level": 0, "parent_id": None}  # exists as a department
    action, _ = leaves.plan_leaf_action("painting", "Painting", "home-and-property-services", cats)
    assert action == "abort"


# --- run(): all-or-nothing -------------------------------------------------


def test_run_creates_every_leaf_when_departments_present(iso_session, tmp_path) -> None:
    _seed_departments(iso_session)
    counts = leaves.run(apply=True, confirm=True, snapshot_dir=tmp_path, session=iso_session)
    assert counts["insert"] == len(leaves.LEAVES_TO_CREATE)
    assert counts["committed"] == 1
    assert counts["abort"] == 0
    made = {c.slug for c in iso_session.query(Category).filter(Category.level == 1)}
    for slug, _name, _dept in leaves.LEAVES_TO_CREATE:
        assert slug in made, slug


def test_run_writes_nothing_when_any_leaf_aborts(iso_session, tmp_path) -> None:
    _seed_departments(iso_session)
    # Force exactly one ABORT: a target slug already present as a level-0 dept.
    iso_session.add(Category(slug="painting", name="Painting", level=0, sort_order=99))
    iso_session.commit()
    before = iso_session.query(Category).filter(Category.level == 1).count()

    counts = leaves.run(apply=True, confirm=True, snapshot_dir=tmp_path, session=iso_session)

    assert counts["abort"] >= 1
    assert counts["committed"] == 0
    # All-or-nothing: not a single level-1 leaf was written.
    after = iso_session.query(Category).filter(Category.level == 1).count()
    assert after == before


def test_run_dry_run_writes_nothing(iso_session, tmp_path) -> None:
    _seed_departments(iso_session)
    counts = leaves.run(apply=False, confirm=False, snapshot_dir=tmp_path, session=iso_session)
    assert counts["committed"] == 0
    assert iso_session.query(Category).filter(Category.level == 1).count() == 0


# --- seed_service_businesses: entity_id is populated by the dual-write hook --


def test_seeded_provider_gets_entity_id_and_entity(iso_session) -> None:
    rec = {
        "provider_name": "Acme Test Painters",
        "legacy_category": "home_services",
        "address": "1 Main St",
        "phone": "555-0100",
        "website": "https://example.com",
        "leaf_slug": "painters",
    }
    msg = seed.upsert(iso_session, rec, commit=True, counts=Counter())
    iso_session.commit()
    assert "insert" in msg
    prov = iso_session.query(Provider).filter(Provider.slug == "acme-test-painters").one()
    assert prov.entity_id is not None, "entity_id NULL → --commit would IntegrityError on prod"
    assert iso_session.get(Entity, prov.entity_id) is not None
    assert prov.draft is True and prov.pending_review is True


def test_seed_upsert_skips_existing_slug(iso_session) -> None:
    rec = {"provider_name": "Dup Co", "legacy_category": "home_services", "leaf_slug": "fencing"}
    seed.upsert(iso_session, rec, commit=True, counts=Counter())
    iso_session.commit()
    counts: Counter = Counter()
    msg = seed.upsert(iso_session, rec, commit=True, counts=counts)
    assert "skip (exists)" in msg
    assert counts["skip_exists"] == 1
