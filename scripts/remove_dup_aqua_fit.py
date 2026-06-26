"""Soft-delete the leaked placeholder event "Dup Aqua Fit 91b5ad".

Calendar audit (2026-06-26): an Aquatic-fitness row literally named
"Dup Aqua Fit 91b5ad" shows every Thursday 6 PM under Fitness & Sports →
Aquatic fitness (venue "Aquatic Center"). The "Dup " prefix + hex suffix is a
de-dup / test artifact that leaked into live data; it is not in source code.

Soft-delete: set status to 'duplicate' (the live calendar only reads
status='live'). Fully reversible (set back to 'live'). Per CLAUDE.md: dry-run,
show, approve, --apply.

    python scripts/remove_dup_aqua_fit.py            # dry-run
    python scripts/remove_dup_aqua_fit.py --apply    # commit
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

DROP_TITLE = "Dup Aqua Fit 91b5ad"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit (prod-data UPDATE)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(Event)
            .filter(Event.title == DROP_TITLE, Event.status == "live")
            .all()
        )
        if not rows:
            print("ABORT: no live 'Dup Aqua Fit 91b5ad' rows found / already removed.")
            return
        snap = [
            {"id": r.id, "title": r.title, "status_before": r.status,
             "venue": r.location_name, "date": str(r.date)}
            for r in rows
        ]
        for r in rows:
            print("DROP  :", r.id, "|", r.location_name, "|", r.date)
        print("SNAPSHOT:", json.dumps(snap))
        if not args.apply:
            print(f"\nDRY-RUN: would set status='duplicate' on {len(rows)} row(s). "
                  "Re-run with --apply.")
            return
        for r in rows:
            r.status = "duplicate"
        db.commit()
        print(f"APPLIED: {len(rows)} row(s) status='duplicate'. "
              "Reversible (set back to 'live').")
    finally:
        db.close()


if __name__ == "__main__":
    main()
