"""Read-only diagnostic: does CATEGORY_FILTERS cover the live Provider.category vocab?

The map_data repoint (PR #78) surfaces pins by mapping each map scope to its
``CATEGORY_FILTERS`` legacy-string set and selecting on ``Provider.category``. If
prod carries ``Provider.category`` strings that no route covers, those providers
will never pin (an under-count, never an over-count). This script reports:

  1. Active/non-draft Provider.category values NOT covered by any CATEGORY_FILTERS
     route — the under-count risk, with provider + geocoded counts.
  2. Per map scope: how many providers match and how many are geocoded (would pin).

SELECT-only — safe to run against prod. Point DATABASE_URL at the target DB:

    DATABASE_URL=<prod-url> python -m scripts.diagnose_map_category_coverage

(PowerShell:  $env:DATABASE_URL="<prod-url>"; python -m scripts.diagnose_map_category_coverage)
"""

from __future__ import annotations

from sqlalchemy import and_, case, func

from app.categories.queries import CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.db.models import Provider


def _covered_legacy_strings() -> set[str]:
    covered: set[str] = set()
    for legacy in CATEGORY_FILTERS.values():
        covered.update(legacy)
    return covered


def main() -> int:
    covered = _covered_legacy_strings()
    # Portable across SQLite (local) and Postgres (prod): a CASE that yields 1
    # when both coords are present, summed — never SUM(boolean), which Postgres
    # rejects.
    geocoded_expr = func.sum(
        case((and_(Provider.lat.isnot(None), Provider.lng.isnot(None)), 1), else_=0)
    )
    with SessionLocal() as db:
        # All active, non-draft providers grouped by legacy category string.
        rows = (
            db.query(Provider.category, func.count(Provider.id), geocoded_expr)
            .filter(Provider.is_active.is_(True), Provider.draft.is_(False))
            .group_by(Provider.category)
            .all()
        )

    by_cat: dict[str, tuple[int, int]] = {}
    for cat, total, geocoded in rows:
        by_cat[cat or "<NULL>"] = (int(total or 0), int(geocoded or 0))

    total_providers = sum(t for t, _ in by_cat.values())
    print("=" * 72)
    print("Provider.category coverage vs CATEGORY_FILTERS (active, non-draft)")
    print("=" * 72)
    print(f"distinct categories: {len(by_cat)}   active providers: {total_providers}")
    print(f"legacy strings covered by some route: {len(covered)}")
    print()

    # --- 1. Uncovered categories (the under-count risk) -------------------
    uncovered = {c: v for c, v in by_cat.items() if c not in covered}
    print("-- UNCOVERED categories (will never pin on any scope) --")
    if not uncovered:
        print("  (none — every active Provider.category is covered by a route)")
    else:
        lost_providers = 0
        lost_geocoded = 0
        for cat, (total, geocoded) in sorted(uncovered.items(), key=lambda kv: -kv[1][0]):
            lost_providers += total
            lost_geocoded += geocoded
            print(f"  {cat:<32} providers={total:<5} geocoded(would-pin)={geocoded}")
        print(
            f"  => {lost_providers} providers ({lost_geocoded} geocoded) are invisible "
            f"to the map until added to a CATEGORY_FILTERS route."
        )
    print()

    # --- 2. Per-scope pin potential --------------------------------------
    print("-- Per map scope: matched providers / geocoded (would-pin) --")
    for slug in sorted(CATEGORY_FILTERS):
        legacy = CATEGORY_FILTERS[slug]
        matched = sum(by_cat.get(s, (0, 0))[0] for s in legacy)
        geocoded = sum(by_cat.get(s, (0, 0))[1] for s in legacy)
        flag = "  <-- 0 pins!" if geocoded == 0 and matched > 0 else ""
        print(f"  {slug:<28} matched={matched:<5} geocoded={geocoded}{flag}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
