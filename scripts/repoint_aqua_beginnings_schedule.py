"""Re-point the Aqua Beginnings class schedule onto its provider-bearing entity.

Calendar-completeness finding (2026-06-23): the "Swim Lessons (Station-Based
Program)" Schedule sits on entity ``aqua-beginnings`` (slug ``aqua-beginnings``),
which has NO Provider row, so the /events-ui row renders with no link. A SIBLING
entity ``aqua-beginnings-swim-lessons`` already has an active, non-draft Provider
(slug ``aqua-beginnings-swim-lessons``, website https://aquabeginnings.com/,
description "Kids swim lesson program"). Moving the Schedule to the provider
entity makes the calendar row link to the existing directory page — no new
content, no new Provider.

Per CLAUDE.md: dry-run first (default), show counts, get Casey's approval, apply.
Read-only by default; --apply commits (prod-data UPDATE). Re-runnable / idempotent.

    python scripts/repoint_aqua_beginnings_schedule.py            # dry-run
    python scripts/repoint_aqua_beginnings_schedule.py --apply    # commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity, Provider, Schedule  # noqa: E402

FROM_SLUG = "aqua-beginnings"                 # entity with the schedule, no provider
TO_SLUG = "aqua-beginnings-swim-lessons"      # entity with the active provider


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit the move (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        src = db.query(Entity).filter(Entity.slug == FROM_SLUG).one_or_none()
        dst = db.query(Entity).filter(Entity.slug == TO_SLUG).one_or_none()
        if src is None or dst is None:
            print(f"ABORT: entities not found (src={src is not None}, dst={dst is not None})")
            return
        prov = db.query(Provider).filter(Provider.entity_id == dst.id).one_or_none()
        if prov is None or not prov.is_active or prov.draft:
            print(f"ABORT: destination entity has no usable provider (prov={prov is not None})")
            return
        scheds = db.query(Schedule).filter(Schedule.entity_id == src.id).all()
        already = db.query(Schedule).filter(Schedule.entity_id == dst.id).count()
        print(f"src entity {src.id} ({FROM_SLUG}) schedules: {len(scheds)}")
        print(f"dst entity {dst.id} ({TO_SLUG}) provider slug={prov.slug!r} "
              f"website={prov.website!r}; existing schedules: {already}")
        for s in scheds:
            print(f"  would move schedule id={s.id} notes={s.notes!r} days={s.days_of_week}")
        if not args.apply:
            print(f"\nDRY-RUN: would move {len(scheds)} schedule(s) -> /provider/{prov.slug}. "
                  f"Re-run with --apply to commit.")
            return
        for s in scheds:
            s.entity_id = dst.id
        db.commit()
        print(f"APPLIED: moved {len(scheds)} schedule(s) onto {TO_SLUG}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
