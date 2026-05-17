"""Phase 5.8 — dump the 22 ambig reconciler skips + edge-case routings
for the §2 audit. Mirrors outputs/phase5_7_ambig_audit_dump.py shape
with three §8-specific adjustments:

1. **Narrow scope filter.** The 5.8 §1 dispatch was scoped to 7 labels
   (event venues, live music venues, art galleries, museums, movie
   theaters, bowling alleys, arcades — all entertainment_attractions
   domain) per kickoff §1. The dump filters on
   ``_first_seen_domain == "entertainment_attractions"`` to mirror
   the Narrow scope intent. Any row discovered under a cat-7 label
   (mini golf, golf courses, parks — deferred per 5.8 Narrow scope
   because 5.7 already absorbed them) that somehow routes to cat-2
   would surface as an anomaly worth flagging.

2. **Special-audit axis swap.** 5.7 audited the on-the-water /
   classes-sports-recreation / SARA-de-dup axes. 5.8 audits THREE
   axes per kickoff §2:
     (a) **cat-7 outdoors-parks-trails cross-list** — the primary
         5.8 audit focus. 5.7's catch-all
         ``(None, "entertainment_attractions") -> "outdoors-parks-trails"``
         swept 9 edge-case primary_types into cat-7. None of those
         9 should re-route to cat-2; the check catches new 5.8
         scrape rows that overlap with what 5.7 already loaded.
     (b) **cat-13 public-civic-resources cross-list** — event_venue
         at LHC City Hall? Museum at LHC Library? Civic spaces
         double-tagged as event hosts may surface here.
     (c) **Seasonal-activation de-dup** — the 2 pre-existing cat-2
         entries (Buses By The Bridge, Desert Storm Headquarters)
         are annual recurring events. Check for duplicate Provider
         rows for different years' events that should be merged.

3. **Edge-case routing review** for entertainment_attractions
   primary_types that landed in cat-2 events. With the 5.8
   sustainability commit (0b426e1) the 7 event primary_types map
   directly to cat-2 via ``_PRIMARY_TYPE_MAP``; other primary_types
   (tourist_attraction, point_of_interest, etc.) fall through to
   the 5.7 catch-all → cat-7 and don't land in cat-2. So the cat-2
   rubric is focused on the 7 direct mappings + any edge primary_type
   that surfaces unexpectedly.

Outputs:
  - outputs/phase5_8_ambig_audit_data.json (structured records)
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
OUT_PATH = ROOT / "outputs" / "phase5_8_ambig_audit_data.json"

TARGET_SLUG = "events"
GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0

# The 10 entertainment_attractions labels per HEAD scripts/places_categories.json
# (lines 184-193). Phase 5.8 Narrow scope ingested 7 of these (event venues,
# live music venues, art galleries, museums, movie theaters, bowling alleys,
# arcades); the dump tracks all 10 in case cache-resurfacing brought any other
# labels' rows into the load pool.
ENTERTAINMENT_LABELS = frozenset({
    "movie theaters", "bowling alleys", "arcades", "mini golf",
    "golf courses", "parks", "museums", "art galleries",
    "live music venues", "event venues",
})

# The 7 in-scope labels per Phase 5.8 kickoff §1 Narrow scope decision.
NARROW_LABELS = frozenset({
    "event venues", "live music venues", "art galleries", "museums",
    "movie theaters", "bowling alleys", "arcades",
})

# The 3 cat-7 deferred labels (already absorbed by 5.7). Any surfacing
# here would be a §2 anomaly worth flagging — the cat-7 routings should
# stay in cat-7 via 5.7's catch-all or the park/dog_park/golf_course
# direct mappings.
DEFERRED_CAT7_LABELS = frozenset({"parks", "golf courses", "mini golf"})

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


def is_deferred_cat7(row: dict) -> bool:
    """True if the enriched row was discovered under a cat-7-deferred
    label (parks / golf courses / mini golf). Surfacing in the cat-2
    audit pool is an anomaly — those labels should not route to cat-2."""
    fsc = row.get("_first_seen_category")
    if fsc in DEFERRED_CAT7_LABELS:
        return True
    seen = row.get("_seen_categories") or []
    return any(s in DEFERRED_CAT7_LABELS for s in seen)


def main() -> int:
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Reconstruct the entertainment_attractions input set
    # (post --category + post ZIP filter). Expected: 52 rows
    # (matches the [load] line: "after ZIP filter: 52 kept").
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
    cat7_anomalies = [
        r for r in enrichment.values()
        if is_deferred_cat7(r) and (r.get("zip") in LHC_ZIPS)
    ]
    print(f"[dump] enrichment cache: {len(enrichment)} place_ids")
    print(
        "[dump] entertainment+ZIP-filtered input: "
        f"{len(input_rows)} rows (expected 52)"
    )
    print(
        "[dump] cat-7-deferred+ZIP-filtered (anomaly surface): "
        f"{len(cat7_anomalies)} rows "
        "(expected ~25-30 from 5.7's load — these stay in cat-7)"
    )

    # 2. Query DB for which of these place_ids are already Providers
    # (= the inserted+updated set). The complement is the ambig-skipped set.
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
        f"[dump] inserted (Providers in DB): {len(inserted_pids)} "
        "(expected 30 = 1 fresh + 29 updates from §1 load)"
    )
    print(
        f"[dump] ambig-skipped (NOT in DB): {len(ambig_pids)} "
        "(expected 22)"
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

    # 6. Special audit (a): cat-7 outdoors-parks-trails cross-list.
    # Per 5.8 kickoff §2 — the PRIMARY 5.8 audit focus. 5.7's catch-all
    # swept 9 edge-case primary_types into cat-7; none should re-route
    # to cat-2. The check catches NEW 5.8 scrape rows overlapping with
    # what 5.7 already loaded.
    print("\n=== special audit (a): cat-7 outdoors-parks-trails cross-list ===")
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
                    "V1 policy: KEEP in cat-7 unless event-primary "
                    "(then FLIP to cat-2)"
                )
                cat7_flagged += 1
                break
    if cat7_flagged == 0:
        print("  (no cat-7 outdoors-parks-trails cross-list hits in ambig pool)")

    # Also surface the §1-updated entries that are still in cat-7
    # — these are the 29 updates that didn't get dual-written to cat-2.
    print(
        "\n  --- §1-updated entries (currently in cat-7) "
        "that match this 5.8 scrape ---"
    )
    cur.execute("""
        SELECT p.provider_name, p.google_primary_category,
               GROUP_CONCAT(DISTINCT c.slug)
        FROM providers p
        JOIN entities e ON e.id = p.entity_id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE p.google_place_id IN ({})
          AND e.id IN (
              SELECT entity_id FROM entity_categories
              WHERE category_id = (SELECT id FROM categories
                                   WHERE slug='outdoors-parks-trails')
          )
        GROUP BY e.id
        ORDER BY p.provider_name
    """.format(",".join("?" * len(inserted_pids))), tuple(inserted_pids))
    rows = cur.fetchall()
    if rows:
        for name, gpc, slugs in rows:
            print(f"    {name!r:42s}  primary={gpc!r:20s}  slugs={slugs}")
    else:
        print("    (no §1-updated entries are currently in cat-7)")

    # 7. Special audit (b): cat-13 public-civic-resources cross-list.
    # Event venues at City Hall? Museums at the Library? Civic spaces
    # double-tagged as event hosts may surface here.
    print(
        "\n=== special audit (b): cat-13 public-civic-resources cross-list ==="
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
                    "V1 policy: KEEP in cat-13 if civic-primary; "
                    "cross-link if both apply"
                )
                civic_flagged += 1
                break
    if civic_flagged == 0:
        print("  (no public-civic-resources cross-list hits in ambig pool)")

    # 8. Special audit (c): seasonal-activation de-dup.
    # The 2 pre-existing cat-2 entries are annual events. Check for
    # duplicate Provider rows for different years that should be merged.
    print("\n=== special audit (c): seasonal-activation de-dup ===")
    cur.execute("""
        SELECT p.provider_name, p.google_primary_category, e.id, p.id,
               COALESCE(l.lat, p.lat), COALESCE(l.lng, p.lng),
               p.google_place_id
        FROM providers p
        JOIN entities e ON e.id = p.entity_id
        LEFT JOIN locations l ON l.entity_id = e.id
        JOIN entity_categories ec ON ec.entity_id = e.id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = ?
        ORDER BY p.provider_name
    """, (TARGET_SLUG,))
    cat2_rows = cur.fetchall()
    print(f"  Current cat-2 entries in DB: {len(cat2_rows)}")
    for name, gpc, eid, pid, lat, lng, gpid in cat2_rows:
        lat_str = f"{lat:.5f}" if lat is not None else "None"
        lng_str = f"{lng:.5f}" if lng is not None else "None"
        print(
            f"    {name!r:42s}  primary={gpc!r:18s}  "
            f"({lat_str},{lng_str})  e_id={eid[:8]}"
        )
    # Look for name-pattern collisions (e.g., "Buses By The Bridge 2025"
    # vs "Buses By The Bridge" — would suggest a year-specific event row
    # that should merge to the parent).
    if len(cat2_rows) > 1:
        print(
            "  -> V1 decision: KEEP distinct named events; merge "
            "rows whose names differ only by year suffix or whose "
            "Provider data overlaps fully."
        )

    # 9. Edge-case routing review — entertainment_attractions primary_types
    # currently in cat-2 (post-§1-load). With the 5.8 sustainability commit
    # (0b426e1) only the 7 directly-mapped primary_types route to cat-2;
    # surfacing any other primary_type here is unexpected.
    print(
        "\n=== edge-case review: primary_types in cat-2 events "
        "(post-§1-load) ==="
    )
    cur.execute("SELECT id FROM categories WHERE slug=?", (TARGET_SLUG,))
    events_id = cur.fetchone()[0]
    cur.execute("""
        SELECT provider_name, google_primary_category, address,
               google_place_id, id
        FROM providers
        WHERE category_id=? AND source='google_places'
        ORDER BY google_primary_category, provider_name
    """, (events_id,))

    # Operator-decision rubric per primary_type for 5.8.
    rubric: dict[str | None, tuple[str, str]] = {
        "event_venue": ("KEEP cat-2 (commercial per 5.8 sustainability)", "keep"),
        "art_gallery": (
            "KEEP cat-2 (place-typed per kickoff §1 starting point; "
            "flip to commercial if charges admission)",
            "keep",
        ),
        "museum": (
            "KEEP cat-2 (place-typed per kickoff §1 starting point; "
            "Lake Havasu Museum of History likely flips to commercial)",
            "review",
        ),
        "live_music_venue": (
            "KEEP cat-2 (commercial per 5.8 sustainability)",
            "keep",
        ),
        "movie_theater": ("KEEP cat-2 (commercial)", "keep"),
        "bowling_alley": ("KEEP cat-2 (commercial)", "keep"),
        "amusement_arcade": ("KEEP cat-2 (commercial)", "keep"),
        "performing_arts_theater": (
            "REVIEW: edge case — Google primary_type variant of "
            "live_music_venue; likely KEEP cat-2",
            "review",
        ),
        "concert_hall": (
            "REVIEW: edge case — likely KEEP cat-2",
            "review",
        ),
        "tourist_attraction": (
            "ANOMALY — tourist_attraction should route to cat-7 "
            "via the 5.7 catch-all, not cat-2. Investigate.",
            "anomaly",
        ),
        "amusement_park": (
            "REVIEW: 5.7 caught Altitude Trampoline Park here as cat-7 "
            "DRAFTed; if surfacing in cat-2, verify routing",
            "review",
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

    print(f"  {'primary_type':<28s}  {'name':<42s}  recommended action")
    edge_rows = cur.fetchall()
    if not edge_rows:
        print("  (no entries in cat-2 — unexpected; verify §1 load ran)")
    for r in edge_rows:
        name, gpc, addr, place_id, prov_id = r
        action, code = rubric.get(gpc, ("REVIEW (uncoded primary type)", "unknown"))
        gpc_disp = str(gpc)[:26] if gpc else "(None)"
        name_disp = name[:40] if name else "(noname)"
        print(f"  {gpc_disp!r:28s}  {name_disp!r:42s}  {action}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
