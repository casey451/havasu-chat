"""Backfill ``Provider.primary_category`` (WP-9 — one of Home's 12 canonical slugs).

Idempotent and re-runnable: recomputes the canonical primary category for every
provider and writes it when it differs. DEFAULT IS DRY-RUN — it prints per-primary
counts (mapped / unmapped / would-change) and writes NOTHING. Pass ``--apply`` to
commit. Safe to run after each ingestion.

The primary is derived deterministically (no LLM) from ``Provider.subcategory``
(the strong Google-derived signal), falling back to the legacy ``Provider.category``
when no subcategory is stored — see app.categories.subcategories.derive_primary_category.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\backfill_primary_category.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\backfill_primary_category.py --apply    # writes
    .venv\\Scripts\\python.exe scripts\\backfill_primary_category.py --all      # include drafts/inactive
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

from app.categories.subcategories import derive_primary_category  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402


def run(*, apply: bool = False, include_all: bool = False) -> Counter:
    """Recompute primary_category for every (active, non-draft) provider.

    Returns a Counter of derived primary -> row count. Writes only when
    ``apply`` is True; otherwise reports what would change.
    """
    db = SessionLocal()
    counts: Counter = Counter()
    changed = 0
    try:
        q = db.query(Provider)
        if not include_all:
            q = q.filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        for provider in q.yield_per(500):
            derived = derive_primary_category(
                category=provider.category,
                subcategory=provider.subcategory,
                google_primary_category=provider.google_primary_category,
                google_categories=provider.google_categories,
                attributes=provider.attributes,
            )
            counts[derived] += 1
            if derived != provider.primary_category:
                changed += 1
                if apply:
                    provider.primary_category = derived
        if apply:
            db.commit()
    finally:
        db.close()

    total = sum(counts.values())
    unmapped = counts.get(None, 0)
    mapped = total - unmapped
    verb = "changed" if apply else "would change"
    mode = "APPLY" if apply else "DRY-RUN (no writes)"
    print(f"[{mode}] {verb} {changed} rows; mapped {mapped}/{total} "
          f"({(100 * mapped // total) if total else 0}%), unmapped {unmapped}")
    for primary, n in counts.most_common():
        print(f"  {primary or '<unmapped>'}: {n}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--all", action="store_true", help="include drafts and inactive rows")
    args = parser.parse_args()
    run(apply=args.apply, include_all=args.all)


if __name__ == "__main__":
    main()
