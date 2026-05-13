# Cursor Brief — Phase 5: Tier 1 data gathering

> **Operator note:** this brief is structurally different from Phase 1-4 briefs. **Phase 5 is operator-driven, multi-week, not a single Cursor dispatch.** The Phase 4 infrastructure (Google Places Layer-1 client + OSM Layer-2 client + cross-layer reconciler + must-not-lose Outbox + Railway scheduled-job runbook) is the runtime; Phase 5 is the operator running scrapes, reviewing the reconciler's ambiguous queue, doing Layer-5 manual recovery, and entering operator-curated fields (heat_exposure, crowd_notes, boat_access, seasonal_hours) for ~390-740 Tier 1 entries.
>
> **Pre-dispatch prereqs:** the 11 operator decisions + 10 external data-source verifications in `outputs/phase5_prereq_checklist.md` should close out before Phase 5 dispatches. Lead-up window: ~1-2 weeks of intermittent operator + Cowork primary time. Brief authored at session-23-extension-3 (2026-05-13) alongside the Phase 4 SHIPPED close-out at `ac94b6c`.
>
> The brief is structured around **per-category playbooks (§3.1-§3.6)** that the operator references one category at a time during the 4-8 week execution period. §4 lists likely tooling-touchup tasks as stubs — each becomes its own small Cursor dispatch prompt when Phase 5 surfaces the need (Phase 5 isn't pre-planning every micro-task; it's responding to what real data surfaces). §5 covers the operator daily/weekly rhythm. §9 recommends a starting sequence.

---

## §0 Baseline + reads + halt etiquette

Before dispatching Phase 5 (or before the first per-category playbook run), confirm + report:

