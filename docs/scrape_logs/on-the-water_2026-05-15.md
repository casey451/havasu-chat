# Scrape log — `on-the-water` — 2026-05-15

Per `docs/operations/scrape_logs_template.md`. First per-category scrape run
for Phase 5.2 (second sub-phase of the Phase 5 restructure, post-5.1 SHIPPED
2026-05-15 at `273fe61`). Layer 1 (Google) + Layer 2 (OSM) data plane both
complete; field-entry (Tasks #6/#7) and Layer 5 (Task #8) remain.

---

## §0 Pre-flight (closed)

| Check | Result |
|---|---|
| `git log -1 --oneline` | `bee73f8` (origin pre-load top) |
| `python -m alembic current` | `0a1b2c3d4e5f (head)` ✅ |
| `python -m pytest --collect-only \| tail -3` | 1855 collected ✅ |
| OSM tooling chain end-to-end | Functional after `2ef4b3b` (JSONL writer) + `155a41a` (UA + diagnostics) |

Five commits chained on top of `273fe61` during this scrape:

| Commit | Contents |
|---|---|
| `2ef4b3b` | `fix(scripts)` — OSM pull writes JSONL (Task #10) |
| `155a41a` | `fix(osm)` — descriptive UA + visible diagnostics (Task #11). Root cause: Overpass returned 406 for default `python-httpx/X.Y.Z` UA |
| `bee73f8` | `chore(outputs)` — OSM yield recalibration + extended test dispatch |
| `efd193a` | `fix(scripts)` — places_load sets Provider.category_id + Phase 5.1 backfill (Tasks #13 + #14). **Retroactively closed Phase 5.1 gate item 5** — `/category/eat-drink` rendered 0 entities at HEAD pre-fix; 255 post-fix |
| `8800761` | `fix(scripts)` — widen on-the-water mapping (types-map +fishing_pier/+ferry_service + apply_on_the_water_promote_unmapped). 4 → 72 entities at `/category/on-the-water` post-promote (Task #15) |

**Phase 5.1 retroactive correction note** — diagnostic
(`outputs/diagnose_category_id_gap.py`) surfaced that
`scripts/places_load.py` never set `Provider.category_id`, so the dual-write
hook never created `EntityCategory` rows and `/category/<slug>` rendered 0
entities for all newly-loaded rows. Phase 5.1 acceptance gate item 5
("Phase 6 `/category/eat-drink` renders 15+") was retroactively false at
the SHIPPED ledger entry. `efd193a` shipped both the load fix and a
backfill apply-script (`outputs/apply_provider_category_id_backfill.py`)
that linked the existing 287 5.1 food_drink Providers. Post-fix
`/category/eat-drink` renders 255 (matches close-out projection).
**Coordinate with Phase 6 agent + master plan** — `master_build_plan.md
§Phase 5.1` SHIPPED line + `STATE.md` Recently-shipped block need a
"retro corrected at `efd193a`" note. Out of this chat's scope.

---

## §1 Layer 1 — Google Places

### Discovery (real, full sweep)

```
python -m scripts.places_discovery --category on-the-water
```

| Field | Value |
|---|---|
| Mode | full |
| Categories run | 24 (`lake_recreation` discovery domain) |
| Requests | 46 |
| Unique places | 289 |
| Cost (actual) | ~$1.50 |
| Run time | <2 min |

Per-label breakdown (last run): boat rentals 37, houseboat 0, jet ski 12,
kayak 5, paddleboard 4, pontoon 3, boat tours 8, fishing charters 1,
fishing guides 2, bait/tackle 6, marinas 1, boat dealers 46, boat repair
30, boat storage 49, boat detailing 20, watersports 1, parasailing 3,
ATV 2, off-road tours 1, RV parks 20, RV rentals 3, RV dealers 15,
RV repair 12, campgrounds 8.

### Enrichment

```
python -m scripts.places_enrichment --limit 200
```

| Field | Value |
|---|---|
| Resume-skips | 198 (cache had ~280 prior `lake_recreation` rows + Phase 5.1 backfill) |
| New enrichments | 2 |
| 404 errors | 0 |
| Other errors | 0 |
| Cache size after | 2551 enriched rows |
| Cost (actual) | ~$0.04 |

### Load

```
# dry-run
python -m scripts.places_load --category on-the-water --dry-run
# real
python -m scripts.places_load --category on-the-water
```

| Field | Value |
|---|---|
| Enriched rows in cache | 2551 |
| After `--category on-the-water` filter | 291 |
| After ZIP filter | 253 kept, 38 dropped |
| Dropped ZIP top reasons | 14 × 85344 (Salome AZ), 6 × 92363 (Needles CA), 16 various surrounding |
| `inserted` | 224 |
| `updated` | 0 |
| `reconcile_skipped_ambiguous` | 29 (geo within 50m + name differs — mostly storage/dealer rows colliding intra-category) |
| `reconcile_merged_geo` | 0 |
| `category_id_set` | 166 (post-fix `efd193a`) |
| `category_id_unmapped` | 87 (operator queue — 71 inserted + 16 ambiguous-skipped) |
| `EntityCategory` inserts | 153 |

### Promote unmapped (apply-script post-`8800761`)

```
python outputs/apply_on_the_water_promote_unmapped.py
```

| Field | Value |
|---|---|
| Candidates (lake_recreation + category_id=NULL today) | 71 |
| Promoted to on-the-water | 68 |
| Excluded (real_estate_agency / bridge / transportation_service) | 3 |
| EntityCategory inserts | 68 |

Promote breakdown: 48 `service` (boat repair/storage/detailing), 10 `<none>`,
5 `tour_agency` (boat tours, fishing charters), 1 each of `tourist_attraction`,
`ferry_service`, `tourist_information_center`, `point_of_interest`,
`fishing_pier`. Plus the 4 originals (`marina` primary_type) = 72 entities at
`/category/on-the-water` post-Layer-1.

### Tier-1 distribution from this load

| Slug | Count | Notes |
|---|---|---|
| on-the-water | 72 | 4 marinas + 68 promoted |
| home-property-services | 46 | boat storage/repair → `storage` Google type |
| auto-rv-fuel | 41 | RV dealers/repair + boat dealers tagged `car_dealer` ⚠️ |
| shopping-essentials | 35 | bait & tackle (`store` type), possibly more boat dealers |
| lodging-vacation-rentals | 23 | RV parks |
| outdoors-parks-trails | 4 | parks |
| **5.2 inserts total** | **221 routed + 3 excluded = 224** | matches load summary |

⚠️ **Open follow-on (Task #5 data-quality audit)** — ~30-40 boat dealers
landed in `auto-rv-fuel` because Google tags them `car_dealer`. Conceptually
they belong on-the-water (lake economy). Audit pass examines
auto-rv-fuel + shopping-essentials rows and decides re-route. Not blocking
gate item 1 (already CLEARED at 73 after Layer 2).

---

## §2 Layer 2 — OSM Overpass

### Pulls

| Tag pair | Status | Total in bbox | **Named** | Names |
|---|---|---|---|---|
| `leisure=marina` | RUN | 6 | **2** | Lake Havasu Marina (way 227901073), Havasu Cove (way 622179700) |
| `man_made=pier` | RUN | 114 | **0** | (all unnamed shoreline polygon segments) |
| `natural=beach` | RUN | 11 | **0** | (all unnamed shoreline polygons) |

Yield matches `outputs/phase5_2_osm_yield_recalibration.md` §1 prediction
exactly. Pier and beach pulls produced 0-element JSONLs as expected.

### Loads

| Tag pair | `payloads_ready` | `inserted` | `updated` | `ambiguous` | `merged_geo` |
|---|---|---|---|---|---|
| `leisure=marina` | 2 | 1 | 0 | 1 | 0 |
| `man_made=pier` | 0 | 0 | 0 | 0 | 0 |
| `natural=beach` | 0 | 0 | 0 | 0 | 0 |

The 1 marina inserted is **Havasu Cove** (no Google entity by that name).
The 1 ambiguous is **Lake Havasu Marina** — name slug matched the existing
Google entity but coords were >50m apart (OSM way's first-geometry-node
vs Google's centroid pin). Reconciler correctly skipped insert per the
`1560bd2` priority rule.

**Known latent issue (not blocking 5.2):**
`OsmOverpassClient._element_to_raw_hit` doesn't fall back to
`el["geometry"][0]` for way elements (only handles `el["lat"]/["lon"]` for
nodes and `el["center"]` for queries using `out center;`). Affects only
`client.run()` consumers — the load reads raw JSONL directly via
`_element_lat_lng` which DOES handle geometry. Cosmetic in the pull's
print (showed `(None, None)` for ways); deferred fix queued.

---

## §3 Ambiguous-queue triage (gate item 3)

Per the runbook §2 / brief §3.2.f locked SQL.

| Hit | Action |
|---|---|
| Lake Havasu Marina (OSM way 227901073) vs Lake Havasu Marina (Google) at 1100 McCulloch Blvd N | **Reviewed — no action.** Same physical marina; Google entity is canonical with full enrichment; OSM duplicate correctly skipped per `1560bd2` priority. |

Recalibration doc §3 prediction (~0 actionable hits) confirmed.
**Gate item 3 satisfied.**

---

## §4 Layer 5 manual recovery (Task #8 — operator field-trip)

Deferred. Plan: `manual_recovery_checklist.md` §7 highest-value sweep —
Lake Havasu State Park, Cattail Cove, Site Six, Castle Rock beaches,
Pittsburgh Point. Looking for BLM/state-land primitive launches,
private-property dock access (with consent), seasonal water-level spots,
small kayak launches.

---

## §5 Data-quality audit (Task #5 — next up)

Reuse `outputs/phase5_1_eat_drink_data_quality_audit.md` shape. Audit
the 73 on-the-water entities for non-on-the-water leak; examine the
`auto-rv-fuel` + `shopping-essentials` boat-dealer follow-on. Outputs:
`outputs/phase5_2_on_the_water_data_quality_audit.md` + apply-script for
any cleanup.

---

## §6 Acceptance gate (locked, runbook §6)

| # | Gate item | Status |
|---|---|---|
| 1 | 25+ entries in `on-the-water` post-load | ✅ **73** |
| 2 | Every marina has `boat_access` JSON populated | ⏳ Task #6 |
| 3 | All Google ↔ OSM ambiguous reconciler hits reviewed | ✅ 1 reviewed, no action |
| 4 | Top-10 marinas + ramps have `crowd_notes` | ⏳ Task #7 |
| 5 | `heat_exposure` set on every entry | ⏳ Task #7 |
| 6 | Phase 6 `/category/on-the-water` + boat-mode toggle render ≥15 | ✅ Page: 73; boat-mode pending Task #6 + Phase 6.4 |

**3 of 6 gate items closed.** Remaining (boat_access, crowd_notes,
heat_exposure) are all operator-curated field-entry work.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.2 session
(2026-05-15). Updated as scrape steps completed. Next session picks up
at Task #5 (data-quality audit).*
