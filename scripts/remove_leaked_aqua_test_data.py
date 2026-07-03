"""Neutralise leaked test data that renders "Dup Aqua Fit …" on the calendar.

Root cause (2026-07-03 audit, corrected): the Thursday-6PM "Dup Aqua Fit" rows
are NOT a Program (the earlier remove_dup_aqua_fit*.py scripts targeted Event and
Program and found nothing live). They come from two leaked **test venue
Entities** — ``source='t'``, ``ve-XXXXXX`` slugs, named "Aquatic Center" — each
carrying a recurring Thursday Schedule. The class-occurrence bridge
(app/events/class_occurrences.py:158-160) only renders schedules whose Entity
``is_active`` is True, so deactivating those two entities removes the render
cleanly and REVERSIBLY (set is_active back to True). A stray live Event titled
"Dup Aqua Fit …" is also marked status='duplicate' (matching the prior cleanup).

Soft, reversible. Per CLAUDE.md: dry-run -> show -> approve -> --apply.

    .venv\\Scripts\\python.exe scripts\\remove_leaked_aqua_test_data.py           # dry-run
    .venv\\Scripts\\python.exe scripts\\remove_leaked_aqua_test_data.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity, Event, Schedule  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # 1. leaked test venue entities: source='t' + aquatic name (the render source)
        ents = db.scalars(
            select(Entity).where(
                Entity.source == "t",
                Entity.name.ilike("%aquatic%"),
                Entity.is_active.is_(True),
            )
        ).all()
        # 2. stray live "Dup Aqua Fit" events
        evs = db.scalars(
            select(Event).where(Event.title.like("Dup Aqua Fit%"), Event.status == "live")
        ).all()

        snap: list[dict] = []
        for e in ents:
            scheds = db.scalars(select(Schedule).where(Schedule.entity_id == e.id)).all()
            snap.append({"kind": "entity", "id": e.id, "name": e.name, "source": e.source,
                         "slug": e.slug, "schedules": [s.id for s in scheds]})
            print(f"DEACTIVATE entity {e.id[:8]} {e.name!r} source={e.source} "
                  f"slug={e.slug} schedules={[s.id for s in scheds]}")
        for ev in evs:
            snap.append({"kind": "event", "id": ev.id, "title": ev.title,
                         "status_before": ev.status})
            print(f"MARK-DUPLICATE event {ev.id[:8]} {ev.title!r} (status live -> duplicate)")

        if not ents and not evs:
            print("Nothing to do — no active leaked aquatic test entities or live Dup Aqua Fit events.")
            return

        print("\nSNAPSHOT:", json.dumps(snap, default=str))
        if not args.apply:
            print(f"\nDRY-RUN: would deactivate {len(ents)} entity(ies) + mark "
                  f"{len(evs)} event(s) duplicate. Re-run with --apply.")
            return

        for e in ents:
            e.is_active = False
        for ev in evs:
            ev.status = "duplicate"
        db.commit()
        print(f"\nAPPLIED: {len(ents)} entity(ies) is_active=False, {len(evs)} event(s) "
              "status=duplicate. Reversible (entity is_active=True / event status=live).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
