"""Tests for scripts/seed_havasu_stitchers.py (quilt-guild gap seed)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from app.events.recurrence import expand_event
from scripts.seed_havasu_stitchers import (
    ENTITY_SLUG,
    SEED_EVENTS,
    SEED_SOURCE,
    run_seed,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _cleanup(db) -> None:
    db.execute(delete(Event).where(Event.source == SEED_SOURCE))
    ent = db.scalars(select(Entity).where(Entity.slug == ENTITY_SLUG)).first()
    if ent is not None and ent.source == SEED_SOURCE:
        db.execute(delete(Entity).where(Entity.id == ent.id))
    db.commit()


@pytest.fixture
def clean_slate(db):
    _cleanup(db)
    yield
    _cleanup(db)


def test_dry_run_writes_nothing(db, clean_slate) -> None:
    counts = run_seed(dry_run=True)
    assert counts["events_created"] == 2
    assert db.scalars(select(Event).where(Event.source == SEED_SOURCE)).first() is None


def test_commit_is_idempotent(db, clean_slate) -> None:
    first = run_seed(dry_run=False)
    assert first["events_created"] == 2
    assert first["entity_created"] + first["entity_updated"] + first["entity_unchanged"] == 1

    second = run_seed(dry_run=False)
    assert second["events_created"] == 0
    assert second["events_existing"] == 2

    rows = db.scalars(select(Event).where(Event.source == SEED_SOURCE)).all()
    assert len(rows) == 2
    assert all(r.is_recurring and r.rrule for r in rows)


def test_general_meeting_expansion_handles_july_wednesday(db, clean_slate) -> None:
    run_seed(dry_run=False)
    meeting = db.scalars(
        select(Event).where(
            Event.source == SEED_SOURCE,
            Event.title.ilike("%general member meeting%"),
        )
    ).one()
    occs = expand_event(
        meeting, window_start=date(2026, 6, 1), window_end=date(2026, 8, 31)
    )
    # Site-published instances: Jun 11 (2nd Thu), Jul 8 (Wednesday — explicit
    # site anomaly), Aug 13 (2nd Thu). Jul 9 must be excluded by exdate.
    assert occs == [date(2026, 6, 11), date(2026, 7, 8), date(2026, 8, 13)]


def test_outreach_expansion_third_wednesday(db, clean_slate) -> None:
    run_seed(dry_run=False)
    outreach = db.scalars(
        select(Event).where(
            Event.source == SEED_SOURCE,
            Event.title.ilike("%outreach sewing%"),
        )
    ).one()
    occs = expand_event(
        outreach, window_start=date(2026, 6, 1), window_end=date(2026, 7, 31)
    )
    assert occs == [date(2026, 6, 17), date(2026, 7, 15)]


def test_seed_specs_match_site_instances() -> None:
    # DTSTART anchors must themselves satisfy their rules.
    general, outreach = SEED_EVENTS
    assert general["date"] == date(2026, 6, 11)  # 2nd Thursday of June 2026
    assert outreach["date"] == date(2026, 6, 17)  # 3rd Wednesday of June 2026
