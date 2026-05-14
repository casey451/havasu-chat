# Phase 5 Operator Prereq Checklist — Tier 1 Data Gathering

> Pre-positioned at session-23-extension-3 alongside the Phase 4.4 close-out + Phase 4 SHIPPED ledger entry. Phase 5 dispatches once the operator has chipped through these prereqs and has the Tier 1 data-source landscape locked. Use this doc to chip away at decisions + external verifications during the lead-up period (~1-2 weeks of intermittent operator time) so Phase 5's first dispatch isn't blocked at the boundary.
>
> Authored after the failed sub-agent doc write at session-23-extension; this version recovers the agent's 7 surprises + grounds them in the now-shipped Phase 4 surface (commits `91cd37b` → `ac94b6c`). The agent's findings stay valuable; the file just needed to land on Windows-authoritative disk, which earlier writes didn't.

## §1 What Phase 5 is

Per master plan §4 Phase 5: **Tier 1 data gathering — populate the 6 Tier 1 categories using the layered-scrape infrastructure shipped in Phase 4.** Home & Property Services + Health, Wellness & Care + Eat & Drink + On the Water + Auto, RV & Fuel + Shopping, Grocery & Essentials. These are the **resident-critical spine**: making them dense first means the site is immediately useful for residents the moment Phase 6 UI ships. Phase 5 runs in parallel with Phase 6 UI build over 4-8 weeks; both depend on Phase 1-4 infrastructure but neither blocks the other (Phase 6 builds against schema; Phase 5 fills against schema).

Phase 5 is **operator-driven**, not engineering-driven. The infrastructure exists (Phase 4 shipped: Google Places Layer-1 client + OSM Layer-2 client + cross-layer reconciler + must-not-lose Outbox + Railway scheduled-job runbook); Phase 5 is the operator running the scrapes, reviewing the reconciler's "ambiguous" queue, doing Layer-5 manual recovery for the small-mom-and-pop venues that Layer-1-4 miss, and entering the operator-curated fields (heat_exposure, crowd_notes, boat_access details, seasonal_hours) for each entity at ~5-15 minutes per row.

## §2 Tier 1 categories — the scope

Per master plan §4 Phase 5 + ChatGPT taxonomy synthesis §1 Tier 1 order:

| Category slug | Master-plan estimate | Source layers expected | Sensitivities |
|---|---|---|---|
| `home-property-services` | 120-220 entries | Google Places (primary) + AZ ROC license cross-reference (Layer 3) + Layer 5 (small contractors) | License verification is the differentiator — operator must lock the AZ ROC cross-reference workflow before scraping starts |
| `health-wellness-care` | 30-70 entries | Google Places + NPI registry (Layer 4; already integrated) | Practitioner-vs-clinic deduplication is non-trivial; reconciler may surface many "ambiguous" hits |
| `eat-drink` | 90-140 entries | Google Places (primary) — no Layer 3/4 sources in scope (Tripadvisor not used) | Highest-volume category; heat_exposure + crowd_notes operator entry is the bottleneck |
| `on-the-water` | 40-90 entries | Google Places + OSM Layer-2 (marinas + ramps + beaches) | boat_access detail entry is V1.5-critical; Phase 5 must populate enough to make the boat-mode toggle (Phase 6) feel real |
| `auto-rv-fuel` | 50-100 entries | Google Places (primary) | RV-park vs lodging-vacation-rentals boundary is operator decision (see §3.1.b) |
| `shopping-essentials` | 60-120 entries | Google Places (primary) | Independent / locally-owned shops may need Layer 5 supplementation |

**Total Tier 1 target: 390-740 entries.** Master plan success criterion: "each Tier 1 category renders 15+ entries per default filter on its Phase 6 landing page."

## §3 Operator decisions to lock BEFORE Phase 5 dispatches

### §3.1 — Open Phase-3-carry-forward decisions (3 items)

These were named in the Phase 3 category-backfill audit memo but never explicitly locked before Phase 5; surface them now or accept Phase 5 will hit them as ambiguous reconciler outputs.

