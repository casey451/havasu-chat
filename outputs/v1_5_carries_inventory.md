# V1.5 carries inventory — havasu-chat

> **What this is:** consolidated backlog of all V1.5-deferred items found across the codebase (`app/`, `tests/`), outputs/, and docs/ as of 2026-05-21. Captured for ready dispatch when V1 ships. Builds on (does not replace) the pre-existing `outputs/v1_5_carry_inventory_triage.md` which holds the canonical 52-item triage of Phase 5.0–5.11 + Phase 8a-prereq carries.
>
> **Authored by:** Cowork primary via sub-agent, 2026-05-21, post-Phase-7.5.2-ship.
>
> **Status:** inventory only; no scoping memos or dispatch wrappers authored. Use this as input when planning the V1.5 release.
>
> **Relationship to triage doc:** the triage doc at `outputs/v1_5_carry_inventory_triage.md` (52 items, 8 sections, last updated 2026-05-20 at commit `7143976`) is the canonical source for Phase 5-era carries + Phase 8a-prereq carries. This inventory restates them at one-line resolution under §2 + cross-references back, then adds the newer Phase 7.5 / 8 / 9 design-doc-and-wrapper carries that surfaced after that triage was cut.

---

## §1 Summary

- **Total items:** 81 (52 from triage doc + 29 net-new from this sweep).
- **By priority:**
  - **High (8):** Layer-4 verifier bundle highest-yield, water temperature data source, Nixle replacement, hint_extractor perf, F6/F7 validator-polish carries, post-deploy smoke automation, peer recommendations pilot, SMS alerts.
  - **Medium (32):** Data-source carries, dual-place_id consolidations, dual-cat reviews, Phase 9 V1.5 features, lower-yield verifier surfaces, tighter AirNow fidelity, accessibility profiles, owner uploaded video.
  - **Low (41):** Individual-entity reviews, cosmetic surfaces, polish, exclusion-list items unlikely to move soon.
- **By category:**
  - §2.1 Strategic V1.5 features (master plan §4 Phase 13): 11
  - §2.2 Data-source carries (USGS/Nixle/AirNow alt-source research): 5
  - §2.3 Layer-4 verifier bundle (AZ MVD / AZCC / AZ TPT / BBB / AZ State Parks / NPS / LHC Parks-Rec / AZDHS / franchise gyms / AZDOR / AZRE / LHC Tourism / pet franchises / visitarizona): 13
  - §2.4 Validator / HALT 3 polish (F6, F7, post-deploy smoke): 3
  - §2.5 Chat / routing carries (hint_extractor perf): 1
  - §2.6 Phase 9 events carries (event detail route, .ics export, multi-day expansion, scrape-monitoring dashboard, RRULE UI polish, etc.): 9
  - §2.7 Alerts / conditions polish (SMS via Twilio, conditions-driven category banners, per-favorite alerts, operator-side preview, multi-language, forecast-based, user-defined thresholds, reservoir-storage UX, gauge-height-delta heuristic doc): 9
  - §2.8 Sustainability-layer + data shape carries: 4
  - §2.9 Dual-place_id / dual-category consolidations: 11
  - §2.10 Specific-entity reviews + DRAFT cleanup: 13
  - §2.11 UI / browse polish (single-input chat-search collapse, district paragraph rendering, filter chips, themed-group sort tuning, etc.): 4

Where item-counts here differ from the triage doc, the discrepancy is intentional: this inventory restates §2.x as one-line summaries to make the cross-doc reader's eye fast, and the triage doc retains the per-row dispatch detail.

---

## §2 Items by category

### §2.1 Strategic V1.5 features (master plan §4 Phase 13)

