"""Aquatic Center audit #3 (venue-identity) + #4 (duplicate schedules).

#3 — After the #1 cleanup removed the bogus bare "Aquatic Center" *venue*
entities, the remaining split is cosmetic: live events carry the display string
``location_name = "Aquatic Center"`` while the pool's classes sit on the
"Lake Havasu City Aquatic Center" entity, so they render under two venue names.
There is exactly one Aquatic Center in LHC (the municipal one; the "…Indoor
Waterpark" is a separately-named resort facility), so normalising the event
display string to the canonical venue name unifies the pool. Reversible.

#4 — The pool's schedule was captured twice; two duplicate pairs remain on the
"Lake Havasu City Aquatic Center" entity. We keep the better row of each pair
(more complete day-set / more specific title) and soft-remove the other by
NULLing its ``days_of_week`` — the class-occurrence bridge requires
``days_of_week IS NOT NULL`` (app/events/class_occurrences.py), so this drops it
from every calendar/provider surface. Reversible (restore the days).

Both passes snapshot originals to a CSV. Per CLAUDE.md: dry-run -> show ->
approve -> --apply.

    .venv\\Scripts\\python.exe scripts\\aquatic_identity_and_schedule_dedup.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\aquatic_identity_and_schedule_dedup.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event, Schedule  # noqa: E402

CANONICAL_VENUE = "Lake Havasu City Aquatic Center"
CANONICAL_NORM = "lake havasu city aquatic center"

# #4: the duplicate schedule rows to soft-remove (keep the twin noted alongside).
#   716  "Tai Chi (Aquatic)"  Mon/Wed        -> drop (keep 1395 "Tai Chi" Mon/Wed/Fri, fuller cadence)
#   1396 "Arthritis Class"    Mon/Wed/Fri    -> drop (keep 717 "Arthritis Water Class", same slot, specific title)
DUP_SCHEDULE_IDS_TO_DROP = {716: "keep 1395 (Tai Chi, Mon/Wed/Fri)", 1396: "keep 717 (Arthritis Water Class)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    ap.add_argument(
        "--snapshot",
        default=str(Path(__file__).resolve().parents[1] / "aquatic_dedup_undo.csv"),
    )
    args = ap.parse_args()

    db = SessionLocal()
    undo: list[dict] = []
    try:
        # --- #3: normalise event venue display string ---
        evs = db.scalars(
            select(Event).where(
                Event.location_name.ilike("aquatic center%"), Event.status == "live"
            )
        ).all()
        print(f"#3 venue-identity: {len(evs)} live event(s) with location_name ~ 'Aquatic Center':")
        for ev in evs:
            print(f"    {ev.id[:8]} {ev.title!r} | {ev.location_name!r} -> {CANONICAL_VENUE!r}")
            undo.append({"kind": "event_location", "id": ev.id,
                         "old_location_name": ev.location_name,
                         "old_location_normalized": ev.location_normalized})

        # --- #4: soft-remove duplicate schedules ---
        scheds = db.scalars(
            select(Schedule).where(Schedule.id.in_(list(DUP_SCHEDULE_IDS_TO_DROP)))
        ).all()
        print(f"\n#4 schedule-dedup: {len(scheds)} duplicate schedule(s) to soft-remove:")
        for s in scheds:
            print(f"    id={s.id} notes={s.notes!r} days={s.days_of_week} "
                  f"-> days=NULL  ({DUP_SCHEDULE_IDS_TO_DROP[s.id]})")
            undo.append({"kind": "schedule_days", "id": str(s.id),
                         "old_days_of_week": s.days_of_week})

        if not evs and not scheds:
            print("Nothing to do.")
            return

        if not args.apply:
            print(f"\nDRY-RUN: would update {len(evs)} event(s) + soft-remove {len(scheds)} "
                  "schedule(s). Re-run with --apply.")
            return

        Path(args.snapshot).parent.mkdir(parents=True, exist_ok=True)
        with open(args.snapshot, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["kind", "id", "old_location_name",
                                               "old_location_normalized", "old_days_of_week"])
            w.writeheader()
            for r in undo:
                w.writerow(r)

        for ev in evs:
            ev.location_name = CANONICAL_VENUE
            ev.location_normalized = CANONICAL_NORM
        for s in scheds:
            s.days_of_week = None
        db.commit()
        print(f"\nAPPLIED: {len(evs)} event(s) re-venued, {len(scheds)} schedule(s) days=NULL. "
              f"Undo snapshot: {args.snapshot}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
