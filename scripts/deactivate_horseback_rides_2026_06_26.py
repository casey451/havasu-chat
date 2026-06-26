"""One-time gated prod-data op: deactivate the ``havasu-horseback-rides`` venue
Entity so its recurring Schedule occurrences stop expanding onto the calendar
(two-surface spec §6, Casey 2026-06-25).

The "Havasu Horseback Rides / Pony & Lead Line Rides" rows are Schedule-expanded
class occurrences with no usable info. The render-side curated link was already
removed (``_PAGELESS_VENUE_WEBSITES`` in app/events/class_occurrences.py); this
stops the occurrences at the data layer by flipping the Entity publish flag
(``is_active`` -> False). It does **not delete** anything, so it is fully
reversible from the undo snapshot.

Behaviour:

  * ``--dry-run`` (DEFAULT): reports the matched Entity (id / slug / name /
    is_active), its recurring Schedule rows, and the occurrences they expand in a
    14-day window. Writes nothing.
  * a real run (``--apply``) writes an **undo snapshot CSV**
    (entity_id, slug, is_active_before) BEFORE committing, then sets
    ``is_active = False``.

Per ``CLAUDE.md`` a non-dry-run writes to PROD (the repo ``.env`` points
``DATABASE_URL`` at prod): **dry-run -> show counts -> Casey approves -> apply.**

Usage::

    .venv\\Scripts\\python.exe -m scripts.deactivate_horseback_rides_2026_06_26 --dry-run
    .venv\\Scripts\\python.exe -m scripts.deactivate_horseback_rides_2026_06_26 --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity, Schedule  # noqa: E402
from app.events.class_occurrences import class_occurrences_in_window  # noqa: E402

_SLUG = "havasu-horseback-rides"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the prod write (default: dry-run)")
    args = ap.parse_args()
    dry_run = not args.apply

    with SessionLocal() as db:
        ent = db.query(Entity).filter(Entity.slug == _SLUG).one_or_none()
        if ent is None:
            print(f"No Entity with slug {_SLUG!r} — nothing to do.")
            return 0
        scheds = db.query(Schedule).filter(Schedule.entity_id == ent.id).all()
        recurring = [s for s in scheds if s.schedule_type == "recurring"]
        win_start = date.today()
        win_end = win_start + timedelta(days=13)
        occs = [
            o for o in class_occurrences_in_window(db, window_start=win_start, window_end=win_end)
            if (o.venue or "").strip().lower() == (ent.name or "").strip().lower()
        ]

        print(f"Entity: id={ent.id} slug={ent.slug!r} name={ent.name!r} is_active={ent.is_active}")
        print(f"Schedule rows: {len(scheds)} ({len(recurring)} recurring)")
        print(f"Occurrences expanded in {win_start}..{win_end}: {len(occs)}")
        for o in occs[:10]:
            print(f"  - {o.date} {o.title}")

        if dry_run:
            print("\nDRY-RUN — no write performed. Re-run with --apply to deactivate.")
            return 0

        if ent.is_active is False:
            print("\nEntity already inactive — nothing to apply.")
            return 0

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = _ROOT / f"undo_horseback_deactivation_{ts}.csv"
        with snap.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["entity_id", "slug", "is_active_before"])
            w.writerow([ent.id, ent.slug, ent.is_active])
        print(f"\nUndo snapshot written: {snap}")

        ent.is_active = False
        db.commit()
        print(f"APPLIED — Entity {ent.id} ({ent.slug}) is_active set to False.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
