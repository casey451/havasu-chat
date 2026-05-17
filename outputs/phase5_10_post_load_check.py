"""Phase 5.10 1.7 -- post-1.6-load investigation for sustainability decision.

Run Windows-side from repo root: ``python outputs/phase5_10_post_load_check.py``
(read-only; copies events.db to tempdir).

Investigates the 1.6 load output:
  - The 2 ``category_id_unmapped`` rows -- what are they (name, primary_type,
    first-seen domain)? Decides whether 1.7 sustainability commit (Option A
    direct mappings) is justified or these are true edge cases.
  - The 36 new inserts -- breakdown by resolved category_id (cat-10 target
    + any cat-3 side-effect inserts).
  - Post-1.6 category totals for cat-10, cat-3, cat-12, cat-2 (delta vs
    0h baseline informs gate-1).
  - The 37 ambig records -- aggregate primary_type + first-seen domain
    breakdown for 2 audit dump-script targeting.

ASCII-only stdout per the 5.9 cp1252-codec lesson.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"


def _open_db() -> sqlite3.Connection:
    if not DB_SRC.is_file():
        print(
            f"ERROR: {DB_SRC} not found. Run from the repo root.",
            file=sys.stderr,
        )
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.phase5_10_post_load_check"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.10 -- 1.7 Post-1.6-load investigation")
    print("=" * 78)
    print()

    # --- [A] Unmapped providers ---------------------------------------------
    print("[A] Providers with category_id IS NULL touched by 1.6 load")
    print("    (these are the 2 'category_id unmapped' rows -- the 1.7 sustainability")
    print("    decision signal)")
    print("-" * 78)
    rows = cur.execute(
        """
        SELECT p.id, p.provider_name, p.google_place_id,
               p.google_primary_category, p.entity_id, p.last_google_scraped_at
        FROM providers p
        WHERE p.is_active = 1
          AND p.category_id IS NULL
          AND p.last_google_scraped_at > datetime('now', '-30 minutes')
        ORDER BY p.last_google_scraped_at DESC
        """
    ).fetchall()
    if not rows:
        print("  (no recently-touched unmapped providers found -- they may have been")
        print("   inserted but committed before the 30-min window, or this query needs")
        print("   widening)")
        # Widen: ANY unmapped active provider
        print()
        print("  Widening: ALL active unmapped providers (any age):")
        rows = cur.execute(
            """
            SELECT p.id, p.provider_name, p.google_place_id,
                   p.google_primary_category, p.entity_id, p.last_google_scraped_at
            FROM providers p
            WHERE p.is_active = 1 AND p.category_id IS NULL
            ORDER BY p.last_google_scraped_at DESC NULLS LAST
            LIMIT 20
            """
        ).fetchall()
    for row in rows:
        print(f"  id={row[0]}  name={row[1]!r:<50}  primary_type={row[3]!r:<22}")
        print(f"     place_id={row[2]}  entity_id={row[4]}  scraped={row[5]}")
    print()

    # --- [B] Recently-inserted providers (the 36 new) -----------------------
    print("[B] Providers inserted in the last 30 min (the 36 new from 1.6)")
    print("    Breakdown by resolved category_id and primary_type")
    print("-" * 78)
    rows = cur.execute(
        """
        SELECT c.slug, p.google_primary_category, COUNT(*) AS n
        FROM providers p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.is_active = 1
          AND p.created_at > datetime('now', '-30 minutes')
        GROUP BY c.slug, p.google_primary_category
        ORDER BY c.slug, n DESC
        """
    ).fetchall()
    for row in rows:
        slug = row[0] if row[0] else "(NULL -- unmapped)"
        print(f"  cat={slug!r:<35}  primary={row[1]!r:<28}  n={row[2]}")
    total_new = cur.execute(
        """
        SELECT COUNT(*) FROM providers
        WHERE is_active = 1 AND created_at > datetime('now', '-30 minutes')
        """
    ).fetchone()[0]
    print(f"  TOTAL new providers in last 30 min: {total_new}")
    print()

    # --- [C] Post-1.6 category totals --------------------------------------
    print("[C] Post-1.6 category totals (delta vs 0h baseline)")
    print("-" * 78)
    for slug, baseline in [
        ("lodging-vacation-rentals", 31),
        ("on-the-water", 119),
        ("classes-sports-recreation", 31),
        ("events", 20),
    ]:
        n_total = cur.execute(
            """
            SELECT COUNT(DISTINCT e.id)
            FROM entities e
            JOIN entity_categories ec ON ec.entity_id = e.id
            JOIN categories c ON c.id = ec.category_id
            WHERE e.is_active = 1 AND c.slug = ?
            """,
            (slug,),
        ).fetchone()[0]
        n_render = cur.execute(
            """
            SELECT COUNT(DISTINCT e.id)
            FROM entities e
            JOIN entity_categories ec ON ec.entity_id = e.id
            JOIN categories c ON c.id = ec.category_id
            LEFT JOIN providers p ON p.entity_id = e.id
            WHERE e.is_active = 1
              AND c.slug = ?
              AND (e.entity_type != 'commercial'
                   OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
            """,
            (slug,),
        ).fetchone()[0]
        delta = n_total - baseline
        sign = "+" if delta >= 0 else ""
        print(f"  {slug!r:<35}  total={n_total:>4}  render={n_render:>4}  "
              f"delta_vs_baseline={sign}{delta}  (baseline={baseline})")
    print()

    # --- [D] Cumulative DB shape -------------------------------------------
    print("[D] Cumulative DB shape (sanity)")
    print("-" * 78)
    n_ent = cur.execute(
        "SELECT COUNT(*) FROM entities WHERE is_active=1"
    ).fetchone()[0]
    n_prov = cur.execute(
        "SELECT COUNT(*) FROM providers WHERE is_active=1"
    ).fetchone()[0]
    print(f"  active entities  : {n_ent}  (baseline 1235; delta {n_ent - 1235:+})")
    print(f"  active providers : {n_prov}  (baseline 1235; delta {n_prov - 1235:+})")
    print()

    # --- [E] Cat-10 entity dump (post-1.6) ---------------------------------
    print("[E] Cat-10 lodging-vacation-rentals entities post-1.6 (full dump)")
    print("-" * 78)
    rows = cur.execute(
        """
        SELECT e.id, e.name, e.entity_type, p.google_primary_category, p.draft,
               GROUP_CONCAT(DISTINCT c.slug) AS all_slugs
        FROM entities e
        JOIN entity_categories ec_target ON ec_target.entity_id = e.id
          AND ec_target.category_id = (
              SELECT id FROM categories WHERE slug = 'lodging-vacation-rentals'
          )
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
        GROUP BY e.id
        ORDER BY e.name
        """
    ).fetchall()
    for row in rows:
        slugs = row[5] or ""
        print(
            f"    {row[1]!r:<55}  primary={row[3]!r:<28}  cats=[{slugs}]"
        )
    print(f"  TOTAL cat-10 entities: {len(rows)}")
    print()

    print("=" * 78)
    print("Post-load check complete. Surface to operator before 1.7 decision.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
