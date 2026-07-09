"""One-time cleanup: retire the movie-tagged Event rows left over from the
events-pipeline approach (before showtimes moved to the dedicated
``movie_showtimes`` table).

Non-destructive: flips ``status`` from ``live`` to ``deleted`` so the rows drop
out of every status-filtered feed, WITHOUT removing Event rows or orphaning their
dual-write ``entities`` graphs. (The defensive ``not_movie_event_clause`` filter
already hides them; this is hygiene so the stale "live" rows don't linger.)

``deleted`` — not ``archived`` — because ``ck_events_status`` only permits
``draft|live|cancelled|expired|pending_review|deleted|duplicate``; ``archived``
is not a valid event status and Postgres rejects the UPDATE. ``deleted`` is the
right fit: the events surface treats a deleted event's permalink as 410 Gone,
which is correct for showtimes that no longer exist as events.

Dry-run by default. This is a production DB write — review the count first.

Usage:
  python scripts/archive_movie_events.py --dry-run
  python scripts/archive_movie_events.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import String, cast, select, update  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

_MOVIE_LIKE = cast(Event.tags, String).like('%"movie"%')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive leftover movie Event rows")
    parser.add_argument("--apply", action="store_true", help="write (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    dry_run = not args.apply or args.dry_run

    with SessionLocal() as db:
        count = len(
            list(
                db.scalars(
                    select(Event.id).where(Event.status == "live", _MOVIE_LIKE)
                ).all()
            )
        )
        if dry_run:
            print(f"DRY RUN: would retire {count} movie-tagged live Event rows (-> deleted)")
            return 0
        db.execute(
            update(Event)
            .where(Event.status == "live", _MOVIE_LIKE)
            .values(status="deleted")
        )
        db.commit()
    print(f"APPLY: retired {count} movie-tagged Event rows (status -> deleted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
