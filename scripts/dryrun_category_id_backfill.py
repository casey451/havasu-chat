"""DRY-RUN: propose Provider.category_id backfill for rows where it's NULL.

READ-ONLY — makes no writes. Reuses the SAME legacy-category -> tier-1 route
mapping the live category pages use (``CATEGORY_FILTERS``), then resolves the
route slug to a ``Category`` row. This guarantees a provider's proposed
``category_id`` matches the page it already appears on.

Buckets the report into:
  * assignable    — legacy category maps to a route that HAS a Category row.
  * needs_bucket  — maps to a real route (things-to-do, professional, beauty-care,
                    attractions, services) that has NO Category row yet → blocked
                    on seeding those Category rows first (a gated prod write +
                    taxonomy decision).
  * ambiguous     — legacy category appears under >1 route → needs a hand rule.
  * unmappable    — legacy category in no route (uncategorized, misc) → stays NULL.

Run:  .venv\\Scripts\\python.exe scripts/dryrun_category_id_backfill.py
Nothing is applied. The real backfill is a separate, owner-approved step.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.categories.queries import CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.db.models import Category, Provider


def _legacy_to_routes() -> dict[str, list[str]]:
    """Invert CATEGORY_FILTERS: legacy Provider.category value -> [route slugs]."""
    out: dict[str, list[str]] = defaultdict(list)
    for route, legacy_values in CATEGORY_FILTERS.items():
        for legacy in legacy_values:
            out[legacy].append(route)
    return out


def main() -> None:
    legacy_to_routes = _legacy_to_routes()
    with SessionLocal() as db:
        route_to_cat_id = {c.slug: c.id for c in db.query(Category).all()}
        rows = (
            db.query(Provider.id, Provider.category)
            .filter(Provider.category_id.is_(None))
            .all()
        )

    total = len(rows)
    assignable: Counter[str] = Counter()      # route slug -> count
    needs_bucket: Counter[str] = Counter()     # route slug (no Category row) -> count
    ambiguous: Counter[str] = Counter()        # legacy cat -> count
    unmappable: Counter[str] = Counter()       # legacy cat -> count

    for _pid, legacy in rows:
        legacy = (legacy or "").strip().lower()
        routes = legacy_to_routes.get(legacy, [])
        if not routes:
            unmappable[legacy or "(empty)"] += 1
        elif len(routes) > 1:
            ambiguous[legacy] += 1
        else:
            route = routes[0]
            if route in route_to_cat_id:
                assignable[route] += 1
            else:
                needs_bucket[route] += 1

    def _dump(title: str, counter: Counter[str]) -> int:
        n = sum(counter.values())
        print(f"\n{title}: {n}")
        for key, cnt in counter.most_common():
            print(f"    {key}: {cnt}")
        return n

    print("=" * 64)
    print("DRY-RUN — Provider.category_id backfill proposal (NO WRITES)")
    print("=" * 64)
    print(f"Providers with NULL category_id: {total}")
    a = _dump("ASSIGNABLE now (route has a Category row)", assignable)
    b = _dump("NEEDS new Category row first (gated decision)", needs_bucket)
    c = _dump("AMBIGUOUS (legacy cat under >1 route — needs a hand rule)", ambiguous)
    d = _dump("UNMAPPABLE (no route — stays NULL, honest)", unmappable)
    print("\n" + "-" * 64)
    print(f"Summary: {a} assignable | {b} need-bucket | {c} ambiguous | {d} unmappable")
    print("Nothing was written. Apply only after owner review of the above.")


if __name__ == "__main__":
    main()
