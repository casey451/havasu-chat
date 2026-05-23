"""Phase 9a — expire_past_events sweep."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
from scripts.expire_past_events import _should_expire, run


def _ev(on_date: date, *, rrule: str | None = None, status: str = "live") -> Event:
    title = f"Exp {uuid.uuid4().hex[:6]}"
    return Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=time(10, 0),
        location_name="L",
        location_normalized="l",
        description="d",
        status=status,
        source="test",
        rrule=rrule,
        is_recurring=bool(rrule),
    )


def test_should_expire_past_one_off() -> None:
    cutoff = date.today() - timedelta(days=7)
    ev = _ev(cutoff - timedelta(days=1))
    assert _should_expire(ev, cutoff=cutoff) is True


def test_open_ended_recurring_does_not_expire() -> None:
    cutoff = date.today() - timedelta(days=7)
    ev = _ev(cutoff - timedelta(days=30), rrule="FREQ=WEEKLY;BYDAY=MO")
    assert _should_expire(ev, cutoff=cutoff) is False


def test_bounded_recurring_expires_after_until() -> None:
    cutoff = date.today() - timedelta(days=7)
    past = cutoff - timedelta(days=30)
    ev = _ev(past, rrule=f"FREQ=WEEKLY;UNTIL={past.strftime('%Y%m%d')}T000000Z")
    assert _should_expire(ev, cutoff=cutoff) is True


def test_run_dry_run() -> None:
    with SessionLocal() as db:
        ev = _ev(date.today() - timedelta(days=30))
        db.add(ev)
        create_event_and_entity(db, ev)
        db.commit()
        eid = ev.id
    try:
        n = run(dry_run=True)
        assert n >= 0
    finally:
        with SessionLocal() as db:
            row = db.get(Event, eid)
            if row:
                db.delete(row)
                db.commit()