**a. `beauty_personal_care` final home.** Per audit memo §4 Q3 — V1.5 deferred per session-19 lock per current memo, but Phase 5's Eat-Drink-adjacent salon scrapes will pull these via Google `types[]` like `hair_salon` / `beauty_salon` / `nail_salon`. Decision: ship these into `eat-drink`? Into `shopping-essentials`? Into V1.5 NULL queue and skip in Phase 5? **Recommendation: skip in Phase 5** (V1.5 has time to settle); requires `google_types_mapping.py` patch to add `hair_salon` / `beauty_salon` / `nail_salon` → `(None, None)` so they don't surface as `(eat-drink, commercial)` accidentally.

**b. RV-park vs lodging-vacation-rentals boundary.** ChatGPT taxonomy synthesis §1 says broaden Auto/Gas to `auto-rv-fuel` to include RV needs (gas, repair, dump stations). But Google's `rv_park` type currently maps to `lodging-vacation-rentals` in `google_types_mapping.py:763` (`"rv_park": ("lodging-vacation-rentals", "commercial")`). Decision: does an RV park appear under `auto-rv-fuel` (gas + repair + RV access bundle for travelers) OR `lodging-vacation-rentals` (where you stay overnight)? **Recommendation: lodging-vacation-rentals** (where-you-stay is the dominant resident-question framing); leave existing mapping as-is.

**c. Eat & Drink Google `types[]` coverage list.** `google_types_mapping.py` currently has ~28 entries; the Eat & Drink set is `restaurant`, `cafe`, `bar`, `bakery` (4 entries). Google's full `types[]` includes `meal_delivery`, `meal_takeaway`, `fast_food`, `dessert_shop`, `wine_bar`, `pub`, `pizza_restaurant`, `seafood_restaurant`, etc. Decision: expand the mapping to cover the full Eat & Drink type space, or let Phase 5 fill gaps as the operator-review queue surfaces them? **Recommendation: expand pre-dispatch** — operator queue cleanup is cheap if done before scrapes vs expensive if 200 ambiguous rows pile up. Estimated patch: ~15-20 new entries in `google_types_mapping.py`, ~30 min of operator+Cursor work.

### §3.2 — Layered-scrape sequencing decisions (3 items)

**d. Discovery-then-enrich vs interleaved.** Phase 4.2's scripts/places_discovery + scripts/places_enrichment shipped as a two-pass pipeline (discover all categories → write JSONL → enrich all rows → write enriched JSONL → load via places_load). Decision: run all 6 categories through discovery first (one batch), then enrich all 6 (one batch), then load all 6 (one batch)? Or sequence per-category (discover eat-drink → enrich eat-drink → load eat-drink → next category)? **Recommendation: per-category** (smaller blast radius; operator can review one category's reconciler output before scaling).

**e. OSM coverage per category.** Phase 4.3's OsmOverpassClient currently ships `leisure=dog_park` as the single-category proof. Phase 5 needs to decide which Tier 1 categories get OSM coverage. Strategy memo §3.2 recommends OSM for `on-the-water` (marinas / ramps / beaches via `leisure=marina`, `man_made=pier`, `natural=beach`) + parks-adjacent rows in `outdoors-parks-trails`. Decision: which OSM `(tag, value)` pairs to scrape for Phase 5? **Recommendation: ship `leisure=marina` + `man_made=pier` + `natural=beach` for on-the-water (Tier 1 category 4); defer the rest to V1.5 or as-surfaces.**

**f. Reconciler `ambiguous` queue triage workflow.** Phase 4.3's reconciler emits `action="ambiguous"` when geo-proximity + name match conflict OR name-only match with no geo (operator-review queue surface). The admin form for reviewing this queue ships in Phase 6 / V1.5, NOT Phase 5. Decision: how does the operator triage these during Phase 5 — read `places_load` log output line-by-line, query the DB directly, or wait for the admin form? **Recommendation: direct DB query** — operator runs `SELECT * FROM entities WHERE source LIKE 'google_places,osm%' ORDER BY created_at DESC LIMIT 50` after each scrape; the `log_ambiguous_reconcile` calls already structure the log lines so a quick grep + manual review is workable for ~20-40 ambiguous hits per category.

### §3.3 — Operator-curated field-entry rubrics (3 items)

These are the rubrics the operator follows when entering the operator-curated fields (Phase 3.1 shipped the columns; Phase 5 fills them).

