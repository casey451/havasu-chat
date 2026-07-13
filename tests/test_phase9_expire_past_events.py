"""Phase 9a — expire_past_events sweep (end-date keyed, one-day grace)."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.models import Event
from scripts.expire_past_events import _should_expire, run

TODAY = date.today()


def _ev(
    on_date: date,
    *,
    end_date: date | None = None,
    rrule: str | None = None,
    status: str = "live",
) -> Event:
    title = f"Exp {uuid.uuid4().hex[:6]}"
    return Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        end_date=end_date,
        start_time=time(10, 0),
        location_name="L",
        location_normalized="l",
        description="d",
        status=status,
        source="test",
        rrule=rrule,
        is_recurring=bool(rrule),
    )


def test_single_day_yesterday_expires() -> None:
    # cutoff = today; an event that ended yesterday is over → expire (one-day grace).
    ev = _ev(TODAY - timedelta(days=1))
    assert _should_expire(ev, cutoff=TODAY) is True


def test_single_day_today_is_kept() -> None:
    # Today's event is still live through its day.
    ev = _ev(TODAY)
    assert _should_expire(ev, cutoff=TODAY) is False


def test_multiday_still_running_is_kept() -> None:
    # Started in the past but still running (end_date >= today) — the old
    # start-date sweep would have wrongly expired this.
    ev = _ev(TODAY - timedelta(days=10), end_date=TODAY + timedelta(days=2))
    assert _should_expire(ev, cutoff=TODAY) is False


def test_multiday_ended_expires() -> None:
    ev = _ev(TODAY - timedelta(days=10), end_date=TODAY - timedelta(days=1))
    assert _should_expire(ev, cutoff=TODAY) is True


def test_open_ended_recurring_does_not_expire() -> None:
    ev = _ev(TODAY - timedelta(days=30), rrule="FREQ=WEEKLY;BYDAY=MO")
    assert _should_expire(ev, cutoff=TODAY) is False


def test_bounded_recurring_expires_after_until() -> None:
    past = TODAY - timedelta(days=30)
    ev = _ev(past, rrule=f"FREQ=WEEKLY;UNTIL={past.strftime('%Y%m%d')}T000000Z")
    assert _should_expire(ev, cutoff=TODAY) is True


def test_bounded_recurring_with_future_until_is_kept() -> None:
    future = TODAY + timedelta(days=30)
    ev = _ev(TODAY - timedelta(days=30), rrule=f"FREQ=WEEKLY;UNTIL={future.strftime('%Y%m%d')}T000000Z")
    assert _should_expire(ev, cutoff=TODAY) is False


def test_already_expired_is_skipped() -> None:
    ev = _ev(TODAY - timedelta(days=10), status="expired")
    assert _should_expire(ev, cutoff=TODAY) is False


def test_run_dry_run() -> None:
    with SessionLocal() as db:
        ev = _ev(TODAY - timedelta(days=30))
        db.add(ev)
        create_event_and_entity(db, ev)
        db.commit()
        eid = ev.id
    try:
        n = run(dry_run=True)
        assert n >= 1  # our just-added past event must be counted
    finally:
        with SessionLocal() as db:
            row = db.get(Event, eid)
            if row:
                db.delete(row)
                db.commit()
