"""Phase 5.10 -- dump the 37 ambig reconciler skips + 1-update surface +
cross-cat axes for the 2 audit. Mirrors outputs/phase5_9_ambig_audit_
dump.py shape with three 5.10-specific adjustments:

1. **Narrow scope filter, TWO domains.** The 5.10 1 dispatch was scoped
   to 5 labels (all 5 lodging-domain: hotels, motels, resorts, vacation
   rentals, bed and breakfast) per kickoff 1. The dump filters on
   ``_first_seen_domain in {"lodging", "lake_recreation"}`` to mirror the
   two-domain bundle that ``places_load --category lodging-vacation-
   rentals`` actually processes. The 24 lake_recreation labels are
   DEFERRED to V1.5 per kickoff 1 Narrow scope decision -- marina/boat
   shape absorbed by 5.2's on-the-water scrape via the ``(None,
   "lake_recreation") -> "on-the-water"`` catch-all; RV parks +
   campgrounds + mobile_home_park + camping_cabin already in cat-10 via
   pre-Phase-5 ``rv_park`` direct mapping or secondary-types[] first-match
   on existing ``lodging`` direct mapping. So while the 5.10 load
   processed 297 in-LHC rows from BOTH domains, the audit's 37 ambig
   records are mostly geo-proximity false positives (per the 5.4 +
   5.5 + 5.6 + 5.7 + 5.8 + 5.9 history of 0 real misroutes from ambig
   pools).

2. **Special-audit axis swap.** 5.9 audited cat-5 HWC + cat-7 + cat-13
   axes. 5.10 audits THREE axes per kickoff 2:
     (a) **cat-3 on-the-water primary axis.** Waterfront resorts may
         already be in cat-3 from 5.2 lake_recreation absorption.
         V1 policy per kickoff 2: DUAL cat-3 + cat-10 (mirror 5.9
         Slice D Our Lady DUAL cat-12+cat-13 pattern via
         _dual_add_category helper). The 5.10 0 spot-check Block E
         empirically confirmed ZERO forecast waterfront resorts (London
         Bridge Resort, Nautical Beachfront, Heat Hotel, Havasu Springs,
         Pirate Cove, Sandpoint, Black Meadow) pre-exist in cat-3 --
         meaning the 5.10 1 scrape brought them in as NEW cat-10
         creates, NOT pre-existing cat-3 review subjects. So Slice D
         becomes "post-1 DUAL ADD cat-3 to NEW lodging creates that
         are also waterfront."
     (b) **cat-1 eat-drink secondary axis.** Hotel restaurants. Most
         LHC hotels in cat-10 don't have separate cat-1 entities;
         typically keep cat-1 if food-primary, cross-link only if
         hotel-restaurant is the marketing draw.
     (c) **cat-2 events tertiary axis.** Resort event venues
         (weddings). Typically the resort is primary entity; event
         venue is sub-amenity. Review per-row.

3. **Edge-case routing review** for lodging-vacation-rentals
   primary_types currently in cat-10 (post-1.6 + 1.7c re-run). With
   the 5.10 1.7 sustainability commit (bf24e16) 5 direct mappings
   (hotel/motel/resort_hotel/extended_stay_hotel/bed_and_breakfast) +
   new (None, "lodging") catch-all + pre-Phase-5 lodging/rv_park
   direct mappings cover the cat-10 surface. The empirical 1 load
   showed 6 distinct primary_types landing in cat-10 from this
   scrape: hotel x13, motel x4, resort_hotel x2, guest_house x1,
   cottage x15, service x1 (Vanderpump Rules villa). Plus 4 more
   primary_types in cat-10 from prior phases (lodging/rv_park/
   campground/mobile_home_park/camping_cabin). The rubric covers
   all of these + the expected edge cases.

Outputs:
  - outputs/phase5_10_ambig_audit_data.json (structured records)
  - stdout aggregates + 3 special-audit sections + edge-case rubric +
    DB-verify carry candidates

ASCII-only stdout per the 5.9 cp1252-codec lesson.
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
OUT_PATH = ROOT / "outputs" / "phase5_10_ambig_audit_data.json"

TARGET_SLUG = "lodging-vacation-rentals"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# The lodging-vacation-rentals bundle labels per HEAD scripts/places_
# categories.json:
#   - lodging domain (5): hotels, motels, resorts, vacation rentals,
#     bed and breakfast
#   - lake_recreation domain (24): boat rentals, houseboat rentals,
#     jet ski rentals, kayak rentals, paddleboard rentals, pontoon
#     rentals, boat tours, fishing charters, fishing guides, bait and
#     tackle shops, marinas, boat dealers, boat repair, boat storage,
#     boat detailing, watersports rentals, parasailing, ATV rentals,
#     off-road tours, RV parks, RV rentals, RV dealers, RV repair,
#     campgrounds
# Phase 5.10 Narrow scope ingested only the 5 lodging-domain labels;
# the 24 lake_recreation labels were absorbed by 5.2 (marina/boat
# shape -> cat-3 on-the-water; RV parks + campgrounds -> cat-10 via
# direct map or secondary-types[] match).
TWO_DOMAIN_DOMAINS = frozenset({"lodging", "lake_recreation"})

# The 5 in-scope labels per Phase 5.10 kickoff 1 Narrow scope decision.
NARROW_LABELS = frozenset({
    "hotels", "motels", "resorts", "vacation rentals", "bed and breakfast",
})

# The 24 lake_recreation labels (deferred to V1.5 per Narrow scope).
DEFERRED_LAKE_REC_LABELS = frozenset({
    "boat rentals", "houseboat rentals", "jet ski rentals", "kayak rentals",
    "paddleboard rentals", "pontoon rentals", "boat tours",
    "fishing charters", "fishing guides", "bait and tackle shops",
    "marinas", "boat dealers", "boat repair", "boat storage",
    "boat detailing", "watersports rentals", "parasailing", "ATV rentals",
    "off-road tours", "RV parks", "RV rentals", "RV dealers", "RV repair",
    "campgrounds",
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


def normalize_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def jaccard_chars(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def is_cat10_two_domain(row: dict) -> bool:
    """True if the enriched row was discovered under either of the two
    lodging-vacation-rentals domains (lodging or lake_recreation),
    regardless of specific label."""
    domain = row.get("_first_seen_domain")
    if domain in TWO_DOMAIN_DOMAINS:
        return True
    fsc = row.get("_first_seen_category")
    if fsc in NARROW_LABELS or fsc in DEFERRED_LAKE_REC_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in NARROW_LABELS or s in DEFERRED_LAKE_REC_LABELS for s in seen)


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the two-domain input set (post --category + post
    # ZIP filter). Expected: 297 rows (matches the [load] line:
    # "after ZIP filter: 297 kept, 68 dropped").
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
        if is_cat10_two_domain(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(
        "[dump] two-domain+ZIP-filtered input: "
        f"{len(input_rows)} rows (expected 297)"
    )

    # 2. Query DB for which of these place_ids are already Providers
    # (= the inserted+updated set after 1.7c re-run). The complement is
    # the ambig-skipped set.
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
        "(expected 260 = 36 inserts + 224 updates from 1.6 load; 1.7c "
        "re-run added 0 new inserts but routed Vanderpump villa from "
        "NULL to cat-10)"
    )
    print(
        f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
        "(expected 37)"
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

    # 6. Special audit (a): cat-3 on-the-water primary axis. Waterfront
    # resorts may already be in cat-3 from 5.2 lake_recreation
    # absorption. The 5.10 0 spot-check Block E found ZERO forecast
    # waterfront resorts pre-exist in cat-3 -- but the geo-proximity
    # ambig dump may surface NEW lodging creates that are co-located
    # with cat-3 entities (marinas, boat businesses). V1 policy:
    # DUAL cat-3 + cat-10 if the lodging entity has waterfront-primary
    # identity (vs just being near a marina).
    print("\n=== special audit (a): cat-3 on-the-water primary axis ===")
    cat3_flagged = 0
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
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: NEW create in cat-10 if waterfront-primary; "
                    "DUAL ADD cat-3 if lodging at marina; KEEP ambig if "
                    "geo-noise (cat-3 marina just adjacent to cat-10 hotel)"
                )
                cat3_flagged += 1
                break
    if cat3_flagged == 0:
        print("  (no cat-3 on-the-water cross-list hits in ambig pool)")

    # 7. Special audit (b): cat-1 eat-drink secondary axis. Hotels in
    # cat-10 may have restaurants in cat-1 (5.1 absorbed 287 eat-drink
    # entities). V1 policy: typically KEEP cat-1 if food-primary;
    # cross-link only if hotel-restaurant is the marketing draw.
    print("\n=== special audit (b): cat-1 eat-drink secondary axis ===")
    cat1_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "eat-drink" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: typically KEEP cat-1 (food-primary); "
                    "cross-link only if hotel-restaurant is marketing draw"
                )
                cat1_flagged += 1
                break
    if cat1_flagged == 0:
        print("  (no cat-1 eat-drink cross-list hits in ambig pool)")

    # 8. Special audit (c): cat-2 events tertiary axis. Resort event
    # venues (weddings). 5.8 absorbed 20 event entities. V1 policy:
    # typically the resort/hotel is primary entity; the event venue is
    # a sub-amenity. Review per-row.
    print("\n=== special audit (c): cat-2 events tertiary axis ===")
    cat2_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "events" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) -- "
                    "V1 policy: typically resort is primary entity; "
                    "event venue is sub-amenity; review per-row"
                )
                cat2_flagged += 1
                break
    if cat2_flagged == 0:
        print("  (no cat-2 events cross-list hits in ambig pool)")

    # 9. Edge-case routing review -- lodging-vacation-rentals
    # primary_types currently in cat-10 (post-1.6 + 1.7c re-run). With
    # the 5.10 1.7 sustainability commit (bf24e16) the 5 directly-
    # mapped primary types route to cat-10; the pre-Phase-5 lodging +
    # rv_park direct mappings also route to cat-10; the new (None,
    # "lodging") catch-all covers unmapped lodging-domain rows; the
    # 5.2 (None, "lake_recreation") catch-all routes lake_recreation
    # rows to cat-3 on-the-water (so they DON'T land in cat-10 by
    # default -- they only land in cat-10 if their primary_type
    # directly maps to cat-10 like rv_park).
    print(
        "\n=== edge-case review: primary_types in cat-10 lodging-vacation-rentals "
        "(post-1.6 + 1.7c) ==="
    )
    cur.execute("SELECT id FROM categories WHERE slug=?", (TARGET_SLUG,))
    cat10_id = cur.fetchone()[0]
    cur.execute("""
        SELECT provider_name, google_primary_category, address,
               google_place_id, id
        FROM providers
        WHERE category_id=? AND source='google_places'
        ORDER BY google_primary_category, provider_name
    """, (cat10_id,))

    # Operator-decision rubric per primary_type for 5.10.
    rubric: dict[str | None, tuple[str, str]] = {
        # The 5 direct mappings shipped at bf24e16.
        "hotel": ("KEEP cat-10 (commercial)", "keep"),
        "motel": ("KEEP cat-10 (commercial)", "keep"),
        "resort_hotel": ("KEEP cat-10 (commercial)", "keep"),
        "extended_stay_hotel": ("KEEP cat-10 (commercial)", "keep"),
        "bed_and_breakfast": ("KEEP cat-10 (commercial)", "keep"),
        # Pre-Phase-5 direct mappings.
        "lodging": (
            "KEEP cat-10 (commercial, pre-Phase-5 direct mapping)",
            "keep",
        ),
        "rv_park": (
            "KEEP cat-10 (commercial, pre-Phase-5 direct mapping)",
            "keep",
        ),
        # Caught via secondary-types[] first-match on the existing
        # lodging direct mapping (these primary_types don't have direct
        # mappings but the entity's types[] array includes 'lodging' as
        # a secondary slot -- map_google_types_to_slug_and_place_type
        # iterates first-match and hits the lodging mapping).
        "campground": (
            "KEEP cat-10 (caught via secondary-types[] match on lodging; "
            "5.10 0 spot-check confirmed 6 campgrounds in cat-10 from "
            "prior phases)",
            "keep",
        ),
        "mobile_home_park": (
            "KEEP cat-10 (caught via secondary-types[] match on lodging)",
            "keep",
        ),
        "camping_cabin": (
            "KEEP cat-10 (caught via secondary-types[] match on lodging)",
            "keep",
        ),
        # New from 5.10 1 scrape -- cottage is Google's primary type
        # for many vacation rental properties (Airbnb-style listings
        # with claimed Business Profiles). The 5.10 1 load surfaced 15
        # cottage-primary entries.
        "cottage": (
            "KEEP cat-10 (vacation rental shape; caught via secondary-"
            "types[] match on lodging; 5.10 1 load surfaced 15 entries)",
            "keep",
        ),
        "guest_house": (
            "KEEP cat-10 (vacation rental / B&B shape; caught via "
            "secondary-types[] match on lodging)",
            "keep",
        ),
        # Edge case routed via the NEW (None, 'lodging') catch-all
        # shipped at bf24e16 -- the Vanderpump Rules villa (primary=
        # 'service', _first_seen_domain='lodging', types[] without
        # 'lodging' secondary). The catch-all is the safety net for
        # this rare case.
        "service": (
            "KEEP cat-10 IF discovery_domain=lodging (caught via NEW "
            "(None, 'lodging') catch-all shipped at bf24e16; Vanderpump "
            "Rules villa was the 5.10 1 motivating case). REVIEW IF "
            "discovery_domain=lake_recreation (would route to cat-3 via "
            "5.2 catch-all)",
            "review",
        ),
        # Edge cases that may show up via primary_type drift.
        "point_of_interest": (
            "REVIEW -- generic catch-all; needs per-row decision",
            "review",
        ),
        "establishment": (
            "REVIEW -- generic catch-all; needs per-row decision",
            "review",
        ),
        "tourist_attraction": (
            "REVIEW -- entertainment_attractions axis; could be cat-7 "
            "outdoors-parks-trails (5.7 catch-all) but ended up in "
            "cat-10 via secondary-types[] match",
            "review",
        ),
        None: (
            "REVIEW -- no primary_type; needs per-row decision (would "
            "route via the new (None, 'lodging') catch-all if discovered "
            "under that domain)",
            "review",
        ),
    }

    print(f"  {'primary_type':<28s}  {'name':<42s}  recommended action")
    edge_rows = cur.fetchall()
    if not edge_rows:
        print("  (no entries in cat-10 -- unexpected; verify 1 load ran)")
    for r in edge_rows:
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW (uncoded primary type)", "unknown"))
        gpc_disp = str(gpc)[:26] if gpc else "(None)"
        name_disp = name[:40] if name else "(noname)"
        print(f"  {gpc_disp!r:28s}  {name_disp!r:42s}  {action}")

    # 10. DB-verify the cross-cat axis carry candidates per kickoff 2.
    # The 5.8 + 5.9 lesson: DB-verify the "existing entity in cat-X"
    # premise before authoring any cross-cat moves. For 5.10 these
    # are the waterfront-resort name keywords + franchise chains.
    print(
        "\n=== DB-verify cross-cat axis carry candidates (kickoff 2 hand-off) ==="
    )
    # Waterfront resort names + lake-proximity keywords (cat-3 DUAL
    # candidates if pre-existing in cat-3 OR if NEW creates in cat-10
    # are waterfront-primary).
    waterfront_keywords = [
        "London Bridge Resort",
        "Nautical Beachfront",
        "Heat Hotel",
        "Havasu Springs",
        "Pirate Cove",
        "Sandpoint",
        "Black Meadow",
        "Riviera",
        "Lakeside",
        "Beachfront",
        "Waterfront",
    ]
    print("  --- waterfront / lake-proximity name keyword scan ---")
    for kw in waterfront_keywords:
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

    # Franchise chains (5.8 lesson: same-name distinct place_ids =
    # distinct entities; verify no orphan dupes).
    chain_keywords = [
        "Hampton Inn",
        "Days Inn",
        "Super 8",
        "Quality Inn",
        "Travelers Inn",
        "Studio 6",
        "Rodeway Inn",
        "Home2 Suites",
        "Hilton",
        "Marriott",
        "Holiday Inn",
        "Best Western",
        "Comfort Inn",
    ]
    print("\n  --- franchise chain dedup scan (same-name distinct place_ids) ---")
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
            print(f"  {kw!r:<18}  -> 0 entities")
        else:
            for row in rows:
                print(
                    f"  {kw!r:<18}  -> {row[1]!r:<45}  type={row[2]!r:<11}  "
                    f"cats=[{row[3]!r}]  primary={row[4]!r}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