**g. `heat_exposure` rubric.** Per Phase 3.1 schema: `enum (indoor / shaded / outdoor / water_adjacent)`. Phase 8 alert venue-context mapping depends on the operator tagging ~30 entities with non-default heat_exposure (master plan §7 risk row 10). Decision: which entities get explicit tagging vs default-to-`indoor`? **Recommendation: tag the obvious priority-30 list during Phase 5** (parks, marinas, restaurants with patios, public-civic outdoor venues, dog parks); the master plan calls this "Opus hidden dependency" but the list itself isn't authored anywhere — operator should brainstorm before scrapes start, ~30 min of work.

**h. `crowd_notes` rubric.** Per Phase 3.1 schema: `JSON, operator-curated text per venue`. The Opus design §5 example was "English Village fills up after 5pm Fri-Sun — parking lots near the bridge get tight by 6". Decision: short-form (1-sentence per venue) or long-form (multi-paragraph for high-traffic venues)? **Recommendation: short-form by default**, long-form only for the top-20 highest-volume venues (Aquatic Park, English Village restaurants, Lake Havasu State Park) where the texture pays off.

**i. `boat_access` shape per entity-type.** Per Phase 3.1 schema: `JSON, shape varies per venue type`. For marinas: `{"ramps": N, "slips": N, "fuel": bool, "haul_out": bool}`. For shoreline restaurants: `{"dockable": bool, "ramp_walkable_m": N}`. For beaches: `{"trailer_ramp": bool, "kayak_launch": bool}`. Decision: lock the per-type JSON shape before operator entry starts so Phase 6's profile-page rendering can rely on consistent keys. **Recommendation: author a short rubric doc** at `docs/operations/boat_access_rubric.md` listing the per-venue-type key sets; ~1 hour of operator+Cowork work pre-dispatch.

### §3.4 — Cross-cutting decisions (2 items)

