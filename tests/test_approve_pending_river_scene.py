"""Tests for ``scripts/approve_pending_river_scene.py`` (Fix 2 backfill)."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.contrib.approval_service import approve_contribution_as_event as real_approve_contribution_as_event
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal
from app.db.models import Contribution, Event
from app.schemas.contribution import ContributionCreate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def approve_pending_mod():
    path = ROOT / "scripts" / "approve_pending_river_scene.py"
    spec = importlib.util.spec_from_file_location("approve_pending_river_scene", path)
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


def test_backfill_approves_pending_river_scene_contributions(approve_pending_mod) -> None:
    mod = approve_pending_mod
    u = uuid.uuid4().hex[:8]
    long_notes = (
        f"Date: June 1, 2026\n\nCommunity fair description {u} with enough text here.\n\n"
        f"Venue: London Bridge Beach\n"
        f"Categories: family, free\n"
    )
    for i in range(3):
        with SessionLocal() as db:
            create_contribution(
                db,
                ContributionCreate(
                    entity_type="event",
                    submission_name=f"Backfill Event {i} {u}",
                    submission_url=f"https://riverscenemagazine.com/events/bf-{i}-{u}/",
                    submission_notes=long_notes,
                    event_date=date(2026, 6, 1 + i),
                    event_time_start=time(10, 0),
                    event_time_end=time(14, 0),
                    source="river_scene_import",
                ),
            )
    out = mod.run_backfill()
    assert out == (3, 3, 0)
    with SessionLocal() as db:
        rows = db.query(Contribution).filter(Contribution.source == "river_scene_import").all()
        assert len(rows) == 3
        assert all(r.status == "approved" and r.created_event_id is not None for r in rows)
        evs = db.query(Event).filter(Event.source == "river_scene_import").all()
        assert len(evs) == 3


def test_backfill_skips_non_river_scene_pending(approve_pending_mod) -> None:
    mod = approve_pending_mod
    u = uuid.uuid4().hex[:8]
    notes = f"Y" * 22 + f"\nVenue: Test Venue Here\n"
    with SessionLocal() as db:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="event",
                submission_name=f"River Ok {u}",
                submission_url=f"https://riverscenemagazine.com/e/rs-{u}/",
                submission_notes=notes,
                event_date=date(2026, 7, 1),
                event_time_start=time(9, 0),
                source="river_scene_import",
            ),
        )
        create_contribution(
            db,
            ContributionCreate(
                entity_type="event",
                submission_name=f"User stay {u}",
                submission_url=f"https://example.com/user-{u}/",
                submission_notes=notes,
                event_date=date(2026, 7, 2),
                event_time_start=time(10, 0),
                source="user_submission",
            ),
        )
    mod.run_backfill()
    with SessionLocal() as db:
        rs = (
            db.query(Contribution)
            .filter(Contribution.submission_name.like(f"%{u}%"), Contribution.source == "river_scene_import")
            .one()
        )
        us = (
            db.query(Contribution)
            .filter(Contribution.submission_name.like(f"%{u}%"), Contribution.source == "user_submission")
            .one()
        )
        assert rs.status == "approved" and rs.created_event_id is not None
        assert us.status == "pending" and us.created_event_id is None
        assert db.query(Event).filter(Event.source == "river_scene_import").count() == 1


def test_backfill_skips_already_approved(approve_pending_mod) -> None:
    mod = approve_pending_mod
    u = uuid.uuid4().hex[:8]
    notes = "Z" * 22 + "\nVenue: Rotary Park\n"
    for i in range(3):
        with SessionLocal() as db:
            create_contribution(
                db,
                ContributionCreate(
                    entity_type="event",
                    submission_name=f"Idem {i} {u}",
                    submission_url=f"https://riverscenemagazine.com/e/id{i}-{u}/",
                    submission_notes=notes,
                    event_date=date(2026, 8, 1 + i),
                    event_time_start=time(11, 0),
                    source="river_scene_import",
                ),
            )
    a1 = mod.run_backfill()
    assert a1[0] == 3 and a1[1] == 3 and a1[2] == 0
    a2 = mod.run_backfill()
    assert a2 == (0, 0, 0)


def test_backfill_continues_on_individual_failure(approve_pending_mod) -> None:
    mod = approve_pending_mod
    u = uuid.uuid4().hex[:8]
    notes = "K" * 22 + "\nVenue: City Park\n"
    ids: list[int] = []
    for i in range(3):
        with SessionLocal() as db:
            c = create_contribution(
                db,
                ContributionCreate(
                    entity_type="event",
                    submission_name=f"Failmix {i} {u}",
                    submission_url=f"https://riverscenemagazine.com/e/fm{i}-{u}/",
                    submission_notes=notes,
                    event_date=date(2026, 9, 1 + i),
                    event_time_start=time(8, 0),
                    source="river_scene_import",
                ),
            )
            ids.append(c.id)
    sid = sorted(ids)
    fail_id = sid[1]

    def _maybe_fail(db, cid, fields, tags):
        if cid == fail_id:
            raise RuntimeError("boom")
        return real_approve_contribution_as_event(db, cid, fields, tags)

    with patch.object(mod, "approve_contribution_as_event", side_effect=_maybe_fail):
        out = mod.run_backfill()
    assert out[1] == 2 and out[2] == 1
    with SessionLocal() as db:
        by_id = {c.id: c for c in db.query(Contribution).filter(Contribution.id.in_(ids)).all()}
        assert by_id[sid[0]].status == "approved"
        assert by_id[sid[2]].status == "approved"
        assert by_id[fail_id].status == "pending"
        assert db.query(Event).count() == 2


def test_backfill_passes_contribution_event_end_date_to_event(approve_pending_mod) -> None:
    mod = approve_pending_mod
    u = uuid.uuid4().hex[:8]
    long_notes = (
        f"Date: May 7–9, 2026\n\nTournament blurb {u} with enough text here for validation.\n\n"
        f"Venue: Test Pier\n"
    )
    with SessionLocal() as db:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="event",
                submission_name=f"EndDate Row {u}",
                submission_url=f"https://riverscenemagazine.com/events/ed-{u}/",
                submission_notes=long_notes,
                event_date=date(2026, 5, 7),
                event_end_date=date(2026, 5, 9),
                event_time_start=time(8, 0),
                event_time_end=time(17, 0),
                source="river_scene_import",
            ),
        )
    mod.run_backfill()
    with SessionLocal() as db:
        c = (
            db.query(Contribution)
            .filter(Contribution.submission_name == f"EndDate Row {u}")
            .one()
        )
        assert c.status == "approved" and c.created_event_id
        ev = db.get(Event, c.created_event_id)
        assert ev is not None
        assert ev.end_date == date(2026, 5, 9)
        assert ev.date == date(2026, 5, 7)