1. **`git log --oneline -10`** — origin/main should top at the Phase 4 close-out chain. Floor: `ac94b6c` (Phase 4.4 close-out) → `2eb2759` → `2f87211` → `997cdc3` → `2ab5f07` → `86eeaf8` → `aaac4db` → `a75cfe8` → `f5b3953` → `91cd37b`.
2. **`git status`** — clean unless mid-operator-session.
3. **`python -m alembic heads`** — single head: `0a1b2c3d4e5f` (Phase 4.1 outbox table). Phase 5 ships **no schema migrations** — Phase 3 + Phase 4 shipped every column Phase 5 fills.
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — floor: **1795 collected** (Phase 4.4 baseline). Phase 5 may add a small number of tooling-touchup tests as §4 items land.
5. **Production deploy status** — `e1f2a3b4c5d6` deployed prod (session-22) vs `0a1b2c3d4e5f` on origin. **Phase 4 redeploy is the operator's first concrete pre-Phase-5 action** per the prereq checklist; the new `outbox` table + `with_retry` wrappers should be live in prod before scrapes start so any real failures land in the Outbox redrive surface.
6. **Read these docs end-to-end before starting:**
   - `outputs/phase5_prereq_checklist.md` (this brief's companion — operator decisions + verifications + workload audit)
   - `docs/maintainability/master_build_plan.md` §4 Phase 5
   - `docs/maintainability/layered_scrape_strategy.md` end-to-end (5-layer pattern; per-layer client modules; reconciliation logic §4; sequencing §5)
   - `docs/maintainability/background_job_infrastructure_decision.md` §6.1 (Railway scheduled jobs)
   - `docs/operations/railway_scheduled_jobs_runbook.md` (Phase 4.4 deliverable; the operator's playbook for cron services)
   - `docs/operations/scrape_logs_template.md` (per-run summary template — operator fills one per scrape run)
   - `docs/maintainability/manual_recovery_checklist.md` (Layer 5 workflow — currently structurally ready but content-empty per prereq §3.4.j; Cowork primary back-fills during lead-up)
   - `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md` (Phase 3 backfill audit; informs ambiguous-row triage during Phase 5)
   - `outputs/chatgpt_taxonomy_research_synthesis.md` (Tier 1 → 2 → 3 ordering + category boundary calls)
7. **Read these source files** so per-category playbooks resolve cleanly:
   - `app/contrib/google_types_mapping.py` (Google `types[]` → `(slug, place_type)` table; ~28 entries; will need expansion per §4 tooling queue)
   - `app/contrib/google_places_scraper.py` (Layer-1 client; `GooglePlacesClient.run_discovery(category=...)` + `run_enrichment(dry_run=...)`)
   - `app/contrib/osm_overpass_client.py` (Layer-2 client; `OsmOverpassClient` + `build_query(tag, value)` Overpass-QL)
   - `app/contrib/ingest_reconciler.py` (`reconcile_hit` + `SOURCE_PRIORITY` + `log_ambiguous_reconcile`; reconciler `action` paths)
   - `scripts/places_load.py` (JSONL → DB pipeline; reconciler hook integration; emits `reconcile_skipped_ambiguous` / `reconcile_merged_geo` counts in return)
   - `scripts/osm_overpass_pull.py` (operator-runnable OSM wrapper; `--tag` + `--value` + `--dry-run` flags)
8. Report all baseline values. **HALT and report** if any baseline value materially mismatches the floor — Phase 5 runs against a moving infrastructure target and the per-category playbooks assume the Phase 4 surface is live.

**Halt etiquette:** Phase 5 is multi-week. There's no "end of Phase 5 sub-phase" boundary like Phase 4. Each per-category run is a natural HALT point — operator commits scrape results + log markdown + field-entry deltas, reviews against §6 risk register, then dispatches the next category (or pauses for field-entry consolidation). The Phase 5 close-out boundary is §8 — when all 6 categories meet the success criterion (15+ entries per default filter on Phase 6 landing).

---

## §1 Why this phase exists

Phase 1-3 built the schema. Phase 4 built the runtime (background jobs + layered-scrape framework + cross-layer reconciler). **Phase 5 fills the schema using the runtime.** It's the first phase that produces user-visible value at scale — the Phase 6 UI being built in parallel renders empty when there's nothing in the database; Phase 5 supplies the data that makes the Phase 6 pages feel like a real directory.

**Texture rule (carried forward from every prior brief):** every existing chat-route response, every Provider profile render, every Tier 2 catalog lookup, every search-bar query, every Photo upload must produce **equivalent output** during and after Phase 5 as before. Phase 5 adds rows to the catalog; it does not change the catalog schema, the API response shape, the UI surface, or any consumer pathway. New rows surface in Phase 6 UI as the data lands; existing rows are unchanged.

**Tier 1 is the resident-critical spine.** Per Opus design + ChatGPT taxonomy synthesis §1: the 6 Tier 1 categories cover the "I need to find a plumber / a restaurant / a marina / a doctor / a gas station / a grocery store" surface area. Making Tier 1 dense first means:
- The directory is immediately useful for residents the moment Phase 6 UI ships
- The Phase 6 category landing pages have enough entries to test ranking + heat-aware bias + sort dropdowns against real data
- Tier 2 (lower-frequency but resident-relevant) and Tier 3 (visitor-only) can fill on a longer arc without blocking V1 launch

**Phase 5 is the longest engineering-phase by elapsed time** — 4-8 weeks of operator work vs Phase 4's one calendar day. But it has the smallest engineering surface — most Phase 5 work is operator-driven (scrape runs, reviews, field entry) with occasional tooling glue (§4) when the data surfaces a real gap.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Layered-scrape strategy | LOCKED per Phase 4 ship + `layered_scrape_strategy.md`. Layer 1 (Google Places) primary for all 6 Tier 1 categories; Layer 2 (OSM) supplemental for on-the-water; Layer 3 (city/state) AZ ROC for home-property; Layer 4 (specialized) NPI for health; Layer 5 (manual recovery) for small-mom-and-pop in every category. | Phase 4 SHIPPED |
| Reconciler `action` paths | LOCKED — `insert` writes via Phase 1D dual-write (session.add); `update` runs reconcile-then-sync + optional merge_fields on Entity; `ambiguous` skips + logs (no admin form in Phase 5). | Phase 4.3 ship |
| `entities.sources` JSON-array migration | DEFERRED — comma-separated string in existing `entity.source` column. Reconciler's `_combine_sources` produces the multi-source string. Revisit V1.5+ if query patterns force it. | Phase 4.3 operator decision-lock |
| `manual_recovery_checklist.md` back-fill | LOCKED as Phase 5 lead-up task per prereq checklist §3.4.j — Cowork primary back-fills before Phase 5 dispatches; ~2-3h work. | Prereq checklist §3.4.j |
| Phase 5 admin form for field entry | NOT IN SCOPE — operator uses direct DB SQL or existing admin/* HTML surfaces. Proper admin form ships in Phase 6 / V1.5. | Master plan §4 Phase 5 + prereq §8 |
| Ambiguous-queue review workflow | LOCKED — direct DB query after each scrape (`SELECT * FROM entities WHERE source LIKE '...' ORDER BY created_at DESC LIMIT 50`); admin form is V1.5+. | Prereq §3.2.f |
| Per-category sequencing | RECOMMENDED per §9 below — eat-drink first (warm-up), on-the-water second (boat_access entry rhythm), home-property-services third (AZ ROC integration test), etc. Operator may reorder if blocked. | §9 below |
| Tier 1 success criterion | LOCKED — "each Tier 1 category renders 15+ entries per default filter on its Phase 6 landing page" per master plan §4 Phase 5 success criteria. Below 15 = Layer 5 manual recovery + re-scrape; below the per-category low-end estimate = potential gap in coverage worth flagging. | Master plan §4 Phase 5 |
| Reconciler `GEO_PROXIMITY_THRESHOLD_M = 50.0` | LOCKED — operator-tunable but defaults stick unless real data surfaces a problem. If first category run produces >50 ambiguous hits in `geo-within-50m-but-name-mismatch`, pause + tune before continuing. | Phase 4.3 ship |
| `SOURCE_PRIORITY` field-merge | LOCKED — operator-typed > google_places > osm > lhc_open_data / az_roc > npi_registry / usapickleball / pdga. Operator-typed entity returns empty merge (no overwrite). | Phase 4.3 ship |

Locks from prereq checklist §3 land here once operator closes them out during lead-up week 2.

---

## §3 Per-category playbooks

Six sub-sections, one per Tier 1 category. Each follows the same shape: **Google Places types[] coverage** + **Supplemental layers** + **Layer 5 manual-recovery prompts** + **Operator-curated field rubric** + **Acceptance gate**. The operator works one category at a time; each takes ~1 week of intermittent operator time.

### §3.1 Eat & Drink (`eat-drink`)

**Target:** 90-140 entries.

**Google Places `types[]` coverage** (per prereq §3.1.c — expand `google_types_mapping.py` before scrape):
- Existing: `restaurant`, `cafe`, `bar`, `bakery`
- Add: `meal_delivery`, `meal_takeaway`, `fast_food`, `dessert_shop`, `wine_bar`, `pub`, `pizza_restaurant`, `seafood_restaurant`, `mexican_restaurant`, `breakfast_restaurant`, `barbecue_restaurant`, `coffee_shop`, `ice_cream_shop`
- All map to `("eat-drink", "commercial")`

**Supplemental layers:**
- Layer 2 OSM: not in scope (Tripadvisor not used; OSM coverage thin for restaurants)
- Layer 3 city: not in scope
- Layer 4 specialized: not in scope
- Layer 5 manual recovery: food trucks, pop-ups, seasonal vendors, dock-and-dine spots that Google doesn't carry

**Discovery + load commands:**
```
python -m scripts.places_discovery --category eat-drink --dry-run  # sanity check
python -m scripts.places_discovery --category eat-drink            # full discovery
python -m scripts.places_enrichment --limit 200                    # enrich the discovered rows
python -m scripts.places_load                                       # load to DB with reconciler
```

**Layer 5 manual-recovery prompts:**
- Lake Havasu food-truck Facebook groups (operator search; landing-page list per `manual_recovery_checklist.md` §3 once back-filled)
- River Scene magazine restaurant features (sample issue scan; cross-reference against Google output)
- Seasonal vendors (winter-only RV-park restaurants; document seasonal_hours)
- Dock-and-dine spots that don't have Google listings (operator boat survey)

**Operator-curated field rubric:**
- `heat_exposure`: outdoor for patio-only / outdoor-seating-prevalent venues; water_adjacent for shoreline restaurants; shaded for covered patios; indoor for the default
- `crowd_notes`: short-form (1 sentence) for typical venues; long-form for top-20 (English Village restaurants, Aquatic Park dock-and-dines, Friday night BBQ spots)
- `boat_access` (where applicable per §3.4 rubric doc): for shoreline restaurants, populate `{"dockable": bool, "ramp_walkable_m": N}`
- `seasonal_hours`: critical for any venue with snowbird-driven schedule shift; the JSON schema is summer/winter/shoulder blocks

**Acceptance gate:**
- 60+ entries in `eat-drink` post-load (low end of 90-140 estimate)
- All ambiguous reconciler hits reviewed via direct DB query
- Top-20 entries have crowd_notes long-form populated
- heat_exposure tagged on every entry (no NULL)
- Phase 6 `/category/eat-drink` smoke renders 15+ entries per default filter

**Expected operator time:** 10-25 hours over 1-2 weeks (~3h scrape + review, ~7-22h field entry depending on long-form crowd_notes coverage).

---

### §3.2 On the Water (`on-the-water`)

**Target:** 40-90 entries.

**Google Places `types[]` coverage:**
- Existing: `marina`, `beach`
- Add: `boat_dealer`, `boat_rental`, `harbor`, `aquarium` (if any local), `swimming_pool` (public only)
- All map to `("on-the-water", "place")` for marinas/beaches OR `("on-the-water", "commercial")` for dealers/rentals — operator decision per entity (boundary not clean)

**Supplemental layers:**
- **Layer 2 OSM** — primary supplemental per prereq §3.2.e: `leisure=marina`, `man_made=pier`, `natural=beach`. Each OSM tag pair gets its own `scripts/osm_overpass_pull.py --tag <tag> --value <value>` run.
- Layer 3 city: Lake Havasu City Parks & Rec facility list (boat ramps, public beaches) — reuse the existing `parks-rec-scrapes.yml` workflow output
- Layer 4 specialized: not in scope
- Layer 5 manual recovery: small kayak launches, unofficial beach access points, primitive ramps

**Discovery + load commands:**
```
python -m scripts.places_discovery --category on-the-water
python -m scripts.places_enrichment
python -m scripts.places_load

python -m scripts.osm_overpass_pull --tag leisure --value marina
python -m scripts.osm_overpass_pull --tag man_made --value pier
python -m scripts.osm_overpass_pull --tag natural --value beach
# OSM load path: TBD — Phase 4.3 shipped osm_overpass_pull but not the load-to-DB script
# Operator may run a small Cursor tooling-touchup (§4) to add scripts/osm_overpass_load.py
# mirroring scripts/places_load.py shape, OR may direct-INSERT via the reconciler from a Python REPL
```

**Layer 5 manual-recovery prompts:**
- BLM/state-land primitive launches not on Google or OSM
- Private-property dock access points the operator can legitimately surface (with owner consent)
- Seasonal water-level spots (cove access points that disappear at low lake)

**Operator-curated field rubric:**
- `heat_exposure`: water_adjacent for everything in this category (it's the defining attribute)
- `crowd_notes`: critical for weekend-busy marinas (parking, fuel-dock wait times); skip for unofficial ramps
- `boat_access`: this is the **dominant operator-curated surface** for Phase 5 + V1 boat-mode UX. Per the rubric doc at `docs/operations/boat_access_rubric.md` (Cowork primary authors during lead-up):
  - Marinas: `{"ramps": N, "slips": N, "fuel": bool, "haul_out": bool, "pump_out": bool, "transient_dock": bool}`
  - Public ramps: `{"trailer_ramp": bool, "kayak_launch": bool, "dock_walk_m": N | null, "parking_spaces": N}`
  - Beaches: `{"trailer_ramp": bool, "kayak_launch": bool, "swimming_marked": bool}`
  - Shoreline commercial (under eat-drink or shopping but cross-listed): `{"dockable": bool, "ramp_walkable_m": N}`
- `seasonal_hours`: most marinas + ramps stay open year-round but with reduced winter hours; document where shift is material
- `is_mobile_service`: NA for this category (places, not commercial)

**Acceptance gate:**
- 25+ entries (low end of 40-90 estimate)
- Every marina has boat_access JSON populated
- All ambiguous reconciler hits between Google + OSM reviewed (high-overlap category — expect 5-15 ambiguous per run)
- Top-10 marinas + ramps have crowd_notes
- Phase 6 `/category/on-the-water` + boat-mode toggle smoke both render ≥15

**Expected operator time:** 15-30 hours over 1-2 weeks (~5h scrape + review including OSM, ~10-25h field entry — boat_access entry is detail-heavy).

---

### §3.3 Home & Property Services (`home-property-services`)

**Target:** 120-220 entries.

**Google Places `types[]` coverage:**
- Existing: `plumber`, `electrician`, `hvac_contractor`, `general_contractor`
- Add: `roofing_contractor`, `painter`, `locksmith`, `moving_company`, `storage`, `landscaper` (if Google supports), `lawn_care_service`, `home_inspection`, `pest_control_service`, `cleaning_service`, `appliance_repair`
- All map to `("home-property-services", "commercial")`

**Supplemental layers:**
- Layer 2 OSM: not in scope (OSM coverage thin for contractors)
- **Layer 3 AZ ROC license cross-reference** — primary supplemental per prereq §4.1 verification. AZ ROC public search returns license + status + classification for any Arizona licensed contractor. Phase 5 cross-references each Google hit's `business_name` against AZ ROC; license-verified entries get `verified=True` + `verified_field="az_roc_license"` populated on Provider row. Unverified entries land but get a flag for V1.5 review.
- Layer 4 specialized: not in scope
- Layer 5 manual recovery: small contractors who work by word-of-mouth, local handymen, RV-park-specific service techs

**Discovery + load commands:**
```
python -m scripts.places_discovery --category home-property-services
python -m scripts.places_enrichment
# AZ ROC cross-reference: TBD — Phase 5 tooling-touchup (§4.b) to add
# scripts/az_roc_verify.py that reads loaded providers + queries AZ ROC + updates verified flag
python -m scripts.places_load
```

**Layer 5 manual-recovery prompts:**
- Lake Havasu Chamber of Commerce member directory
- Nextdoor / Facebook neighborhood groups (operator search for "recommended plumber" / "good electrician" threads)
- RV-park bulletin boards (operator photo + transcribe during routine errands)
- AZ ROC search by ZIP code (cross-reference against Google output to find license-only contractors with no Google presence)

**Operator-curated field rubric:**
- `heat_exposure`: indoor for most office-based contractors; mobile-service is the dominant pattern (see is_mobile_service below)
- `is_mobile_service`: TRUE for the majority of this category (they come to you); FALSE only for showrooms / brick-and-mortar (paint stores, plumbing supply)
- `crowd_notes`: not typically applicable for service contractors
- `verified`: auto-set TRUE if AZ ROC cross-reference matches; operator manually sets for non-Arizona-licensed types (locksmith, moving, cleaning — not ROC-licensed)

**Acceptance gate:**
- 80+ entries (low end of 120-220 estimate)
- AZ ROC cross-reference coverage on every licensed-trade entry (electricians, plumbers, contractors, roofers)
- is_mobile_service populated on every entry
- Phase 6 `/category/home-property-services` smoke renders ≥15

**Expected operator time:** 20-40 hours over 2-3 weeks (~6h scrape + verify + review, ~14-34h field entry — high-volume category but field entry is per-entity simpler than eat-drink).

---

### §3.4 Health, Wellness & Care (`health-wellness-care`)

**Target:** 30-70 entries.

**Google Places `types[]` coverage:**
- Existing: `doctor`, `dentist`, `hospital`, `pharmacy`, `gym`
- Add: `physiotherapist`, `chiropractor`, `optometrist`, `orthodontist`, `pediatrician`, `psychologist`, `dermatologist`, `medical_lab`, `home_health_care_service`
- All map to `("health-wellness-care", "commercial")`
- Note: `veterinary_care` and `pet_store` map to `pets` not health — keep them separate

**Supplemental layers:**
- Layer 2 OSM: not in scope (OSM coverage thin for medical)
- Layer 3 city: not in scope
- **Layer 4 NPI registry** — primary supplemental, already integrated. NPI lookup returns practitioner name + specialty + license + practice address. Phase 5 cross-references each Google hit's `business_name` (which is usually the practice name, not the practitioner name) against NPI registry; matches populate `npi_number` on the entity extension.
- Layer 5 manual recovery: small independent practitioners, mental-health providers who don't advertise on Google, alternative-medicine (acupuncturists, herbalists)

**Discovery + load commands:**
```
python -m scripts.places_discovery --category health-wellness-care
python -m scripts.places_enrichment
# NPI verification: existing app/contrib/npi/ surface — Phase 5 may need a wrapper script
# scripts/npi_verify.py (§4.c) that mirrors az_roc_verify shape
python -m scripts.places_load
```

**Layer 5 manual-recovery prompts:**
- Lake Havasu Regional Medical Center physician directory (cross-reference vs Google + NPI)
- Health-insurance-network provider lookups (operator may share their own coverage's directory)
- Alternative-medicine practitioners (operator manual search; not on NPI)

**Operator-curated field rubric:**
- `heat_exposure`: indoor for everything
- `is_mobile_service`: TRUE for home health care, hospice care, mobile dental; FALSE for the default
- `crowd_notes`: short-form for waiting-room-heavy practices (pediatrics during cold/flu); skip otherwise

**Acceptance gate:**
- 20+ entries (low end of 30-70 estimate)
- NPI cross-reference coverage on every practitioner-led practice
- Mental-health + alternative-medicine coverage via Layer 5 (Google misses many)
- Phase 6 `/category/health-wellness-care` smoke renders ≥15

**Expected operator time:** 8-18 hours over 1-2 weeks (~3h scrape + verify, ~5-15h field entry).

---

### §3.5 Auto, RV & Fuel (`auto-rv-fuel`)

**Target:** 50-100 entries.

**Google Places `types[]` coverage:**
- Existing: `gas_station`, `car_repair`, `car_dealer`
- Add: `car_wash`, `oil_change_service`, `tire_shop`, `auto_parts_store`, `motorcycle_dealer`, `rv_repair`
- Note: `rv_park` stays in `lodging-vacation-rentals` per prereq §3.1.b lock
- All add-ons map to `("auto-rv-fuel", "commercial")`

**Supplemental layers:**
- Layer 2 OSM: not in scope
- Layer 3 city: not in scope
- Layer 4 specialized: not in scope
- Layer 5 manual recovery: mobile-mechanic services that don't advertise on Google, RV-specific shops near major parks

**Discovery + load commands:**
```
python -m scripts.places_discovery --category auto-rv-fuel
python -m scripts.places_enrichment
python -m scripts.places_load
```

**Layer 5 manual-recovery prompts:**
- RV-park resident referrals (operator asks at front desk during routine errands)
- Mobile-mechanic Craigslist + Facebook Marketplace (operator harvest)
- Boat-trailer-specific repair (overlap with on-the-water; cross-list)

**Operator-curated field rubric:**
- `heat_exposure`: indoor for repair shops + parts stores; outdoor for gas-station-pumps-only entries; mixed for the default
- `is_mobile_service`: TRUE for mobile mechanics, mobile RV-tech, on-call tow; FALSE for the default
- `crowd_notes`: skip for the default; long-form only for high-volume gas stations (peak-hour wait times) or seasonal RV-tech surge

**Acceptance gate:**
- 30+ entries (low end of 50-100 estimate)
- is_mobile_service populated on every entry
- RV-specific coverage via Layer 5
- Phase 6 `/category/auto-rv-fuel` smoke renders ≥15

**Expected operator time:** 8-18 hours over 1-2 weeks.

---

### §3.6 Shopping, Grocery & Essentials (`shopping-essentials`)

**Target:** 60-120 entries.

**Google Places `types[]` coverage:**
- Existing: `store`, `supermarket`, `grocery_or_supermarket`
- Add: `clothing_store`, `electronics_store`, `hardware_store`, `convenience_store`, `furniture_store`, `home_goods_store`, `liquor_store`, `book_store`, `florist`, `jewelry_store`
- All map to `("shopping-essentials", "commercial")`

**Supplemental layers:**
- Layer 2 OSM: not in scope
- Layer 3 city: Lake Havasu business-license search if the verification in prereq §4.3 surfaces a viable endpoint; otherwise skip
- Layer 4 specialized: not in scope
- Layer 5 manual recovery: small local boutiques, Saturday-market vendors with permanent storefronts elsewhere, consignment shops

**Discovery + load commands:**
```
python -m scripts.places_discovery --category shopping-essentials
python -m scripts.places_enrichment
python -m scripts.places_load
```

**Layer 5 manual-recovery prompts:**
- Downtown / Main Street walking survey (operator photo-tour + transcribe)
- Lake Havasu City annual Visitor Guide (commercial annual; operator scan for non-Google retail)
- McCulloch corridor strip-mall directories (operator drive-by spot)

**Operator-curated field rubric:**
- `heat_exposure`: indoor for everything (default)
- `is_mobile_service`: NA for this category
- `crowd_notes`: skip for the default; long-form for top-5 high-traffic (Walmart, Home Depot, the main grocery anchor)
- `seasonal_hours`: applicable for any winter-visitor-heavy boutique (operator judgment)

**Acceptance gate:**
- 40+ entries (low end of 60-120 estimate)
- Independent boutique coverage via Layer 5 (Google misses many)
- Phase 6 `/category/shopping-essentials` smoke renders ≥15

**Expected operator time:** 10-22 hours over 1-2 weeks.

---

## §4 Tooling-touchup queue

Phase 5 surfaces real-data needs that the Phase 4 infrastructure doesn't fully cover. Each becomes its own small Cursor dispatch when the need arises. These are **stubs** — not pre-positioned dispatch prompts — because their exact shape depends on what Phase 5 surfaces.

**a. Google `types[]` mapping expansions.** Per §3.1-§3.6 above, each category needs ~5-13 new entries added to `google_types_mapping.py`. These can all land in one dispatch prompt (~50 line Cursor session) authored during prereq lead-up week 2. Estimated effort: 1-2 hours.

**b. AZ ROC license cross-reference script.** New `scripts/az_roc_verify.py` reads loaded `home-property-services` providers + queries AZ ROC public search + updates `Provider.verified` + `Provider.verified_field='az_roc_license'`. Authored after prereq §4.1 verification confirms the endpoint shape. Estimated effort: 4-6 hours (Cursor dispatch, single session).

**c. NPI cross-reference wrapper.** New `scripts/npi_verify.py` mirrors `az_roc_verify` shape, but reads loaded `health-wellness-care` entries + uses the existing `app/contrib/npi/` surface. Operator may also direct-call the existing surface from a Python REPL for spot checks. Estimated effort: 2-4 hours.

**d. OSM JSONL → DB load path.** Phase 4.3 shipped `scripts/osm_overpass_pull.py` but no OSM-specific load script (Layer 1 has `places_load.py`; Layer 2 doesn't have an equivalent). For Phase 5's on-the-water category, operator either (i) authors `scripts/osm_overpass_load.py` mirroring `places_load.py` shape via a small Cursor dispatch, OR (ii) hand-loads via Python REPL using `reconcile_hit` + `session.add` direct. Estimated effort: 3-5 hours for the script path.

**e. Ambiguous-queue grep helper.** Lightweight one-line shell helper for `places_load` log output: `grep "ambiguous" docs/scrape_logs/*.md | wc -l` or similar. Not really a Cursor task — operator authors as a shell alias. Estimated effort: 15 minutes.

**f. Phase 6 admin form for operator-curated field entry.** OUT OF SCOPE for Phase 5 (admin form is Phase 6 deliverable). If Phase 5 surfaces that direct-DB entry is too slow + Phase 6 hasn't shipped the admin form yet, operator + Cowork primary triage whether to (i) accept the per-entity time hit, (ii) author a minimal Phase 5 admin-form shim, OR (iii) shift category sequencing to wait for Phase 6's form. Estimated effort if option (ii) ships: 8-12 hours.

**g. Reconciler GEO_PROXIMITY_THRESHOLD_M tuning.** If first per-category scrape produces >50 ambiguous "geo-within-50m + name-mismatch" hits, operator tunes the constant. Currently 50m at `app/contrib/ingest_reconciler.py:1020`. Phase 5 may need to drop to 30m for dense commercial corridors (Eat & Drink English Village cluster) or expand to 100m for sparse rural (BLM-land ramps). Estimated effort: 30 min Cursor dispatch.

**Each tooling task authored as needed during Phase 5 execution.** No pre-positioned dispatch prompts — Phase 5's tooling shape is reactive to real-data surface, not pre-planned.

---

## §5 Operator daily/weekly rhythm

Phase 5 burns out operators if structured poorly. Suggested rhythm:

**Daily session cap:** ~2 hours max of field entry + ~30 min of scrape-run watching. More than that produces error-prone field entries.

**Weekly cadence:**
- **Day 1:** Scrape run (~30 min including review) + log markdown to `docs/scrape_logs/<source>_<YYYY-MM-DD>.md` per `docs/operations/scrape_logs_template.md`
- **Day 2:** Ambiguous-queue triage via direct DB query (~30-60 min depending on volume)
- **Day 3-5:** Operator-curated field entry sessions (~1.5h each, 3 sessions/week = ~5h/week)
- **Day 6:** Layer 5 manual-recovery hour (~1h)
- **Day 7:** QA spot-check pass (~1h) — operator picks 20 random entries from the week's loads and validates against the operator-curated field rubrics

Total: **~7-9 hours operator time per week**, distributed across 6 days. Sustainable for 4-8 weeks. If operator hits a streak where one category fills faster than expected, the next week shifts focus to the next category in sequence.

**Reward landmarks:**
- Every 50 entries field-entered: ✓ (small celebration; operator chooses)
- Every category acceptance gate met: ✓ (close-out commit + push to origin; STATE.md refresh)
- All 6 categories closed: ✓ (Phase 5 SHIPPED commit; master plan ledger update)

---

## §6 Risk register

12 entries carrying forward from prereq checklist §6 with Phase-5-execution-specific refinements:

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | Layer-5 manual recovery volume exceeds 40 items/category | M | H | Triage against 15+-per-default-filter success criterion; defer non-essential to V1.5 |
| 2 | Operator-curated entry exceeds 15 min average | M | H | Pre-locked rubrics (§3 above); defer long-form `crowd_notes` to top-N venues |
| 3 | Reconciler ambiguous queue >50 hits | L | M | First per-category run is smoke test; tune `GEO_PROXIMITY_THRESHOLD_M` if needed (§4.g) |
| 4 | Google Places API spend exceeds budget | L | M | Spend cap pre-set in Google Console; per-category dry-runs first |
| 5 | OSM Overpass rate-limited | L | L | `OSM_OVERPASS_LIMITER` at qps=0.5 conservative; comfortable under public throttles |
| 6 | `heat_exposure` priority-30 list unauthored | M | M | Per prereq §3.3.g; operator brainstorm during lead-up |
| 7 | AZ ROC public access changes / blocks Layer 3 | L | H | Verify in prereq §4.1; fallback to Layer 5 manual recovery for home-property |
| 8 | LHC business-license endpoint doesn't exist | M | M | Document gap (prereq §4.3); fall back to Layer 5 |
| 9 | Operator burns out on field-entry monotony | M | H | §5 daily cap + reward landmarks; alternate scrape-days with entry-days |
| 10 | Phase 6 UI hungry for entries before Phase 5 finishes | M | M | Sequence so high-traffic first (eat-drink, on-the-water); Phase 6 renders early-stage with empty-state copy |
| 11 | Reconciler false-positive merge | L | H | Conservative by default (geo+name required for auto-merge); operator reviews merge log after each run |
| 12 | Phase 5 elapsed time exceeds 8 weeks | M | M | If at week 6 only 3 categories closed, scope down — defer auto-rv-fuel + shopping-essentials to V1.5 polish; Phase 6 launches with 4 categories not 6 |

---

## §7 What NOT to do

Phase 5 design rails — carry-forward from prereq §8 + brief-shape precedent:

1. **No new schema migrations.** Phase 3 + Phase 4 shipped every column. If Phase 5 surfaces a real missing column (e.g., `boat_access` JSON shape needs sub-keys not in Phase 3.1), defer to a Phase 5-late or V1.5 migration — don't pile schema work onto a data-gathering phase.
2. **No admin form surfaces.** Operator uses direct DB SQL or existing admin/* HTML. Admin form is Phase 6 / V1.5.
3. **No `entities.sources` JSON-array migration.** Comma-separated string in `entity.source` suffices for V1 per Phase 4.3 lock.
4. **No re-scrape automation beyond Phase 4.4's runbook.** Operator manually runs scrapes per category per the playbooks above. Railway scheduled-job services per the runbook are operator-configured if cadence becomes clear.
5. **No data-quality dashboards.** Operator's daily QA spot-check is the QA pass.
6. **No Phase 6 UI work.** Phase 5 and Phase 6 are scope-disjoint. Phase 5 fills; Phase 6 renders.
7. **No `auto_close` retry-storm prevention beyond Phase 4.1's `with_retry`.** If real failures surface, defer tuning to Phase 4.5 follow-up commit.
8. **No multi-operator parallel work.** Phase 5 is single-operator-driven. Coordination overhead with multiple operators exceeds the time savings at this scale.
9. **No deprecation of Layer-1 scripts.** `scripts/places_discovery.py` + `scripts/places_enrichment.py` stay as Phase 5 entry points; they're the JSONL → DB pipeline.
10. **No premature Tier 2/Tier 3 dispatch.** Phase 5 is Tier 1 only. Tier 2 dispatches as Phase 5-late or V1.5 once Tier 1 acceptance gates all pass.

---

## §8 Close-out criteria

Phase 5 SHIPS when **all 6 Tier 1 categories meet their acceptance gates** (§3.1.acceptance + §3.2.acceptance + §3.3.acceptance + §3.4.acceptance + §3.5.acceptance + §3.6.acceptance simultaneously). At that point:

1. Operator commits final per-category scrape logs to `docs/scrape_logs/`
2. Operator authors final Phase 5 close-out narrative (~1 page) at `outputs/phase5_close_out_narrative.md`
3. Cowork primary updates master plan §4 Phase 5 with SHIPPED 2026-XX-XX header
4. Cowork primary updates STATE.md Production block + Recently shipped §1 with Phase 5 ship-line
5. Operator pushes to origin
6. **Phase 5 is COMPLETE.** Phase 6 UI build continues in parallel; Tier 2 data gathering becomes the next dispatchable major data lane (or V1.5 post-launch).

If Phase 5 hits the 8-week elapsed time ceiling without all 6 categories closing, **partial close-out is acceptable**: close the categories that meet acceptance + flag the remaining as deferred-to-V1.5. Phase 6 UI launches against whatever Tier 1 is closed; missing categories show empty-state with "more coming soon" copy.

---

## §9 Recommended starting sequence

Operator may reorder if blocked on prereqs for a specific category. Recommended order:

1. **Eat & Drink (§3.1) — warm-up.** Highest-volume category, single-layer scrape (Google only), no Layer 3/4 cross-references. Operator gets the rhythm. ~Week 1-2.
2. **On the Water (§3.2) — boat_access rhythm.** Forces the operator into the boat_access JSON-shape rubric early so V1 boat-mode UX (Phase 6) feels real. Multi-layer (Google + OSM). ~Week 2-3.
3. **Home & Property Services (§3.3) — AZ ROC integration test.** Highest-volume category by entry count. Layer 3 AZ ROC cross-reference is the new tooling surface. ~Week 3-5.
4. **Health, Wellness & Care (§3.4) — NPI integration test.** Layer 4 NPI cross-reference reuses existing surface. ~Week 4-5.
5. **Auto, RV & Fuel (§3.5) — operator-mobile-service category.** Single-layer + Layer 5. ~Week 5-6.
6. **Shopping, Grocery & Essentials (§3.6) — straight-Google category.** Single-layer + Layer 5. Lowest-priority for Phase 6 UI. ~Week 6-7.

**Buffer:** ~1 week of slack at the end for QA + Layer 5 cleanup + Phase 5 close-out narrative authoring.

If at week 4 only eat-drink + on-the-water are closed: operator + Cowork primary triage whether to scope down (defer 2-3 categories to V1.5) or extend Phase 5 by 1-2 weeks. The 8-week ceiling is soft.

---

## §10 First operator action

1. **Read this brief end-to-end** alongside `outputs/phase5_prereq_checklist.md` — both authored at session-23-extension-3 (2026-05-13).
2. **Lead-up week 1:** chip through prereq checklist §4 external verifications (~3-4h).
3. **Lead-up week 2:** lock prereq checklist §3 operator decisions (~2h); Cowork primary back-fills `manual_recovery_checklist.md` (~2-3h) + authors `docs/operations/boat_access_rubric.md` (~1h).
4. **Lead-up close:** Cowork primary fills in §2 of this brief with the locked decisions.
5. **Tooling-touchup pre-flight (§4.a):** small Cursor dispatch to expand `google_types_mapping.py` with the per-category `types[]` additions from §3.1-§3.6 (~30 min).
6. **Railway redeploy** (if not already done from Phase 4 close-out operator action 1) — Phase 4.1 outbox migration + Phase 4.2-4.4 wrappers should be in prod before Phase 5 first scrape.
7. **Dispatch §3.1 Eat & Drink** as the warm-up category. Run discovery + enrichment + load + ambiguous-queue review + field-entry sessions per the §5 daily/weekly rhythm.

Phase 5 begins.

---

*Authored at session-23-extension-3 (2026-05-13) after Phase 4 SHIPPED on origin at `ac94b6c`. The Phase 4 infrastructure (Outbox + retry-wrapper + layered-scrape framework + cross-layer reconciler + Railway scheduled-jobs runbook) is the runtime for Phase 5's operator-driven data gathering. Lead-up window: ~1-2 weeks before first scrape; execution window: 4-8 weeks. Phase 5 SHIPS when all 6 Tier 1 categories meet their acceptance gates.*
