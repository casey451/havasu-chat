"""Backfill ``Provider.subcategory`` from Google types / legacy category.

Idempotent and re-runnable: recomputes the derived subcategory for every active,
non-draft provider and writes it when it differs. Safe to run after each
ingestion. Prints a coverage summary; never raises on an individual row.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\backfill_subcategory.py
    .venv\\Scripts\\python.exe scripts\\backfill_subcategory.py --dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_subcategory.py --all   # include drafts/inactive
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.subcategories import derive_subcategory  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def run(*, dry_run: bool = False, include_all: bool = False) -> Counter:
    db = SessionLocal()
    counts: Counter = Counter()
    changed = 0
    try:
        q = db.query(Provider)
        if not include_all:
            q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        for provider in q.yield_per(500):
            derived = derive_subcategory(
                category=provider.category,
                google_primary_category=provider.google_primary_category,
                google_categories=provider.google_categories,
                attributes=provider.attributes,
            )
            counts[derived] += 1
            if derived != provider.subcategory:
                changed += 1
                if not dry_run:
                    provider.subcategory = derived
        if not dry_run:
            db.commit()
    finally:
        db.close()

    total = sum(counts.values())
    mapped = total - counts.get(None, 0)
    verb = "would change" if dry_run else "changed"
    print(f"{verb} {changed} rows; mapped {mapped}/{total} ({(100 * mapped // total) if total else 0}%)")
    for sub, n in counts.most_common():
        print(f"  {sub or '<unmapped>'}: {n}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--all", action="store_true", help="include drafts and inactive rows")
    args = parser.parse_args()
    run(dry_run=args.dry_run, include_all=args.all)


if __name__ == "__main__":
    main()
