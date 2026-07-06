"""T3.5 — flag verified out-of-area rows is_local=False (gate already enforced).

The leaf/home/map queries already exclude ``Provider.is_local == False``
(app/categories/leaf_pages.py). This sets that flag on landmarks/tours that are
NOT in the Lake Havasu area so they stop competing on local surfaces:
  * Hoover Dam (~75 mi, NV/AZ border)
  * Topock Maze / Mystic Maze
  * Blythe Intaglios (~100 mi, Blythe CA)
  * London Bridge Jet Boat Tour (operates out of Laughlin)

Audit rows the DATA contradicted are deliberately NOT touched: California
Dermatology Institute and Screenworks both carry Lake Havasu City addresses
(local despite the name), and the "Parker …" businesses are LHC-addressed (Parker
is the business name, not a location).

Match is exact (case-insensitive) on the curated names. DRY-RUN by default;
``--apply`` writes and emits an undo CSV. Reversible — restore any day-trip
landmark by setting is_local back to True.

    .venv\\Scripts\\python.exe scripts\\set_out_of_area_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\set_out_of_area_2026_07_06.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import func, select  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_UNDO_CSV = "set_out_of_area_undo_2026-07-06.csv"

_OUT_OF_AREA_NAMES = {
    "hoover dam",
    "topock maze (mystic maze)",
    "blythe intaglios",
    "london bridge jet boat tour",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flag out-of-area rows is_local=False.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        rows = db.scalars(
            select(Provider).where(
                func.lower(Provider.provider_name).in_(_OUT_OF_AREA_NAMES),
                Provider.is_active.is_(True),
            )
        ).all()
        targets = [p for p in rows if p.is_local is not False]

        print(f"matched active rows={len(rows)}  would set is_local=False on={len(targets)}")
        for p in targets:
            print(f"    id={p.id} name={p.provider_name!r} is_local={p.is_local} region={p.region!r}")

        if not targets:
            print("Nothing to update.")
            return 0
        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "provider_name", "old_is_local"])
            for p in targets:
                w.writerow([p.id, p.provider_name, p.is_local])

        for p in targets:
            p.is_local = False
        db.commit()
        print(f"APPLIED: set is_local=False on {len(targets)} rows. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
