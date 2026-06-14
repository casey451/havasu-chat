"""§6.1 Merge "Quick Bites" into "Restaurants".

Quick Bites is fast-food / takeout (Arby's, McDonald's, Subway, Wienerschnitzel,
ice-cream & juice spots) — all genuine eateries. Per the brief, fold them into
Restaurants rather than keep a separate tab. This reassigns the leaf-landing
field ``Provider.subcategory`` from "quick-bites" to "restaurants" (both already
live under the eat-drink primary, so ``primary_category`` is unchanged).

After this runs, the quick-bites subcategory has 0 active listings; the tab is
removed from the taxonomy separately in code.

Gate (CLAUDE.md): READ-ONLY by default; writes only with ``--apply``. Reversible
— writes a JSON snapshot mapping each id to its previous subcategory.

    .venv\\Scripts\\python.exe scripts\\merge_quick_bites.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\merge_quick_bites.py --apply     # apply + snapshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

FROM_SUB = "quick-bites"
TO_SUB = "restaurants"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the write (default: dry-run)")
    ap.add_argument("--include-inactive", action="store_true",
                    help="also move inactive rows (default: active only)")
    args = ap.parse_args()

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    db = SessionLocal()
    try:
        stmt = select(Provider).where(Provider.subcategory == FROM_SUB)
        if not args.include_inactive:
            stmt = stmt.where(Provider.is_active.is_(True))
        rows = list(db.scalars(stmt).all())

        print(f"{len(rows)} '{FROM_SUB}' rows -> '{TO_SUB}':")
        for p in rows:
            print(f"  {p.provider_name}")

        if not rows:
            print("Nothing to do.")
            return 0
        if not args.apply:
            print(f"\nDRY-RUN: would reassign {len(rows)} rows. Re-run with --apply.")
            return 0

        snapshot = {"script": "merge_quick_bites", "applied_at": stamp,
                    "moved": [{"id": p.id, "from": p.subcategory, "to": TO_SUB} for p in rows]}
        with open(f"merge_quick_bites_snapshot_{stamp}.json", "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)

        for p in rows:
            p.subcategory = TO_SUB
        db.commit()
        print(f"\nAPPLIED: moved {len(rows)} rows. Snapshot: merge_quick_bites_snapshot_{stamp}.json")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
