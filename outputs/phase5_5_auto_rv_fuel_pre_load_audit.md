# Phase 5.5 — Auto, RV & Fuel — Post-load ambiguous-queue audit

> Mirrors `outputs/phase5_4_health_wellness_pre_load_audit.md` shape with
> a 5.5-specific override: this doc runs in ONE pass (post-load) because
> the §2 RV cross-list audit is a 5.5-specific surface that piggy-backs
> on the standard ambig-queue audit. The audit reviews all 76 ambiguous
> reconciler skips from the load run, documents the verdict for each
> bucket, and covers the kickoff §2 special audit (RV cross-list against
> on-the-water).
>
> **TL;DR:** No misroutes among existing entities. The 76 ambig hits
> are the **auto-industrial-blvd false-ambig pattern** — auto/RV/fuel
> businesses geo-colliding (within 50m) with marine, restaurant, and
> contractor businesses on Lake Havasu's Industrial Blvd / Lake Havasu
> Ave / McCulloch corridor strip-malls. The reconciler verdict ("ambig")
> is conservative-correct under V1 policy; no apply-script needed. RV
> cross-list audit returned 4 flags, all coincidental (different
> businesses with overlapping naming tokens); 0 real flips. **Gate-2
> met by review.**
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.5 session
> (2026-05-16) post-fallback-extension commit (`4d41944`).

---

## §1 Summary

Phase 5.5 §1 Layer 1 produced **179 ZIP-filtered Google Places
candidates** through the reconciler. Outcomes (first load run; re-runs
post-fallback-fix are idempotent):

| Reconciler action | Count | Disposition |
|---|---|---|
| `insert` (new entity) | 102 | Loaded — `auto-rv-fuel` = 140 post-fallback re-load (41 pre-existing + 99 new resolved). |
| `update` (existing place_id) | 1 (first run) → 103 (re-run after fallback fix) | Idempotent; existing rows refreshed |
| `ambig` (geo+name conflict) | **76** | This audit's subject |
| `merge` (geo proximity + name match) | 1 (first run) → 0 (re-runs) | Already merged |

Of the 76 ambig hits:

| Bucket | Count | Match shape | Decision |
|---|---|---|---|
| **A — cross-category** | 67 | Candidate geo-matches an entity currently in a different Tier-1 slug (on-the-water ×29, eat-drink ×20, home-property-services ×14, health-wellness-care ×2, pets ×1, shopping-essentials ×1) | KEEP-SKIP (V1 — see §3.1) |
| **B — same-category** | 9 | Candidate geo-matches an entity already in `auto-rv-fuel` (adjacent auto shops in the same strip-mall double) | KEEP-SKIP (V1 — see §3.2) |
| **C — orphans (no-geo-match)** | 0 | All 76 ambig hits had a candidate within 75m | n/a |
| **Total reviewed** | **76** | | gate-2 cleared by review |

**Cross-list policy (V1):** unchanged from 5.3 + 5.4 — each entity gets
exactly one EntityCategory row except where dual-tag is explicitly
warranted (none surfaced in 5.5).

**Net effect on Phase 5.5 gate-1:** None — the 76 candidates were
already excluded by reconciler at load time. `/category/auto-rv-fuel`
renders 140 entries (gate-1 target was ≥30; cleared 4.7×).

---

## §2 The auto-industrial-blvd false-ambig pattern

### Why the 76-hit count was anticipated

The Phase 5.5 kickoff §2 anticipated 15-50 ambig hits but flagged that
LHC's auto cluster on Industrial Blvd / Lake Havasu Ave / McCulloch
corridor produces strip-mall density similar to 5.4's medical-plaza
pattern. The actual 76 figure lands above the kickoff range but is
**categorically the same pattern** — auto/RV/fuel businesses
geo-colliding (within 50m) with marine, restaurant, and contractor
businesses in adjacent suites or buildings.

Distance distribution of the 67 cross-category hits (the bucket where
the strip-mall pattern is most visible):