Source: `docs/maintainability/master_build_plan.md` lines ~549-572 ("Phase 13 — V1.5 features (post-launch, ongoing)").

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 1 | Peer recommendations (5-10 merchant pilot) — Opus feature #7 | High | L | Schema landed Phase 3.1 (`PeerRecommendation` model exists; writes V1.5-gated per `app/db/models.py` line 1437); UX + pilot dispatch in V1.5. |
| 2 | UGC "describe this district" layer | Medium | L | Master plan §4 Phase 13. |
| 3 | SMS alerts via Twilio | High | M | Schema is SMS-ready from Phase 3 (`alert_subscriptions.delivery_channel` enum includes `'sms'`/`'both'`); just code switch + Twilio account. Source: `app/db/models.py` line 136, `docs/maintainability/conditions_panel_and_alerts_design.md` §10 Q6, master plan §8 OQ #13. |
| 4 | Accessibility profile data collection (structured ADA fields per Opus design deferral) | Medium | M | Master plan §4 Phase 13. |
| 5 | `Provider.category → category_id` backfill (legacy column drop) | Medium | S | Master plan §4 Phase 13. |
| 6 | Owner-uploaded video | Medium | M | Master plan §4 Phase 13. |
| 7 | Bookings / reservations | Medium | L | Master plan §4 Phase 13 + master plan §8 OQ #3. |
| 8 | Itinerary builder | Medium | L | Master plan §4 Phase 13. |
| 9 | Real-time fuel prices / room availability / launch conditions | Medium | L | Master plan §4 Phase 13 + master plan §8 OQ #3. |
| 10 | White-label | Low | L | Master plan §4 Phase 13. |
| 11 | Native review system | Low | L | Master plan §4 Phase 13 — "still deferred unless review-war dynamics in Havasu prove otherwise." |

### §2.2 Data-source carries (post-Phase-8a-prereq research)

Source: `outputs/phase_8a_prereq_verification_report.md` §8 + §11.5 + §12.4, surfaced 2026-05-19 by live verification; cross-referenced in `outputs/v1_5_carry_inventory_triage.md` §11.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 12 | Water temperature data source for Lake Havasu | High | M | USGS `09427500` has no `00010`. Candidates: USGS `09426630` Bill Williams River (browser-verify pending), Bureau of Reclamation Lower Colorado Region gauges, NDBC buoy partnership, marina sensor partnership. `outputs/phase_8a_prereq_verification_report.md` §8 + §2 + `master_build_plan.md` §4 Phase 8 line ~426. |
| 13 | LHC public-safety alert source (Nixle replacement) | High | M | Nixle agency `3726` silent since 2021-09-01; staff-recall content only when active. Candidates: Mohave County Sheriff's Office alerting platform, ein.az.gov, lhcaz.gov RSS, AZ DPS alerts. `outputs/phase_8a_prereq_verification_report.md` §4 + `master_build_plan.md` §4 Phase 8 line ~427; `outputs/phase_8_nixle_agency_id_lookup.md` line 57. |
| 14 | Tighter local AirNow fidelity for LHC | Medium | M | Nearest AirNow monitor at Blythe CA ~60mi south, O3-only. Candidates (decreasing yield): PurpleAir community sensors, AZDEQ state monitors, BLM dust stations. V1 ships with honest "from Blythe, CA" attribution chip. `outputs/phase_8a_prereq_verification_report.md` §12.4. |
| 15 | Reservoir-storage UX ("X% full" / capacity) | Low | S | `00054` acre-ft available at `09427500`; nice-to-have conditions-strip tile beyond gauge-height. `outputs/phase_8a_prereq_verification_report.md` §8. |
| 16 | Gauge-height-delta heuristic bounds doc | Medium | S | Document what drop threshold is meaningful for a managed reservoir; tune `LAKE_HAZARD_GAUGE_DROP_FT` at deploy. Tagged "V1 — operator action" in triage but listed here for completeness. `outputs/phase_8a_prereq_verification_report.md` §8. |

### §2.3 Layer-4 verifier bundle (per `outputs/v1_5_carry_inventory_triage.md` §2)

13 items, ~35–60h total V1.5 eng work. Restated here at one-line resolution; full per-row dispatch detail in triage doc §2 rows #1–#13 + #15. Priority order per triage doc §8 #5 ranking.

| # | Item | Priority | Effort | Source (triage row) |
|---|---|---|---|---|
| 17 | AZDHS childcare-license registry (cat-12 highest-yield, high-anxiety category) | High | 4–6h | triage #9 |
| 18 | AZDOR transient-lodging tax registry (cat-10) | High | 4–6h | triage #11 |
| 19 | AZRE vacation-rental license registry (cat-10) | Medium | 3–5h | triage #12 |
| 20 | AZ MVD Dealer Locator Playwright (cat-9) | Medium | 2–4h | triage #1 |
| 21 | AZCC towing carrier (cat-9) | Medium | 1–2h | triage #2 |
| 22 | AZ TPT Playwright (cat-8 retail) | Medium | 3–5h | triage #3 |
| 23 | BBB cross-reference (cat-8 retail) | Medium | 2–3h | triage #4 |
| 24 | AZ State Parks Playwright (cat-7) | Low | 2–3h | triage #5 |
| 25 | NPS REST API (cat-7) | Low | 1–2h | triage #6 |
| 26 | LHC Parks & Rec municipal scrape (cat-7 + cat-12 shared) | Medium | 3–4h | triage #7 (Phase 9 may absorb) |
| 27 | LHC Tourism Board lodging directory (cat-10) | Low | 2–3h | triage #13 |
| 28 | Franchise gym chain APIs (Anytime / Snap / Orange Theory / CycleBar) | Low | 6–8h | triage #10 |
| 29 | National pet franchise locators (PetSmart / Petco / Banfield) | Low | 3–5h | triage #15 |
| 29a | visitarizona.com event aggregator scrape (Phase 9 Source 6 candidate) | Medium | 1–2h | triage #8b — may upgrade to Phase 9 if scrape-research confirms ≥10% LHC-local yield. |

