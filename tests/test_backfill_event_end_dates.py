"""Tests for ``scripts/backfill_event_end_dates.py``."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import date, time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Contribution, Event

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def backfill_mod():
    path = ROOT / "scripts" / "backfill_event_end_dates.py"
    spec = importlib.util.spec_from_file_location("backfill_event_end_dates", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _wipe_contributions_and_events() -> None:
    with SessionLocal() as db:
        db.query(Contribution).delete()
        db.query(Event).delete()
        db.commit()


def _seed_river_event(
    *,
    event_date: date,
    end_date: date | None,
    notes: str,
) -> tuple[str, int]:
    eid = str(uuid4())
    with SessionLocal() as db:
        ev = Event(
            id=eid,
            title="Backfill Test",
            normalized_title="backfill test",
            date=event_date,
            end_date=end_date,
            start_time=time(9, 0),
            end_time=None,
            location_name="Lake Havasu",
            location_normalized="lake havasu",
            description=notes,
            event_url="",
            source="river_scene_import",
        )
        db.add(ev)
        c = Contribution(
            entity_type="event",
            submission_name="Backfill Test",
            submission_url="https://riverscene.example.com/e/bf-test",
            submission_notes=notes,
            event_date=event_date,
            event_end_date=end_date,
            event_time_start=time(9, 0),
            event_time_end=None,
            source="river_scene_import",
            status="approved",
            created_event_id=eid,
        )
        db.add(c)
        db.commit()
        cid = c.id
    return eid, cid


def test_backfill_updates_multi_day_event(backfill_mod) -> None:
    mod = backfill_mod
    u = uuid.uuid4().hex[:8]
    notes = (
        f"Date: May 8\u201310, 2026\n\nTournament body {u} with more text here.\n"
        f"Venue: Test\n"
    )
    eid, _cid = _seed_river_event(
        event_date=date(2026, 5, 8),
        end_date=None,
        notes=notes,
    )
    out = mod.run_backfill()
    assert out[0] == 1
    assert out[1] == 1
    assert out[2] == 0
    with SessionLocal() as db:
        ev = db.get(Event, eid)
        assert ev is not None
        assert ev.end_date == date(2026, 5, 10)
        c = db.execute(
            select(Contribution).where(Contribution.created_event_id == eid)
        ).scalar_one()
        assert c.event_end_date == date(2026, 5, 10)


def test_backfill_skips_already_correct(backfill_mod) -> None:
    mod = backfill_mod
    u = uuid.uuid4().hex[:8]
    notes = f"Date: June 1\u20133, 2026\n\nRange {u}\n"
    eid, _ = _seed_river_event(
        event_date=date(2026, 6, 1),
        end_date=None,
        notes=notes,
    )
    first = mod.run_backfill()
    assert first[1] == 1
    second = mod.run_backfill()
    assert second[0] == 1
    assert second[1] == 0
    assert second[2] == 1
    with SessionLocal() as db:
        ev = db.get(Event, eid)
        assert ev is not None and ev.end_date == date(2026, 6, 3)


def test_backfill_skips_unparseable(backfill_mod) -> None:
    mod = backfill_mod
    u = uuid.uuid4().hex[:8]
    notes = f"Date: May 8, 2026 \u2013 May 10, 2026\n\ncross {u}\n"
    eid, _ = _seed_river_event(
        event_date=date(2026, 5, 8),
        end_date=None,
        notes=notes,
    )
    out = mod.run_backfill()
    assert out[0] == 1
    assert out[1] == 0
    assert out[4] == 1
    with SessionLocal() as db:
        ev = db.get(Event, eid)
        assert ev is not None
        assert ev.end_date is None
        c = db.execute(
            select(Contribution).where(Contribution.created_event_id == eid)
        ).scalar_one()
        assert c.event_end_date is None
