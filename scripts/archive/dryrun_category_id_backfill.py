"""DRY-RUN: report exactly what the category_id backfill migration will do.

READ-ONLY — no writes. Uses the SAME plan (app.categories.backfill_plan) the
alembic data migration applies, so these counts match the real run. Shows, per
legacy category, how many NULL-category_id providers will be assigned to which
bucket, plus the rows deliberately left NULL (uncategorized/misc).

Run:  PYTHONPATH=. .venv\\Scripts\\python.exe scripts/dryrun_category_id_backfill.py
"""

from __future__ import annotations

from collections import Counter

from app.categories.backfill_plan import LEGACY_TO_BUCKET, NEW_BUCKETS
from app.db.database import SessionLocal
from app.db.models import Category, Provider


def main() -> None:
    with SessionLocal() as db:
        existing_slugs = {c.slug for c in db.query(Category).all()}
        rows = (
            db.query(Provider.category)
            .filter(Provider.category_id.is_(None))
            .all()
        )

    by_legacy: Counter[str] = Counter((c or "(empty)").strip().lower() for (c,) in rows)
    total = sum(by_legacy.values())

    will_create = [f"{slug} ({name})" for slug, name, _ in NEW_BUCKETS if slug not in existing_slugs]

    assigned: list[tuple[str, str, int]] = []  # (legacy, bucket, count)
    left_null: list[tuple[str, int]] = []
    for legacy, count in by_legacy.most_common():
        bucket = LEGACY_TO_BUCKET.get(legacy)
        if bucket:
            assigned.append((legacy, bucket, count))
        else:
            left_null.append((legacy, count))

    print("=" * 68)
    print("DRY-RUN — category_id backfill migration (b1f2a3c4d5e6) — NO WRITES")
    print("=" * 68)
    print(f"Providers with NULL category_id: {total}")
    print(f"\nNew Category buckets to seed: {', '.join(will_create) or '(none — all exist)'}")
    assigned_total = sum(c for _, _, c in assigned)
    print(f"\nWILL ASSIGN ({assigned_total}):")
    for legacy, bucket, count in assigned:
        print(f"    {legacy:24s} -> {bucket:26s} {count}")
    null_total = sum(c for _, c in left_null)
    print(f"\nLEFT NULL — unclassified, honest ({null_total}):")
    for legacy, count in left_null:
        print(f"    {legacy:24s} {count}")
    print("\n" + "-" * 68)
    print(f"Summary: assign {assigned_total} | leave {null_total} NULL | of {total} total")
    print("Applied on deploy via the alembic migration (reversible downgrade).")


if __name__ == "__main__":
    main()
