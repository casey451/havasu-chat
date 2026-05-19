"""Phase 5.11 -- dump the 25 ambig reconciler skips + 1-update surface
+ cross-cat axes for the 2 audit. Mirrors outputs/phase5_10_ambig_audit_
dump.py shape with three 5.11-specific adjustments:

1. **Single-domain filter.** The 5.11 1 dispatch is single-domain
   (``pets`` only -- no bundle complexity). Filters on
   ``_first_seen_domain == "pets"``. All 4 labels are in scope (pet
   stores / dog groomers / dog boarding / dog trainers); no
   deferred-label complexity.

2. **Special-audit axes (3 + 1 decorative).** Per kickoff 2:
     (a) **cat-5 HWC vet-overlap primary axis.** Vet clinics may already
         be in cat-5 from 5.4 absorption via ``medical_clinic`` direct
         mapping. Empirical 5.11 0 spot-check Block F found ZERO LHC
         vets in cat-5 (all 4 baseline vets have primary=
         ``veterinary_care`` which routes to cat-11, not
         ``medical_clinic`` which would route to cat-5). So this axis is
         likely vacant. KEEP cat-5 policy if any do show up; V1.5 may
         dual-cat selectively.
     (b) **cat-7 outdoors-parks-trails dog-park secondary axis.** Dog
         parks pre-exist in cat-7 from pre-Phase-5 ``dog_park`` direct
         mapping (1 entity: SARA Park Dog Park per Block G). 5.11
         labels don't map to ``dog_park`` primary so 0 cross-cat hits
         expected. KEEP cat-7 policy.
     (c) **cat-8 shopping-essentials retail-overlap tertiary axis.** Pet
         supply stores with ``pet_store`` primary route to cat-11 via
         the existing direct mapping. Mixed retail venues (Walmart with
         pet aisle, Albertsons, Safeway) have ``store`` / ``supermarket``
         primary and stay cat-8. The 5.11 1 load surfaced PetSmart
         in cat-8 (Block H) -- review per-row whether it should remain
         cat-8 (mixed-retail with pet aisle) or FLIP/DUAL to cat-11
         (pet-primary).
     (d) **cat-1 eat-drink decorative axis.** McCulloch Blvd N strip-
         mall geo-noise (pet shops adjacent to restaurants); typically
         benign geo-proximity false positives.

3. **Edge-case routing review** for pets primary_types currently in
   cat-11 (post-1.4 first run + sustainability re-run). With the 5.11
   1 sustainability commit (1dd443a) 4 direct mappings (pet_care /
   dog_groomer / pet_boarding / dog_trainer) + new (None, "pets")
   catch-all + pre-Phase-5 veterinary_care / pet_store direct mappings
   cover the cat-11 surface. The empirical 1 load showed 4 distinct
   primary_types landing in cat-11 from this 5.11 1 scrape:
   veterinary_care (5 baseline), pet_store (1 baseline + maybe new),
   pet_care (5 new from re-run), service (3 new via catch-all).

ASCII-only stdout per 5.9 cp1252-codec lesson.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENRICHMENT_PATH = (
    ROOT / "scripts" / "output" / "places_pull" / "enrichment_enriched.jsonl"
)
DB_PATH = ROOT / "data" / "events.db"
OUT_PATH = ROOT / "outputs" / "phase5_11_ambig_audit_data.json"

TARGET_SLUG = "pets"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# Single-domain filter for 5.11 -- no bundle complexity.
PETS_DOMAIN = "pets"

# The 4 in-scope labels per Phase 5.11 kickoff 1 (all in scope; no
# narrow-scope decision needed).
PETS_LABELS = frozenset({
    "pet stores", "dog groomers", "dog boarding", "dog trainers",
})

# ZIP filter mirrors places_load.py -- LHC ZIPs.
LHC_ZIPS = frozenset({"86403", "86404", "86405", "86406"})


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalize_name(name):
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def jaccard_chars(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def is_pets_domain(row: dict) -> bool:
    return row.get("_first_seen_domain") == PETS_DOMAIN


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the single-domain input set (post --category +
    # post ZIP filter). Expected: 37 rows (matches the [load] line:
    # "after ZIP filter: 37 kept, 6 dropped").
    enrichment: dict[str, dict] = {}
    for line in ENRICHMENT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pid = row.get("place_id")
        if pid:
            enrichment[pid] = row

    input_rows = [
        r for r in enrichment.values()
        if is_pets_domain(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(
        f"[dump] pets-domain+ZIP-filtered input: {len(input_rows)} rows "
        "(expected 37)"
    )

    # 2. Query DB for which of these place_ids are already Providers (=
    # the inserted+updated set). The complement is the ambig-skipped
    # set.
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()

    input_pids = {r["place_id"] for r in input_rows}
    placeholders = ",".join("?" * len(input_pids))
    cur.execute(
        f"SELECT google_place_id FROM providers "
        f"WHERE google_place_id IN ({placeholders})",
        tuple(input_pids),
    )
    inserted_pids = {r[0] for r in cur.fetchall() if r[0]}
    ambig_pids = input_pids - inserted_pids
    print(
        f"[dump] inserted/updated (Providers in DB): {len(inserted_pids)} "
        "(expected 12 = 12 inserts from 1.4 first run; sustainability "
        "re-run added no inserts but routed 7 from NULL to cat-11)"
    )
    print(
        f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
        "(expected 25)"
    )

    # 3. Pull active entities with geo + slugs for nearest-match scoring.
    db_entities = list(cur.execute("""
        SELECT
            e.id, e.name,
            COALESCE(l.lat, p.lat) AS lat,
            COALESCE(l.lng, p.lng) AS lng,
            COALESCE(GROUP_CONCAT(DISTINCT c.slug), '') AS slugs,
            COALESCE(p.google_place_id, '') AS google_place_id,
            COALESCE(p.google_primary_category, '') AS google_primary
        FROM entities e
        LEFT JOIN locations l ON l.entity_id = e.id
        LEFT JOIN entity_categories ec ON ec.entity_id = e.id
        LEFT JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
        GROUP BY e.id
    """))
    print(f"[dump] {len(db_entities)} active entities loaded from DB")

    # 4. For each ambig hit, find matched existing entity.
    records = []
    for pid in sorted(ambig_pids):
        cand = enrichment.get(pid, {})
        c_name = cand.get("display_name") or cand.get("name")
        c_lat = cand.get("lat") or cand.get("latitude")
        c_lng = cand.get("lng") or cand.get("longitude")
        c_addr = cand.get("formatted_address") or cand.get("address")
        c_domain = cand.get("_first_seen_domain")
        c_label = cand.get("_first_seen_category")
        c_primary = cand.get("primary_type")
        c_reviews = cand.get("review_count")
        c_norm = normalize_name(c_name)

        matched: list[dict] = []
        if c_lat is not None and c_lng is not None:
            for eid, ename, elat, elng, eslug, eplaceid, eprimary in db_entities:
                if elat is None or elng is None:
                    continue
                d = haversine_m(c_lat, c_lng, elat, elng)
                if d <= NEAR_GEO_INCLUDE_M:
                    e_norm = normalize_name(ename)
                    matched.append({
                        "entity_id_prefix": eid[:8],
                        "entity_id": eid,
                        "name": ename,
                        "current_slugs": eslug.split(",") if eslug else [],
                        "distance_m": round(d, 1),
                        "name_similarity": round(jaccard_chars(c_norm, e_norm), 3),
                        "existing_place_id": eplaceid,
                        "existing_primary": eprimary,
                    })
        matched.sort(key=lambda x: (x["distance_m"], -x["name_similarity"]))

        records.append({
            "ambig_kind": "geo50m_name_diff",
            "candidate": {
                "place_id": pid,
                "name": c_name,
                "address": c_addr,
                "lat": c_lat,
                "lng": c_lng,
                "primary_type": c_primary,
                "discovery_domain": c_domain,
                "discovery_label": c_label,
                "reviews": c_reviews,
            },
            "matched_entities": matched,
        })

    OUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"[dump] wrote {OUT_PATH} ({len(records)} records)")

    # 5. Aggregates: cross-cat vs same-cat vs no-match.
    cross_cat = same_cat = no_match = 0
    cross_cat_by_slug: dict[str, int] = {}
    for rec in records:
        if not rec["matched_entities"]:
            no_match += 1
            continue
        top = rec["matched_entities"][0]
        if TARGET_SLUG in top["current_slugs"]:
            same_cat += 1
        else:
            cross_cat += 1
            for s in top["current_slugs"]:
                if s and s != TARGET_SLUG:
                    cross_cat_by_slug[s] = cross_cat_by_slug.get(s, 0) + 1

    print(f"\n=== aggregates: {len(records)} ambig-skipped breakdown ===")
    print(f"  total ambig hits:        {len(records)}")
    print(f"  no match (orphan ambig): {no_match}")
    print(
        f"  same-category match:     {same_cat}  "
        f"(matched entity already in {TARGET_SLUG})"
    )
    print(
        f"  cross-category match:    {cross_cat}  "
        "(matched entity in a different Tier-1 slug)"
    )
    if cross_cat_by_slug:
        print("  cross-cat slug breakdown:")
        for slug, cnt in sorted(cross_cat_by_slug.items(), key=lambda x: -x[1]):
            print(f"    {slug:35s}  {cnt}")

    # 6. Special audit (a): cat-5 HWC vet-overlap primary axis. Vet
    # clinics may already be in cat-5 from 5.4 absorption via
    # medical_clinic direct mapping. Empirical 5.11 0 spot-check
    # Block F found ZERO LHC vets in cat-5 -- so this axis is likely
    # vacant. KEEP cat-5 policy if any do show up; V1.5 may dual-cat
    # selectively if a vet also offers grooming/boarding.
    print("\n=== special audit (a): cat-5 HWC vet-overlap primary axis ===")
    cat5_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "health-wellness-care" in m["current_slugs"]:
                print(
                    f"  - cand {(rec['candidate'].get('name') or '?')!r:42s}  "
                    f"label={(rec['candidate'].get('discovery_label') or '?')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: KEEP cat-5 if vet-primary; V1.5 may "
                    "DUAL ADD cat-11 if vet also offers grooming/boarding"
                )
                cat5_flagged += 1
                break
    if cat5_flagged == 0:
        print("  (no cat-5 HWC cross-list hits in ambig pool -- forecast confirmed)")

    # 7. Special audit (b): cat-7 outdoors-parks-trails dog-park
    # secondary axis. Dog parks pre-exist in cat-7 from pre-Phase-5
    # dog_park direct mapping. 5.11 labels don't map to dog_park
    # primary so 0 cross-cat hits expected.
    print("\n=== special audit (b): cat-7 outdoors-parks-trails dog-park secondary axis ===")
    cat7_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "outdoors-parks-trails" in m["current_slugs"]:
                print(
                    f"  - cand {(rec['candidate'].get('name') or '?')!r:42s}  "
                    f"label={(rec['candidate'].get('discovery_label') or '?')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: KEEP cat-7 (dog parks are park-primary)"
                )
                cat7_flagged += 1
                break
    if cat7_flagged == 0:
        print("  (no cat-7 dog-park cross-list hits in ambig pool -- forecast confirmed)")

    # 8. Special audit (c): cat-8 shopping-essentials retail-overlap
    # tertiary axis. Pet supply stores with pet_store primary go to
    # cat-11 (direct mapping). Mixed-retail venues stay cat-8. The
    # 5.11 1 load empirically routed PetSmart to cat-8 (likely
    # because PetSmart's existing cat-8 placement from 5.6 was
    # preserved). Review per-row for FLIP/DUAL candidates.
    print("\n=== special audit (c): cat-8 shopping-essentials retail-overlap tertiary axis ===")
    cat8_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "shopping-essentials" in m["current_slugs"]:
                print(
                    f"  - cand {(rec['candidate'].get('name') or '?')!r:42s}  "
                    f"label={(rec['candidate'].get('discovery_label') or '?')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: KEEP cat-8 if mixed-retail (store/supermarket "
                    "primary); FLIP cat-11 OR DUAL cat-8+cat-11 if pet-primary"
                )
                cat8_flagged += 1
                break
    if cat8_flagged == 0:
        print("  (no cat-8 shopping-essentials cross-list hits in ambig pool)")

    # 9. Special audit (d): cat-1 eat-drink decorative axis. Strip-mall
    # geo-noise (5.6/5.10 lesson). Typically benign geo-proximity
    # false positives (a pet shop next to a restaurant on McCulloch
    # Blvd N etc.).
    print("\n=== special audit (d): cat-1 eat-drink decorative axis (strip-mall geo-noise) ===")
    cat1_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "eat-drink" in m["current_slugs"]:
                print(
                    f"  - cand {(rec['candidate'].get('name') or '?')!r:42s}  "
                    f"label={(rec['candidate'].get('discovery_label') or '?')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: typically KEEP-ambig (strip-mall geo-noise; "
                    "pet shop next to restaurant)"
                )
                cat1_flagged += 1
                break
    if cat1_flagged == 0:
        print("  (no cat-1 eat-drink cross-list hits in ambig pool)")

    # 10. Edge-case routing review: cat-11 primary_types currently in
    # cat-11 post-1.4 load. Confirms each primary_type's destination.
    print("\n=== edge-case routing review (cat-11 primary_types post-1.4) ===")
    rubric = {
        "veterinary_care": (
            "KEEP cat-11 (commercial, pre-Phase-5 direct mapping; "
            "5.11 0 baseline 4 vets)",
            "keep",
        ),
        "pet_store": (
            "KEEP cat-11 (commercial, pre-Phase-5 direct mapping; "
            "5.11 0 baseline 1: Exotic Pet Kingdom)",
            "keep",
        ),
        "pet_care": (
            "KEEP cat-11 (commercial, 5.11 1 NEW direct mapping at "
            "1dd443a; Google's consolidated type for dog grooming + "
            "pet boarding + dog training)",
            "keep",
        ),
        "dog_groomer": (
            "KEEP cat-11 (commercial, 5.11 1 NEW defensive direct "
            "mapping; not currently emitted by Google for LHC)",
            "keep",
        ),
        "pet_boarding": (
            "KEEP cat-11 (commercial, 5.11 1 NEW defensive direct "
            "mapping; not currently emitted by Google for LHC)",
            "keep",
        ),
        "dog_trainer": (
            "KEEP cat-11 (commercial, 5.11 1 NEW defensive direct "
            "mapping; not currently emitted by Google for LHC)",
            "keep",
        ),
        "service": (
            "KEEP cat-11 IF discovery_domain=pets (caught via NEW (None, "
            "'pets') catch-all shipped at 1dd443a). Mirrors 5.10 "
            "Vanderpump pattern.",
            "review",
        ),
        "point_of_interest": (
            "REVIEW -- generic catch-all; needs per-row decision",
            "review",
        ),
        "establishment": (
            "REVIEW -- generic catch-all; needs per-row decision",
            "review",
        ),
        None: (
            "REVIEW -- no primary_type; would route via (None, 'pets') "
            "catch-all if discovered under pets domain",
            "review",
        ),
    }

    edge_rows = cur.execute(
        """
        SELECT e.name, p.google_primary_category, p.address,
               p.google_place_id, p.id
        FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        JOIN entities e ON e.id = p.entity_id
        WHERE c.slug = ? AND e.is_active = 1 AND p.is_active = 1
        ORDER BY e.name
        """,
        (TARGET_SLUG,),
    ).fetchall()

    print(f"  {'primary_type':<28s}  {'name':<42s}  recommended action")
    if not edge_rows:
        print("  (no entries in cat-11 -- unexpected; verify 1 load ran)")
    for r in edge_rows:
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW (uncoded primary type)", "unknown"))
        gpc_disp = str(gpc)[:26] if gpc else "(None)"
        name_disp = name[:40] if name else "(noname)"
        print(f"  {gpc_disp!r:28s}  {name_disp!r:42s}  {action}")

    # 11. DB-verify cross-cat axis carry candidates per kickoff 2.
    # The 5.8 + 5.9 + 5.10 lesson: DB-verify the "existing entity in
    # cat-X" premise before authoring cross-cat moves. For 5.11 these
    # are vet name keywords + dog park keywords + pet-retail chains.
    print(
        "\n=== DB-verify cross-cat axis carry candidates (kickoff 2 hand-off) ==="
    )
    vet_keywords = [
        "Veterinary", "Animal Hospital", "Animal Clinic", "Pet Hospital",
        "Vet Clinic", "Vet Hospital", "Animal Medical",
    ]
    print("  --- cat-5 HWC vet-overlap primary axis: name keyword scan ---")
    for kw in vet_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs,
                   p.google_primary_category
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            LEFT JOIN providers p ON p.entity_id = e.id
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
                print(
                    f"  {kw!r:<22}  -> {row[1]!r:<45}  type={row[2]!r:<11}  "
                    f"cats=[{row[3]!r}]  primary={row[4]!r}"
                )

    dog_park_keywords = ["Dog Park", "Bark Park", "Off-Leash", "Doggie Park", "K9"]
    print("\n  --- cat-7 dog-park secondary axis: name keyword scan ---")
    for kw in dog_park_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs,
                   p.google_primary_category
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            LEFT JOIN providers p ON p.entity_id = e.id
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
                print(
                    f"  {kw!r:<18}  -> {row[1]!r:<45}  type={row[2]!r:<11}  "
                    f"cats=[{row[3]!r}]  primary={row[4]!r}"
                )

    chain_keywords = [
        "PetSmart", "Petco", "Petsense", "Pet Supplies Plus",
        "Tractor Supply", "Banfield",
    ]
    print("\n  --- cat-8 chain dedup tertiary axis: name keyword scan ---")
    for kw in chain_keywords:
        rows = cur.execute(
            """
            SELECT e.id, e.name, e.entity_type,
                   GROUP_CONCAT(c.slug, ', ') AS slugs,
                   p.google_primary_category, p.google_place_id
            FROM entities e
            LEFT JOIN entity_categories ec ON ec.entity_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            LEFT JOIN providers p ON p.entity_id = e.id
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
                print(
                    f"  {kw!r:<20}  -> {row[1]!r:<45}  type={row[2]!r:<11}  "
                    f"cats=[{row[3]!r}]  primary={row[4]!r}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
