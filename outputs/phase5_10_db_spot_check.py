"""Phase 5.10 -- 0 pre-flight DB spot-check.

Run Windows-side from repo root: ``python outputs/phase5_10_db_spot_check.py``
(read-only; copies events.db to tempdir first per the established
gate-verification pattern). Audit-trail artifact -- captures the pre-1
DB state of the three categories that 5.10 cares about + the 5.10 2
cross-cat DB-verify candidates the audit will need to verify before
authoring slice decisions.

Expected output per kickoff 0 item 9:
  * events (cat-2): 20 entries / 0 verified / 17 indoor + 3 outdoor /
    20 render / 10 long-form crowd_notes (the 5.8 SHIPPED state -- should
    be unchanged on this pre-5.10 1 baseline)
  * classes-sports-recreation (cat-12): 31 entries / 0 verified /
    29 indoor + 2 outdoor / 31 render / 10 long-form crowd_notes (the
    5.9 SHIPPED state -- should be unchanged on this pre-5.10 1 baseline)
  * lodging-vacation-rentals (cat-10): 0-5 entries pre-load (5.2-era loads
    via `rv_park` / `lodging` direct mappings may have absorbed a small
    number of entities; per-entity cat dump informs 2 baseline)
  * 5.10 2 cross-cat DB-verify candidates: waterfront resorts likely in
    cat-3 from 5.2 absorption (London Bridge Resort, Nautical Beachfront,
    Heat Hotel, Havasu Springs); franchise chain dedup (Holiday Inn /
    Hampton / Best Western per 5.8 lesson); RV park / marina / campground
    5.2-absorption sanity
  * categories table: lodging-vacation-rentals slug exists at id=10

Mirrors the read-only / tempdir-copy / one-shot shape of
outputs/phase5_9_db_spot_check.py with the 5.10 swaps. ASCII-only stdout
per the 5.9 cp1252-codec lesson (no -> arrows, no emoji; route any
Unicode to JSON files instead).
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
    tmp = Path(tempfile.gettempdir()) / "events.db.phase5_10_spot_check"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def _category_stats(cur: sqlite3.Cursor, slug: str) -> dict:
    """Return total / render / verified / heat_mix / long-crowd counts."""
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
    n_verified = cur.execute(
        """
        SELECT COUNT(DISTINCT p.entity_id)
        FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ? AND p.verified = 1
        """,
        (slug,),
    ).fetchone()[0]
    heat_rows = cur.execute(
        """
        SELECT e.heat_exposure, COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ? AND e.is_active = 1
        GROUP BY e.heat_exposure
        ORDER BY 2 DESC
        """,
        (slug,),
    ).fetchall()
    n_crowd = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ? AND e.is_active = 1
          AND json_extract(e.crowd_notes, '$.long') IS NOT NULL
        """,
        (slug,),
    ).fetchone()[0]
    return {
        "total": n_total,
        "render": n_render,
        "verified": n_verified,
        "heat": heat_rows,
        "crowd": n_crowd,
    }


