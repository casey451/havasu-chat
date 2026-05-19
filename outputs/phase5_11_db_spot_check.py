"""Phase 5.11 -- 0 pre-flight DB spot-check.

Run Windows-side from repo root: ``python outputs/phase5_11_db_spot_check.py``
(read-only; copies events.db to tempdir first per the established
gate-verification pattern). Audit-trail artifact -- captures the pre-1
DB state of the four categories that 5.11 cares about + the 5.11 2
cross-cat DB-verify candidates the audit will need to verify before
authoring slice decisions.

Expected output per kickoff 0 item 9:
  * events (cat-2): 20 entries / 0 verified / 17 indoor + 3 outdoor /
    20 render / 10 long-form crowd_notes (5.8 SHIPPED, unchanged)
  * classes-sports-recreation (cat-12): 31 entries / 0 verified /
    29 indoor + 2 outdoor / 31 render / 10 long-form crowd_notes
    (5.9 SHIPPED, unchanged)
  * lodging-vacation-rentals (cat-10): 73 entries / 0 verified /
    53 indoor + 19 outdoor + 1 water_adjacent / 73 render / 10 long-form
    crowd_notes (5.10 SHIPPED, unchanged)
  * pets (cat-11): 0-10 entries pre-load (pre-Phase-5 `veterinary_care`
    + `pet_store` direct mappings may have absorbed a small number of
    entities; per-entity cat dump informs 2 baseline + gate-1 starting
    count)
  * 5.11 2 cross-cat DB-verify candidates:
      [F] vet clinics likely in cat-5 HWC from 5.4 absorption
          (via `medical_clinic` primary type widening at 1dfd28e)
      [G] dog parks already in cat-7 outdoors-parks-trails from 5.7
          (via pre-Phase-5 `dog_park` direct mapping)
      [H] pet-retail chain dedup (PetSmart, Petco) + mixed-retail
          venues (Walmart, Target) that may carry pet supplies
  * categories table: pets slug exists at id=11

Mirrors the read-only / tempdir-copy / one-shot shape of
outputs/phase5_10_db_spot_check.py with the 5.11 swaps. ASCII-only stdout
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
    tmp = Path(tempfile.gettempdir()) / "events.db.phase5_11_spot_check"
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
    parts = expect.split(" / ")
    print(f"  total entries     : {stats['total']} (expect {parts[0]})")
    print(f"  rendering         : {stats['render']} (expect {parts[3]})")
    print(f"  verified=True     : {stats['verified']} (expect {parts[1]})")
    print(f"  heat_exposure mix : {stats['heat']} (expect {parts[2]})")
    print(f"  long-form crowd   : {stats['crowd']} (expect {parts[4]})")


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.11 -- 0 Pre-flight DB Spot-check (Pets)")
    print("=" * 78)
    print()

    # --- [A] Categories table sanity ------------------------------------
    print("[A] Categories table -- pets + prior-phase slugs presence")
    print("-" * 78)
    rows = cur.execute(
        "SELECT id, slug, name FROM categories "
        "WHERE slug IN ('pets', 'lodging-vacation-rentals', "
        "'classes-sports-recreation', 'events', "
        "'health-wellness-care', 'outdoors-parks-trails', "
        "'shopping-essentials') "
        "ORDER BY id"
    ).fetchall()
    for row in rows:
        print(f"  id={row[0]:>3}  slug={row[1]!r:<32}  name={row[2]!r}")
    if not any(r[1] == "pets" for r in rows):
        print("  [ERROR] pets slug NOT found in categories.")
    print()

    # --- [B] Cat-2 events baseline (5.8 SHIPPED, should be unchanged) ---
    print("[B] Events (cat-2) -- 5.8 SHIPPED baseline, expect unchanged")
    print("-" * 78)
    _print_category_block(
        "events",
        "20 / 0 / 17 indoor + 3 outdoor / 20 / 10",
        _category_stats(cur, "events"),
    )
    print()

    # --- [C] Cat-12 classes-sports-recreation (5.9 SHIPPED) -------------
    print("[C] Classes-Sports-Recreation (cat-12) -- 5.9 SHIPPED baseline, "
          "expect unchanged")
    print("-" * 78)
    _print_category_block(
        "classes-sports-recreation",
        "31 / 0 / 29 indoor + 2 outdoor / 31 / 10",
        _category_stats(cur, "classes-sports-recreation"),
    )
    print()

    # --- [D] Cat-10 lodging-vacation-rentals (5.10 SHIPPED) -------------
    print("[D] Lodging-Vacation-Rentals (cat-10) -- 5.10 SHIPPED baseline, "
          "expect unchanged")
    print("-" * 78)
    _print_category_block(
        "lodging-vacation-rentals",
        "73 / 0 / 53 indoor + 19 outdoor + 1 water_adjacent / 73 / 10",
        _category_stats(cur, "lodging-vacation-rentals"),
    )
    print()

    # --- [E] Cat-11 pets (5.11 pre-1 baseline) --------------------------
    print("[E] Pets (cat-11) -- pre-5.11-1 baseline")
    print("-" * 78)
    n_cat11 = cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1 AND c.slug = 'pets'
        """
    ).fetchone()[0]
    print(f"  total entries : {n_cat11} (expect 0-10 from pre-Phase-5 "
          "`veterinary_care` / `pet_store` direct-map absorption)")
    if n_cat11 > 0:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   p.google_primary_category, p.draft,
                   GROUP_CONCAT(DISTINCT c.slug) AS all_slugs
            FROM entities e
            JOIN entity_categories ec_target ON ec_target.entity_id = e.id
              AND ec_target.category_id = (
                  SELECT id FROM categories WHERE slug = 'pets'
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

    # --- [F] 5.11 cross-cat DB-verify -- vet clinics in cat-5 HWC -------
    print("[F] 5.11 2 cross-cat DB-verify -- vet clinic baseline in cat-5 HWC")
    print("    (any vet clinic already in cat-5 from 5.4 absorption via "
          "`medical_clinic` primary type informs the primary cat-5 vet-"
          "overlap audit axis -- V1 policy is KEEP cat-5; V1.5 may dual-cat "
          "if vet also offers grooming/boarding)")
    print("-" * 78)
    vet_keywords = [
        "Veterinary",
        "Animal Hospital",
        "Animal Clinic",
        "Pet Hospital",
        "Vet Clinic",
        "Vet Hospital",
        "Animal Medical",
        "Pet Care",
        "Pet Clinic",
    ]
    for kw in vet_keywords:
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

    # --- [G] 5.11 cross-cat DB-verify -- dog parks in cat-7 -------------
    print("[G] 5.11 2 cross-cat DB-verify -- dog park baseline in cat-7 "
          "outdoors-parks-trails")
    print("    (any dog park already in cat-7 from pre-Phase-5 `dog_park` "
          "direct mapping informs the secondary cat-7 dog-park-overlap "
          "audit axis -- forecast 0 cross-cat hits because 5.11 labels do "
          "not map to dog_park primary type)")
    print("-" * 78)
    dog_park_keywords = [
        "Dog Park",
        "Bark Park",
        "Off-Leash",
        "Doggie Park",
        "K9",
    ]
    for kw in dog_park_keywords:
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

    # --- [H] 5.11 chain dedup -- pet-retail chains + mixed-retail venues
    print("[H] 5.11 chain dedup -- pet-retail chains + mixed-retail check")
    print("    (per 5.8 lesson + 5.10 lesson: surface PetSmart / Petco "
          "presence, plus mixed-retail venues like Walmart / Target that "
          "carry pet supplies; standalone pet stores get cat-11 via "
          "`pet_store` primary; mixed-retail stays cat-8 shopping-essentials "
          "via `store` / `supermarket` primary)")
    print("-" * 78)
    chain_keywords = [
        "PetSmart",
        "Petco",
        "Petsense",
        "Pet Supplies Plus",
        "Walmart",
        "Target",
        "Albertsons",
        "Safeway",
        "Tractor Supply",
        "Banfield",
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
            print(f"  {kw!r:<20}  -> 0 entities")
        else:
            for row in rows:
                print(f"  {kw!r:<20}  -> {row[1]!r:<55}  "
                      f"type={row[2]!r:<11}  cats={row[3]!r}")
    print()

    # --- [I] Pet-service keyword sweep (broader 5.11 candidate surface) -
    print("[I] Pet-service keyword sweep -- name-based 5.11 candidate hits")
    print("    (informs gate-1 forecast and identifies any pet-service "
          "businesses already in DB under prior phases via `pet_store` or "
          "`veterinary_care` direct mappings; expected hits low)")
    print("-" * 78)
    pet_service_keywords = [
        "Groomer",
        "Grooming",
        "Boarding",
        "Kennel",
        "Doggy Daycare",
        "Pet Sitter",
        "Dog Trainer",
        "Pet Store",
        "Pet Supplies",
        "Aquarium",
    ]
    for kw in pet_service_keywords:
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

    # --- [J] Cumulative DB shape ----------------------------------------
    print("[J] Cumulative DB shape (sanity)")
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