### §2.4 Validator / HALT 3 polish

Source: `outputs/phase_7_5_prod_divergence_investigation.md` §9 (lines ~398-406), `outputs/phase_7_5_close_out.md` §3, `outputs/phase_7_5_3_validator_polish_design_memo.md`.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 30 | F6 — `near_match_subject_overlaps` fail-open on all-category-words queries | High | S | Residual after Phase 7.5.1; tagged explicitly V1.5 in §9 of post-mortem (line 401). |
| 31 | F7 — `_USEFUL_CONTENT_RE` accepts any capitalized word as "useful content" | High | S | Over-broad voice-quality regex. §9 line 402. |
| 32 | `scripts/post_deploy_smoke.py` automation | High | M | Concrete proposal: scripted prod-eval smoke that runs q01-q23 against the prod URL post-deploy + posts to Slack or fails the GH Actions workflow. Would have caught the 3 prod bugs Phase 7.5 missed. `phase_7_5_prod_divergence_investigation.md` lines 378-380 + §9 line 405. |

Note: F1, F4, F5 are explicitly Phase 7.5.3 candidates (NOT V1.5) per the post-mortem; G4 list promiscuity + template-echo sanitization are Phase 7.5.4 watch items (NOT V1.5) per `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md`.

### §2.5 Chat / routing carries

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 33 | `hint_extractor` token-budget perf | Medium | S | 22× `hint_extractor: token usage exceeds soft budget (inp=~378 out=8)` per HALT 3 validator run. Tighten prompt OR raise soft-budget constant. Tagged explicitly V1.5 in `outputs/phase_7_5_close_out.md` §3 Finding #3 + `outputs/phase_7_close_out.md` Finding #5 + cross-referenced in `session_close_out_2026_05_20.md` §4. Already in triage §11.4 but listed here for chat-category proximity. |
| 34 | Tier-3 grounding contract for non-"about-X" missing-data queries | Medium | M | Even with the about-gate, tier-3 still confabulates on missing-data queries that don't match `_ABOUT_GATE_STRICT_PATTERNS`. `phase_7_5_prod_divergence_investigation.md` §9 line 403 — "Phase 8+ scope; needs a tier-3 prompt rewrite or wholesale missing-data → gap-template guarantee at the router level." Listed V1.5 with Phase 8+ scoping note. |
| 35 | Confab classes not yet probed (price, license number, opening dates, etc.) | Low | S | `outputs/cursor_dispatch_prompt_phase_7_5_2.md` §12.8 — "should they be added in a future hardening lane?" V1.5 candidate. |
| 36 | "Ask Hava as search vs parallel surfaces" — single intelligent input collapse | Low | M | `master_build_plan.md` §8 OQ #11 — "V1.5 candidate after user data shows behavior." Currently keep separate Search + Ask Hava button. |

### §2.6 Phase 9 events carries

