"""Phase 5.11 2 audit -- DB-verify the cross-cat premises + slice
candidates surfaced in outputs/phase5_11_ambig_audit_data.json.
Read-only.

Run Windows-side: ``python outputs/phase5_11_dupe_check.py``

Five investigations (mirrors the 5.10 dupe-check shape):

  1. **5 baseline cat-11 entries** (sanity) -- verify each still
     in DB with primary='veterinary_care' or 'pet_store'. These are
     the 5.11 0 spot-check Block E entries:
       (a) Animal Hospital of Havasu       (veterinary_care)
       (b) Buckman Cary DVM                (veterinary_care)
       (c) Exotic Pet Kingdom              (pet_store)
       (d) Paws and Claws Animal Care      (veterinary_care)
       (e) PetVet Vaccination Clinic       (veterinary_care)

  2. **Cross-cat axis (a) -- cat-5 HWC vet-overlap.** Kickoff 2 PRIMARY
     axis framed: "vet clinics already in cat-5 from 5.4 absorption via
     `medical_clinic` direct mapping". Empirical Block F finding: ZERO
     vets in cat-5 across 9 keyword searches. Re-verify here with a
     broader sweep (includes primary_type='medical_clinic' query without
     name keyword). Confirms whether the axis is truly vacant.

  3. **Cross-cat axis (b) -- cat-7 outdoors-parks-trails dog-park
     overlap.** Kickoff 2 SECONDARY axis: dog parks pre-exist in cat-7
     via pre-Phase-5 `dog_park` direct mapping. Block G found 1 entity
     (SARA Park Dog Park). 5.11 labels don't map to `dog_park` primary
     so 0 cross-cat hits expected.

  4. **Cross-cat axis (c) -- cat-8 shopping-essentials retail-overlap.**
     Kickoff 2 TERTIARY axis: pet-retail chains. Block H found PetSmart
     in cat-8. The 5.11 1 load may have routed 4 additional pet-domain
     candidates to cat-8 via `store` primary type (kickoff 2 line:
     "Mixed retail venues have `store` or `supermarket` primary -- cat-8 --
     so they stay correctly categorized"). Verify each: is it
     pet-primary (potential FLIP/DUAL to cat-11) or mixed-retail (stay
     cat-8)?

  5. **Full 25 ambig record enumeration.** Reads the JSON dump from
     outputs/phase5_11_ambig_audit_data.json (written by
     phase5_11_ambig_audit_dump.py). Lists each ambig record with
     candidate name, primary_type, discovery_label, lat/lng,
     reviews, and top-1 matched-entity name/distance/cats. Authoritative
     per-row table for the 2 audit doc Slice plan.

Surfaces: entity_id, name, entity_type, google_place_id,
google_primary_category, all linked category slugs, address,
lat/lng.

ASCII-only stdout per 5.9 cp1252-codec lesson.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "events.db"
AMBIG_JSON_PATH = ROOT / "outputs" / "phase5_11_ambig_audit_data.json"


def _open_db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        print(f"ERROR: {DB_PATH} not found. Run from the repo root.", file=sys.stderr)
        sys.exit(2)
    tmp = Path(tempfile.gettempdir()) / "events.db.phase5_11_dupe_check"
    shutil.copy2(DB_PATH, tmp)
    return sqlite3.connect(tmp)


def _query_by_name(cur, like_clause: str):
    return cur.execute(
        """
        SELECT e.id, e.name, e.entity_type,
               GROUP_CONCAT(c.slug, ', ') AS slugs,
               p.google_place_id, p.google_primary_category
        FROM entities e
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1 AND e.name LIKE ?
        GROUP BY e.id
        ORDER BY e.name
        """,
        (like_clause,),
    ).fetchall()


def _query_by_primary_type(cur, primary_type: str):
    return cur.execute(
        """
        SELECT e.id, e.name, e.entity_type,
               GROUP_CONCAT(c.slug, ', ') AS slugs,
               p.google_place_id, p.google_primary_category
        FROM entities e
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1 AND p.google_primary_category = ?
        GROUP BY e.id
        ORDER BY e.name
        """,
        (primary_type,),
    ).fetchall()


def _print(label: str, rows) -> None:
    if not rows:
        print(f"  {label!r:<22}  -> 0 entities")
        return
    for row in rows:
        eid, name, etype, slugs, place_id, primary = row
        slug_disp = (slugs or "")[:35]
        name_disp = (name or "")[:42]
        primary_disp = str(primary)[:24] if primary else "(None)"
        print(
            f"  {label!r:<22}  -> {name_disp!r:<44}  type={etype!r:<11}  "
            f"cats=[{slug_disp!r}]  primary={primary_disp!r}"
        )


def main() -> int:
    conn = _open_db()
    cur = conn.cursor()

    print("=" * 78)
    print("Phase 5.11 -- 2 Dupe-check + DB-verify cross-cat axes (Pets)")
    print("=" * 78)
    print()

    # --- [1] 5 baseline cat-11 entries (sanity) -------------------------
    print("[1] 5 baseline cat-11 entries (sanity -- should still match 5.11 0 Block E)")
    print("-" * 78)
    baseline_names = [
        "Animal Hospital of Havasu",
        "Buckman Cary DVM",
        "Exotic Pet Kingdom",
        "Paws and Claws Animal Care",
        "PetVet Vaccination Clinic",
    ]
    for nm in baseline_names:
        rows = _query_by_name(cur, f"%{nm}%")
        if not rows:
            print(f"  {nm!r:<35}  -> MISSING (regression)")
            continue
        for row in rows:
            eid, name, etype, slugs, place_id, primary = row
            print(
                f"  {nm!r:<35}  -> entity_id={eid[:8]}  primary={primary!r}  "
                f"cats=[{slugs!r}]"
            )
    print()

    # --- [2] Cross-cat axis (a): cat-5 HWC vet-overlap -----------------
    print("[2] Cross-cat axis (a) cat-5 HWC vet-overlap PRIMARY axis")
    print("    (kickoff 2 forecast: vets in cat-5 from 5.4 medical_clinic absorption;")
    print("     empirical Block F forecast 0; re-verify here broadly)")
    print("-" * 78)
    print("  --- name keyword sweep ---")
    vet_keywords = [
        "Veterinary", "Animal Hospital", "Animal Clinic", "Pet Hospital",
        "Vet Clinic", "Vet Hospital", "Animal Medical",
        "DVM", "Pet Medical", "Animal Care",
    ]
    for kw in vet_keywords:
        rows = _query_by_name(cur, f"%{kw}%")
        if not rows:
            print(f"  {kw!r:<22}  -> 0 entities")
        else:
            for row in rows:
                eid, name, etype, slugs, place_id, primary = row
                primary_disp = str(primary)[:22] if primary else "(None)"
                print(
                    f"  {kw!r:<22}  -> {(name or '')[:44]!r:<46}  "
                    f"cats=[{(slugs or '')!r}]  primary={primary_disp!r}"
                )
    print()
    print("  --- primary_type='medical_clinic' query (catches vets NOT name-matched above) ---")
    rows = _query_by_primary_type(cur, "medical_clinic")
    if not rows:
        print("  (0 entities with primary_type='medical_clinic')")
    else:
        for row in rows:
            eid, name, etype, slugs, place_id, primary = row
            print(
                f"  -> {(name or '')[:44]!r:<46}  cats=[{(slugs or '')!r}]"
            )
    print()

    # --- [3] Cross-cat axis (b): cat-7 dog-park overlap ----------------
    print("[3] Cross-cat axis (b) cat-7 outdoors-parks-trails dog-park SECONDARY axis")
    print("    (kickoff 2 forecast: 1 entity SARA Park Dog Park; no 5.11 collision)")
    print("-" * 78)
    print("  --- name keyword sweep ---")
    dog_park_keywords = ["Dog Park", "Bark Park", "Off-Leash", "Doggie Park", "K9"]
    for kw in dog_park_keywords:
        rows = _query_by_name(cur, f"%{kw}%")
        if not rows:
            print(f"  {kw!r:<18}  -> 0 entities")
        else:
            for row in rows:
                eid, name, etype, slugs, place_id, primary = row
                print(
                    f"  {kw!r:<18}  -> {(name or '')[:44]!r:<46}  "
                    f"cats=[{(slugs or '')!r}]"
                )
    print()
    print("  --- primary_type='dog_park' query ---")
    rows = _query_by_primary_type(cur, "dog_park")
    if not rows:
        print("  (0 entities with primary_type='dog_park')")
    else:
        for row in rows:
            eid, name, etype, slugs, place_id, primary = row
            print(
                f"  -> {(name or '')[:44]!r:<46}  cats=[{(slugs or '')!r}]"
            )
    print()

    # --- [4] Cross-cat axis (c): cat-8 retail-overlap -------------------
    print("[4] Cross-cat axis (c) cat-8 shopping-essentials retail-overlap TERTIARY axis")
    print("    (kickoff 2 forecast: PetSmart in cat-8 from 5.6; the 5.11 1 load may have")
    print("     routed 4 pet-domain candidates to cat-8 via `store` primary -- verify")
    print("     each is mixed-retail (stay cat-8) vs pet-primary (FLIP/DUAL to cat-11))")
    print("-" * 78)
    print("  --- pet-retail chain name keyword sweep ---")
    chain_keywords = [
        "PetSmart", "Petco", "Petsense", "Pet Supplies Plus",
        "Tractor Supply", "Banfield",
    ]
    for kw in chain_keywords:
        rows = _query_by_name(cur, f"%{kw}%")
        if not rows:
            print(f"  {kw!r:<20}  -> 0 entities")
        else:
            for row in rows:
                eid, name, etype, slugs, place_id, primary = row
                primary_disp = str(primary)[:22] if primary else "(None)"
                print(
                    f"  {kw!r:<20}  -> {(name or '')[:42]!r:<44}  "
                    f"cats=[{(slugs or '')!r}]  primary={primary_disp!r}"
                )
    print()
    print("  --- all cat-8 entities with pet-shape primary_type or 'pet'/'animal' in name ---")
    rows = cur.execute(
        """
        SELECT e.id, e.name, e.entity_type,
               GROUP_CONCAT(c.slug, ', ') AS slugs,
               p.google_place_id, p.google_primary_category
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1 AND c.slug = 'shopping-essentials'
          AND (p.google_primary_category IN ('pet_store', 'pet_care',
                                              'dog_groomer', 'pet_boarding',
                                              'dog_trainer', 'veterinary_care')
               OR LOWER(e.name) LIKE '%pet%'
               OR LOWER(e.name) LIKE '%animal%'
               OR LOWER(e.name) LIKE '%dog%'
               OR LOWER(e.name) LIKE '%cat%')
        GROUP BY e.id
        ORDER BY e.name
        """
    ).fetchall()
    if not rows:
        print("  (0 cat-8 entities with pet-shape primary or pet/animal/dog/cat in name)")
    else:
        for row in rows:
            eid, name, etype, slugs, place_id, primary = row
            primary_disp = str(primary)[:22] if primary else "(None)"
            print(
                f"  -> {(name or '')[:42]!r:<44}  type={etype!r:<11}  "
                f"cats=[{(slugs or '')!r}]  primary={primary_disp!r}"
            )
    print()

    # --- [5] Full 25 ambig record enumeration --------------------------
    print("[5] Full 25 ambig record enumeration (per outputs/phase5_11_ambig_audit_data.json)")
    print("-" * 78)
    if not AMBIG_JSON_PATH.is_file():
        print(f"  WARN: {AMBIG_JSON_PATH} not found.")
        print(
            "  Run `python outputs/phase5_11_ambig_audit_dump.py` first to "
            "produce the JSON dump."
        )
    else:
        ambig_data = json.loads(AMBIG_JSON_PATH.read_text(encoding="utf-8"))
        print(f"  (loaded {len(ambig_data)} ambig records)")
        print()
        print(f"  {'#':<3}  {'candidate name':<40}  {'primary':<14}  "
              f"{'label':<14}  {'rev':>4}  matched entity (slug, dist)")
        for i, rec in enumerate(ambig_data, start=1):
            cand = rec["candidate"]
            name = (cand.get("name") or "(noname)")[:38]
            primary = (cand.get("primary_type") or "(none)")[:12]
            label = (cand.get("discovery_label") or "(none)")[:12]
            reviews = cand.get("reviews") or 0
            matched = rec.get("matched_entities") or []
            if matched:
                top = matched[0]
                m_name = (top.get("name") or "(noname)")[:30]
                m_slugs = "/".join(top.get("current_slugs") or []) or "?"
                m_dist = top.get("distance_m") or 0
                match_disp = f"{m_name!r} ({m_slugs}, {m_dist}m)"
            else:
                match_disp = "(no geo-match)"
            print(
                f"  {i:<3}  {name!r:<42}  {primary!r:<14}  {label!r:<14}  "
                f"{reviews:>4}  {match_disp}"
            )
    print()

    # --- [6] Cumulative cat-11 + cat-8 shape ----------------------------
    print("[6] Post-1.4-load shape summary (cumulative DB)")
    print("-" * 78)
    cat_counts = cur.execute(
        """
        SELECT c.slug, COUNT(DISTINCT e.id)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE e.is_active = 1
        GROUP BY c.slug
        ORDER BY c.id
        """
    ).fetchall()
    for slug, cnt in cat_counts:
        print(f"  {slug!r:<35}  {cnt} entities")
    print()

    print("=" * 78)
    print("Dupe-check complete. Surface deltas to agent for 2 audit doc.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
