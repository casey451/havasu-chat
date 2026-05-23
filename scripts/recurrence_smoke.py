"""One-off RRULE expansion smoke for all live recurring events (Phase 9a).

Usage::

    python -m scripts.recurrence_smoke
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta

from sqlalchemy import or_, select

from app.db.database import SessionLocal
from app.db.models import Event
from app.events.recurrence import expand_event

logger = logging.getLogger("scripts.recurrence_smoke")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    today = date.today()
    window_end = today + timedelta(days=365)
    errors = 0
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(Event).where(
                    Event.status == "live",
                    or_(
                        Event.is_recurring.is_(True),
                        Event.rrule.isnot(None),
                        Event.rdate.isnot(None),
                    ),
                )
            ).all()
        )
        for ev in rows:
            try:
                dates = expand_event(
                    ev, window_start=today, window_end=window_end, cap=100
                )
                logger.info(
                    "ok event=%s title=%r occurrences=%s",
                    ev.id[:8],
                    ev.title[:40],
                    len(dates),
                )
            except ValueError as exc:
                errors += 1
                logger.warning("cap-exceeded event=%s: %s", ev.id, exc)
            except Exception as exc:
                errors += 1
                logger.warning("parse-error event=%s: %s", ev.id, exc)
    logger.info(
        "recurrence_smoke complete: %s events, %s errors", len(rows), errors
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