Source: `outputs/cursor_dispatch_prompt_phase_9.md` lines ~580-625 + 767-773, `outputs/phase_9_architecture_design.md` lines 119, 171, 333-336, 1130-1132, 1241, 1293-1306, 1322, 1369-1374, 1600.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 37 | Event detail page route (`/events/<id>` standalone) | Medium | S | Card links to `event_url` by default in V1; dedicated detail page V1.5. The existing `_profile_url_for_card` returns `/events/<id>` but route itself not shipped in Phase 9. |
| 38 | Calendar export (.ics file per event) | Low | S | `phase_9_architecture_design.md` line 1301. |
| 39 | Multi-day event detail expansion ("see all dates") | Medium | S | Card shows next occurrence; multi-occurrence drill-in V1.5. `phase_9_architecture_design.md` line 1300. |
| 40 | Operator scrape-monitoring dashboard | Medium | S | Phase 9b stretch may ship in V1; otherwise V1.5. Sentry breadcrumbs + Railway service logs are V1 surface. `phase_9_architecture_design.md` line 1304, 1322. |
| 41 | Row-expansion materialization for recurrence | Low | M | At-query-time expansion fast enough at V1 scale; materialize via nightly background job if profiling shows need. Phase 13 / V1.5. `phase_9_architecture_design.md` lines 171, 335, 1130. |
| 42 | RRULE editor structured-form UI (vs JSON textarea) | Low | M | Design ships JSON-textarea RRULE editing in V1 + structured form V1.5 if admin-UI scope grows uncomfortable. `cursor_dispatch_prompt_phase_9.md` line 584. |
| 43 | Multi-occurrence-per-event on `/venue/<slug>` | Low | S | V1 ships deduplicated single-occurrence-per-event on venue page. `phase_9_architecture_design.md` line 1241. |
| 44 | Process-local LRU cache for "What's on at this venue" profile region | Low | S | If V1.5 profiling shows this becomes a bottleneck. `phase_9_architecture_design.md` line 1130. |
| 45 | Stale-source warning chip on event card after >14d scraper miss | Low | S | `phase_9_architecture_design.md` line 776 — "Phase 13 / V1.5 may add a 'stale-source' warning chip." Currently no auto-cancellation. |
| 45a | Simpleview API-key flip (Chamber / GLH iCal share) | Low | S | `phase_9_event_source_research.md` line 93 — operator follow-up to ask DMO admin for GrowthZone iCal feed URL or Simpleview API key. Would flip Chamber from HTML-scrape to API. |
| 45b | RRULE recurrence-expansion via JSON-LD description hints | Low | S | `phase_9_event_source_research.md` line 89 — for V1, treat each scraped page as single event; recurrence expansion V1.5. |

### §2.7 Alerts / conditions polish

Source: `docs/maintainability/conditions_panel_and_alerts_design.md` lines 416-441, `outputs/cursor_dispatch_prompt_phase_8.md` lines 154, 196, 373-375, 386-394.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 46 | Conditions-strip WebSocket-push (vs 60s poll) | Low | S | `cursor_dispatch_prompt_phase_8.md` line 375 — "If WebSocket push reads cleaner, V1.5 (don't ship in Phase 8)." |
| 47 | `event_traffic` alert type | Medium | M | Master plan §8 OQ #12 + design doc §11. Phase 9.5 (when Events surface lands) rather than core V1.5. Listed here for completeness — wired in Phase 9.5 after events ship. |
| 48 | Conditions-driven category-page banners | Low | S | Homepage panel only in V1; "Heat advisory — these listings re-ranked" banners on category pages V1.5. Design doc §10. |
| 49 | Per-favorite alerts ("alert me if this specific business's outdoor seating is unwise") | Low | M | Alerts are city-wide in V1; per-favorite V1.5+. Design doc §10. |
| 50 | Operator-side alert preview / approval flow | Low | S | No "Casey reviews each alert before send" workflow in V1. V1.5 adds approval gating if false-positives become problem. Design doc §10. |
| 51 | Forecast-based alerts ("tomorrow will be 115°F — heat advisory likely") | Low | M | Only current-state triggers in V1. V1.5 / V2. Design doc §10. |
| 52 | Multi-language alert bodies | Low | M | English only in V1. Design doc §10. |
| 53 | User-defined alert thresholds | Low | L | No "alert me when temp exceeds X" UI in V1; operator-set defaults only. Tagged V2 in design doc but worth keeping in V1.5+ inventory. |
| 54 | Phase 8b filter chips on `/category/public-civic-resources` | Low | S | Government services / Civic groups / Utilities / Transit chips that filter cat-13 entity list. `cursor_dispatch_prompt_phase_8b.md` lines 143-146, 225-228, 276-285. Optional in Phase 8b; V1.5 carry if skipped. |

### §2.8 Sustainability-layer + data shape carries