**j. Manual-recovery checklist back-fill.** `docs/maintainability/manual_recovery_checklist.md` exists structurally but §1-§7 body items still say "populated by ChatGPT taxonomy research — TBD" (per the sub-agent's surprise #4). Phase 5's Layer-5 step (~20-40 manual-recovery items per Tier 1 category) needs this content-filled. **Recommendation: Cowork primary back-fills during Phase 5 lead-up** — ~2-3 hour task; the taxonomy synthesis at `outputs/chatgpt_taxonomy_research_synthesis.md` has enough context to seed each Layer-5 section.

**k. `relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md` doc gap.** This file is referenced in `scripts/places_discovery.py:12` docstring but doesn't exist in working tree (per the sub-agent's surprise #2). Either restore from git history (if it ever existed), re-author the operator-facing execution plan, or remove the stale reference from the script docstring. **Recommendation: re-author** if the operator wants a single-doc Phase 5 execution playbook; otherwise just patch the docstring to point at this checklist doc.

### §3.5 — Lock state (new-chat session 2026-05-13)

All 11 §3 decisions locked at the recommendation. Locks captured in brief `outputs/cursor_brief_phase_5_tier_1_data.md` §2; implementation across three commit batches:

| Decision | Locked answer (short form) | Implementation |
|---|---|---|
| §3.1.a Beauty / personal care | Skip in Phase 5; `(None, None)` mapping documents intent | commit `62ab3b7` |
| §3.1.b RV-park boundary | `rv_park` → `lodging-vacation-rentals`; `rv_repair` → `auto-rv-fuel` | commit `62ab3b7` |
| §3.1.c Eat & Drink `types[]` | Expanded `google_types_mapping.py` (+~54 entries across all 6 Tier 1 categories) | commit `62ab3b7` |
| §3.2.d Run sequencing | Per-category (discover → enrich → load → review → next), not all-at-once | doc-state this session |
| §3.2.e OSM scope | `leisure=marina` + `man_made=pier` + `natural=beach` for `on-the-water` only | doc-state this session |
| §3.2.f Ambig-queue triage | Direct DB query post-scrape; no Phase 5 admin form | doc-state this session |
| §3.3.g `heat_exposure` rubric | Operator priority-30 brainstorm during lead-up; everything else → `indoor` | doc-state this session |
| §3.3.h `crowd_notes` rubric | Short-form default; long-form for top-20 highest-volume venues only | doc-state this session |
| §3.3.i `boat_access` shape | `docs/operations/boat_access_rubric.md` authored with 4 canonical shapes | commit `b755b03` |
| §3.4.j `manual_recovery_checklist.md` back-fill | ~250 lines back-filled across §1-§7 with field-work prompts | commit `b755b03` |
| §3.4.k `places_discovery.py` docstring | Repointed to `outputs/cursor_brief_phase_5_tier_1_data.md` + this checklist | commit `62ab3b7` |

The 5 doc-state-only locks (§3.2.d-f + §3.3.g-h) require no code change — they govern operator workflow during Phase 5 execution. Brief §2 carries the full locked narrative; per-category playbooks (brief §3.1-§3.6) dispatch cleanly off these locks without further operator decision-friction.

§3 lead-up is **closed**. Remaining Phase 5 lead-up surface: §4 external verifications (operator-driven browser work, ~3-4h) + Phase 4 Railway redeploy (operator UI action) + §3.3.g priority-30 list brainstorm (~30 min) before first scrape.

## §4 External data-source verifications

Per strategy memo §3.3-§3.4, four external sources were named but never URL-verified in any memo before Phase 5 dispatch. The sub-agent flagged this as surprises #5 + #6; remediation here.

| # | Source | What to verify | Estimated time |
|---|---|---|---|
| 1 | **AZ ROC (Arizona Registrar of Contractors)** ⚠️ | License search endpoint still publicly accessible; test query for a known Lake Havasu contractor returns license + status + classification; rate-limit posture (any throttling?). Inform Layer 3 client design. | 30-45 min |
| 2 | **City of Lake Havasu Parks & Recreation** ✅ | Facility list URL still live + format unchanged since the `parks-rec-scrapes.yml` cron last ran; confirm the workflow_dispatch run #26 baseline still applies (session-22 verified at 1m 5s end-to-end); operator inspects the latest scrape output for stale rows. | 20-30 min |
| 3 | **Lake Havasu business licenses (city)** ⚠️ | City of Lake Havasu issues business licenses; is there a public search endpoint? If not, document the gap (master plan §4 Phase 5 references this as a maybe-source; if no endpoint exists, defer to Layer 5 manual recovery + AZ ROC cross-reference for the home-property subset). | 20-30 min |
| 4 | **Mohave County GIS** ⚠️ | County GIS portal for parcel data — does it serve commercial-business data alongside parcel data? If yes, Layer 3 client opportunity. If no, document the gap. | 20-30 min |
| 5 | **NPI registry** ⚠️ | Already integrated per master plan §4 Phase 4 (Layer 4); verify current Lake Havasu NPI search query still returns expected practitioners (cross-reference against the existing `app/contrib/npi/` surface). | 15-20 min |
| 6 | **USAPickleball** ⚠️ | National pickleball court directory — does Lake Havasu have meaningful coverage? Sample query. Inform Layer 4 priority-add ordering. | 10-15 min |
| 7 | **PDGA (Professional Disc Golf Association)** ✅ | Disc-golf course directory — does Lake Havasu have any registered courses? Sample query. Inform Layer 4 priority-add ordering. | 10-15 min |
| 8 | **Google Places billing posture** ⏸ | Confirm `GOOGLE_PLACES_API_KEY` is still active in Railway Variables; verify estimated Phase 5 spend (per category: ~$5-9 discovery + ~$100 enrichment per `scripts/places_discovery.py` cost estimate at `:11` docstring; × 6 categories = ~$30-54 discovery + ~$600 enrichment, but enrichment cost scales with row count not category count); set spend cap in Google Console if not already. | 30-45 min |
| 9 | **OSM Overpass rate posture** ✅ | Test the Overpass public endpoint with the `leisure=marina` LHC bbox query Phase 5 will use; confirm response time + no rate-limit warnings; document any throttling observed. | 15-20 min |
| 10 | **`parks-rec-scrapes.yml` workflow health** ⚠️ | Cheapest leading indicator for Layer 3 LHC viability — verify the workflow has been running green on the `15 */6 * * *` cron since session-22's `18a4100` re-enable (workflow_dispatch run #26 was the last verified-green; many more should have run since). Surface any persistent failures + their stack traces. | 15-20 min |

**Total external-verification time:** ~3-4 hours of operator work, mostly read-only browser + occasional script run.

## §5 Operator workload estimate

Master plan §4 Phase 5 says "Operator workload ~60-100 hours spread over 4-8 weeks." The sub-agent's bottom-up re-derivation says **80-190 hours** — a real discrepancy worth flagging now.

Bottom-up breakdown:

| Lane | Estimated hours |
|---|---|
| External verifications + decision-lock prep (§3 + §4) | 6-10 |
| Discovery scrape runs (6 categories × ~30 min operator time per category for setup + run-watching + log review) | 3-6 |
| Reconciler `ambiguous` queue triage (~20-40 hits per category × 6 categories × ~3-5 min per hit) | 6-20 |
| Layer 5 manual recovery (~20-40 items per category × 6 categories × ~15-30 min per item) | 30-120 |
| Operator-curated field entry (heat_exposure + crowd_notes + boat_access + seasonal_hours; ~390-740 entries × ~5-15 min per entry) | 33-185 |
| Quality-assurance passes + spot-checks + bug-surface during operator runs | 5-10 |
| **Total** | **83-351** |

The wide range comes from three big leverage points: (a) Layer-5 item count (20 vs 40 per category × low-end vs high-end manual recovery time per item); (b) operator-curated entry time per entity (5min for the boilerplate categories, 15min for venues that need crowd_notes long-form + boat_access detail); (c) reconciler ambiguous-hit volume (depends on Google vs OSM overlap in real data — TBD).

**Pragmatic recommendation: budget 100-150 hours over 6-8 weeks** as the realistic mid-range; treat the 60-100h master plan estimate as the floor and the 190h ceiling as the worst-case (only hit if every leverage point lands at its high end simultaneously). If you're consistently above 150h after the first two categories, that's a signal to defer some lower-priority operator-curated field entry to V1.5.

## §6 Risks to flag before dispatch

Mirroring the brief §10 risk-register shape from Phase 4 briefs:

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | Layer-5 manual recovery volume exceeds 40 items per category | M | H | Triage list against Tier-1 success criterion (15+ per default filter on Phase 6 landing); defer non-essential rows to V1.5 manual-recovery sweep |
| 2 | Operator-curated entry per-entity time exceeds 15 min average | M | H | Standardize rubrics (§3.3.g+h+i above) pre-dispatch so the per-entity decision tree is fast; consider deferring long-form `crowd_notes` to top-20 venues only |
| 3 | Reconciler `ambiguous` queue volume blocks operator review | L | M | First per-category run is a smoke test; if >50 ambiguous hits, pause + tune `GEO_PROXIMITY_THRESHOLD_M` (currently 50m) before continuing |
| 4 | Google Places API spend exceeds budget | L | M | Set spend cap in Google Console pre-dispatch; per-category dry-runs first; reconciler dedupe prevents re-scraping existing entities |
| 5 | OSM Overpass rate-limited under Phase 5 query volume | L | L | Existing `OSM_OVERPASS_LIMITER` at qps=0.5 is conservative; Phase 5 should comfortably stay under any public throttle |
| 6 | `heat_exposure` priority-30 list still unauthored at dispatch time | M | M | Author during Phase 5 lead-up (§3.3.g above); ~30 min operator brainstorm |
| 7 | AZ ROC public access changes / blocks Layer 3 client | L | H | Verify in §4.1 above before dispatch; if blocked, drop Layer 3 from `home-property-services` plan + fall through to Layer 5 manual recovery |
| 8 | LHC business-license endpoint doesn't exist | M | M | Document the gap (§4.3); fall back to Layer 5 for the home-property-services subset that depends on city-level licensing |
| 9 | Operator burns out on field-entry monotony | M | H | Cap daily field-entry sessions at ~2h; alternate field-entry days with scrape-run days; reward landmark thresholds (every 50 entries = ✓) |
| 10 | Phase 6 UI is hungry for entries before Phase 5 finishes | M | M | Sequence categories so highest-traffic ones (eat-drink, on-the-water) land first; Phase 6 can render early-stage data with the "< 15 entries" empty-state copy already in scope |
| 11 | Reconciler false-positive merge degrades data quality | L | H | Reconciler is conservative by default (geo+name required for auto-merge; name-only returns ambiguous); operator reviews the merge log after each run |
| 12 | Stale doc references mislead future operators | M | L | Patch `scripts/places_discovery.py:12` to point at this checklist (§3.4.k); back-fill `manual_recovery_checklist.md` (§3.4.j) |

## §7 Phase 4 deliverables Phase 5 depends on

**Blockers (Phase 5 cannot dispatch without these):**
1. ✅ `app/contrib/ingest_base.py` — `BaseIngestClient` abstract interface (Phase 4.2 `86eeaf8`)
2. ✅ `app/contrib/google_places_scraper.py` — Layer-1 Google Places client (Phase 4.2 `86eeaf8`)
3. ✅ `app/contrib/google_types_mapping.py` — Google `types[]` → `(slug, place_type)` table (Phase 4.2 `86eeaf8`)
4. ✅ `app/contrib/osm_overpass_client.py` — Layer-2 OSM Overpass client (Phase 4.3 `2f87211`)
5. ✅ `app/contrib/ingest_reconciler.py` — `reconcile_hit` + `SOURCE_PRIORITY` table (Phase 4.3 `2f87211`)
6. ✅ `scripts/places_load.py` — JSONL → DB pipeline with reconciler integration (Phase 4.3 `2f87211`)
7. ✅ `scripts/osm_overpass_pull.py` — OSM operator-runnable wrapper (Phase 4.3 `2f87211`)
8. ✅ `app/core/background.py` `with_retry` + Outbox surface (Phase 4.1 `91cd37b`)
9. ✅ `docs/operations/railway_scheduled_jobs_runbook.md` — operator runbook (Phase 4.4 `ac94b6c`)
10. ✅ `docs/operations/scrape_logs_template.md` — per-run summary template (Phase 4.4 `ac94b6c`)

**Nice-to-haves (Phase 5 can dispatch without but benefits):**
1. Admin form for operator-curated field entry — currently doesn't exist; operator enters via direct DB SQL or via the existing admin/* HTML surfaces (`admin_contributions_html`, `admin_provider_create`). Phase 6 has the proper admin-form surface in scope.
2. Admin form for reconciler `ambiguous` queue review — Phase 5 / V1.5 territory; for Phase 5 use direct DB query (§3.2.f).

All blockers are SHIPPED on origin. Phase 5 is **structurally unblocked** the moment the operator commits to chipping through this checklist + the Railway redeploy lands.

## §8 What Phase 5 explicitly does NOT do

Per master plan + brief §3 + §11 design rails carry-forward:

1. **No admin form surfaces.** Phase 5 uses direct DB queries + existing `admin/*` HTML surfaces. Admin forms for the operator-review queue + curated-field entry are Phase 6 / V1.5.
2. **No new schema migrations.** Phase 3 + Phase 4 shipped all the columns Phase 5 fills (`heat_exposure`, `crowd_notes`, `boat_access`, `seasonal_hours`, `district_id`, `featured`, plus the entity-extension tables for `Location`, `ContactPoint`, `Schedule`, etc.).
3. **No `entities.sources` JSON-array migration.** Phase 4.3 locked-defer; comma-separated string in `entity.source` suffices for V1. Revisit when reconciler query patterns force it (probably V1.5 or Phase 5 fill-in).
4. **No Layer 5 admin entry surface.** Manual recovery is operator workflow per `docs/maintainability/manual_recovery_checklist.md`; entries land via direct DB INSERTs or existing admin surfaces.
5. **No `heat_exposure` priority-30 list auto-tagging.** Operator-driven during field entry; Phase 8 alert venue-context mapping consumes whatever Phase 5 produces.
6. **No Phase 6 UI surfaces.** Phase 5 and Phase 6 run in parallel but are scope-disjoint. Phase 5 fills data; Phase 6 renders.
7. **No `auto_close` retry-storm prevention beyond Phase 4.1's `with_retry`.** If Phase 5 surfaces a transient Google API failure mode that the current `with_retry` doesn't handle gracefully, defer the tuning to a Phase 4.5 follow-up commit rather than expanding Phase 5 scope.
8. **No data-quality QA tooling beyond direct operator review.** Phase 5 doesn't ship a data-quality dashboard; the operator's daily field-entry sessions are the QA pass.
9. **No re-scrape automation beyond Phase 4.4's runbook.** The Railway scheduled-job services run on the cron the operator configures; Phase 5 doesn't add per-category schedulers (that's a Phase 5-late or V1.5 task once cadence is known).
10. **No Phase 5 dispatch prompt artifact.** Unlike Phase 4's tightly-bounded sub-phases, Phase 5 is multi-week operator workflow — the first Cursor dispatch is the Phase 5 brief itself (TBD authoring), not a paste-into-Cursor prompt. Cursor sessions during Phase 5 are tooling glue (e.g., `--category` flag patches, types-mapping additions, ambiguous-queue grep helpers), each authored on demand.

## §9 Lead-up timeline

Suggested operator chipping schedule over ~1-2 weeks:

| Week | Tasks |
|---|---|
| **Lead-up week 1** | §4 external verifications (3-4h); §3.4.j manual_recovery_checklist back-fill (2-3h Cowork primary); §3.1.c google_types_mapping Eat & Drink expansion (~30 min Cowork primary) |
| **Lead-up week 2** | §3.1.a + §3.1.b operator decisions locked (~30 min); §3.2 sequencing decisions locked (~30 min); §3.3 field-entry rubrics drafted at `docs/operations/boat_access_rubric.md` (~1h Cowork primary + operator); §3.4.k stale-reference patch (~15 min); Phase 5 brief authored at `outputs/cursor_brief_phase_5_tier_1_data.md` (Cowork primary, ~3-4h) |
| **Dispatch boundary** | Operator says "go"; first Cursor session (if needed for tooling) OR first manual scrape run dispatches |

After lead-up, the 4-8 week Phase 5 execution period itself is operator-driven scrape-and-curate work as outlined in §1.

## §10 What lives in the Phase 5 brief (when authored)

The Phase 5 brief at `outputs/cursor_brief_phase_5_tier_1_data.md` (TBD) is structurally different from Phase 4's brief because Phase 5 isn't an engineering sub-phase chain. It's an **operator playbook + tooling-touchup checklist** that benefits from being a single doc rather than 4 separate sub-phase briefs. Suggested brief structure (when authored in lead-up week 2):

- §0 Baseline + reads + halt etiquette (mirrors Phase 4 §0)
- §1 Why this phase exists + texture rule
- §2 Locked decisions (do not relitigate) — populated from this checklist's §3 once operator decides
- §3 Per-category playbook — one section per Tier 1 category, with scrape commands, reconciler review steps, manual-recovery prompts, operator-curated field rubric pointers
- §4 Tooling-touchup queue — small Cursor sessions for `--category` flag patches, types-mapping additions, etc. as needed
- §5 Operator daily/weekly rhythm — sample workflow week with field-entry caps + scrape-run cadence + QA spot-check timing
- §6 Risk register (carry forward from this checklist's §6)
- §7 What NOT to do (carry forward from this checklist's §8)
- §8 Phase 5 close-out criteria — what "Phase 5 SHIPPED" looks like (probably "all 6 Tier 1 category landing pages render 15+ entries per default filter in Phase 6 UI smoke")

## §11 Next concrete action for the operator

1. **Today / this week:** Read this checklist end-to-end. Skim master plan §4 Phase 5 + strategy memo §3 + §6 for grounding context (~30 min).
2. **Lead-up week 1:** Knock out the 10 external verifications in §4 (~3-4h total, spread across multiple sessions).
3. **Lead-up week 2:** Lock the 11 operator decisions in §3 (~2h). Cowork primary back-fills `manual_recovery_checklist.md` (~2-3h). Cowork primary authors `outputs/cursor_brief_phase_5_tier_1_data.md` once decisions are locked (~3-4h).
4. **Dispatch boundary:** Operator says go; Phase 5 begins.

Phase 4 SHIPPED on origin at `ac94b6c` (2026-05-13). Phase 5 dispatchable once this checklist closes out + the Phase 5 brief lands. Estimated lead-up window: **1-2 weeks of intermittent operator + Cowork primary time**.
