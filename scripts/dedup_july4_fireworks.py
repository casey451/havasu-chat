"""Collapse the duplicate July-4 fireworks listing (two feeds, one event).

Calendar audit (2026-06-23): the July 4 Rotary Park fireworks is listed twice:
  KEEP   aa51b758  "4th of July Fireworks at the Beach"        go_lake_havasu   venue "Rotary Park"
  DROP   1ef18616  "4th of July Fireworks in Lake Havasu City" river_scene_import venue "Rotary Park 1400 S. Smoketree..."
Same date (2026-07-04), same venue (Rotary Park), same event. The go_lake_havasu
row has the cleaner title + venue, so it is the survivor.

Soft-delete: set the duplicate's status to 'duplicate' (the same value the
ingest dedup uses; the live calendar only reads status='live'). Fully reversible
(set back to 'live'). Per CLAUDE.md: dry-run, show, approve, --apply.

    python scripts/dedup_july4_fireworks.py            # dry-run
    python scripts/dedup_july4_fireworks.py --apply    # commit
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
from app.db.models import Event  # noqa: E402

KEEP_ID = "aa51b758"   # prefix; resolved below
DROP_TITLE = "4th of July Fireworks in Lake Havasu City"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        dup = (
            db.query(Event)
            .filter(Event.title == DROP_TITLE, Event.status == "live")
            .one_or_none()
        )
        if dup is None:
            print("ABORT: duplicate not found / already collapsed.")
            return
        snap = {"id": dup.id, "title": dup.title, "status_before": dup.status,
                "venue": dup.location_name, "date": str(dup.date)}
        print("DROP  :", dup.id, dup.title, "|", dup.location_name, "|", dup.date)
        print("SNAPSHOT:", json.dumps(snap))
        if not args.apply:
            print("\nDRY-RUN: would set status='duplicate' on this row. Re-run with --apply.")
            return
        dup.status = "duplicate"
        db.commit()
        print("APPLIED: status='duplicate'. Reversible (set back to 'live').")
    finally:
        db.close()


if __name__ == "__main__":
    main()
