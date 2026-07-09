"""Tests for ``scripts/phase5_event_link_repoint.py`` (event-link cleanup).

Mirrors the loader pattern of ``test_backfill_river_scene_urls.py`` (scripts/ is
not a package) and exercises the core ``repoint_events`` against an in-memory DB:
dry-run never writes, ``--apply`` repoints and preserves provenance via source_url.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import Event

ROOT = Path(__file__).resolve().parents[1]
_BREW = "https://allevents.in/lake-havasu-city/the-brew-band/200030132717746"


@pytest.fixture
def mod():
    path = ROOT / "scripts" / "phase5_event_link_repoint.py"
    spec = importlib.util.spec_from_file_location("phase5_event_link_repoint", path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve PEP 563 string annotations
    # via the module namespace (Python 3.13 dataclasses looks it up in sys.modules).
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


def _seed(db: Session, *, event_url: str, source_url: str | None = None) -> Event:
    ev = Event(
        title="T", normalized_title="t", date=date(2026, 6, 20), start_time=time(19, 0),
        location_name="L", location_normalized="l", description="d",
        event_url=event_url, source_url=source_url, status="live",
    )
    db.add(ev)
    db.flush()
    return ev


def test_mapping_has_no_self_pointing_rules(mod) -> None:
    # Every resolved rule must change the URL (match != to); None = unresolved.
    for rp in mod.REPOINTS:
        if rp.to is not None:
            assert mod._norm(rp.match) != mod._norm(rp.to), rp.venue
    # Every rule is now resolved to a primary URL (The Views confirmed).
    assert sum(1 for rp in mod.REPOINTS if rp.to is None) == 0


def test_dry_run_changes_nothing(mod, db) -> None:
    ev = _seed(db, event_url=_BREW)
    db.commit()
    c = mod.repoint_events(db, apply=False)
    db.refresh(ev)
    assert ev.event_url == _BREW  # untouched
    assert c["applied"] == 0
    assert c["would_change"] == 1
    assert c["needs_url"] == 0  # all rules resolved
    assert c["total"] == len(mod.REPOINTS)


def test_apply_repoints_and_preserves_provenance(mod, db, tmp_path) -> None:
    ev = _seed(db, event_url=_BREW)  # no source_url yet
    db.commit()
    c = mod.repoint_events(db, apply=True, snapshot_dir=tmp_path)
    db.refresh(ev)
    assert ev.event_url == mod._LIGHTHOUSE_FB
    # provenance preserved so the detail page's "Source:" byline lights up
    assert ev.source_url == _BREW
    assert c["applied"] == c["would_change"] == 1
    # an undo snapshot was written
    assert list(tmp_path.glob("_phase5_repoint_undo_*.json"))


def test_apply_does_not_clobber_existing_source_url(mod, db, tmp_path) -> None:
    ev = _seed(db, event_url=_BREW, source_url="https://keep.example/origin")
    db.commit()
    mod.repoint_events(db, apply=True, snapshot_dir=tmp_path)
    db.refresh(ev)
    assert ev.event_url == mod._LIGHTHOUSE_FB
    assert ev.source_url == "https://keep.example/origin"  # untouched


def test_unmatched_url_is_skipped(mod, db, tmp_path) -> None:
    ev = _seed(db, event_url="https://example.com/not-in-the-mapping")
    db.commit()
    c = mod.repoint_events(db, apply=True, snapshot_dir=tmp_path)
    db.refresh(ev)
    assert ev.event_url == "https://example.com/not-in-the-mapping"
    assert c["applied"] == 0
