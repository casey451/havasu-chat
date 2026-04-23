"""
Backfill events.is_recurring from title/description/tags heuristics (Phase 8.9).

Uses DATABASE_URL like other scripts (e.g. scripts/activate_scraped_programs.py).
Does not auto-commit: prints a report, then prompts Commit changes? [y/N].

Usage (local or Railway with injected DATABASE_URL):
  python scripts/backfill_event_recurrence.py
  railway run python scripts/backfill_event_recurrence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.event_recurrence import is_recurring_from_event_model
from app.db.database import SessionLocal
from app.db.models import Event


def _run() -> int:
    with SessionLocal() as db:
        events = list(db.query(Event).order_by(Event.date, Event.id).all())
        total = len(events)
        recurring: list[Event] = []
        to_true: list[Event] = []
        to_false: list[Event] = []

        for e in events:
            want = is_recurring_from_event_model(e)
            if want and not e.is_recurring:
                to_true.append(e)
            elif not want and e.is_recurring:
                to_false.append(e)
            if want:
                recurring.append(e)

    print("--- backfill_event_recurrence (Phase 8.9) ---")
    print(f"Total events: {total}")
    print(f"Classified as recurring (by heuristic): {len(recurring)}")
    print(f"Will set is_recurring True:  {len(to_true)}")
    print(f"Will set is_recurring False: {len(to_false)}")

    one_time = total - len(recurring)
    print(f"One-time (unchanged or inferred non-recurring): {one_time}")
    print()
    if recurring:
        print("Recurring (id + title) — owner review:")
        for e in sorted(recurring, key=lambda x: (x.title or "", x.id)):
            print(f"  {e.id}  {e.title!r}")
    else:
        print("No events matched recurring heuristics.")

    try:
        answer = input("Commit changes? [y/N] ").strip().lower()
    except EOFError:
        print("\nNo TTY / EOF — not committing.")
        return 1

    if answer != "y":
        print("Aborted; no changes written.")
        return 0

    with SessionLocal() as db:
        for e in db.query(Event).all():
            want = is_recurring_from_event_model(e)
            if e.is_recurring != want:
                e.is_recurring = want
        db.commit()
    print("Committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
