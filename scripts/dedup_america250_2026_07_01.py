"""Collapse the triple-listed America 250 celebration on 2026-07-01.

Calendar audit (2026-06-26): the same ~12 PM July-1 celebration is listed three
times under different titles (one event, multiple ingests):

  KEEP  "Havasu Celebrates America 250 - Pizza Party, Open Swim, and Proclamation"
  DROP  "America 250 Celebration - Pizza & Pool Party"
  DROP  "America 250 Celebration"

Casey chose the descriptive Parks & Rec title as the survivor (2026-06-26).

Soft-delete: set the two duplicates' status to 'duplicate' (the live calendar
only reads status='live'). Fully reversible. Per CLAUDE.md: dry-run, show,
approve, --apply.

    python scripts/dedup_america250_2026_07_01.py            # dry-run
    python scripts/dedup_america250_2026_07_01.py --apply    # commit
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Event  # noqa: E402

EVENT_DATE = date(2026, 7, 1)
KEEP_TITLE = "Havasu Celebrates America 250 - Pizza Party, Open Swim, and Proclamation"
DROP_TITLES = (
    "America 250 Celebration - Pizza & Pool Party",
    "America 250 Celebration",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        keep = (
            db.query(Event)
            .filter(Event.title == KEEP_TITLE, Event.date == EVENT_DATE,
                    Event.status == "live")
            .one_or_none()
        )
        if keep is None:
            print(f"WARNING: survivor not found live on {EVENT_DATE}: {KEEP_TITLE!r}")
            print("Aborting so we never drop all copies. Verify titles/date first.")
            return
        print("KEEP  :", keep.id, "|", keep.location_name, "|", keep.date)

        dups = (
            db.query(Event)
            .filter(Event.title.in_(DROP_TITLES), Event.date == EVENT_DATE,
                    Event.status == "live")
            .all()
        )
        if not dups:
            print("ABORT: no live duplicates found / already collapsed.")
            return
        snap = [
            {"id": d.id, "title": d.title, "status_before": d.status,
             "venue": d.location_name, "date": str(d.date)}
            for d in dups
        ]
        for d in dups:
            print("DROP  :", d.id, d.title, "|", d.location_name, "|", d.date)
        print("SNAPSHOT:", json.dumps(snap))
        if not args.apply:
            print(f"\nDRY-RUN: would set status='duplicate' on {len(dups)} row(s). "
                  "Re-run with --apply.")
            return
        for d in dups:
            d.status = "duplicate"
        db.commit()
        print(f"APPLIED: {len(dups)} row(s) status='duplicate'. "
              "Reversible (set back to 'live').")
    finally:
        db.close()


if __name__ == "__main__":
    main()
