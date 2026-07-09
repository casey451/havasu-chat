"""Tests for ``scripts/dedupe_providers.py``.

Loads the script via importlib (mirrors ``test_phase4b_misfile_recat.py``).
Seeds providers with the dual-write helper (so each gets an Entity +
EntityCategory), then exercises the two real MERGE_SPECS: the bike pair
(distinct names) and the Next Generation pair (same name, disambiguated by
``google_place_id``). Dry-run never merges; ``--apply`` soft-retires the loser
and records an undo snapshot entry.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Provider
from app.db.seed_helpers import derive_provider_slug

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "dedupe_providers.py"
    spec = importlib.util.spec_from_file_location("dedupe_providers", path)
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


def _seed_leaf(db: Session, slug: str, cid: int) -> Category:
    cat = Category(id=cid, slug=slug, name=slug.replace("-", " ").title(), level=1, parent_id=1)
    db.add(cat)
    db.flush()
    return cat


def _provider(db: Session, name: str, *, leaf_id: int | None = None, **kw) -> Provider:
    p = Provider(
        provider_name=name,
        category=kw.pop("category", "fitness_sports"),
        slug=derive_provider_slug(db, name),
        source=kw.pop("source", "go_lake_havasu"),
        is_active=kw.pop("is_active", True),
        draft=kw.pop("draft", False),
        category_id=leaf_id,
        **kw,
    )
    db.add(p)
    create_provider_and_entity(db, p)
    db.flush()
    return p


def _seed_bike(db: Session) -> tuple[Provider, Provider]:
    _seed_leaf(db, "sporting-goods", 40)
    keep = _provider(db, "Havasu Bike and Fitness", leaf_id=40, google_place_id="PID_BIKE")
    dup = _provider(db, "Lake Havasu Bike & Fitness", leaf_id=40, website="https://dup-bike.example")
    return keep, dup


def _seed_nextgen(db: Session) -> tuple[Provider, Provider]:
    _seed_leaf(db, "martial-arts", 30)
    keep = _provider(db, "Next Generation Mixed Martial Arts", leaf_id=30, google_place_id="PID_NG")
    dup = _provider(db, "Next Generation Mixed Martial Arts", leaf_id=30)  # no place id
    return keep, dup


def _seed_911(db: Session) -> tuple[Provider, Provider]:
    # Same business, two Google records: SAME name, BOTH carry a (distinct)
    # place_id, so place_id can't disambiguate — the survivor is chosen by slug.
    _seed_leaf(db, "auto-repair", 50)
    keep = _provider(db, "911 Mobile Mechanic", leaf_id=50, google_place_id="PID_911_A")
    dup = _provider(db, "911 Mobile Mechanic", leaf_id=50, google_place_id="PID_911_B")
    return keep, dup


# ------------------------------ resolve -------------------------------- #
def test_resolve_bike_picks_correct_keeper(mod, db) -> None:
    keep, dup = _seed_bike(db)
    db.commit()
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "names")
    keeper, dups, note = mod._resolve(db, spec)
    assert note == "ok"
    assert keeper.id == keep.id
    assert [d.id for d in dups] == [dup.id]


def test_resolve_nextgen_keeps_the_one_with_place_id(mod, db) -> None:
    keep, dup = _seed_nextgen(db)
    db.commit()
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "place_id")
    keeper, dups, note = mod._resolve(db, spec)
    assert note == "ok"
    assert keeper.id == keep.id and keeper.google_place_id == "PID_NG"
    assert [d.id for d in dups] == [dup.id]


def test_resolve_911_picks_keeper_by_slug(mod, db) -> None:
    keep, dup = _seed_911(db)
    db.commit()
    # Both rows carry a place_id, so the survivor is picked by exact slug.
    assert keep.slug == "911-mobile-mechanic" and dup.slug == "911-mobile-mechanic-2"
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "slugs")
    keeper, dups, note = mod._resolve(db, spec)
    assert note == "ok"
    assert keeper.id == keep.id
    assert [d.id for d in dups] == [dup.id]


def test_resolve_skips_when_no_distinct_dup(mod, db) -> None:
    # Only the keeper present -> nothing to merge, reported, not guessed.
    _seed_leaf(db, "sporting-goods", 40)
    _provider(db, "Havasu Bike and Fitness", leaf_id=40, google_place_id="PID_BIKE")
    db.commit()
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "names")
    keeper, dups, note = mod._resolve(db, spec)
    assert keeper is None and "no distinct duplicate" in note


def test_resolve_skips_ambiguous_keeper(mod, db) -> None:
    _seed_leaf(db, "sporting-goods", 40)
    _provider(db, "Havasu Bike and Fitness", leaf_id=40)
    _provider(db, "Havasu Bike and Fitness Annex", leaf_id=40)  # second keep match
    _provider(db, "Lake Havasu Bike & Fitness", leaf_id=40)
    db.commit()
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "names")
    keeper, dups, note = mod._resolve(db, spec)
    assert keeper is None and "not unique" in note


def test_resolve_nextgen_skips_when_no_placeidless_dup(mod, db) -> None:
    # Both have place ids -> can't tell which is the bare dup; skip.
    _seed_leaf(db, "martial-arts", 30)
    _provider(db, "Next Generation Mixed Martial Arts", leaf_id=30, google_place_id="A")
    _provider(db, "Next Generation Mixed Martial Arts", leaf_id=30, google_place_id="B")
    db.commit()
    spec = next(s for s in mod.MERGE_SPECS if s.strategy == "place_id")
    keeper, dups, note = mod._resolve(db, spec)
    assert keeper is None and "keeper not unique" in note


# ------------------------------- run ----------------------------------- #
def test_dry_run_merges_nothing(mod, db) -> None:
    _seed_bike(db)
    _seed_nextgen(db)
    db.commit()
    c = mod.run(db, apply=False)
    assert c["would_merge"] == 2 and c["merged"] == 0
    # Both dups still active.
    actives = db.scalars(select(Provider).where(Provider.is_active.is_(True))).all()
    assert len(actives) == 4


def test_apply_soft_retires_both_dups(mod, db) -> None:
    bike_keep, bike_dup = _seed_bike(db)
    ng_keep, ng_dup = _seed_nextgen(db)
    db.commit()
    undo: list = []
    c = mod.dedupe(db, apply=True, undo=undo)
    db.commit()
    assert c["merged"] == 2
    for dup in (bike_dup, ng_dup):
        db.refresh(dup)
        assert dup.is_active is False and dup.draft is True
    for keep in (bike_keep, ng_keep):
        db.refresh(keep)
        assert keep.is_active is True
    # Gap-fill: the bike keeper had no website; the dup's website moves over.
    db.refresh(bike_keep)
    assert bike_keep.website == "https://dup-bike.example"
    assert len(undo) == 2 and {u["op"] for u in undo} == {"merge"}


def test_run_apply_writes_undo_snapshot(mod, db, tmp_path) -> None:
    _seed_nextgen(db)
    db.commit()
    c = mod.run(db, apply=True, snapshot_dir=tmp_path)
    assert c["merged"] == 1
    snaps = list(tmp_path.glob("_dedupe_providers_undo_*.json"))
    assert len(snaps) == 1
