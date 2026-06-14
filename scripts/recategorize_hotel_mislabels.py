"""§6.3 follow-up: two rows mislabeled under the 'hotels' subcategory are a bar
and a restaurant. Move them to their correct eat-drink subcategories (they are
real local businesses — recategorize, never hide).

Exact-name match (case-insensitive equality) so 'HEAT Bar' can't catch the
separate 'Heat Hotel' row.

Gate (CLAUDE.md): READ-ONLY by default; writes only with ``--apply`` + snapshot.

    .venv\\Scripts\\python.exe scripts\\recategorize_hotel_mislabels.py
    .venv\\Scripts\\python.exe scripts\\recategorize_hotel_mislabels.py --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

# exact lower-name -> (subcategory, primary_category)
TARGETS = {
    "heat bar": ("bars-breweries", "eat-drink"),
    "turtle grille at the nautical beachfront resort": ("restaurants", "eat-drink"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform writes (default: dry-run)")
    args = ap.parse_args()

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    db = SessionLocal()
    try:
        changes = []
        for name_l, (sub, prim) in TARGETS.items():
            rows = list(db.scalars(select(Provider).where(
                func.lower(Provider.provider_name) == name_l)))
            for p in rows:
                changes.append((p, sub, prim))
                print(f"{p.provider_name!r}: subcategory {p.subcategory!r} -> {sub!r}, "
                      f"primary {p.primary_category!r} -> {prim!r}")

        if not changes:
            print("No matching rows found.")
            return 0
        if not args.apply:
            print(f"\nDRY-RUN: would update {len(changes)} rows. Re-run with --apply.")
            return 0

        snap = {"script": "recategorize_hotel_mislabels", "applied_at": stamp,
                "changed": [{"id": p.id, "name": p.provider_name,
                             "old_subcategory": p.subcategory,
                             "old_primary": p.primary_category} for p, _, _ in changes]}
        with open(f"recat_hotel_mislabels_snapshot_{stamp}.json", "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=2)

        for p, sub, prim in changes:
            p.subcategory = sub
            p.primary_category = prim
        db.commit()
        print(f"\nAPPLIED: updated {len(changes)} rows. "
              f"Snapshot: recat_hotel_mislabels_snapshot_{stamp}.json")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
