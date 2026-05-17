"""Phase 5.9 — §0 pre-flight DB spot-check.

Run Windows-side from repo root: ``python outputs/phase5_9_db_spot_check.py``
(read-only; copies events.db to tempdir first per the established
gate-verification pattern). Audit-trail artifact — captures the pre-§1
DB state of the two categories that 5.9 cares about + the 5.8 §9 V1.5
carry candidates the 5.9 §2 audit will need to verify.

Expected output per kickoff §0 item 9:
  • events (cat-2): 20 entries / 0 verified / 17 indoor + 3 outdoor /
    20 render / 10 long-form crowd_notes (the 5.8 SHIPPED state)
  • classes-sports-recreation (cat-12): 0-5 entries pre-load (likely 0;
    the existing _PRIMARY_TYPE_MAP["school"] entry would have caught any
    school primary_type from prior phases)
  • 5.8 §9 V1.5 carry candidates: Lake Havasu City Aquatic Center,
    Nomadic coworking, Lions Dog Park, Main Street Commons — for each,
    surface whether an Entity row exists + which category it sits in
    (the 5.8 close-out lesson: DB-verify before authoring cross-cat moves)
  • categories table: classes-sports-recreation slug exists at id=12

Mirrors the read-only / tempdir-copy / one-shot shape of
outputs/phase5_8_gate_verification.py and outputs/phase5_7_top10_
discovery.py.
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
    tmp = Path(tempfile.gettempdir()) / "events.db.phase5_9_spot_check"
    shutil.copy2(DB_SRC, tmp)
    return sqlite3.connect(tmp)


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.9 — §0 Pre-flight DB Spot-check")
    print("=" * 78)
    print()

    # --- Categories table sanity ----------------------------------------
    print("[A] Categories table — classes-sports-recreation slug presence")
    print("-" * 78)
    rows = cur.execute(
        "SELECT id, slug, name FROM categories "
        "WHERE slug IN ('classes-sports-recreation', 'events') "
        "ORDER BY id"
    ).fetchall()
    for row in rows:
        print(f"  id={row[0]:>3}  slug={row[1]!r:<35}  name={row[2]!r}")
    if not any(r[1] == "classes-sports-recreation" for r in rows):
        print("  🚨 ERROR: classes-sports-recreation slug NOT found in categories.")
    print()

    # --- Cat-2 events baseline ------------------------------------------
    print("[B] Events (cat-2) — 5.8 SHIPPED baseline")
    print("-" * 78)
    n_total = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1 AND c.slug = 'events'
        """
    ).fetchone()[0]
    n_render = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'events'
          AND (e.entity_type != 'commercial'
               OR (p.id IS NOT NULL AND p.is_active = 1 AND p.draft = 0))
        """
    ).fetchone()[0]
    n_verified = cur.execute(
        """
        SELECT COUNT(DISTINCT p.entity_id)
        FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events' AND p.verified = 1
        """
    ).fetchone()[0]
    heat_rows = cur.execute(
        """
        SELECT e.heat_exposure, COUNT(*) FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events' AND e.is_active = 1
        GROUP BY e.heat_exposure
        ORDER BY 2 DESC
        """
    ).fetchall()
    n_crowd = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'events' AND e.is_active = 1
          AND json_extract(e.crowd_notes, '$.long') IS NOT NULL
        """
    ).fetchone()[0]
    print(f"  total entries     : {n_total} (expect 20)")
    print(f"  rendering         : {n_render} (expect 20)")
    print(f"  verified=True     : {n_verified} (expect 0)")
    print(f"  heat_exposure mix : {heat_rows} (expect 17 indoor + 3 outdoor)")
    print(f"  long-form crowd   : {n_crowd} (expect 10)")
    print()

    # --- Cat-12 classes-sports-recreation state (post-§1 / post-§2) -----
    print("[C] Classes-Sports-Recreation (cat-12) — current state")
    print("-" * 78)
    n_cat12 = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1 AND c.slug = 'classes-sports-recreation'
        """
    ).fetchone()[0]
    print(f"  total entries : {n_cat12} (target >= 20 per kickoff §6; "
          "expected ~29 post-§2)")
    if n_cat12 > 0:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   p.google_primary_category, p.draft,
                   GROUP_CONCAT(DISTINCT c.slug) AS all_slugs
            FROM entities e
            JOIN entity_categories ec_target ON ec_target.entity_id = e.id
              AND ec_target.category_id = (
                  SELECT id FROM categories WHERE slug = 'classes-sports-recreation'
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

    # --- 5.8 §9 V1.5 carry candidates: DB-verify existing state ---------
    print("[D] 5.8 §9 V1.5 carry candidates — DB-verify before any §2 cross-cat moves")
    print("-" * 78)
    keywords = [
        "Aquatic",
        "Nomadic",
        "Lions Dog",
        "Main Street Commons",
        "SARA",
        "Motocross",
        "Sportsman",
        "Thompson Bay",
        "Ofd Racing",
        "Butterfly",
    ]
    for kw in keywords:
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
            print(f"  {kw!r:<22}  → 0 entities found in DB")
        else:
            for row in rows:
                print(f"  {kw!r:<22}  → {row[1]!r:<55}  type={row[2]!r:<11}  cats={row[3]!r}")
    print()

    # --- Cumulative DB shape ---------------------------------------------
    print("[E] Cumulative DB shape (sanity)")
    print("-" * 78)
    n_ent = cur.execute("SELECT COUNT(*) FROM entities WHERE is_active=1").fetchone()[0]
    n_prov = cur.execute("SELECT COUNT(*) FROM providers WHERE is_active=1").fetchone()[0]
    print(f"  active entities  : {n_ent}")
    print(f"  active providers : {n_prov}")
    print()

    print("=" * 78)
    print("Spot-check complete. Surface deltas to operator before §1 dispatch.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
