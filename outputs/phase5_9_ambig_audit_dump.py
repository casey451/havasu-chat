"""Phase 5.9 — dump the 23 ambig reconciler skips + §1-update surface +
cross-cat axes for the §2 audit. Mirrors outputs/phase5_8_ambig_audit_
dump.py shape with three 5.9-specific adjustments:

1. **Narrow scope filter, TWO domains.** The 5.9 §1 dispatch was scoped
   to 9 labels (5 childcare_education + 4 cat-12-native fitness_sports)
   per kickoff §1. The dump filters on
   ``_first_seen_domain in {"childcare_education", "fitness_sports"}``
   to mirror the Narrow scope intent. Any row discovered under a
   deferred HWC-absorbed fitness_sports label (gyms, yoga studios,
   pilates studios, crossfit gyms, martial arts, jiu-jitsu, dance
   studios — already absorbed by 5.4 HWC) that somehow routes to
   cat-12 would surface as an anomaly worth flagging — but with the
   Narrow scope filter, these 7 deferred labels should not be in the
   5.9 enrichment set at all.

2. **Special-audit axis swap.** 5.8 audited the cat-7 / cat-13 /
   seasonal-activation axes. 5.9 audits THREE axes per kickoff §2:
     (a) **cat-5 HWC primary axis — the BIG one.** 5.4 absorbed
         gyms / yoga / pilates / crossfit / martial / jiu_jitsu /
         dance studios into HWC. 5.9's personal_trainer label
         rediscovers many of them (place_id-matched -> UPDATE branch
         preserves existing cat-5). The 32 §1-updates surface here.
         V1 policy per kickoff §2: KEEP cat-5; V1.5 may want dual-cat.
     (b) **cat-7 outdoors-parks-trails secondary axis.** Public pools
         / tennis / pickleball courts may overlap with park amenities
         (Rotary Park, Lions Park, Lake Havasu State Park) already in
         cat-7 from 5.7. V1 policy: review per-row; FLIP candidates
         are those where the swimming_pool / tennis_court /
         pickleball_court is the primary identity vs incidental amenity.
     (c) **cat-13 public-civic-resources cross-list.** Church-
         affiliated daycare (cat-13 entity) could double-tag as
         daycare (cat-12). V1 policy: KEEP cat-13 if civic-primary;
         cross-link if both apply.

3. **Edge-case routing review** for classes-sports-recreation
   primary_types currently in cat-12 (post-§1-load). With the 5.9
   sustainability commit (0af5f73) 9 direct mappings beat the 5.4
   ``(None, "fitness_sports") -> "health-wellness-care"`` catch-all
   for the 4 cat-12-native types (personal_trainer / swimming_pool /
   tennis_court / pickleball_court); the new ``(None,
   "childcare_education") -> "classes-sports-recreation"`` catch-all
   covers any unmapped childcare types. The pre-Phase-5 ``school``
   direct mapping continues to route schools to cat-12. The rubric
   below covers the 10 expected primary_types + edge cases.

Outputs:
  - outputs/phase5_9_ambig_audit_data.json (structured records)
  - stdout aggregates + 3 special-audit sections + §1-update enumeration
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
OUT_PATH = ROOT / "outputs" / "phase5_9_ambig_audit_data.json"

TARGET_SLUG = "classes-sports-recreation"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# The 16 classes-sports-recreation labels per HEAD scripts/places_
# categories.json (5 childcare_education + 11 fitness_sports). Phase
# 5.9 Narrow scope ingested 9 of these; the dump tracks all 16 in case
# cache-resurfacing brought any other labels' rows into the load pool.
TWO_DOMAIN_LABELS = frozenset({
    # childcare_education (5)
    "daycare", "preschools", "tutoring", "music lessons", "driving schools",
    # fitness_sports (11)
    "gyms", "personal trainers", "yoga studios", "pilates studios",
    "crossfit gyms", "martial arts", "jiu-jitsu", "dance studios",
    "swimming pools", "tennis courts", "pickleball",
})

# The 9 in-scope labels per Phase 5.9 kickoff §1 Narrow scope decision.
NARROW_LABELS = frozenset({
    "daycare", "preschools", "tutoring", "music lessons", "driving schools",
    "personal trainers", "swimming pools", "tennis courts", "pickleball",
})

# The 7 HWC-deferred labels (already absorbed by 5.4 HWC). Any
# surfacing in the 5.9 enrichment pool would be a §1 anomaly — the
# Narrow scope wrapper should have filtered them out at discovery.
DEFERRED_HWC_LABELS = frozenset({
    "gyms", "yoga studios", "pilates studios", "crossfit gyms",
    "martial arts", "jiu-jitsu", "dance studios",
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


def is_cat12_two_domain(row: dict) -> bool:
    """True if the enriched row was discovered under either of the two
    classes-sports-recreation domains (childcare_education or
    fitness_sports), regardless of specific label."""
    domain = row.get("_first_seen_domain")
    if domain in ("childcare_education", "fitness_sports"):
        return True
    fsc = row.get("_first_seen_category")
    if fsc in TWO_DOMAIN_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in TWO_DOMAIN_LABELS for s in seen)


def is_deferred_hwc(row: dict) -> bool:
    """True if the enriched row was discovered under a 5.4-HWC-absorbed
    label (gyms / yoga / pilates / etc.). Surfacing in the 5.9 pool
    means the Narrow scope wrapper filter leaked — anomaly."""
    fsc = row.get("_first_seen_category")
    if fsc in DEFERRED_HWC_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in DEFERRED_HWC_LABELS for s in seen)


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the two-domain input set (post --category + post
    # ZIP filter). Expected: 82 rows (matches the [load] line:
    # "after ZIP filter: 82 kept").
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
        if is_cat12_two_domain(r) and (r.get("zip") in LHC_ZIPS)
    ]
    hwc_anomalies = [
        r for r in enrichment.values()
        if is_deferred_hwc(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(
        "[dump] two-domain+ZIP-filtered input: "
        f"{len(input_rows)} rows (expected 82)"
    )
    print(
        "[dump] HWC-deferred+ZIP-filtered (anomaly surface): "
        f"{len(hwc_anomalies)} rows (expected 0 — Narrow scope wrapper "
        "should have filtered these at discovery)"
    )
    if hwc_anomalies:
        print("  [!] HWC-deferred anomalies (investigate):")
        for r in hwc_anomalies[:10]:
            print(
                f"    {r.get('display_name')!r:42s}  "
                f"label={r.get('_first_seen_category')!r}"
            )

    # 2. Query DB for which of these place_ids are already Providers
    # (= the inserted+updated set). The complement is the
    # ambig-skipped set.
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
        "(expected 59 = 27 inserts + 32 updates from §1 load)"
    )
    print(
        f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
        "(expected 23)"
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
            "ambig_kind": "geo50m_name_diff",  # all 23 per §1 load log
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

    # 6. Special audit (a): cat-5 HWC primary axis. THE BIG ONE per
    # kickoff §2 — 5.4 absorbed gyms/yoga/pilates/etc. into HWC; 5.9's
    # personal_trainer label rediscovers many of them via place_id match
    # (= UPDATE branch, preserving cat-5). Surfaces both ambig matches +
    # the 32 §1-updated entries still in cat-5.
    print("\n=== special audit (a): cat-5 HWC primary axis (the BIG one) ===")
    print("  --- (a.1) Ambig pool — cat-5 HWC matches ---")
    hwc_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "health-wellness-care" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    "V1 policy: NEW create in cat-12 if distinct service "
                    "(personal trainer vs gym); KEEP ambig if geo-noise"
                )
                hwc_flagged += 1
                break
    if hwc_flagged == 0:
        print("    (no cat-5 HWC cross-list hits in ambig pool)")

    # Surface the §1-updated entries currently in cat-5 — the dual-cat
    # consideration set per kickoff §2 V1.5 policy.
    print("\n  --- (a.2) §1-updated entries currently in cat-5 HWC "
          "(dual-cat candidates) ---")
    if inserted_pids:
        cur.execute("""
            SELECT p.provider_name, p.google_primary_category, p.google_place_id,
                   GROUP_CONCAT(DISTINCT c.slug)
            FROM providers p
            JOIN entities e ON e.id = p.entity_id
            JOIN entity_categories ec ON ec.entity_id = e.id
            JOIN categories c ON c.id = ec.category_id
            WHERE p.google_place_id IN ({})
              AND e.id IN (
                  SELECT entity_id FROM entity_categories
                  WHERE category_id = (SELECT id FROM categories
                                       WHERE slug='health-wellness-care')
              )
            GROUP BY e.id
            ORDER BY p.google_primary_category, p.provider_name
        """.format(",".join("?" * len(inserted_pids))), tuple(inserted_pids))
        hwc_rows = cur.fetchall()
        print(f"    Count: {len(hwc_rows)} entities (of 59 §1-updated)")
        for name, gpc, _gpid, slugs in hwc_rows:
            name_disp = name[:42] if name else "(noname)"
            gpc_disp = gpc or "(None)"
            slug_disp = slugs or "(none)"
            print(f"    {name_disp!r:44s}  primary={gpc_disp!r:22s}  slugs={slug_disp}")
        if len(hwc_rows) > 0:
            print(
                "    --> V1 policy per kickoff §2: KEEP cat-5 for V1 "
                "(default — the load script's preserve-operator-choice "
                "behavior already kept them in cat-5). V1.5 may "
                "selectively dual-cat for entities offering distinct "
                "cat-12 services (e.g. a gym whose personal trainers "
                "deserve a separate cat-12 listing)."
            )
    else:
        print("    (no §1-updated entries to check)")

    # 7. Special audit (b): cat-7 outdoors-parks-trails secondary axis.
    # Public pools / tennis / pickleball courts may overlap with park
    # amenities (Rotary Park, Lions Park, Lake Havasu State Park) from
    # 5.7. V1 policy: review per-row; FLIP candidates are those where
    # the pool/court is the primary identity (vs incidental amenity).
    print(
        "\n=== special audit (b): cat-7 outdoors-parks-trails secondary axis ==="
    )
    cat7_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "outdoors-parks-trails" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    "V1 policy: KEEP cat-7 if park-primary; FLIP to cat-12 "
                    "if pool/court is the primary identity"
                )
                cat7_flagged += 1
                break
    if cat7_flagged == 0:
        print("  (no cat-7 outdoors-parks-trails cross-list hits in ambig pool)")

    # 8. Special audit (c): cat-13 public-civic-resources cross-list.
    # Church-affiliated daycare (cat-13 entity) could double-tag as
    # daycare (cat-12). V1 policy: KEEP cat-13 if civic-primary;
    # cross-link if both apply.
    print(
        "\n=== special audit (c): cat-13 public-civic-resources cross-list ==="
    )
    civic_flagged = 0
    for rec in records:
        if not rec["matched_entities"]:
            continue
        for m in rec["matched_entities"]:
            if "public-civic-resources" in m["current_slugs"]:
                print(
                    f"  - cand {rec['candidate'].get('name')!r:42s}  "
                    f"label={rec['candidate'].get('discovery_label')!r:18s} "
                    f"-> existing {m['name']!r:35s} @ "
                    f"{'/'.join(m['current_slugs']) or '?'} "
                    f"({m['existing_primary']}, {m['distance_m']}m) — "
                    "V1 policy: KEEP cat-13 if civic-primary; "
                    "cross-link if both apply"
                )
                civic_flagged += 1
                break
    if civic_flagged == 0:
        print("  (no public-civic-resources cross-list hits in ambig pool)")

    # 9. Edge-case routing review — classes-sports-recreation
    # primary_types currently in cat-12 (post-§1-load). With the 5.9
    # sustainability commit (0af5f73) the 9 directly-mapped primary
    # types route to cat-12; the pre-Phase-5 school direct mapping also
    # routes to cat-12. Other primary_types fall through to the 5.4
    # ``(None, "fitness_sports") -> "health-wellness-care"`` catch-all
    # (-> cat-5) or the new ``(None, "childcare_education") ->
    # "classes-sports-recreation"`` catch-all (-> cat-12 for unmapped
    # childcare types).
    print(
        "\n=== edge-case review: primary_types in cat-12 classes-sports-recreation "
        "(post-§1-load) ==="
    )
    cur.execute("SELECT id FROM categories WHERE slug=?", (TARGET_SLUG,))
    cat12_id = cur.fetchone()[0]
    cur.execute("""
        SELECT provider_name, google_primary_category, address,
               google_place_id, id
        FROM providers
        WHERE category_id=? AND source='google_places'
        ORDER BY google_primary_category, provider_name
    """, (cat12_id,))

    # Operator-decision rubric per primary_type for 5.9.
    rubric: dict[str | None, tuple[str, str]] = {
        # The 9 direct mappings shipped at 0af5f73.
        "child_care_agency": ("KEEP cat-12 (commercial)", "keep"),
        "preschool": ("KEEP cat-12 (commercial)", "keep"),
        "music_school": ("KEEP cat-12 (commercial)", "keep"),
        "driving_school": ("KEEP cat-12 (commercial)", "keep"),
        "tutor": ("KEEP cat-12 (commercial)", "keep"),
        "personal_trainer": ("KEEP cat-12 (commercial)", "keep"),
        "swimming_pool": (
            "KEEP cat-12 (place per kickoff §1; flip to commercial if "
            "membership-club venue)",
            "keep",
        ),
        "tennis_court": (
            "KEEP cat-12 (place per kickoff §1; flip to commercial if "
            "membership-club venue)",
            "keep",
        ),
        "pickleball_court": (
            "KEEP cat-12 (place per kickoff §1; flip to commercial if "
            "membership-club venue)",
            "keep",
        ),
        # Pre-Phase-5 school mapping.
        "school": (
            "KEEP cat-12 (commercial, pre-Phase-5 direct mapping)",
            "keep",
        ),
        # Edge cases that may show up via the new childcare_education
        # catch-all or via primary_type drift.
        "educational_consultant": (
            "REVIEW: edge case — adjacent to tutor; likely KEEP cat-12",
            "review",
        ),
        "sports_complex": (
            "REVIEW: edge case — could be cat-12 if courts/pools are "
            "primary; could overlap cat-7 if park-primary",
            "review",
        ),
        "athletic_field": (
            "REVIEW: edge case — likely cat-7 outdoor park amenity but "
            "could be cat-12 if school/program-affiliated",
            "review",
        ),
        "sports_school": (
            "REVIEW: edge case — likely KEEP cat-12 (school-shape)",
            "review",
        ),
        "country_club": (
            "REVIEW: edge case — golf+pool+tennis combo; primary is "
            "usually golf (cat-7 commercial); cat-12 cross-link possible",
            "review",
        ),
        "amusement_park": (
            "ANOMALY — amusement_park should route to cat-7 via the 5.7 "
            "catch-all, not cat-12. Investigate.",
            "anomaly",
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
            "REVIEW — no primary_type; needs per-row decision (would have "
            "routed via the new childcare_education catch-all if discovered "
            "under that domain)",
            "review",
        ),
    }

    print(f"  {'primary_type':<28s}  {'name':<42s}  recommended action")
    edge_rows = cur.fetchall()
    if not edge_rows:
        print("  (no entries in cat-12 — unexpected; verify §1 load ran)")
    for r in edge_rows:
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW (uncoded primary type)", "unknown"))
        gpc_disp = str(gpc)[:26] if gpc else "(None)"
        name_disp = name[:40] if name else "(noname)"
        print(f"  {gpc_disp!r:28s}  {name_disp!r:42s}  {action}")

    # 10. DB-verify the 5.8 §9 V1.5 carry candidates per kickoff §8.
    # The 5.8 close-out lesson: DB-verify the "existing entity in cat-X"
    # premise before authoring any cross-cat moves.
    print(
        "\n=== DB-verify 5.8 §9 V1.5 carry candidates (kickoff §8 hand-off) ==="
    )
    keywords = [
        "Aquatic",       # cat-12 FLIP candidate (swimming_pool primary)
        "Nomadic",       # possible cat-12 if hosts classes
        "Lions Dog",     # cat-7 not yet in DB?
        "Main Street Commons",  # cat-7 V1.5 hand-curation
    ]
    for kw in keywords:
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