Source: `outputs/v1_5_carry_inventory_triage.md` §3 + §11.4. Per triage doc, the 4 google-types-mapping widenings (#17-#20 in triage) were CLOSED 2026-05-20 via commit `a4260ce` (sustainability-extensions apply). The remaining items:

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 55 | `crowd_notes` JSON convention lock | Medium | S | Schema is `Mapped[dict | list | None]`; no convention locked for shape. Locking a JSON-correct convention enables operator annotations without ad-hoc shape. Triage §11.4. |
| 56 | `beauty_personal_care` final-home decision (`hair_salon`/`nail_salon`/etc.) | Low | S | Currently routed to `(None, None)` to surface operator-queue rather than absorbed into wrong category. Per `app/contrib/google_types_mapping.py` line 12 + line 359 — "skip beauty_personal_care in Phase 5; revisit V1.5." |
| 57 | Drop legacy `Provider` / `Event` / `Program` tables after entity-pivot complete | Medium | M | Per `app/db/models.py` line 634 — "legacy table drops are deferred to V1.5+/Phase 13 per master plan." Phase 1B/C/D pivoted reads then writes; drop is post-launch. |
| 58 | `sponsor_notification` outbox handler wiring | Low | S | Per `app/core/background.py` line 407 — "sponsor_notification is V1.5." Phase 4.1 wired magic_link; Phase 4.4 wired image_processing; sponsor_notification deferred. |

### §2.9 Dual-place_id / dual-category consolidations

11 items per `outputs/v1_5_carry_inventory_triage.md` §4 + 2 newer items from triage §11.4. Per-entity operator-decide; all KEEP-as-V1.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 59 | HEAT Bar ↔ Heat Hotel cross-link | Low | S | triage #21 |
| 60 | Havasu Dunes Resort ↔ GetAways at Havasu Dunes Resort | Low | S | triage #22 |
| 61 | 3 Beautiful Beards franchise multi-location consolidation | Low | S | triage #23 |
| 62 | 3 PetSmart franchise multi-location consolidation | Low | S | triage #24 |
| 63 | 3 cat-8 pet-retail DUAL ADD candidates (PetSmart / Doggie Shades / Rok Dog Leashes for cat-8 + cat-11) | Low | S | triage #25 |
| 64 | 26 cat-5 HWC dual-cat with cat-12 reviews (gyms/yoga/pilates/dance/martial arts) | Medium | M | triage #26 — per-entry review |
| 65 | Universal Sonics Gymnastics + Shah Racquetball Club — NEW-create in cat-12 with primary_type override | Low | S | triage #27 |
| 66 | Sand Volleyball at Rotary Park — FLIP cat-5 → cat-12 OR dual-cat with cat-7 | Low | S | triage #28 |
| 67 | The Ark Center recategorization (cat-5 → cat-13 religious OR dual-cat with cat-12) | Low | S | triage #29 |
| 68 | Lake Havasu City Aquatic Center primary identity (cat-12 swimming_pool → dual-cat with cat-13 municipal) | Low | S | triage #30 |
| 69 | 5 dual-cat soft-edges cat-7 outdoor (SARA Disc Golf / Motocross Park / Ofd Racing / Thompson Bay Beach / Sportsman's Club) | Low | S | triage #31 |
| 70 | PetSmart DUAL ADD pattern modeling (sub-services of franchise parent) | Medium | M | triage §11.4 — schema/UX decision: keep granular vs fold under cat-8 parent. |
| 71 | Anderson Powersports Lake Havasu sister-location dedupe (1040 N Lake Havasu Ave vs 3198 Sweetwater Ave) | Low | S | triage §11.4 + `session_close_out_2026_05_20.md` §4. |

### §2.10 Specific-entity reviews + DRAFT cleanup

13 items per `outputs/v1_5_carry_inventory_triage.md` §5 + 4 newer items from triage §11.4.

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 72 | Sara Park Hiking Trail ↔ Sara Park Trail Head — navigation-alias merge | Low | S | triage #33 |
| 73 | Lake Havasu Museum of History — place_id unification | Low | S | triage #36 |
| 74 | art_gallery / museum entity_type review — `place` vs `commercial` | Low | S | triage #38 |
| 75 | 5.8 §9 carry candidates revisit: Nomadic coworking / Lions Dog Park / Main Street Commons | Low | S | triage #39 (each ~10-15 min field entry) |
| 76 | Bridge Body Fitness + Feelin' Good Fitness — high-signal gyms in §1 ambig pool | Low | S | triage #40 |
| 77 | River City Music — cross-cat with music lessons | Low | S | triage #41 |
| 78 | Havasu Suites — identity re-evaluation (travel_agency primary) | Low | S | triage #42 |
| 79 | Xanadu — identity verification (point_of_interest, 0 reviews) | Low | S | triage #43 |
| 80 | Queens Bay Resort Condominiums — waterfront-DUAL review | Low | S | triage #44 |
| 81 | 5 waterfront-suggestive RV park / campground candidates (Sam's Beachcomber / Anchor Lake House / Campbell Cove / Islander / Havasu Falls) | Low | S | triage #45 |
| 82 | 29 lake_recreation-domain ambig records (boat/marina adjacent to McCulloch) | Medium | M | triage #46 — cat-3 NEW creates IF 5.2 lane re-opened (~3-4h). |
| 83 | Manual recovery surface — mobile groomers, independent dog walkers, cat boarding, pet sitting | Medium | M | triage #48 — Layer 5 manual recovery; Care.com / Rover not Google-indexed. |
| 84 | Off-island heat list deferred venues (Cattail Cove, Take-Off Point) | Low | S | triage #49 |
| 85 | 86 of 265 HWC providers `verified=False` (operator DBA→NPI follow-up) | Medium | L | triage #50 — Layer 5 manual recovery. |
| 86 | Rotary Community Park parent-child modeling (Butterfly Garden sub-feature) | Low | S | triage §11.4 + `session_close_out_2026_05_20.md` §4. |
| 87 | V1.5 Local-makers / Art Trail subcat (Simply Savage Designs et al.) | Medium | M | triage §11.4 — Etsy-style local-makers surface; 20+ Havasu Art Trail participants. |
| 88 | The Q Gallery (2102 McCulloch Blvd N) next-scrape candidate | Low | S | triage §11.4. |

### §2.11 UI / browse polish

| # | Item | Priority | Effort | Notes |
|---|---|---|---|---|
| 89 | District paragraph rendering | Medium | M | `cursor_dispatch_prompt_phase_8.md` line 394 + `cursor_dispatch_prompt_phase_9.md` line 625 + `cursor_dispatch_prompt_phase_6_5.md` line 84 — repeatedly excluded across Phase 6.5 / 8 / 9 dispatches; tagged V1.5. |
| 90 | Themed-group sort tuning (per-group vs first-category-inherits) | Low | S | `outputs/phase_6_4_close_out.md` line 93 — "V1.5 candidate for group-specific sort tuning." |
| 91 | Venue archive view (expired events) | Low | S | `phase_9_architecture_design.md` line 119 — "surfaced only on venue archive view (V1.5)." |
| 92 | "Persistent map vs toggle on desktop category pages" — refinement after V1 data | Low | S | Master plan §8 OQ #10; tagged V1.5 candidate post-V1-user-data. |

---

## §3 Items by priority (one-line summaries)

### High (8)

- **#1 Peer recommendations 5-10 merchant pilot** — Opus feature #7; schema landed Phase 3.1; pilot dispatch V1.5.
- **#3 SMS alerts via Twilio** — schema is SMS-ready; just code + Twilio account.
- **#12 Water temperature data source for Lake Havasu** — USGS `09427500` has no `00010`; alt-source research.
- **#13 LHC public-safety alert source (Nixle replacement)** — Nixle silent since 2021; Mohave County SO / ein.az.gov / lhcaz.gov RSS candidates.
- **#17 AZDHS childcare-license registry (cat-12)** — highest-yield + highest-anxiety verifier; ~70-90% cat-12 childcare coverage.
- **#18 AZDOR transient-lodging tax registry (cat-10)** — strong trust signal; ~70-90% hotel/motel/B&B coverage.
- **#30 + #31 F6 + F7 validator polish** — `near_match_subject_overlaps` fail-open + `_USEFUL_CONTENT_RE` over-broad; voice-quality regression risks.
- **#32 `scripts/post_deploy_smoke.py` automation** — would have caught the 3 prod bugs Phase 7.5 missed; ships against prod after every deploy.

### Medium (32)

UGC district layer, accessibility profile data, `Provider.category` backfill, owner-uploaded video, bookings, itinerary builder, real-time fuel prices, tighter local AirNow fidelity, gauge-height-delta heuristic doc, AZRE vacation-rental license, AZ MVD Dealer Locator, AZCC towing, AZ TPT Playwright, BBB cross-reference, LHC Parks-Rec scrape (Phase 9 may absorb), visitarizona.com event aggregator scrape (Phase 9 Source 6 candidate), `hint_extractor` token-budget perf, tier-3 grounding contract (Phase 8+ scope), event_traffic alert (Phase 9.5), event detail page route, multi-day event detail expansion, operator scrape-monitoring dashboard (or Phase 9b stretch), `crowd_notes` JSON convention lock, legacy Provider/Event/Program table drops, 26 cat-5 HWC dual-cat reviews, PetSmart DUAL ADD pattern modeling, 29 lake_recreation-domain ambig records, manual recovery surface (mobile groomers etc.), 86 HWC providers verified=False, V1.5 local-makers subcat, district paragraph rendering.

### Low (41)

Reservoir-storage UX, AZ State Parks Playwright, NPS REST API, LHC Tourism Board lodging directory, franchise gym chain APIs, national pet franchise locators, confab classes probe (price/license/opening), single-input chat-search collapse, .ics export, RRULE structured form, multi-occurrence venue page, profile LRU cache, stale-source chip, Simpleview API-key flip, RRULE recurrence-expansion JSON-LD, WebSocket-push, conditions-driven category banners, per-favorite alerts, operator-side alert preview, forecast-based alerts, multi-language, user-defined thresholds, Phase 8b filter chips, beauty_personal_care final-home, sponsor_notification outbox, 11 individual dual-place_id consolidations, 13 individual entity reviews, off-island heat list, Q Gallery next-scrape candidate, themed-group sort tuning, venue archive view, persistent map vs toggle refinement, plus white-label and native review system from the strategic list.

---

## §4 Cross-references

### §4.1 Source documents reviewed

**High-signal sources (substantive V1.5 carries):**

- `outputs/v1_5_carry_inventory_triage.md` (52-item canonical triage; CLOSED scorecard at §1 + §7; §11.1-§11.4 add 11 newer carries; last updated 2026-05-20 at commit `7143976`)
- `outputs/master_plan_phase_13_carry_forward_patch.md` (master plan amendment patch for Phase 5 carry-forward)
- `docs/maintainability/master_build_plan.md` §4 Phase 13 (lines ~549-572) + §4 Phase 8 (lines ~424-449) + §8 OQ #11, #12, #13
- `outputs/phase_7_5_prod_divergence_investigation.md` §4 + §9 (lines ~252-259 + 398-406) — F1-F7 enumeration
- `outputs/phase_7_5_close_out.md` §3 Finding #3 (hint_extractor)
- `outputs/phase_7_close_out.md` Finding #5 (hint_extractor)
- `outputs/phase_8a_prereq_verification_report.md` §8 + §11.5 + §12.4 (water temp, Nixle, NWS UA, AirNow fidelity)
- `outputs/cursor_dispatch_prompt_phase_8.md` lines 154, 196, 373-375, 386-394 (Phase 8 V1.5 exclusions)
- `outputs/cursor_dispatch_prompt_phase_8b.md` lines 143-146, 225-228, 276-285 (filter chips deferral)
- `outputs/cursor_dispatch_prompt_phase_9.md` lines ~580-625 + 767-773 (Phase 9 V1.5 exclusions + carry-forward)
- `outputs/phase_9_architecture_design.md` lines 119, 171, 333-336, 1130, 1241, 1293-1306, 1322, 1369-1374, 1600 (Phase 9 V1.5 / V2 exclusion table)
- `outputs/phase_9_event_source_research.md` lines 89, 93, 301-303, 551, 596, 608-625 (Phase 9 source-research V1.5 hooks)
- `docs/maintainability/conditions_panel_and_alerts_design.md` §10 (lines 416-441) — alerts V1.5 exclusion list
- `outputs/phase_8_nixle_agency_id_lookup.md` line 57 (LHC PD Nixle future)
- `outputs/phase_6_4_close_out.md` line 93 (themed-group sort)
- `outputs/cursor_dispatch_prompt_phase_6_5.md` line 84 (district paragraph deferral)
- `outputs/cursor_dispatch_prompt_phase_7_5_2.md` §12.8 (confab classes future hardening)
- `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` §5 + line 61 (hint_extractor explicit V1.5 framing)
- `outputs/session_close_out_2026_05_20.md` §4 (open carries)
- `outputs/session_digest_2026_05_19.md` §4 (open carries low-urgency)
- `outputs/lane_h_flag_flip_action_package.md` line 146 (hint_extractor V1.5 callout)
- `outputs/lane_m_retag_5_8_aggregators_decision_lock.md` (carry #8 split lock)
- `app/db/models.py` lines 136, 634, 1437 (SMS-ready enum, legacy-table drops, PeerRecommendation V1.5-gated)
- `app/core/background.py` line 407 (sponsor_notification V1.5)
- `app/contrib/google_types_mapping.py` lines 12, 91, 147, 218, 240, 281, 337, 359 (V1.5 sustainability carries — most CLOSED by commit `a4260ce` 2026-05-20; comments retained for archaeology)
- `tests/test_sustainability_extensions.py` line 1 (V1.5 carry test guard)
- `tests/test_phase4_ingest_client_interface.py` line 228 (final hair_salon home V1.5)
- `tests/test_phase5_7/8/9_places_load_resolver.py` (multiple V1.5 sustainability comments)
- `tests/test_phase5_10_places_load_resolver.py` line 10 (lake_recreation labels deferred V1.5)

**Also grepped (no net-new carries surfaced):**

- `outputs/phase_7_5_3_validator_polish_design_memo.md` — only references the existing post-mortem §9 V1.5 carries; nothing new.
- `outputs/phase_7_5_4_validator_polish_watch_items_design_memo.md` — Phase 7.5.4 watch items are near-term, NOT V1.5 (G4 list promiscuity + template-echo sanitization).
- `outputs/cursor_dispatch_prompt_phase_7_5_1/_5_2.md` — internal Phase 7.5 dispatch detail; carries surfaced live in the post-mortem.
- `outputs/cc_dispatch_briefs_2026_05_20.md` — references existing carries; nothing new.
- `outputs/lane_l_operator_action_items_chip_away_package.md` + `operator_action_items_*.md` — these are V1 operator-action items (NOT V1.5); see triage doc §5 + §10.
- `outputs/phase5_*_session_closeout.md` (5.0-5.11) — all consolidated into the triage doc already.
- `docs/STATE.md` — references but no net-new items.
- `outputs/phase_9_event_source_research.md` §source-3-source-5 (Library / WebTrac / aquatic) — no V1.5 carries surfaced.

### §4.2 Items NOT included (and why)

- **Phase 7.5.3 validator polish (F1, F4, F5)** — explicitly Phase 7.5.3 (near-term) per `phase_7_5_prod_divergence_investigation.md` §4 line 252-259; NOT V1.5.
- **Phase 7.5.4 watch items** (G4 list promiscuity, template-echo sanitization audit) — explicitly Phase 7.5.4 (near-term) per `phase_7_5_4_validator_polish_watch_items_design_memo.md`; NOT V1.5.
- **Phase 7.6 tier-2 LLM parser** — near-term q03 residual fix; dispatch wrapper authored 2026-05-20; NOT V1.5.
- **Phase 9.5 `event_traffic` alert wiring** — Phase 9.5 (post-events) NOT V1.5; included at #47 above only because Phase 8 dispatch flagged it.
- **Phase 12 launch checklist items** (Google Places API key rotation, .bak file pruning) — V1 operator-action; tracked in triage §6 + closed in Lane L chip-away.
- **Phase 10 polish + accessibility audit** — separate later phase; NOT V1.5.
- **Phase 11 monetization / sponsorship** — separate later phase; NOT V1.5.
- **V2-tagged items** (Eventbrite/Meetup integration, RSVP, ticketing, user-defined alert thresholds beyond V1.5 framework) — explicitly V2 per `phase_9_architecture_design.md` §14 + `conditions_panel_and_alerts_design.md` §10.
- **Phase 7 SHIPPED / Phase 6.4 SHIPPED / Phase 6.5 SHIPPED items** — completed in V1; not deferred.
- **Triage §3 sustainability-layer widenings #17-#20** — closed 2026-05-20 via commit `a4260ce` (sustainability-extensions apply). Source-code V1.5 comments remain for archaeology but the work is shipped.

---

## §5 Top-3 dispatch priorities (recommendation)

If V1.5 ships in tightly-scoped batches:

1. **Validator + ops hardening lane** (~1 week eng): items #30 (F6) + #31 (F7) + #32 (post-deploy smoke). Lowest user-visible polish; highest operator confidence. Pair with #33 hint_extractor perf if trivial.
2. **Trust-signal verifier bundle wave 1** (~1.5 weeks eng): items #17 AZDHS childcare + #18 AZDOR lodging + #19 AZRE vacation-rental. Highest yield + highest user trust impact per category.
3. **Conditions data-source upgrade** (~1 week eng + operator research): items #12 water temp alt-source + #13 Nixle replacement + #14 tighter AirNow fidelity. Honest-data UX promise upgrade; user-visible.

Remainder distributes across small operator-decide chip-aways (§2.9 + §2.10 dual-place_id + entity reviews) + Phase 9 polish backlog (§2.6).

---

*Sweep performed by sub-agent under Cowork primary supervision, 2026-05-21. Coverage: full `outputs/*.md` corpus (140+ files) + `docs/maintainability/*.md` + `docs/BACKLOG.md` (partial — file exceeds 256KB read limit; grep-only) + `app/**/*.py` + `tests/**/*.py`. Build on (does not replace) `outputs/v1_5_carry_inventory_triage.md`. Lives at `outputs/v1_5_carries_inventory.md`.*
