"""Expire live events past their end date (Phase 9a daily cron).

Usage::

    python -m scripts.expire_past_events
    python -m scripts.expire_past_events --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from sqlalchemy import select, update

from app.db.database import SessionLocal
from app.db.models import Event
from app.events.recurrence import parsed_until_from_rrule

logger = logging.getLogger("scripts.expire_past_events")


def _should_expire(event: Event, *, cutoff: date) -> bool:
    if event.status != "live":
        return False
    if event.date >= cutoff:
        return False
    if not event.rrule:
        return True
    until = parsed_until_from_rrule(event.rrule)
    if until is None:
        return False
    return until < cutoff


def run(*, dry_run: bool = False) -> int:
    cutoff = date.today() - timedelta(days=7)
    with SessionLocal() as db:
        rows = list(db.scalars(select(Event).where(Event.status == "live")).all())
        to_expire = [e.id for e in rows if _should_expire(e, cutoff=cutoff)]
        if not to_expire:
            logger.info("expire_past_events: nothing to expire (cutoff=%s)", cutoff)
            return 0
        if dry_run:
            logger.info(
                "expire_past_events: dry-run would expire %s events: %s",
                len(to_expire),
                to_expire[:10],
            )
            return len(to_expire)
        db.execute(
            update(Event).where(Event.id.in_(to_expire)).values(status="expired")
        )
        db.commit()
        logger.info("expire_past_events: expired %s events", len(to_expire))
        return len(to_expire)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep live events to expired.")
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
