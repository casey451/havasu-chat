"""Read-only audit of provider subcategory / primary-category assignments.

Step 1 of the categorization re-derive workstream
(docs/PROMPT_CATEGORIZATION_WORKSTREAM_2026-06-11.md). Casey reports widespread
miscategorization (med spas under Primary Care, nail salons / dermatologists as
Med Spas, "a lot in the wrong place across the board"). Before touching any
derivation rule we MEASURE the families, not the anecdotes.

This script is strictly READ-ONLY — it opens a session, reads every active
provider, recomputes the derivation with the CURRENT rules, and writes a CSV +
prints a summary. It never writes to the DB, so it needs no approval and can be
run against prod safely (CLAUDE.md: read-only scripts may run anytime).

What it emits per active provider (CSV):
  id, slug, name, google_primary_category, google_categories (| joined),
  sub_trades (| joined), legacy_category, stored_subcategory,
  stored_primary_category, fresh_subcategory, fresh_primary_category,
  leaf_category_slugs (Category slugs the provider's entity links to via
  entity_categories), subcat_mismatch, primary_mismatch.

Printed summary:
  - total active providers; stored-subcategory coverage
  - subcategory + primary mismatch counts
  - the (stored -> fresh) subcategory transition table (mismatches only)
  - top 20 google_primary_category values among subcategory mismatches
  - a focused Health/Beauty section (the verticals Casey named)

Re-running this AFTER the step-2 rule fixes shows exactly what the re-derive
would change (the script imports derive_* live), which is the input to the
step-3 dry-run.

Usage (from repo root, Casey's terminal, prod env):
    .venv\\Scripts\\python.exe scripts/audit_subcategory_assignments.py
Optional:
    --out PATH     CSV destination (default: subcategory_audit_<UTC>.csv in repo root)
    --limit N      cap rows scanned (smoke test)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.categories.subcategories import (  # noqa: E402
    derive_primary_category,
    derive_subcategory,
)
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402

# Health/Beauty focus — google_primary_category tokens worth eyeballing. These
# are NOT new rules; they only decide which rows print in the focused section.
_HEALTH_BEAUTY_TOKENS = (
    "spa", "derma", "nail", "salon", "skin", "massage", "clinic", "doctor",
    "medical", "barber", "hair", "tanning", "wax", "lash", "brow", "physician",
    "wellness", "aesthetic", "cosmetic",
)
_HEALTH_BEAUTY_SUBCATS = {"health-medical", "beauty"}


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _as_list(value) -> list[str]:
    """google_categories may arrive as a JSON list or a JSON string."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _sub_trades(attributes) -> list[str]:
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except (ValueError, TypeError):
            return []
    if isinstance(attributes, dict):
        raw = attributes.get("sub_trades")
        if isinstance(raw, list):
            return [str(s) for s in raw if s]
    return []


def _entity_leaf_map(session) -> dict[str, list[str]]:
    """{entity_id: [Category.slug, ...]} from entity_categories, in one query."""
    from app.db.models import Category, EntityCategory

    rows = (
        session.query(EntityCategory.entity_id, Category.slug)
        .join(Category, Category.id == EntityCategory.category_id)
        .all()
    )
    out: dict[str, list[str]] = {}
    for entity_id, slug in rows:
        out.setdefault(entity_id, []).append(slug)
    return out