def _print_category_block(title: str, expect: str, stats: dict) -> None:
    print(f"  total entries     : {stats['total']} (expect {expect.split(' / ')[0]})")
    print(f"  rendering         : {stats['render']} (expect {expect.split(' / ')[3]})")
    print(f"  verified=True     : {stats['verified']} (expect {expect.split(' / ')[1]})")
    print(f"  heat_exposure mix : {stats['heat']} (expect {expect.split(' / ')[2]})")
    print(f"  long-form crowd   : {stats['crowd']} (expect {expect.split(' / ')[4]})")


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.10 -- 0 Pre-flight DB Spot-check")
    print("=" * 78)
    print()

    # --- Categories table sanity ----------------------------------------
    print("[A] Categories table -- lodging-vacation-rentals slug presence")
    print("-" * 78)
    rows = cur.execute(
        "SELECT id, slug, name FROM categories "
        "WHERE slug IN ('lodging-vacation-rentals', "
        "'classes-sports-recreation', 'events', 'on-the-water') "
        "ORDER BY id"
    ).fetchall()
    for row in rows:
        print(f"  id={row[0]:>3}  slug={row[1]!r:<35}  name={row[2]!r}")
    if not any(r[1] == "lodging-vacation-rentals" for r in rows):
        print("  [ERROR] lodging-vacation-rentals slug NOT found in categories.")
    print()

    # --- Cat-2 events baseline (5.8 SHIPPED, should be unchanged) -------
    print("[B] Events (cat-2) -- 5.8 SHIPPED baseline, expect unchanged")
    print("-" * 78)
    _print_category_block(
        "events",
        "20 / 0 / 17 indoor + 3 outdoor / 20 / 10",
        _category_stats(cur, "events"),
    )
    print()

    # --- Cat-12 classes-sports-recreation (5.9 SHIPPED) -----------------
    print("[C] Classes-Sports-Recreation (cat-12) -- 5.9 SHIPPED baseline, "
          "expect unchanged")
    print("-" * 78)
    _print_category_block(
        "classes-sports-recreation",
        "31 / 0 / 29 indoor + 2 outdoor / 31 / 10",
        _category_stats(cur, "classes-sports-recreation"),
    )
    print()

    # --- Cat-10 lodging-vacation-rentals (5.10 pre-1 baseline) ----------
    print("[D] Lodging-Vacation-Rentals (cat-10) -- pre-5.10-1 baseline")
    print("-" * 78)
    n_cat10 = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1 AND c.slug = 'lodging-vacation-rentals'
        """
    ).fetchone()[0]
    print(f"  total entries : {n_cat10} (expect 0-5 from 5.2 `rv_park` / "
          "`lodging` direct-map absorption)")
    if n_cat10 > 0:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   p.google_primary_category, p.draft,
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
                f"    {row[1]!r:<55}  type={row[2]!r:<11}  "
                f"primary={row[3]!r:<28}  draft={row[4]}  cats=[{slugs}]"
            )
    print()

    # --- 5.10 2 cross-cat DB-verify: waterfront resorts (likely cat-3) -
    print("[E] 5.10 2 cross-cat DB-verify -- waterfront resort baseline")
    print("    (any entity already in cat-3 from 5.2 absorption informs DUAL "
          "cat-3+cat-10 candidate list)")
    print("-" * 78)
    waterfront_keywords = [
        "London Bridge",
        "Nautical Beachfront",
        "Heat Hotel",
        "Havasu Springs",
        "Pirate Cove",
        "Cattail Cove",
        "Sandpoint",
        "Black Meadow",
        "Crazy Horse",
    ]
    for kw in waterfront_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.is_active = 1 AND e.name LIKE ?
            GROUP BY e.id
            ORDER BY e.name
            """,
            (f"%{kw}%",),
        ).fetchall()
        if not rows:
            print(f"  {kw!r:<22}  -> 0 entities found in DB")
        else:
            for row in rows:
                print(f"  {kw!r:<22}  -> {row[1]!r:<55}  "
                      f"type={row[2]!r:<11}  cats={row[3]!r}")
    print()

    # --- 5.10 franchise / chain dedup (5.8 lesson: same-name distinct
    # place_ids = distinct entities) -------------------------------------
    print("[F] 5.10 franchise / chain dedup -- same-name multi-place_id check")
    print("    (per 5.8 lesson: e.g. Holiday Inn Express vs Holiday Inn "
          "Express & Suites are distinct entities)")
    print("-" * 78)
    chain_keywords = [
        "Holiday Inn",
        "Hampton",
        "Best Western",
        "Quality Inn",
        "Travelodge",
        "Days Inn",
        "Super 8",
        "Motel 6",
        "EconoLodge",
        "Comfort Inn",
        "Hilton",
        "Marriott",
    ]
    for kw in chain_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.is_active = 1 AND e.name LIKE ?
            GROUP BY e.id
            ORDER BY e.name
            """,
            (f"%{kw}%",),
        ).fetchall()
        if not rows:
            print(f"  {kw!r:<18}  -> 0 entities")
        else:
            for row in rows:
                print(f"  {kw!r:<18}  -> {row[1]!r:<55}  "
                      f"type={row[2]!r:<11}  cats={row[3]!r}")
    print()

    # --- 5.2-absorption sanity: RV parks / marinas / campgrounds --------
    print("[G] 5.2-absorption sanity -- RV parks / marinas / campgrounds "
          "current cat placements")
    print("-" * 78)
    absorption_keywords = [
        "RV Park",
        "RV Resort",
        "Campground",
        "Marina",
        "Houseboat",
    ]
    for kw in absorption_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.is_active = 1 AND e.name LIKE ?
            GROUP BY e.id
            ORDER BY e.name
            """,
            (f"%{kw}%",),
        ).fetchall()
        if not rows:
            print(f"  {kw!r:<14}  -> 0 entities")
        else:
            for row in rows:
                print(f"  {kw!r:<14}  -> {row[1]!r:<55}  "
                      f"type={row[2]!r:<11}  cats={row[3]!r}")
    print()

    # --- Cumulative DB shape ---------------------------------------------
    print("[H] Cumulative DB shape (sanity)")
    print("-" * 78)
    n_ent = cur.execute(
        "SELECT COUNT(*) FROM entities WHERE is_active=1"
    ).fetchone()[0]
    n_prov = cur.execute(
        "SELECT COUNT(*) FROM providers WHERE is_active=1"
    ).fetchone()[0]
    print(f"  active entities  : {n_ent}")
    print(f"  active providers : {n_prov}")
    print()

    print("=" * 78)
    print("Spot-check complete. Surface deltas to operator before 1 dispatch.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
