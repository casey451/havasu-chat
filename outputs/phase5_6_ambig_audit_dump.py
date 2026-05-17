"""Phase 5.6 — dump the 181 ambig reconciler skips + 27 edge-case routings
for the §2 audit. Mirrors outputs/phase5_5_ambig_audit_dump.py shape with
two §6-specific adjustments:

1. **Self-contained derivation.** Instead of parsing a Tee'd load log (5.5
   pattern), this script reconstructs the ambig-skipped set by DB-diffing:
   the 268 input rows minus the 87 actually-inserted = 181 ambig-skipped.
   Removes the dependency on Tee-Object output + sidesteps the
   .gitignore-excluded log issue 5.5 noted in its close-out §6.

2. **Edge-case routing section.** The (None, "retail") catch-all in
   _DISCOVERY_DOMAIN_FALLBACK routed 27 providers with edge-case
   primary_types (corporate_office / manufacturer / garden / farm /
   health / community_center / service / supplier / department_store /
   adventure_sports_center / None) to shopping-essentials. Some are
   correct (Dillard's, Havasu Computers, Clothes Closet, Serrano's
   Nursery) but ~12 need flipping/drafting (Hospice, eye-exam docs,
   powersports dealers, B2B wholesale). Section §2 lists each with a
   recommended action for the operator's apply-script curation.

Outputs:
  - outputs/phase5_6_ambig_audit_data.json (structured records)
  - stdout aggregates + cat-8/cat-9 special audit (gas station / convenience
    store cross-list per kickoff §2)
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
OUT_PATH = ROOT / "outputs" / "phase5_6_ambig_audit_data.json"

TARGET_SLUG = "shopping-essentials"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# The 23 retail labels per kickoff §1.
RETAIL_LABELS = frozenset({
    "grocery stores", "supermarkets", "convenience stores", "liquor stores",
    "pharmacies", "clothing stores", "thrift stores", "consignment stores",
    "shoe stores", "jewelry stores", "furniture stores", "home decor stores",
    "hardware stores", "garden centers", "bookstores", "gift shops",
    "florists", "sporting goods stores", "outdoor gear stores",
    "electronics stores", "music stores", "toy stores", "smoke shops",
})

# ZIP filter mirrors places_load.py — LHC ZIPs.
LHC_ZIPS = frozenset({"86403", "86404", "86405", "86406"})


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalize_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def jaccard_chars(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def is_retail(row: dict) -> bool:
    """True if the enriched row was discovered under a retail label."""
    fsc = row.get("_first_seen_category")
    if fsc in RETAIL_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in RETAIL_LABELS for s in seen)


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the 268-row input set (post --category + post ZIP filter).
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
        if is_retail(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(f"[dump] retail+ZIP-filtered input: {len(input_rows)} rows "
          f"(expected 268)")

    # 2. Query DB for which of these place_ids are already Providers
    # (= the inserted set). The complement is the ambig-skipped set.
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro&immutable=1", uri=True)
    cur = con.cursor()

    input_pids = {r["place_id"] for r in input_rows}
    placeholders = ",".join("?" * len(input_pids))
    cur.execute(
        f"SELECT google_place_id FROM providers WHERE google_place_id IN ({placeholders})",
        tuple(input_pids),
    )
    inserted_pids = {r[0] for r in cur.fetchall() if r[0]}
    ambig_pids = input_pids - inserted_pids
    print(f"[dump] inserted (Providers in DB): {len(inserted_pids)} "
          f"(expected 87)")
    print(f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
          f"(expected 181)")

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
            "ambig_kind": "geo50m_name_diff",  # vast majority per load log
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

    print("\n=== §1 aggregates: 181 ambig-skipped breakdown ===")
    print(f"  total ambig hits:        {len(records)}")
    print(f"  no match (orphan ambig): {no_match}")
    print(f"  same-category match:     {same_cat}  (matched entity already in {TARGET_SLUG})")
    print(f"  cross-category match:    {cross_cat}  (matched entity in a different Tier-1 slug)")
    if cross_cat_by_slug:
        print("  cross-cat slug breakdown:")
        for slug, cnt in sorted(cross_cat_by_slug.items(), key=lambda x: -x[1]):
            print(f"    {slug:35s}  {cnt}")

    # 6. Gas station / convenience store cross-list special audit (kickoff §2).
    print("\n=== §2 special: gas station / convenience store cat-9/cat-8 axis ===")
    gas_conv_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        label = (rec["candidate"].get("discovery_label") or "").lower()
        if label not in ("convenience stores", "grocery stores"):
            continue
        for m in rec["matched_entities"]:
            slugs = m["current_slugs"]
            if "auto-rv-fuel" in slugs and m["existing_primary"] in (
                "gas_station", "convenience_store"
            ):
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={label!r:20s}  -> existing "
                    f"{m['name']!r:35s} @ {'/'.join(slugs) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    f"V1 policy: stay in cat-9 unless convenience-store is primary draw"
                )
                gas_conv_flagged += 1
                break
    if gas_conv_flagged == 0:
        print("  (no gas-station/convenience-store cross-list hits)")

    # 7. Edge-case routing review — the 27 providers routed via the (None,
    # "retail") catch-all with unusual primary types.
    print("\n=== §2 edge-case review: 27 catch-all routings to shopping-essentials ===")
    cur.execute("SELECT id FROM categories WHERE slug=?", (TARGET_SLUG,))
    se_id = cur.fetchone()[0]
    edge_types = (
        "corporate_office", "manufacturer", "garden", "farm", "health",
        "community_center", "service", "health_food_store", "market",
        "medical_center", "laundry", "indoor_playground", "restaurant",
        "truck_stop", "shipping_service", "farmers_market", "butcher_shop",
        "department_store", "supplier", "adventure_sports_center",
        "general_contractor", "body_art_service", "storage",
    )
    edge_placeholders = ",".join("?" * len(edge_types))
    cur.execute(f"""
        SELECT provider_name, google_primary_category, address, google_place_id, id
        FROM providers
        WHERE category_id=? AND source='google_places'
          AND (google_primary_category IN ({edge_placeholders})
               OR google_primary_category IS NULL)
        ORDER BY google_primary_category, provider_name
    """, (se_id, *edge_types))

    # Operator-decision rubric per primary_type.
    rubric = {
        "health": ("FLIP to health-wellness-care", "cat-5"),
        "manufacturer": ("DRAFT (B2B wholesale, not consumer)", "draft=True"),
        "corporate_office": ("DRAFT (B2B wholesale)", "draft=True"),
        "garden": ("DRAFT or FLIP cat-7 if community-public", "review"),
        "farm": ("KEEP if retail nursery; DRAFT if actual farm", "review"),
        "community_center": ("KEEP if thrift/retail; DRAFT if civic", "review"),
        "department_store": ("KEEP in shopping-essentials", "keep"),
        "supplier": ("FLIP if powersports/auto; KEEP if retail; DRAFT if wholesale", "review"),
        "adventure_sports_center": ("FLIP to auto-rv-fuel if motorsports", "review"),
        "service": ("KEEP if IT/electronics retail; FLIP/DRAFT otherwise", "review"),
        None: ("KEEP if obvious retail (Havasu Computers)", "review"),
    }

    print(f"{'primary_type':<28s}  {'name':<42s}  recommended action")
    for r in cur.fetchall():
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW", "unknown"))
        print(f"  {str(gpc)[:26]!r:28s}  {name[:40]!r:42s}  {action}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
