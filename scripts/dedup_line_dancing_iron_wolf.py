"""Remove the duplicate "Line Dancing" schedule double-listed at Iron Wolf.

Calendar audit (2026-06-23): "Line Dancing" (Wed 5 PM) renders twice on
/events-ui — once on entity `iron-wolf-golf-country-club` (Schedule 729, the
canonical country-club listing) and once on entity
`reflections-steakhouse-at-iron-wolf-golf-and-country-club` (Schedule 998). The
steakhouse is the in-house restaurant of the same club; line dancing is the
club's event, so 998 is a spurious duplicate. Both ENTITIES are legit directory
listings and stay untouched — this soft-hides ONLY the duplicate schedule.

Soft-delete (Schedule has no status flag): set `days_of_week = NULL` so the
calendar expander (which requires days_of_week IS NOT NULL) skips it. Fully
reversible from the printed snapshot. Per CLAUDE.md: dry-run first, show counts,
get approval, then --apply.

    python scripts/dedup_line_dancing_iron_wolf.py            # dry-run (default)
    python scripts/dedup_line_dancing_iron_wolf.py --apply    # commit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Schedule  # noqa: E402

DUP_SCHEDULE_ID = 998
KEEP_SCHEDULE_ID = 729


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        dup = db.query(Schedule).filter(Schedule.id == DUP_SCHEDULE_ID).one_or_none()
        keep = db.query(Schedule).filter(Schedule.id == KEEP_SCHEDULE_ID).one_or_none()
        if dup is None or keep is None:
            print(f"ABORT: dup={dup is not None} keep={keep is not None} (already cleaned?)")
            return
        snap = {
            "schedule_id": dup.id, "entity_id": dup.entity_id,
            "days_of_week": dup.days_of_week, "start_time": str(dup.start_time),
            "notes": dup.notes,
        }
        print("KEEP  :", keep.id, keep.notes, keep.days_of_week, str(keep.start_time))
        print("HIDE  :", dup.id, dup.notes, dup.days_of_week, str(dup.start_time))
        print("SNAPSHOT:", json.dumps(snap))
        if not args.apply:
            print("\nDRY-RUN: would set Schedule 998 days_of_week=NULL (soft-hide). "
                  "Re-run with --apply to commit.")
            return
        dup.days_of_week = None
        db.commit()
        print("APPLIED: Schedule 998 hidden (days_of_week=NULL). Reversible from SNAPSHOT.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
