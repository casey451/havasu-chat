"""Apply explicit subcategory moves from a reviewed CSV (2026-06-15 coverage audit).

These are rows the auto-deriver (scripts/backfill_subcategory.py) can NOT decide
from Google types or the name routers — they need a human-reviewed mapping
(e.g. Specialty -> Boutiques/Markets, golf courses out of Parks, CVS out of
Boutiques). The CSV is the source of truth.

Matching is conservative: an active, non-draft provider is matched ONLY on an
exact, case-insensitive ``provider_name``. Zero matches and multiple matches are
both reported and skipped (never guessed), so this can only ever move a row we
are certain about. Setting ``Provider.subcategory`` is sufficient for the
``/lake-havasu/{subcategory}`` page to surface it (same mechanism the backfill
uses).

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\apply_recategorizations.py --dry-run
    .venv\\Scripts\\python.exe scripts\\apply_recategorizations.py            # apply
    .venv\\Scripts\\python.exe scripts\\apply_recategorizations.py --csv other.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func  # noqa: E402

from app.categories.subcategories import subcategory_by_slug  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

DEFAULT_CSV = _ROOT / "category_recategorizations_2026-06-15.csv"


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def run(*, csv_path: Path, dry_run: bool = True) -> Counter:
    counts: Counter = Counter()
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    db = SessionLocal()
    try:
        for row in rows:
            name = (row.get("business") or "").strip()
            target = (row.get("suggested_subcategory") or "").strip()
            if not name:
                continue
            if not target:
                counts["skip_no_target"] += 1
                print(f"  SKIP (no target subcategory): {name}")
                continue
            if subcategory_by_slug(target) is None:
                counts["skip_bad_target"] += 1
                print(f"  SKIP (unknown subcategory '{target}'): {name}")
                continue

            matches = (
                db.query(Provider)
                .filter(
                    func.lower(Provider.provider_name) == _norm(name),
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                )
                .all()
            )
            if not matches:
                counts["unmatched"] += 1
                print(f"  UNMATCHED (no active provider named): {name}")
                continue
            if len(matches) > 1:
                counts["ambiguous"] += 1
                print(f"  AMBIGUOUS ({len(matches)} matches, skipped): {name}")
                continue

            provider = matches[0]
            if provider.subcategory == target:
                counts["already_correct"] += 1
                continue
            counts["changed"] += 1
            print(f"  {'WOULD MOVE' if dry_run else 'MOVED'}: {name}: "
                  f"{provider.subcategory or '<none>'} -> {target}")
            if not dry_run:
                provider.subcategory = target

        if not dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would change" if dry_run else "changed"
    print(
        f"\n{verb} {counts['changed']} rows | already-correct {counts['already_correct']} | "
        f"unmatched {counts['unmatched']} | ambiguous {counts['ambiguous']} | "
        f"skipped(no/bad target) {counts['skip_no_target'] + counts['skip_bad_target']}"
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="recategorization CSV path")
    args = parser.parse_args()
    run(csv_path=args.csv, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
