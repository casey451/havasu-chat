"""Audit: listings whose stored primary_category disagrees with what the
canonical deriver computes from their source signals (READ-ONLY).

Reuses ``app.categories.subcategories.derive_primary_category`` — the same pure
function the ingest + backfill paths use — so this introduces NO new
classification heuristics. For every Provider it recomputes the category from
(subcategory, category, google_primary_category, google_categories, attributes)
and flags rows where the stored ``primary_category`` differs from the derived
one AND the deriver is confident (returns a non-None slug).

Output: proposed moves grouped by (from -> to) with counts and sample rows, then
a flat list. Makes ZERO writes. This is the dry-run half of the
dry-run -> show-counts -> approve -> apply protocol; an --apply companion is
intentionally NOT part of this file.

Usage (run against whatever DATABASE_URL is set; for prod, the operator runs it
in the prod env):
    .venv\\Scripts\\python.exe scripts\\audit_miscategorized.py
    .venv\\Scripts\\python.exe scripts\\audit_miscategorized.py --limit-samples 5
    .venv\\Scripts\\python.exe scripts\\audit_miscategorized.py --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.queries import CATEGORY_FILTERS  # noqa: E402
from app.categories.subcategories import derive_primary_category  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

VALID = set(CATEGORY_FILTERS.keys())


def _audit(limit_samples: int, csv_path: str | None) -> int:
    db = SessionLocal()
    try:
        rows = db.query(Provider).all()
        total = len(rows)
        moves: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        derived_none = 0
        invalid_stored = 0

        for p in rows:
            stored = (getattr(p, "primary_category", None) or "").strip().lower() or None
            derived = derive_primary_category(
                category=getattr(p, "category", None),
                subcategory=getattr(p, "subcategory", None),
                google_primary_category=getattr(p, "google_primary_category", None),
                google_categories=getattr(p, "google_categories", None),
                attributes=getattr(p, "attributes", None),
            )
            if derived is None:
                derived_none += 1
                continue
            if derived not in VALID:
                continue
            if stored is not None and stored not in VALID:
                invalid_stored += 1
            if stored == derived:
                continue
            # A real proposed move: stored disagrees with a confident derivation.
            moves[(stored or "(none)", derived)].append(
                (
                    getattr(p, "id", None),
                    (getattr(p, "provider_name", None) or "").strip(),
                    getattr(p, "category", None),
                    getattr(p, "subcategory", None),
                    getattr(p, "google_primary_category", None),
                )
            )

        flagged = sum(len(v) for v in moves.values())
        print("=" * 72)
        print("MISCATEGORIZATION AUDIT  (read-only — no writes)")
        print("=" * 72)
        print(f"providers scanned : {total}")
        print(f"proposed moves    : {flagged}")
        print(f"deriver returned None (left as-is): {derived_none}")
        print(f"stored slug not in CATEGORY_FILTERS: {invalid_stored}")
        print("-" * 72)
        print("PROPOSED MOVES BY (from -> to):")
        for (src, dst), items in sorted(moves.items(), key=lambda kv: -len(kv[1])):
            print(f"\n  {src:>28}  ->  {dst:<26}  {len(items)} row(s)")
            for rid, name, cat, sub, gpc in items[:limit_samples]:
                nm = (name or "(unnamed)")[:42]
                print(f"      - {nm:<44} cat={cat} sub={sub} gpc={gpc}")
            if len(items) > limit_samples:
                print(f"      … +{len(items) - limit_samples} more")

        if csv_path:
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(
                    ["provider_id", "name", "from_category", "to_category",
                     "category", "subcategory", "google_primary_category"]
                )
                for (src, dst), items in moves.items():
                    for rid, name, cat, sub, gpc in items:
                        w.writerow([rid, name, src, dst, cat, sub, gpc])
            print(f"\nCSV written: {csv_path}")

        print("\n" + "=" * 72)
        print("NOTHING WAS CHANGED. Review the moves above; if they look right,")
        print("Casey approves and we run the --apply companion against prod.")
        print("=" * 72)
        return 0
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only miscategorization audit.")
    ap.add_argument("--limit-samples", type=int, default=8,
                    help="sample rows to print per (from->to) group")
    ap.add_argument("--csv", default=None, help="optional path to write all proposed moves")
    args = ap.parse_args()
    return _audit(args.limit_samples, args.csv)


if __name__ == "__main__":
    raise SystemExit(main())
