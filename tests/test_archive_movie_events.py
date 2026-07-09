"""Regression guard for scripts/archive_movie_events.py.

The script flips leftover movie-tagged ``live`` events to a retired status. The
target MUST be a value ``ck_events_status`` permits — the first cut used
``archived`` (not in the allowed set), which passed on a constraint-free check
but failed on prod Postgres with a CHECK violation and never applied. These
tests run the script against the test DB (whose ``ck_events_status`` constraint
is created by the migrations) so an invalid status fails here, not in prod.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Entity, Event

_DAY = date(2099, 8, 14)


def _seed_event(db, *, title: str, tags: list[str]) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=_DAY,
        start_time=time(19, 0),
        location_name="Star Cinemas",
        location_normalized="star cinemas",
        description="",
        event_url="https://example.com/e",
        tags=tags,
        status="live",
        source="test_archive_movies",
    )
    db.add(ev)
    db.flush()
    eid = ev.entity_id
    db.commit()
    return eid


def _status(db, eid: str) -> str:
    return db.scalars(select(Event.status).where(Event.entity_id == eid)).one()


def _cleanup(eids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.entity_id.in_(eids)))
        db.execute(delete(Entity).where(Entity.id.in_(eids)))
        db.commit()


def test_apply_retires_movie_events_to_an_allowed_status():
    """Movie-tagged live events flip to 'deleted' (an allowed status); a
    same-day non-movie live event is untouched. A disallowed status (e.g. the
    original 'archived') would raise a CHECK violation here."""
    from scripts.archive_movie_events import main

    suffix = uuid.uuid4().hex[:6]
    movie_title = f"ZZ Movie Showtime {suffix}"
    fair_title = f"ZZ Street Fair {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_seed_event(db, title=movie_title, tags=["movie", "showtime", "star-cinemas"]))
        eids.append(_seed_event(db, title=fair_title, tags=["events"]))
    try:
        rc = main(["--apply"])
        assert rc == 0
        with SessionLocal() as db:
            assert _status(db, eids[0]) == "deleted"  # movie row retired
            assert _status(db, eids[1]) == "live"  # non-movie untouched
    finally:
        _cleanup(eids)


def test_dry_run_changes_nothing():
    from scripts.archive_movie_events import main

    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Movie Dryrun {suffix}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_seed_event(db, title=title, tags=["movie", "showtime"]))
    try:
        rc = main(["--dry-run"])
        assert rc == 0
        with SessionLocal() as db:
            assert _status(db, eids[0]) == "live"  # dry-run wrote nothing
    finally:
        _cleanup(eids)
