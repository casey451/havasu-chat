"""Phase 5.9 §2 audit — DB-verify the apparent-duplicate + adjacent-entity
cases surfaced in outputs/phase5_9_ambig_audit_stdout.txt. Read-only.

Run Windows-side: ``python outputs/phase5_9_dupe_check.py``

Three cases to verify:

  1. **New Day School appears twice** in the edge-case rubric — once as
     primary=`educational_institution`, once (twice?) as primary=`preschool`.
     Could be (a) one entity with two Provider rows linked, (b) two distinct
     entities with the same name (different campuses?), (c) a 5.8-style
     dual-place_id from Google. Mirrors the 5.8 Lake Havasu Museum of
     History dual-place_id lesson.

  2. **Psalms Learning Center -> The Ark Center (3.8m apart)** in the cat-5
     HWC ambig pool. Could be same business under two names / two place_ids,
     OR truly adjacent entities. Need both name, address, and place_id to
     decide.

  3. **Hilltop Community Church vs Hilltop Learning Center** — both
     surfaced as cat-12 entries (Church via new childcare_education
     catch-all; Learning Center via None primary_type). Same campus? Cross-
     reference. (Operator note: kickoff §2 forecast church-affiliated
     youth programs as cat-13 cross-link candidates.)

Surfaces: entity_id, name, entity_type, google_place_id,
google_primary_category, all linked category slugs, address.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data") / "events.db"


def _open_db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        print(f"ERROR: {DB_PATH} not found. Run from repo root.", file=sys.stderr)
        sys.exit(2)
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)


def _query(cur: sqlite3.Cursor, like_clause: str) -> list[tuple]:
    return cur.execute(
        """
        SELECT
            e.id,
            e.name,
            e.entity_type,
            p.google_place_id,
            p.google_primary_category,
            COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs,
            COALESCE(l.address, p.address, '') AS addr,
            COALESCE(l.lat, p.lat) AS lat,
            COALESCE(l.lng, p.lng) AS lng,
            p.draft
        FROM entities e
        LEFT JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1 AND e.name LIKE ?
        GROUP BY e.id
        ORDER BY e.name
        """,
        (like_clause,),
    ).fetchall()


def _print(label: str, rows: list[tuple]) -> None:
    print(f"=== {label} ===")
    if not rows:
        print("  (no entities found)")
        print()
        return
    for r in rows:
        eid, name, etype, gpid, gpc, slugs, addr, lat, lng, draft = r
        lat_str = f"{lat:.5f}" if lat is not None else "None"
        lng_str = f"{lng:.5f}" if lng is not None else "None"
        print(f"  entity_id: {eid}")
        print(f"  name:      {name!r}")
        print(f"  type:      {etype!r}    draft={draft}")
        print(f"  primary:   {gpc!r}    place_id: {gpid!r}")
        print(f"  cats:      [{slugs}]")
        print(f"  addr:      {addr!r}")
        print(f"  lat,lng:   ({lat_str}, {lng_str})")
        print()


def main() -> int:
    con = _open_db()
    cur = con.cursor()

    _print("New Day School (dupe check)", _query(cur, "%New Day School%"))
    _print("Psalms Learning Center + Ark Center (3.8m apart)", _query(cur, "%Psalms%"))
    _print("Ark Center", _query(cur, "%Ark Center%"))
    _print("Hilltop (Community Church + Learning Center)", _query(cur, "%Hilltop%"))
    _print(
        "Aquatic / Nomadic / Lions Dog / Main Street Commons "
        "(5.8 V1.5 carry — kickoff said unmapped; dump confirms 0 in DB)",
        _query(cur, "%Aquatic%")
        + _query(cur, "%Nomadic%")
        + _query(cur, "%Lions Dog%")
        + _query(cur, "%Main Street Commons%"),
    )

    # Also list ALL cat-12 entries with primary_type=preschool so we can see
    # the full preschool surface
    print("=== All cat-12 preschool entries ===")
    rows = cur.execute(
        """
        SELECT e.name, p.google_place_id, p.google_primary_category,
               COALESCE(l.address, p.address, '') AS addr
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1
          AND c.slug = 'classes-sports-recreation'
          AND p.google_primary_category = 'preschool'
        ORDER BY e.name
        """
    ).fetchall()
    for r in rows:
        name, gpid, gpc, addr = r
        print(f"  {name!r:42s}  pid={gpid!r}  addr={addr!r}")
    print()

    # Knights of Columbus — confirm it's actually a civic org
    print("=== Knights of Columbus ===")
    rows = cur.execute(
        """
        SELECT e.id, e.name, p.google_place_id, p.google_primary_category,
               COALESCE(l.address, p.address, '') AS addr,
               COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1 AND e.name LIKE '%Knights of Columbus%'
        GROUP BY e.id
        """
    ).fetchall()
    for r in rows:
        print(f"  {r}")
    print()

    # Our Lady of the Lake — verify it's a school (cat-12) AND/OR church (cat-13)
    print("=== Our Lady of the Lake ===")
    rows = cur.execute(
        """
        SELECT e.id, e.name, p.google_place_id, p.google_primary_category,
               COALESCE(l.address, p.address, '') AS addr,
               COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1 AND e.name LIKE '%Our Lady of the Lake%'
        GROUP BY e.id
        """
    ).fetchall()
    for r in rows:
        print(f"  {r}")
    print()

    # Stormy Wade Courts + Sand Volleyball — confirm current cat-5 state + place_id
    print("=== Stormy Wade Courts + Sand Volleyball at Rotary Park ===")
    rows = cur.execute(
        """
        SELECT e.id, e.name, p.google_place_id, p.google_primary_category,
               COALESCE(l.address, p.address, '') AS addr,
               COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1
          AND (e.name LIKE '%Stormy Wade%' OR e.name LIKE '%Sand Volleyball%')
        GROUP BY e.id
        """
    ).fetchall()
    for r in rows:
        print(f"  {r}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