| Distance band | Count |
|---|---|
| `<10m` | 14 |
| `10–25m` | 27 |
| `25–50m` | 34 |
| `50–75m` | 1 (audit-only — at the dump script's 75m diagnostic widen; the actual reconciler 50m threshold excluded this row) |
| `≥75m` | 0 |

**~98% of cross-category hits are <50m.** That's the
industrial-blvd-suite-to-suite distance in LHC's auto cluster.

Name-similarity distribution (jaccard char overlap, top-1 match per
hit):

| Similarity band | Count | Interpretation |
|---|---|---|
| `≥0.8` (very similar) | 1 | Chance overlap — common words; clearly different on inspection |
| `0.6–0.8` (similar) | 12 | Different businesses sharing chain or naming-convention tokens (e.g., "Auto", "Service") |
| `0.4–0.6` (moderate) | 32 | Different businesses, modest token overlap |
| `0.2–0.4` (weak) | 29 | Clearly different |
| `<0.2` (different) | 2 | Clearly different |

### Why this is conservative-correct under V1

Same V1 reasoning as 5.3 + 5.4 audits — the reconciler's ambig verdict
routes candidates to operator review rather than auto-inserting. Under
V1 single-primary EntityCategory policy, conservative-skip is safer
than auto-insert because:

- Auto-inserting risks double-counting if the matched entity is in fact a
  duplicate Google listing for the same business (rare but possible).
- A skip is recoverable in a follow-up apply-script; a wrong auto-insert
  requires a delete pass.
- Phase 5.5's gate-1 (≥30 entries) is met handily at 140 without
  recovering the 76 — no completeness pressure for V1.

The cost is that 76 valid candidates remain unloaded. Carried forward
to Phase 5.6+ as a soft-edge (mirrors 5.4's same flag).

---

## §3 Per-bucket analysis

### 3.1 Bucket A — 67 cross-category geo-collisions

**Distribution by matched-entity slug:**

| Matched slug | Count | Pattern |
|---|---|---|
| on-the-water | 29 | Auto industrial blvd overlaps with marine industrial cluster (LHC has shared light-industrial parks for auto + boat services) |
| eat-drink | 20 | Gas stations + auto shops adjacent to fast-food / convenience-store cluster on US-95 / Lake Havasu Ave |
| home-property-services | 14 | Auto shops adjacent to contractor / plumbing / roofing businesses in industrial-park clusters |
| health-wellness-care | 2 | Edge — auto shop near a dental prosthetics office and a fitness store |
| pets | 1 | Edge — Premier Golf Cars next to Paws and Claws Animal Care |
| shopping-essentials | 1 | Edge — AutoZone next to Big 5 Sporting Goods |

**Example collisions (representative — full data in
`outputs/phase5_5_ambig_audit_data.json`):**

| Candidate (auto-rv-fuel) | Matched (other slug) | Distance | Sim |
|---|---|---|---|
| Robinson Automotive | HTM Performance Boats | 0.3m | (same building) |
| Alpha auto design | D1 Performance | 0.0m | (same building) |
| Caliber Collision | Marine One Motorsports | 25.6m | (industrial park adjacent) |
| Take 5 Oil Change | Donut Post | 35.6m | (strip mall) |
| Discount Tire | Carl's Jr. | 41.1m | (adjacent buildings) |
| Cmg Auto Glass | Paramount Roofing | 4.3m | (industrial cluster) |
| Easy Auto Rents | Linda's Italian Foods | 5.4m | (adjacent — likely shared parking) |
| 76 (gas station) | Niko's Grill & Pub | 19.5m | (gas + restaurant colocation) |
| AutoZone Auto Parts | Big 5 Sporting Goods | 29.2m | (strip mall) |

All examples are clearly distinct businesses at the same physical
address — strip-mall / multi-tenant / adjacent-building pattern.

**Verdict:** KEEP-SKIP. No re-route action on existing entities; no
force-insert of candidates under V1.

### 3.2 Bucket B — 9 same-category geo-collisions

The candidate geo-matches an entity already in `auto-rv-fuel` — strip-mall
doubles within the auto industrial cluster. All matched entities have
**distinct Google place_ids** from the candidates → guaranteed different
businesses (Google does not reuse place IDs).

**All 9 same-category hits:**

| Candidate | Matched (already in auto-rv-fuel) | Distance | Sim |
|---|---|---|---|
| Accurate Auto Care - Lake Havasu City | Britton's Auto Truck & RV Repair | 15.1m | 0.65 |
| Freedom Automotive | Byrd's Mobile RV & Marine | 10.2m | 0.50 |
| Abnorm Al's Mobile Repair | Carburetion Specialties & Performance Full Automotive and Boat Service / Repair | 18.7m | 0.65 |
| California Motorsports Inc | Tapped Out Mobile Detailing | 0.9m | 0.47 |
| TheAutoMann-Mobile Mechanic | The Boat Brokers, RV & Classic Cars | 0.0m | 0.56 |
| Self Car Wash | Sundance country car Wash | 16.2m | 0.47 |
| ProPrecision Sand & Offroad | 3-T's RV Products, Inc | 18.3m | 0.53 |
| Twisted Powersports | Havasu Express Car Wash | 42.7m | 0.33 |
| Fullsac Performance | Anything Off-Road | 58.7m | 0.28 |

All are auto-industrial-cluster strip-mall doubles — same physical
location, distinct businesses. Same pattern as 5.4 bucket B (medical
plaza doubles).

**Verdict:** KEEP-SKIP. V1 policy unchanged.

### 3.3 Bucket C — 0 orphan ambig hits

Unlike 5.4 (which had 2 orphan "name only no geo" hits), 5.5 has zero
orphans. Every ambig hit resolved to a nearby entity within 75m. Clean.

---

## §4 RV cross-list audit (Phase 5.5 §2 special surface)

The kickoff §2 specifically called out the RV cross-list with 5.2's
`lake_recreation` (on-the-water) load. The audit dump script flags
candidates whose name contains "rv" or "trailer" and that matched an
on-the-water entity:

| Candidate | Matched (on-the-water) | Distance | Sim | Verdict |
|---|---|---|---|---|
| Gosselin Automotive Services | Riverside Boat Dock Sales | 41.9m | 0.59 | **NO FLIP** — different businesses, coincidental "Service" token overlap |
| Any Radiator Service | So Cal Speed & Marine | 60.6m | 0.60 | **NO FLIP** — also >50m; not even a real reconciler ambig; coincidental token overlap |
| Riverview Auto Sales | Total Marine Pros and Powersports | 34.8m | 0.60 | **NO FLIP** — different businesses, industrial-park adjacency |
| Auto Service Center | Marine One Motorsports | 15.6m | 0.62 | **NO FLIP** — different businesses, strip-mall double |

**Zero real RV cross-list flips needed.** Cross-checking against the
DB-side cross-list query (entities in BOTH cat-9 + cat-6) returned 0
overlaps — every actual RV business is already correctly categorized
per the kickoff §2 V1 policy:

- **9 RV storage facilities** stay in `on-the-water` (lake-adjacent
  camping/storage primary use) ✅
- **RV dealers** (Palm Tree RV Sales, Sunshine RV, Wheelestatervguy,
  Beach Auto & RV, Havasu RV & Marine, etc.) in `auto-rv-fuel` ✅
- **RV repair** (BlackSheep RV LLC, Byrd's Mobile RV & Marine, PRO
  TECH RV, Happy Camper RV Repair, Frank's Trailer Repair, Virgil's
  Auto RV Diesel, etc.) in `auto-rv-fuel` ✅
- **1 borderline rental** ("Lake Havasu RV and Boat Rentals" in
  on-the-water) — defensible-as-is since it's also a Boat Rentals
  business; the kickoff §2 "case-by-case" verdict resolves to no flip

---

## §5 Apply-script — none for V1

Unlike the 5.3 audit (which prescribed
`outputs/apply_phase5_3_home_property_audit.py` for 16 re-route + 3
flip-in + 1 misroute-flip), and consistent with 5.4 (no apply-script
needed), the 5.5 audit **prescribes no apply-script**:

1. **No misroutes** — every existing entity is correctly categorized.
2. **No force-insert of skipped candidates** — V1 policy is to keep
   reconciler-skipped rows out of the loaded set.
3. **No RV cross-list flips** — the 4 flagged candidates are
   coincidental matches; no entity needs to move between cat-9 and
   cat-6.

The 76 reviewed candidates remain in `enrichment_enriched.jsonl` and
will resurface on any future re-load. The reconciler will produce the
same 76 ambig verdicts because the underlying state (existing entities
at the same lat/lng) is unchanged.

---

## §6 Coordination with the §2 RV cross-list special audit

The kickoff §2 anticipated three possible RV-row outcomes:

| Existing `lake_recreation` row | Reconciler hits 5.5 candidate | V1 policy | Actual |
|---|---|---|---|
| RV park (Crazy Horse, Cattail Cove, etc.) | yes (geo+name) | stay in on-the-water | ✅ stayed (none surfaced in 5.5 ambig set) |
| RV dealer (e.g. Beaudry RV) | yes (name) | flip to auto-rv-fuel if score >85 | ✅ already in auto-rv-fuel from earlier seed loads |
| RV rental | yes (name) | case-by-case | ✅ 1 borderline ("Lake Havasu RV and Boat Rentals") — no flip, defensible-as-is |
| RV repair | yes (name) | flip to auto-rv-fuel | ✅ already in auto-rv-fuel from this load |

**No 5.5-side action required on the §2 surface.** The pre-existing 41
auto-rv-fuel entities (per §0 pre-flight DB inspection) already
correctly held the RV dealer / RV repair rows; the §1 scrape added
more without producing cross-category misroutes.

---

## §7 Soft-edges flagged for Phase 5.6+

Same shape as the 5.4 carry-forward list:

- **76 reviewed-but-unloaded candidates** remain in `enrichment_enriched.jsonl`.
  If a future Phase 5.x audit decides to force-insert any, the same
  `enrichment_enriched.jsonl` is the source. Same risk surface as the
  5.4 carry-forward 114.
- **Optional `GEO_PROXIMITY_THRESHOLD_M` tune (50 → 25)** — would shrink
  the strip-mall false-ambig set but at the cost of missing some real
  same-business dedupes. Not gate-blocking. Carry-forward.
- **Optional same-discovery-domain bypass in reconciler** — would let
  auto candidates skip ambig-check against on-the-water entities (and
  vice versa). Reduces the cross-category false-ambig surface at the
  cost of risking a real cross-list dedupe miss. Carry-forward.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.5 session
(2026-05-16) post-fallback-extension commit `4d41944`. Source data:
`outputs/phase5_5_ambig_audit_data.json` (76 records) +
`outputs/phase5_5_load_real.log` (PowerShell Tee'd output, UTF-16 LE).
Dump script: `outputs/phase5_5_ambig_audit_dump.py`.*
