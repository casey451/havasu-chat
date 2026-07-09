"""Apply the 2026-06-13 business-category audit (GATED — dry-run by default).

Reads the reviewed audit CSV (``category_audit_flagged_2026-06-13.csv``) and moves
each flagged provider's ``primary_category`` (and ``subcategory`` when the CSV gives
one) to the suggested value. Mirrors every other recategorize_* script in this repo:

    DEFAULT  = DRY RUN. Prints move counts + a sample. Writes NOTHING.
    --apply  = perform writes. Must follow dry-run -> show counts -> Casey approves.

Prod-write discipline (CLAUDE.md): never run ``--apply`` against prod without the
dry-run -> counts -> approval sequence. The script snapshots every changed row's
before/after to a timestamped JSON so a mistaken run is one command to reverse. It
touches only ``primary_category`` and ``subcategory`` (narrowest, reversible change),
resets the advisory ``category_confidence``/``category_flagged_at`` on rows it fixes,
and makes no other changes. It does not push, merge, or migrate.

Usage
-----
    python scripts/apply_category_audit.py                       # dry run
    python scripts/apply_category_audit.py --csv path/to.csv     # dry run, custom CSV
    python scripts/apply_category_audit.py --apply               # WRITE (gated!)

To reject a proposed move: delete its row in the CSV, or blank its ``suggested`` cell.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import PRIMARY_CATEGORY_SLUGS  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

VALID = set(PRIMARY_CATEGORY_SLUGS)
DEFAULT_CSV = _ROOT / "category_audit_flagged_2026-06-13.csv"


def _load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        suggested = (r.get("suggested") or "").strip()
        if not suggested:
            continue  # rejected / blanked by reviewer
        if suggested not in VALID:
            print(f"  ! skipping {r.get('name')!r}: invalid target {suggested!r}")
            continue
        out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--apply", action="store_true", help="perform writes (GATED)")
    ap.add_argument("--limit-samples", type=int, default=15)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 2
    rows = _load_rows(csv_path)
    moves = Counter((r["stored"], r["suggested"]) for r in rows)

    print(f"\nAudit CSV: {csv_path}")
    print(f"Proposed moves: {len(rows)} providers")
    print("\n  count   from -> to")
    for (a, b), n in moves.most_common():
        print(f"  {n:5d}   {a or '(none)'} -> {b}")

    print(f"\nSample (first {args.limit_samples}):")
    for r in rows[: args.limit_samples]:
        print(f"  {r['name'][:46]:46s} {r['stored'] or '(none)'} -> {r['suggested']}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply after approval.")
        return 0

    # --- WRITE PATH (gated) ---
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db = SessionLocal()
    snapshot: list[dict] = []
    changed = 0
    try:
        for r in rows:
            p = db.query(Provider).filter(Provider.id == r["id"]).one_or_none()
            if p is None:
                print(f"  ! id not found, skipping: {r['name']!r}")
                continue
            new_sub = (r.get("suggested_subcategory") or "").strip() or None
            snapshot.append({
                "id": r["id"], "name": p.provider_name,
                "old_primary_category": p.primary_category,
                "new_primary_category": r["suggested"],
                "old_subcategory": p.subcategory,
                "new_subcategory": new_sub,
            })
            p.primary_category = r["suggested"]
            if new_sub:
                p.subcategory = new_sub
            # clear the advisory miscategorization flag now that it's resolved
            if hasattr(p, "category_confidence"):
                p.category_confidence = None
            if hasattr(p, "category_flagged_at"):
                p.category_flagged_at = None
            changed += 1

        snap_path = _ROOT / f"apply_category_audit_snapshot_{ts}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        db.commit()
        print(f"\nAPPLIED: {changed} providers updated.")
        print(f"Rollback snapshot: {snap_path}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
