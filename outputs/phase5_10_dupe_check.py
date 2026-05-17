"""Phase 5.10 2 audit -- DB-verify the cross-cat premises + slice
candidates surfaced in outputs/phase5_10_ambig_audit_stdout.txt.
Read-only.

Run Windows-side: ``python outputs/phase5_10_dupe_check.py``

Five investigations (mirrors the 5.9 dupe-check shape):

  1. **5 NEW hotels in the ambig pool** (Slice E candidates) -- verify
     each is NOT in DB by exact place_id. Sanity check before
     authoring the apply-script NEW creates. The Slice E hotels are:
     Heat Hotel, Travelodge by Wyndham Lake Havasu, Knights Inn Lake
     Havasu City, LAKE PLACE INN, Holiday Inn Express & Suites Lake
     Havasu - London Bridge by IHG.

  2. **Heat Hotel + HEAT Bar relationship.** The 1 ambig dump
     surfaced a real same-business / same-building case: Heat Hotel
     (Slice E NEW create candidate, primary='hotel') and HEAT Bar
     (existing cat-1 entity, primary='hotel'-typed in eat-drink, 8.6m
     apart). Verify both place_ids, coordinates, addresses. Mirror
     5.8 Lake Havasu Museum of History dual-place_id lesson: same
     business / two place_ids? OR distinct entities (the bar IS at the
     hotel but registered separately)? Informs whether Heat Hotel
     should DUAL cross-link cat-1 post-create.

  3. **Slice D DUAL cat-3 candidates -- waterfront-adjacent cat-10
     entries.** Three candidates worth verifying via coordinates:
       (a) Lakeside Inn - Lake Havasu City (motel, cat-10) -- name
           suggests waterfront
       (b) Havasu Dunes Resort (resort_hotel, cat-10)
       (c) GetAways at Havasu Dunes Resort (resort_hotel, cat-10)
     Lake Havasu approximate centroid: ~(34.483, -114.355). Anything
     within ~500m of the shoreline could be waterfront-adjacent. For
     cat-3 DUAL ADD: the entity must be waterfront-PRIMARY (lake
     access is the marketing draw), not just incidentally near the
     lake.

  4. **7 cat-10 lodging-primary vacation rentals waterfront check.**
     Names suggest some may be waterfront (Lake-Area Retreat,
     Sunchief Lake Havasu ~ Luxury Home, Luxury Retreat w/pool spa
     near marina, Lake Havasu Luxury Oasis, Havasu Hacienda,
     Downtown LUX Retreat, 9 Hole Mini-golf With Shade...). But
     vacation rental NAMES often invoke the lake without actually
     being at the lake. Coordinates check is authoritative.

  5. **Full 37 ambig record enumeration.** List each with name,
     primary_type, _first_seen_domain, _first_seen_category, geo,
     reviews. Confirms the 5 vs 32 lodging-vs-lake_recreation split
     surfaced in special audit (b).

Surfaces: entity_id, name, entity_type, google_place_id,
google_primary_category, all linked category slugs, address,
lat/lng.

ASCII-only stdout per 5.9 cp1252-codec lesson.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data") / "events.db"
AMBIG_JSON = Path("outputs") / "phase5_10_ambig_audit_data.json"


def _open_db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        print(f"ERROR: {DB_PATH} not found. Run from repo root.", file=sys.stderr)
        sys.exit(2)
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)


def _query_by_name(cur: sqlite3.Cursor, like_clause: str) -> list[tuple]:
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


def _query_by_place_id(cur: sqlite3.Cursor, place_id: str) -> list[tuple]:
    return cur.execute(
        """
        SELECT
            e.id, e.name, e.entity_type, p.google_place_id,
            p.google_primary_category,
            COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs,
            COALESCE(l.address, p.address, '') AS addr,
            COALESCE(l.lat, p.lat) AS lat,
            COALESCE(l.lng, p.lng) AS lng
        FROM entities e
        LEFT JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN locations l ON l.entity_id = e.id
        WHERE e.is_active = 1 AND p.google_place_id = ?
        GROUP BY e.id
        """,
        (place_id,),
    ).fetchall()


def _print(label: str, rows: list[tuple]) -> None:
    print(f"=== {label} ===")
    if not rows:
        print("  (no entities found)")
        print()
        return
    for r in rows:
        eid, name, etype, gpid, gpc, slugs, addr, lat, lng = r[:9]
        draft = r[9] if len(r) > 9 else None
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

    # --- Investigation 1: 5 Slice E NEW hotel candidates not in DB --------
    print("=" * 78)
    print("[1] Slice E NEW hotel candidates -- verify NOT in DB (by name)")
    print("=" * 78)
    slice_e_names = [
        "Heat Hotel",
        "Travelodge",
        "Knights Inn",
        "LAKE PLACE INN",
        "Holiday Inn Express",
    ]
    for nm in slice_e_names:
        _print(f"name LIKE '%{nm}%'", _query_by_name(cur, f"%{nm}%"))

    # --- Investigation 2: HEAT Bar (cat-1 existing) ---------------------
    print("=" * 78)
    print("[2] HEAT Bar -- the cat-1 entity Heat Hotel ambig-matched against")
    print("    (geo: 8.6m apart per 2.1 dump; same building / same business?)")
    print("=" * 78)
    _print("HEAT Bar", _query_by_name(cur, "%HEAT Bar%"))
    # Also check for any entity with primary='hotel' that ISN'T in cat-10
    # (the HEAT Bar entry in cat-1 has primary='hotel' per the 2.1
    # dump output -- unusual)
    print("    --- All entities with primary='hotel' NOT in cat-10 ---")
    rows = cur.execute(
        """
        SELECT e.name, p.google_place_id, p.google_primary_category,
               COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs
        FROM entities e
        JOIN providers p ON p.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1
          AND p.google_primary_category = 'hotel'
        GROUP BY e.id
        HAVING slugs NOT LIKE '%lodging-vacation-rentals%'
        ORDER BY e.name
        """
    ).fetchall()
    if rows:
        for r in rows:
            print(f"    {r[0]!r:42s}  pid={r[1]!r}  cats=[{r[3]}]")
    else:
        print("    (none -- all hotel-primary entities are in cat-10)")
    print()

    # --- Investigation 3: Slice D DUAL cat-3 candidates -----------------
    print("=" * 78)
    print("[3] Slice D DUAL cat-3 candidates -- waterfront-adjacent cat-10 entries")
    print("    (coordinates inform whether each is lake-PRIMARY vs incidentally near)")
    print("=" * 78)
    _print("Lakeside Inn", _query_by_name(cur, "%Lakeside Inn%"))
    _print("Havasu Dunes Resort", _query_by_name(cur, "%Havasu Dunes Resort%"))
    _print("GetAways at Havasu Dunes", _query_by_name(cur, "%GetAways at Havasu Dunes%"))

    # --- Investigation 4: 7 lodging-primary vacation rentals geo check --
    print("=" * 78)
    print("[4] 7 cat-10 lodging-primary vacation rentals -- coordinates for")
    print("    waterfront-adjacency check (names suggest some may be at lake)")
    print("=" * 78)
    vr_names = [
        "Lake-Area Retreat",
        "Sunchief Lake Havasu",
        "Luxury Retreat",  # the one near marina
        "Lake Havasu Luxury Oasis",
        "Havasu Hacienda",
        "Downtown LUX Retreat",
        "9 Hole Mini-golf",
    ]
    for nm in vr_names:
        _print(f"name LIKE '%{nm}%'", _query_by_name(cur, f"%{nm}%"))

    # --- Investigation 5: Full 37 ambig record enumeration --------------
    print("=" * 78)
    print("[5] Full 37 ambig record enumeration (name, primary, domain, label)")
    print("    Splits real lodging-domain candidates from lake_recreation noise")
    print("=" * 78)
    if not AMBIG_JSON.exists():
        print(f"  ERROR: {AMBIG_JSON} not found. Run phase5_10_ambig_audit_dump.py first.")
    else:
        records = json.loads(AMBIG_JSON.read_text(encoding="utf-8"))
        lodging_candidates = []
        lake_rec_candidates = []
        for rec in records:
            cand = rec["candidate"]
            domain = cand.get("discovery_domain")
            if domain == "lodging":
                lodging_candidates.append(rec)
            elif domain == "lake_recreation":
                lake_rec_candidates.append(rec)
            else:
                lodging_candidates.append(rec)
        print(f"  Total ambig records: {len(records)}")
        print(f"  Lodging-domain candidates: {len(lodging_candidates)} (Slice E NEW-create surface)")
        print(f"  Lake_recreation-domain candidates: {len(lake_rec_candidates)} (Slice F KEEP-ambig)")
        print()
        print("  --- Lodging-domain candidates (5 expected): ---")
        for rec in lodging_candidates:
            cand = rec["candidate"]
            top = rec["matched_entities"][0] if rec["matched_entities"] else None
            top_str = (
                f"-> '{top['name']}' "
                f"({'/'.join(top['current_slugs']) or '?'}, "
                f"{top['existing_primary']}, {top['distance_m']}m)"
                if top else "-> (no match)"
            )
            print(
                f"    {cand.get('name')!r:50s}  primary={cand.get('primary_type')!r:14s}  "
                f"label={cand.get('discovery_label')!r:20s}  reviews={cand.get('reviews')}"
            )
            print(f"        {top_str}")
        print()
        print("  --- Lake_recreation-domain candidates (32 expected): ---")
        for rec in lake_rec_candidates:
            cand = rec["candidate"]
            top = rec["matched_entities"][0] if rec["matched_entities"] else None
            top_str = (
                f"-> '{top['name']}' "
                f"({'/'.join(top['current_slugs']) or '?'}, "
                f"{top['existing_primary']}, {top['distance_m']}m)"
                if top else "-> (no match)"
            )
            print(
                f"    {cand.get('name')!r:50s}  primary={cand.get('primary_type')!r:14s}  "
                f"label={cand.get('discovery_label')!r:20s}  reviews={cand.get('reviews')}"
            )
            print(f"        {top_str}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
