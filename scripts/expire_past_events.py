"""Expire live events once they are actually over (daily cron).

Usage::

    python -m scripts.expire_past_events
    python -m scripts.expire_past_events --dry-run

Policy (2026-07-13): a live event is expired once it has **fully ended** — i.e.
its *effective end date* (``end_date`` when present, else the start ``date``) is
strictly before today (Lake Havasu). That is a one-day grace: the event stays
live through its last day and the calendar day after the AZ midnight rollover,
then the 2:30 AM AZ cron sweeps it.

Two things changed from the old sweep, which keyed on the **start** ``date`` with
a 7-day grace:
  * **End-date keyed.** A multi-day event that started days ago but is still
    running (``end_date >= today``) is no longer expired mid-run — the old
    start-date test would have expired it on day 8.
  * **One-day grace, not seven.** "Over" events no longer linger up to a week as
    live rows (searchable, in ``/events.ics``, permalinked) after they end.

Recurring series are spared unless their RRULE ``UNTIL`` has passed; an
open-ended series (weekly-forever, or ``rdate`` with no parseable series end) is
never expired here.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from sqlalchemy import select, update

from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.recurrence import parsed_until_from_rrule

logger = logging.getLogger("scripts.expire_past_events")


def _effective_end(event: Event) -> date:
    """The last day the event occupies: its ``end_date`` if set, else its start
    ``date``. Multi-day rows keep their genuine span so they aren't expired while
    still running."""
    return event.end_date or event.date


def _should_expire(event: Event, *, cutoff: date) -> bool:
    """True when ``event`` is fully over before ``cutoff`` (today, Lake Havasu).

    ``cutoff`` is the first still-live calendar day; an event is expired when it
    ended strictly before it (a one-day grace past the end date)."""
    if event.status != "live":
        return False
    # Recurrence is decided by actual recurrence DATA (rrule/rdate), matching
    # app.events.recurrence._event_is_recurring — never the bare is_recurring flag.
    if event.rrule or event.rdate:
        if not event.rrule:
            return False  # rdate-only series: no parseable end → never expire here
        until = parsed_until_from_rrule(event.rrule)
        if until is None:
            return False  # open-ended series (e.g. FREQ=WEEKLY forever)
        return until < cutoff
    return _effective_end(event) < cutoff


def run(*, dry_run: bool = False) -> int:
    cutoff = now_lake_havasu().date()
    with SessionLocal() as db:
        rows = list(db.scalars(select(Event).where(Event.status == "live")).all())
        to_expire = [e.id for e in rows if _should_expire(e, cutoff=cutoff)]
        if not to_expire:
            logger.info("expire_past_events: nothing to expire (cutoff=%s)", cutoff)
            return 0
        if dry_run:
            logger.info(
                "expire_past_events: dry-run would expire %s events (cutoff=%s): %s",
                len(to_expire),
                cutoff,
                to_expire[:10],
            )
            return len(to_expire)
        db.execute(update(Event).where(Event.id.in_(to_expire)).values(status="expired"))
        db.commit()
        logger.info("expire_past_events: expired %s events (cutoff=%s)", len(to_expire), cutoff)
        return len(to_expire)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep live events to expired once over.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    try:
        run(dry_run=args.dry_run)
        return 0
    except Exception:
        logger.exception("expire_past_events failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
