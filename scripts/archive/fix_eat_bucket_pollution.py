"""Fix: clear the eat-bucket subcategory on flagged non-food providers.

Companion to scripts/audit_eat_bucket_pollution.py (same detection heuristic).
For each flagged row, sets ``subcategory = None`` so the provider drops out of
every Eat & Drink surface (intent layer, category pages, chat listings). It
does NOT touch ``category`` or any other field, and never deletes rows --
``backfill_subcategory.py`` can re-derive a correct subcategory later if the
mapping improves.

DRY-RUN BY DEFAULT. Prod flow per CLAUDE.md: run --dry-run, share the counts
with Casey, get approval, then run with --apply.

Usage:
    .venv\\Scripts\\python.exe scripts\\fix_eat_bucket_pollution.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\fix_eat_bucket_pollution.py --apply    # real write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import or_  # noqa: E402

from app.chat.intents.dicts import EAT_LEGACY_CATEGORIES, EAT_SUBCATS  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from scripts.archive.audit_eat_bucket_pollution import looks_non_food  # noqa: E402


def run(*, apply: bool) -> int:
    db = SessionLocal()
    changed = 0
    try:
        rows = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                or_(
                    Provider.subcategory.in_(EAT_SUBCATS),
                    Provider.category.in_(EAT_LEGACY_CATEGORIES),
                ),
            )
            .all()
        )
        for p in rows:
            if not looks_non_food(p.category, p.google_primary_category, p.google_categories):
                continue
            changed += 1
            # Bucket membership is OR(subcategory, category): clear the
            # subcategory AND, when the legacy category itself is an eat value
            # (the Lovedwell case: category='food_drink' on a florist), replace
            # it with Google's primary label so the row leaves the bucket.
            new_cat = p.category
            if p.category in EAT_LEGACY_CATEGORIES:
                g = (p.google_primary_category or "").strip().lower().replace(" ", "_")
                new_cat = g or "uncategorized"
            verb = "FIX" if apply else "would fix"
            cat_part = (
                f", category {p.category!r} -> {new_cat!r}" if new_cat != p.category else ""
            )
            print(
                f"  {verb} {p.provider_name!r}: clear subcategory={p.subcategory!r}"
                f"{cat_part} (google={p.google_primary_category!r})"
            )
            if apply:
                p.subcategory = None
                p.category = new_cat
        if apply:
            db.commit()
    finally:
        db.close()
    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"\n{mode}: {changed} row(s) {'cleared' if apply else 'would be cleared'}")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()
    run(apply=args.apply)
