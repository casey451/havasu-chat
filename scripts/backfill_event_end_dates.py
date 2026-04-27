"""
Set ``events.end_date`` and ``contributions.event_end_date`` from the first
``Date:`` line in linked ``submission_notes`` (RiverScene import only).

  python scripts/backfill_event_end_dates.py
  python scripts/backfill_event_end_dates.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contrib.event_date_line import parse_event_date_line
from app.db.database import SessionLocal
from app.db.models import Contribution, Event

_DATE_LINE_PREFIX = "date:"


def _first_date_line(notes: str | None) -> str | None:
    if not notes:
        return None
    for raw in str(notes).splitlines():
        s = raw.strip()
        if s.lower().startswith(_DATE_LINE_PREFIX):
            return s
    return None


def _iter_river_scene_events(db: Session) -> Iterator[Event]:
    stmt = select(Event).where(Event.source == "river_scene_import").order_by(Event.id)
    for ev in db.execute(stmt).scalars().all():
        yield ev


def _contribution_for_event(db: Session, event_id: str) -> Contribution | None:
    return (
        db.execute(
            select(Contribution)
            .where(Contribution.created_event_id == event_id)
            .order_by(Contribution.id)
            .limit(1)
        )
        .scalars()
        .one_or_none()
    )


def run_backfill(
    dry_run: bool = False,
) -> tuple[
    int,
    int,
    int,
    int,
    int,
    int,
    int,
]:
    """
    For each ``river_scene_import`` event, parse the first ``Date:`` line on the
    linked contribution and align ``end_date`` / ``event_end_date`` with the
    parser result (see Step 5 mismatch policy: skip if parsed start != event.date).

    Returns
    ``(total_processed, updated, skipped_already_correct, skipped_no_date_line,
    skipped_unparseable, skipped_mismatch, skipped_no_contribution)``.
    """
    total = updated = sa_ok = no_line = unpar = mis = no_c = 0
    with SessionLocal() as db:
        for ev in _iter_river_scene_events(db):
            total += 1
            c = _contribution_for_event(db, ev.id)
            if c is None:
                no_c += 1
                print(
                    f"warning: no contribution for event {ev.id} (created_event_id) — skip",
                    file=sys.stderr,
                )
                continue

            line = _first_date_line(c.submission_notes)
            if not line:
                no_line += 1
                print(
                    f"warning: no Date: line in submission_notes (event {ev.id}, "
                    f"contribution {c.id}) — skip",
                    file=sys.stderr,
                )
                continue

            parsed = parse_event_date_line(line)
            if parsed is None:
                unpar += 1
                print(
                    f"warning: unparseable Date line (event {ev.id}, "
                    f"contribution {c.id}): {line!r} — skip",
                    file=sys.stderr,
                )
                continue
            p_start, p_end = parsed
            if p_start != ev.date:
                mis += 1
                print(
                    f"warning: date mismatch: event.date={ev.date!r} vs parsed start "
                    f"{p_start!r} (event {ev.id}, contribution {c.id}) — skip",
                    file=sys.stderr,
                )
                continue

            target: date | None = p_end

            if ev.end_date == target and c.event_end_date == target:
                sa_ok += 1
                continue

            if dry_run:
                print(
                    f"info: [dry-run] would set end_date={target!r} on event {ev.id} "
                    f"and contribution {c.id} (from contribution submission_notes)"
                )
                updated += 1
                continue

            ev.end_date = target
            c.event_end_date = target
            db.add(ev)
            db.add(c)
            db.commit()
            updated += 1
            print(
                f"info: updated event {ev.id} contribution {c.id} "
                f"end_date={target!r} (from contribution submission_notes)"
            )

    print("Backfill event end_date (complete)")
    print(f"  total_processed:           {total}")
    print(f"  updated:                 {updated}")
    print(f"  skipped_already_correct: {sa_ok}")
    print(f"  skipped_no_date_line:    {no_line}")
    print(f"  skipped_unparseable:     {unpar}")
    print(f"  skipped_mismatch:        {mis}")
    print(f"  skipped_no_contribution: {no_c}")
    return (total, updated, sa_ok, no_line, unpar, mis, no_c)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without writing to the database.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    run_backfill(dry_run=bool(args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
