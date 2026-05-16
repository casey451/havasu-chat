"""Phase 5.4 — dump the 114 ambig reconciler skips with their matched
existing entities for the §2 ambiguous-queue audit.

Reads:
  - outputs/phase5_4_load_real_v2.log (Tee'd output from the real load)
  - scripts/output/places_pull/enrichment_enriched.jsonl (cache)
  - data/events.db (entities + entity_categories + categories)

Writes outputs/phase5_4_ambig_audit_data.json with one record per ambig
hit, each enriched with the matched existing entity (geo within 50m or
name only), current Tier-1 slug, and distance / name similarity.

Mirrors the diagnostic dump pattern from the 5.3 audit run. Operator
runs once; the Cowork primary reads the JSON from sandbox and writes
the audit prose at outputs/phase5_4_health_wellness_pre_load_audit.md.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "outputs" / "phase5_4_load_real_v2.log"
ENRICHMENT_PATH = (
    ROOT / "scripts" / "output" / "places_pull" / "enrichment_enriched.jsonl"
)
DB_PATH = ROOT / "data" / "events.db"
OUT_PATH = ROOT / "outputs" / "phase5_4_ambig_audit_data.json"

GEO_PROXIMITY_THRESHOLD_M = 50.0
NEAR_GEO_INCLUDE_M = 75.0  # widen slightly for diagnostic discovery


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters."""
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


def main() -> int:
    if not LOG_PATH.exists():
        raise SystemExit(f"missing: {LOG_PATH}")
    if not ENRICHMENT_PATH.exists():
        raise SystemExit(f"missing: {ENRICHMENT_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"missing: {DB_PATH}")

    # 1. Extract ambig place_ids from the load log.
    # PS Tee-Object writes UTF-16 LE with BOM by default + wraps long lines.
    # Auto-detect encoding from the BOM, then anchor on each ``place_id=``
    # token and inspect the preceding 300 chars for "ambig" context.
    # Wrap-tolerant and encoding-tolerant by design.
    raw_bytes = LOG_PATH.read_bytes()
    if raw_bytes.startswith(b"\xff\xfe"):
        log_text = raw_bytes.decode("utf-16-le", errors="replace").lstrip("﻿")
        encoding_detected = "utf-16-le (BOM)"
    elif raw_bytes.startswith(b"\xfe\xff"):
        log_text = raw_bytes.decode("utf-16-be", errors="replace").lstrip("﻿")
        encoding_detected = "utf-16-be (BOM)"
    elif raw_bytes.startswith(b"\xef\xbb\xbf"):
        log_text = raw_bytes.decode("utf-8-sig", errors="replace")
        encoding_detected = "utf-8 (BOM)"
    else:
        log_text = raw_bytes.decode("utf-8", errors="replace")
        encoding_detected = "utf-8 (no BOM)"
    print(f"[dump] log encoding: {encoding_detected} ({len(raw_bytes)} bytes -> {len(log_text)} chars)")

    ambig_place_ids: list[tuple[str, str]] = []  # (place_id, ambig_kind)
    for m in re.finditer(r"place_id=([\w_-]+)", log_text):
        ctx = log_text[max(0, m.start() - 300) : m.start()].lower()
        if "ambig" not in ctx:
            continue
        kind = "geo50m_name_diff" if "geo" in ctx else "name_only_no_geo"
        ambig_place_ids.append((m.group(1), kind))

    print(f"[dump] {len(ambig_place_ids)} ambig hits parsed from log")
    if ambig_place_ids:
        print(f"[dump] sample first 3: {ambig_place_ids[:3]}")

    # 2. Load the enrichment cache keyed by place_id.
    enrichment: dict[str, dict] = {}
    for line in ENRICHMENT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pid = row.get("place_id")
        if pid:
            enrichment[pid] = row

    # 3. Pull DB entities with locations + their slug.
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    # NB: Location and Provider both have lat/lng columns; prefer Location
    # but fall back to Provider when Location is missing (some legacy rows).
    db_entities = list(
        cur.execute(
            """
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
            """
        )
    )
    print(f"[dump] {len(db_entities)} active entities loaded from DB")

    # 4. For each ambig hit, enrich + find matched existing entity.
    records = []
    for pid, kind in ambig_place_ids:
        candidate = enrichment.get(pid, {})
        c_name = candidate.get("display_name") or candidate.get("name")
        c_lat = candidate.get("latitude") or candidate.get("lat")
        c_lng = candidate.get("longitude") or candidate.get("lng")
        c_addr = candidate.get("formatted_address") or candidate.get("address")
        c_domain = candidate.get("_first_seen_domain")
        c_primary = candidate.get("primary_type")
        c_reviews = candidate.get("user_rating_count") or candidate.get("review_count")
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
                        "current_slugs": eslug.split("|") if eslug else [],
                        "distance_m": round(d, 1),
                        "name_similarity": round(jaccard_chars(c_norm, e_norm), 3),
                        "existing_place_id": eplaceid,
                        "existing_primary": eprimary,
                    })
        matched.sort(key=lambda x: (x["distance_m"], -x["name_similarity"]))

        records.append({
            "ambig_kind": kind,
            "candidate": {
                "place_id": pid,
                "name": c_name,
                "address": c_addr,
                "lat": c_lat,
                "lng": c_lng,
                "primary_type": c_primary,
                "discovery_domain": c_domain,
                "reviews": c_reviews,
            },
            "matched_entities": matched,
        })

    OUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"[dump] wrote {OUT_PATH} ({len(records)} records)")

    # 5. Quick aggregates.
    cross_cat = same_cat = no_match = 0
    health_slug = "health-wellness-care"
    for rec in records:
        if not rec["matched_entities"]:
            no_match += 1
            continue
        top = rec["matched_entities"][0]
        if health_slug in top["current_slugs"]:
            same_cat += 1
        else:
            cross_cat += 1

    print()
    print("=== aggregates ===")
    print(f"  total ambig hits:        {len(records)}")
    print(f"  no match (orphan ambig): {no_match}")
    print(f"  same-category match:     {same_cat}  (matched entity already in health-wellness-care)")
    print(f"  cross-category match:    {cross_cat}  (matched entity in a different Tier-1 slug)")
    print()
    if cross_cat > 0:
        print("=== cross-category ambig hits (the ones the audit must triage) ===")
        for rec in records:
            if not rec["matched_entities"]:
                continue
            top = rec["matched_entities"][0]
            if health_slug not in top["current_slugs"]:
                slugs = "/".join(top["current_slugs"]) or "(none)"
                cand = rec["candidate"]
                print(
                    f"  - {cand.get('name','?')!r:50s}  domain={cand.get('discovery_domain'):16s}  "
                    f"primary={cand.get('primary_type'):24s}  "
                    f"-> {top['name']!r} @ {slugs} ({top['distance_m']}m)"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
