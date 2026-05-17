"""Phase 5.7 — dump the 42 ambig reconciler skips + edge-case routings
for the §2 audit. Mirrors outputs/phase5_6_ambig_audit_dump.py shape
with two §7-specific adjustments:

1. **Narrow scope filter.** The 5.7 §1 dispatch was scoped to 3 labels
   (parks, golf courses, mini golf — all entertainment_attractions
   domain) per kickoff §1. The dump filters on
   ``_first_seen_domain == "entertainment_attractions"`` to mirror the
   Narrow scope intent. Any fitness_sports-discovered row that somehow
   routes to outdoors-parks-trails would surface as an anomaly worth
   flagging (the existing ``(None, "fitness_sports") ->
   "health-wellness-care"`` fallback SHOULD prevent this).

2. **Special-audit axis swap.** 5.6 audited the gas-station/convenience-
   store cat-9/cat-8 axis. 5.7 audits THREE axes per kickoff §2:
     (a) cat-6 on-the-water cross-list (waterfront parks already
         ingested in 5.2 — Thompson Bay Beach is the obvious
         §1-surfaced candidate; lake-adjacent state parks like
         Cattail Cove SP / Lake Havasu SP may also overlap)
     (b) cat-12 classes-sports-recreation cross-list (gym / sports
         labels we deferred per Narrow scope — Lake Havasu City
         Sportsman's Club / Lake Havasu Motocross Park / Ofd Racing
         arguably belong there)
     (c) same-cat SARA Park de-dup (6 §1-surfaced SARA-related
         entries: parent park + dog park + disc golf + hiking
         trail head + mountain park loop trail + Sara Park
         Hiking Trail — likely sub-features of one physical
         complex, not 6 distinct entities)

3. **Edge-case routing review** for entertainment_attractions
   primary_types that landed via the new ``(None,
   "entertainment_attractions") -> "outdoors-parks-trails"`` catch-all
   from the 5.7 §1 sustainability commit (``1dfd28e``). Operator
   curates per the rubric in section §3 below.

Outputs:
  - outputs/phase5_7_ambig_audit_data.json (structured records)
  - stdout aggregates + 3 special-audit sections
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
OUT_PATH = ROOT / "outputs" / "phase5_7_ambig_audit_data.json"

TARGET_SLUG = "outdoors-parks-trails"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# The 10 entertainment_attractions labels per HEAD scripts/places_categories.json
# (lines 184-193). Phase 5.7 Narrow scope ingested only 3 of these (parks,
# golf courses, mini golf); the dump tracks all 10 in case cache-resurfacing
# brought any other labels' rows into the load pool.
ENTERTAINMENT_LABELS = frozenset({
    "movie theaters", "bowling alleys", "arcades", "mini golf",
    "golf courses", "parks", "museums", "art galleries",
    "live music venues", "event venues",
})

# The 3 in-scope labels per Phase 5.7 kickoff §1 Narrow scope decision.
NARROW_LABELS = frozenset({"parks", "golf courses", "mini golf"})

# The 11 fitness_sports labels (deferred per Narrow scope). Any surfacing
# here is a §2 anomaly worth flagging (the (None, "fitness_sports") -> HWC
# fallback should prevent this).
FITNESS_LABELS = frozenset({
    "gyms", "personal trainers", "yoga studios", "pilates studios",
    "crossfit gyms", "martial arts", "jiu-jitsu", "dance studios",
    "swimming pools", "tennis courts", "pickleball",
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


def is_entertainment(row: dict) -> bool:
    """True if the enriched row was discovered under an
    entertainment_attractions label."""
    fsc = row.get("_first_seen_category")
    if fsc in ENTERTAINMENT_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in ENTERTAINMENT_LABELS for s in seen)


def is_fitness(row: dict) -> bool:
    """True if the enriched row was discovered under a fitness_sports
    label (Narrow-scope deferred surface — flag as anomaly if present)."""
    fsc = row.get("_first_seen_category")
    if fsc in FITNESS_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in FITNESS_LABELS for s in seen)


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the entertainment_attractions input set
    # (post --category + post ZIP filter). Expected: 103 rows
    # (matches the [load] line: "after ZIP filter: 103 kept").
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
        if is_entertainment(r) and (r.get("zip") in LHC_ZIPS)
    ]
    fitness_anomalies = [
        r for r in enrichment.values()
        if is_fitness(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(f"[dump] entertainment+ZIP-filtered input: {len(input_rows)} rows "
          f"(expected ~103)")
    print(f"[dump] fitness+ZIP-filtered (anomaly surface): "
          f"{len(fitness_anomalies)} rows (expected 0 under Narrow scope)")

    # 2. Query DB for which of these place_ids are already Providers
    # (= the inserted set). The complement is the ambig-skipped set.
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
    print(f"[dump] inserted (Providers in DB): {len(inserted_pids)} "
          f"(expected ~61 = 1 fresh + 60 updates from §1 load)")
    print(f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
          f"(expected 42)")

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

    print(f"\n=== aggregates: {len(records)} ambig-skipped breakdown ===")
    print(f"  total ambig hits:        {len(records)}")
    print(f"  no match (orphan ambig): {no_match}")
    print(f"  same-category match:     {same_cat}  "
          f"(matched entity already in {TARGET_SLUG})")
    print(f"  cross-category match:    {cross_cat}  "
          f"(matched entity in a different Tier-1 slug)")
    if cross_cat_by_slug:
        print("  cross-cat slug breakdown:")
        for slug, cnt in sorted(cross_cat_by_slug.items(), key=lambda x: -x[1]):
            print(f"    {slug:35s}  {cnt}")

    # 6. Special audit (a): on-the-water cross-list (cat-6/cat-7 axis).
    # Waterfront parks already ingested in 5.2 — Thompson Bay Beach is
    # the §1-surfaced candidate; Cattail Cove SP / Lake Havasu SP /
    # other lake-adjacent state parks may also overlap.
    print(f"\n=== special audit (a): on-the-water (cat-6) cross-list ===")
    otw_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "on-the-water" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    f"V1 policy: stay in cat-6 if marine-primary"
                )
                otw_flagged += 1
                break
    if otw_flagged == 0:
        print("  (no on-the-water cross-list hits in ambig pool)")
    # Also check the 30 already-inserted outdoors-parks-trails entries
    # for cat-6 overlap (these aren't in the ambig pool but are still
    # cross-cat-relevant per kickoff §2).
    print("\n  --- §1-inserted outdoors-parks-trails entries with cat-6 overlap ---")
    cur.execute("""
        SELECT e.name, p.google_primary_category,
               GROUP_CONCAT(DISTINCT c.slug)
        FROM entities e
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        LEFT JOIN providers p ON p.entity_id = e.id
        WHERE e.is_active = 1
          AND e.id IN (
              SELECT entity_id FROM entity_categories
              WHERE category_id = (SELECT id FROM categories WHERE slug=?)
          )
        GROUP BY e.id
        HAVING GROUP_CONCAT(DISTINCT c.slug) LIKE '%on-the-water%'
        ORDER BY e.name
    """, (TARGET_SLUG,))
    rows = cur.fetchall()
    if rows:
        for name, gpc, slugs in rows:
            print(f"    {name!r:42s}  primary={gpc!r:20s}  slugs={slugs}")
    else:
        print("    (no §1-inserted entries are dual-tagged with on-the-water)")

    # 7. Special audit (b): classes-sports-recreation cross-list
    # (cat-7/cat-12 axis). Per kickoff §1 Narrow scope, fitness_sports
    # labels were deferred — but some of the §1-inserted entries
    # arguably belong in cat-12 (sportsman's club, motocross park, etc.).
    print(f"\n=== special audit (b): classes-sports-recreation (cat-12) cross-list ===")
    csr_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "classes-sports-recreation" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    f"V1 policy: review — recreational use suggests cat-12"
                )
                csr_flagged += 1
                break
    if csr_flagged == 0:
        print("  (no classes-sports-recreation cross-list hits in ambig pool)")
    # Also surface §1-inserted entries with primary_types that suggest cat-12.
    print("\n  --- §1-inserted entries with cat-12-suggestive primary_types ---")
    cat12_suggestive_types = (
        "sports_complex", "race_course", "athletic_field",
        "sports_activity_location",
    )
    placeholders = ",".join("?" * len(cat12_suggestive_types))
    cur.execute(f"""
        SELECT p.provider_name, p.google_primary_category, p.id, e.id
        FROM providers p
        JOIN entities e ON e.id = p.entity_id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ?
          AND p.google_primary_category IN ({placeholders})
        ORDER BY p.google_primary_category, p.provider_name
    """, (TARGET_SLUG, *cat12_suggestive_types))
    for name, gpc, pid, eid in cur.fetchall():
        print(f"    {name!r:42s}  primary={gpc!r:30s}  "
              f"-> review: FLIP to cat-12?")

    # 8. Special audit (c): SARA Park same-cat de-dup
    # (6 §1-surfaced entries: parent + dog park + disc golf + hiking trail
    # head + mountain park loop trail + sara park hiking trail).
    print(f"\n=== special audit (c): SARA Park same-cat de-dup ===")
    cur.execute(f"""
        SELECT p.provider_name, p.google_primary_category, e.id, p.id,
               COALESCE(l.lat, p.lat), COALESCE(l.lng, p.lng)
        FROM providers p
        JOIN entities e ON e.id = p.entity_id
        LEFT JOIN locations l ON l.entity_id = e.id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ?
          AND (LOWER(p.provider_name) LIKE '%sara%'
               OR LOWER(p.provider_name) LIKE '%sara park%')
        ORDER BY p.provider_name
    """, (TARGET_SLUG,))
    sara_rows = cur.fetchall()
    print(f"  Found {len(sara_rows)} SARA-named entries in outdoors-parks-trails:")
    for name, gpc, eid, pid, lat, lng in sara_rows:
        print(f"    {name!r:42s}  primary={gpc!r:18s}  "
              f"({lat:.5f},{lng:.5f})  e_id={eid[:8]}")
    if len(sara_rows) > 1:
        print(f"  -> V1 decision: KEEP parent SARA Park + sub-feature entries"
              f" if each is a distinct physical surface (the dog park, disc"
              f" golf, hiking trail head are real sub-amenities). DRAFT or"
              f" merge if they're navigation aliases.")

    # 9. Edge-case routing review — entertainment_attractions primary_types
    # that landed via the new (None, "entertainment_attractions") catch-all.
    print(f"\n=== edge-case review: catch-all routings to outdoors-parks-trails ===")
    cur.execute("SELECT id FROM categories WHERE slug=?", (TARGET_SLUG,))
    opt_id = cur.fetchone()[0]
    edge_types = (
        "event_venue", "amusement_park", "garden", "sports_complex",
        "race_course", "sports_activity_location", "wildlife_refuge",
        "hiking_area", "athletic_field", "tourist_attraction",
        "point_of_interest", "establishment",
    )
    edge_placeholders = ",".join("?" * len(edge_types))
    cur.execute(f"""
        SELECT provider_name, google_primary_category, address,
               google_place_id, id
        FROM providers
        WHERE category_id=? AND source='google_places'
          AND (google_primary_category IN ({edge_placeholders})
               OR google_primary_category IS NULL)
        ORDER BY google_primary_category, provider_name
    """, (opt_id, *edge_types))

    # Operator-decision rubric per primary_type for 5.7.
    rubric = {
        "event_venue": ("FLIP to events (cat-2)", "cat-2"),
        "amusement_park": (
            "DRAFT (indoor entertainment per kickoff §1 defer; "
            "Altitude Trampoline is indoor)",
            "draft=True",
        ),
        "sports_activity_location": (
            "REVIEW: 'Parks & Rec Dept' is civic (FLIP cat-13); "
            "Thompson Bay Beach is on-the-water (cross-cat check)",
            "review",
        ),
        "sports_complex": (
            "REVIEW: gun club arguably cat-12; FLIP if recreational",
            "review",
        ),
        "race_course": (
            "REVIEW: motocross park / Ofd Racing arguably cat-12; "
            "FLIP if recreational; KEEP if track-as-park-amenity",
            "review",
        ),
        "garden": (
            "REVIEW: public garden = KEEP; community garden = DRAFT or FLIP",
            "review",
        ),
        "wildlife_refuge": (
            "KEEP — federal land, valid parks/trails entry "
            "(Bill Williams River NWR)",
            "keep",
        ),
        "hiking_area": ("KEEP — valid trails entry", "keep"),
        "athletic_field": (
            "REVIEW: KEEP if recreational; FLIP cat-12 if scheduled-use",
            "review",
        ),
        "tourist_attraction": (
            "KEEP — Google's primary type for state parks/scenic spots",
            "keep",
        ),
        "point_of_interest": (
            "REVIEW — generic catch-all; needs per-row decision",
            "review",
        ),
        "establishment": (
            "REVIEW — generic catch-all; needs per-row decision",
            "review",
        ),
        None: (
            "REVIEW — no primary_type; needs per-row decision",
            "review",
        ),
    }

    print(f"{'primary_type':<28s}  {'name':<42s}  recommended action")
    for r in cur.fetchall():
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW (uncoded primary type)", "unknown"))
        print(f"  {str(gpc)[:26]!r:28s}  {name[:40]!r:42s}  {action}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