def run(*, out_path: Path, limit: int | None = None, session=None) -> dict:
    from app.db.models import Provider

    own_session = session is None
    session = session or SessionLocal()
    try:
        leaf_map = _entity_leaf_map(session)

        q = session.query(Provider).filter(Provider.is_active.is_(True))
        if limit:
            q = q.limit(limit)
        providers = q.all()

        rows: list[dict] = []
        subcat_mismatches = 0
        primary_mismatches = 0
        stored_subcat_present = 0
        transitions: Counter = Counter()
        mismatch_gpc: Counter = Counter()

        for p in providers:
            gpc = p.google_primary_category
            gcats = _as_list(p.google_categories)
            subtrades = _sub_trades(p.attributes)

            fresh_sub = derive_subcategory(
                category=p.category,
                google_primary_category=gpc,
                google_categories=p.google_categories,
                attributes=p.attributes,
            )
            fresh_primary = derive_primary_category(
                category=p.category,
                subcategory=fresh_sub,
                google_primary_category=gpc,
                google_categories=p.google_categories,
                attributes=p.attributes,
            )

            stored_sub = (p.subcategory or None)
            stored_primary = (p.primary_category or None)
            if stored_sub:
                stored_subcat_present += 1

            subcat_mismatch = (stored_sub or None) != (fresh_sub or None)
            primary_mismatch = (stored_primary or None) != (fresh_primary or None)
            if subcat_mismatch:
                subcat_mismatches += 1
                transitions[(stored_sub or "∅", fresh_sub or "∅")] += 1
                mismatch_gpc[gpc or "∅"] += 1
            if primary_mismatch:
                primary_mismatches += 1

            leaf_slugs = leaf_map.get(p.entity_id, [])

            rows.append(
                {
                    "id": p.id,
                    "slug": p.slug or "",
                    "name": p.provider_name,
                    "google_primary_category": gpc or "",
                    "google_categories": "|".join(gcats),
                    "sub_trades": "|".join(subtrades),
                    "legacy_category": p.category or "",
                    "stored_subcategory": stored_sub or "",
                    "stored_primary_category": stored_primary or "",
                    "fresh_subcategory": fresh_sub or "",
                    "fresh_primary_category": fresh_primary or "",
                    "leaf_category_slugs": "|".join(leaf_slugs),
                    "subcat_mismatch": "1" if subcat_mismatch else "0",
                    "primary_mismatch": "1" if primary_mismatch else "0",
                }
            )

        _write_csv(out_path, rows)
        summary = {
            "db_target": _sanitized_target(),
            "out_path": str(out_path),
            "total_active": len(providers),
            "stored_subcat_present": stored_subcat_present,
            "subcat_mismatches": subcat_mismatches,
            "primary_mismatches": primary_mismatches,
            "transitions": transitions,
            "mismatch_gpc": mismatch_gpc,
            "rows": rows,
        }
        _print_summary(summary)
        return summary
    finally:
        if own_session:
            session.close()


def _write_csv(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "id", "slug", "name", "google_primary_category", "google_categories",
        "sub_trades", "legacy_category", "stored_subcategory",
        "stored_primary_category", "fresh_subcategory", "fresh_primary_category",
        "leaf_category_slugs", "subcat_mismatch", "primary_mismatch",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(summary: dict) -> None:
    print("=" * 72)
    print("Subcategory assignment audit (READ-ONLY)")
    print(f"DB target : {summary['db_target']}")
    print(f"CSV       : {summary['out_path']}")
    print("-" * 72)
    total = summary["total_active"]
    print(f"Active providers          : {total}")
    print(
        f"With stored subcategory   : {summary['stored_subcat_present']} "
        f"({_pct(summary['stored_subcat_present'], total)})"
    )
    print(
        f"Subcategory mismatches    : {summary['subcat_mismatches']} "
        f"({_pct(summary['subcat_mismatches'], total)})  "
        f"[stored != fresh derivation]"
    )
    print(
        f"Primary-category mismatches: {summary['primary_mismatches']} "
        f"({_pct(summary['primary_mismatches'], total)})"
    )

    print("-" * 72)
    print("Top (stored -> fresh) subcategory transitions (mismatches only):")
    for (old, new), n in summary["transitions"].most_common(30):
        print(f"  {n:>5}  {old:>22}  ->  {new}")

    print("-" * 72)
    print("Top google_primary_category among subcategory mismatches:")
    for tok, n in summary["mismatch_gpc"].most_common(20):
        print(f"  {n:>5}  {tok}")

    print("-" * 72)
    print("Health / Beauty focus (stored OR fresh in {health-medical, beauty}, "
          "or a health/beauty google type):")
    hb = [
        r for r in summary["rows"]
        if r["stored_subcategory"] in _HEALTH_BEAUTY_SUBCATS
        or r["fresh_subcategory"] in _HEALTH_BEAUTY_SUBCATS
        or any(t in (r["google_primary_category"] or "").lower()
               for t in _HEALTH_BEAUTY_TOKENS)
    ]
    hb_mismatch = [r for r in hb if r["subcat_mismatch"] == "1"]
    print(f"  Health/Beauty rows        : {len(hb)}")
    print(f"  ...of which mismatched    : {len(hb_mismatch)}")
    print("  Sample mismatches (up to 40): name | gpc | stored -> fresh | leaves")
    for r in hb_mismatch[:40]:
        print(
            f"    - {r['name'][:34]:34}  {r['google_primary_category'][:24]:24}  "
            f"{(r['stored_subcategory'] or '∅'):>14} -> {(r['fresh_subcategory'] or '∅'):<14}  "
            f"{r['leaf_category_slugs']}"
        )
    print("=" * 72)
    print("NEXT: examine the CSV + this summary, then design rule fixes (step 2). "
          "No rules changed, no rows written.")


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.1f}%" if total else "0.0%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    out_path = args.out or (
        _ROOT / f"subcategory_audit_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
    )
    run(out_path=out_path, limit=args.limit)


if __name__ == "__main__":
    main()
