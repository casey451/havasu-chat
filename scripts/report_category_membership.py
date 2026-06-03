"""Report (read-only) provider multi-membership across top-level category routes.

The audit's S2/R2 root cause is that a provider can match more than one top-level
``/categories/{route}`` listing (via overlapping ``CATEGORY_FILTERS`` legacy slugs),
inflating counts and cross-listing churches/gyms. PR-#95-follow-on de-overlapped
the worst offenders (Things-to-Do). The remaining overlaps are the deliberate
parent/child hierarchy (the ``services`` mega is a superset of its tile routes) and
a few test-encoded product decisions (gyms counted under both Health and Sports).

This script does **no writes**. It enumerates, for every active provider, which
top-level routes it currently matches and the single canonical primary route it
*would* get under bucket-based single-membership — the dry-run report that gates the
full taxonomy reclassification (Part D, §D.5). Output: a summary table + a CSV of
the multi-listed providers for Casey to review.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\report_category_membership.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.categories.queries import CATEGORY_FILTERS  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.v1.categories import BUCKET_SLUG_REDIRECTS, bucket_for_legacy_category  # noqa: E402

_REPORT_PATH = _ROOT / "category_membership_report.csv"

# The Explore "top-level" routes a provider can visibly appear under. The mega
# routes (services, things-to-do) are intentional aggregates of their tiles, so we
# treat the *leaf* tile routes as the partition target and exclude the two megas
# from the multi-membership count to avoid flagging legitimate hierarchy.
_MEGA_ROUTES = {"services", "things-to-do"}
_TOP_LEVEL_ROUTES = [r for r in CATEGORY_FILTERS if r not in _MEGA_ROUTES]


def _routes_matching(category: str | None) -> list[str]:
    cat = (category or "").strip().lower()
    return [r for r in _TOP_LEVEL_ROUTES if cat in CATEGORY_FILTERS[r]]


def _primary_route(category: str | None) -> str | None:
    """The single canonical route under bucket-based single-membership."""
    bucket = bucket_for_legacy_category(category)
    dest = BUCKET_SLUG_REDIRECTS.get(bucket)
    return dest.rsplit("/", 1)[-1] if dest else None


def run() -> None:
    db = SessionLocal()
    multi = 0
    total = 0
    current_counts: Counter = Counter()
    proposed_counts: Counter = Counter()
    rows_out: list[dict[str, str]] = []
    by_overlap: dict[str, int] = defaultdict(int)
    try:
        q = db.query(Provider).filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        for p in q.yield_per(500):
            total += 1
            matches = _routes_matching(p.category)
            for r in matches:
                current_counts[r] += 1
            primary = _primary_route(p.category)
            if primary:
                proposed_counts[primary] += 1
            if len(matches) > 1:
                multi += 1
                by_overlap[" + ".join(sorted(matches))] += 1
                rows_out.append(
                    {
                        "id": p.id,
                        "name": p.provider_name or "",
                        "legacy_category": p.category or "",
                        "subcategory": getattr(p, "subcategory", "") or "",
                        "current_routes": " + ".join(sorted(matches)),
                        "proposed_primary": primary or "",
                    }
                )
    finally:
        db.close()

    with _REPORT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "name",
                "legacy_category",
                "subcategory",
                "current_routes",
                "proposed_primary",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_out)

    print("\nCategory membership report — DRY-RUN (read-only)")
    print(f"  providers scanned:            {total}")
    print(f"  multi-listed (>1 top-level):  {multi}")
    print("\n  Top overlap pairs:")
    for combo, n in sorted(by_overlap.items(), key=lambda kv: -kv[1])[:15]:
        print(f"    {n:>5}  {combo}")
    print("\n  Per-route count — current (overlapping) vs proposed (single primary):")
    for r in _TOP_LEVEL_ROUTES:
        print(f"    {r:<28} {current_counts[r]:>6}  ->  {proposed_counts.get(r, 0):>6}")
    print(f"\n  CSV written: {_REPORT_PATH}")


if __name__ == "__main__":
    run()
