"""Unpublish class schedules attached to venues that have NO public provider page.

Context (2026-06-18): the schedule-hunt session approved class schedules onto two
entities that don't have a published provider page (search routes them to /home),
so the attached Schedule/Offering rows aren't user-visible on a listing and would
only ever surface as orphans on the month calendar. Casey: "just don't include
them if they don't have a page." This removes the Offering + Schedule (+ this
session's facebook/schedule-scrape SourceEvidence) rows from those two entities
and marks the originating contributions rejected, so the data is cleanly pulled.

It does NOT delete the entities or anything else. Re-runnable / idempotent.

Targets (entity_id -> venue):
  376286f6-06ce-4eed-a96f-48915db96043  Marsh Dance Studios
  be9e1db7-ad99-41df-886c-be153f5f6831  Driftwood Acres Equine Center (Roping Group)

Originating contributions: 1213-1218 (Marsh), 611 (Driftwood roping).

Usage (per CLAUDE.md: dry-run first, show counts, then apply):
    python scripts/unpublish_pageless_schedules.py            # dry-run (default)
    python scripts/unpublish_pageless_schedules.py --apply    # commit (prod-data delete!)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution, Entity, Offering, Schedule  # noqa: E402

TARGET_ENTITY_IDS = [
    "376286f6-06ce-4eed-a96f-48915db96043",  # Marsh Dance Studios
    "be9e1db7-ad99-41df-886c-be153f5f6831",  # Driftwood Acres Equine Center
]
CONTRIBUTION_IDS = [1213, 1214, 1215, 1216, 1217, 1218, 611]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit the delete (prod-data op)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        offerings = db.query(Offering).filter(Offering.entity_id.in_(TARGET_ENTITY_IDS)).all()
        schedules = db.query(Schedule).filter(Schedule.entity_id.in_(TARGET_ENTITY_IDS)).all()
        contribs = db.query(Contribution).filter(Contribution.id.in_(CONTRIBUTION_IDS)).all()

        for eid in TARGET_ENTITY_IDS:
            ent = db.get(Entity, eid)
            ename = ent.name if ent else "(missing)"
            offs = [o for o in offerings if o.entity_id == eid]
            schs = [s for s in schedules if s.entity_id == eid]
            print(f"{ename} [{eid}]")
            for o in offs:
                print(f"    offering: {o.name}")
            for s in schs:
                print(f"    schedule: type={s.schedule_type} days={s.days_of_week} {s.start_time}-{s.end_time}")

        verb = "DELETING" if args.apply else "would delete"
        print(
            f"\n{verb}: offerings={len(offerings)} schedules={len(schedules)} "
            f"| contributions->rejected={len(contribs)}"
        )

        if not args.apply:
            print("(dry run — no DB writes)")
            return

        for row in (*offerings, *schedules):
            db.delete(row)
        for c in contribs:
            c.status = "rejected"
            c.rejection_reason = "Unpublished: venue has no public provider page (2026-06-18)."
        db.commit()
        print("Committed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
