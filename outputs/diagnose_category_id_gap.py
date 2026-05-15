"""One-off diagnostic — confirm or refute the suspected places_load
category_id gap before the Phase 5.2 real Layer 1 load.

Reads data/events.db (via a /tmp copy to dodge gotcha #4/#15 file-lock
issues if the FastAPI dev server holds events.db). Runs four queries:

  Q1 — Provider.category_id coverage for the legacy 'food_drink' bucket
       (all 287 5.1 eat-drink rows; how many have category_id set?)

  Q2 — Active eat-drink entities + how many have an EntityCategory row
       linking to the 'eat-drink' Category.slug (the actual filter the
       /category/<slug> route uses)

  Q3 — Same as Q1 but split by whether category_id is set: the actual
       SQL the route uses to JOIN. Tells us how many of the 255 active
       eat-drink rows would *render* on /category/eat-drink.

  Q4 — Quick peek at the categories table itself — what slugs exist,
       what IDs they map to. Confirms 'on-the-water' has a row that
       any fix can look up.

Usage:
    python outputs/diagnose_category_id_gap.py

If output reports the dev server is holding the DB, kill it first
(Ctrl+C in the FastAPI window) or accept the snapshot read might be a
few seconds stale — the diagnostic only counts, doesn't write.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

DB_SRC = Path("data") / "events.db"


def _open_db_via_tmp_copy() -> sqlite3.Connection:
    """Per gotcha #4/#15: bash-mount + dev-server file lock both bite.
    Copy DB to a temp file and read from the snapshot."""
    if not DB_SRC.is_file():
        print(f"ERROR: {DB_SRC} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.diag"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db_via_tmp_copy()
    cur = conn.cursor()

    print("=" * 70)
    print("Q1: providers.category_id coverage for category='food_drink'")
    print("=" * 70)
    row = cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(category_id) AS with_category_id,
            COUNT(*) - COUNT(category_id) AS missing_category_id
        FROM providers
        WHERE category = 'food_drink'
        """
    ).fetchone()
    print(f"  total food_drink providers : {row[0]}")
    print(f"  with category_id set       : {row[1]}")
    print(f"  missing category_id        : {row[2]}")
    print()

    print("=" * 70)
    print("Q2: active eat-drink entities + EntityCategory linkage to 'eat-drink'")
    print("=" * 70)
    row = cur.execute(
        """
        SELECT
            COUNT(DISTINCT e.id) AS active_eat_drink_provider_entities,
            COUNT(DISTINCT CASE WHEN c.slug = 'eat-drink'
                  THEN ec.entity_id END) AS with_eat_drink_link
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1
          AND p.is_active = 1
          AND p.draft = 0
          AND p.category = 'food_drink'
        """
    ).fetchone()
    print(f"  active eat-drink provider entities    : {row[0]}")
    print(f"  with EntityCategory -> eat-drink link : {row[1]}")
    print()

    print("=" * 70)
    print("Q3: how many would actually render at /category/eat-drink?")
    print("    (mirrors category_pages.py:_select_entities_for_category)")
    print("=" * 70)
    row = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'eat-drink'
          AND (
            e.entity_type != 'commercial'
            OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0)
          )
        """
    ).fetchone()
    print(f"  entities rendering at /category/eat-drink : {row[0]}")
    print()

    print("=" * 70)
    print("Q4: categories table — what slugs exist, what IDs they map to")
    print("=" * 70)
    rows = cur.execute(
        "SELECT id, slug FROM categories ORDER BY id"
    ).fetchall()
    for r in rows:
        marker = "  <-- on-the-water target" if r[1] == "on-the-water" else ""
        print(f"  id={r[0]:>3}  slug={r[1]}{marker}")
    print()

    print("=" * 70)
    print("INTERPRETATION:")
    print("=" * 70)
    print("  - If Q1 missing_category_id == 0 AND Q3 ~= 255:")
    print("    -> Concern wrong. Some mechanism sets category_id.")
    print("       Proceed with real Layer 1 load.")
    print("  - If Q1 missing_category_id > 0 AND Q3 < Q2:")
    print("    -> Newly-loaded rows silently skip /category. Need fix.")
    print("  - If Q3 << 255 (huge gap):")
    print("    -> /category/eat-drink renders fewer rows than the close-out")
    print("       suggests. Same fix needed retroactively for 5.1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
