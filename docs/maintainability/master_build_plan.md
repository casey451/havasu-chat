# Master Build Plan — Havasu Chat V1

> **Status:** Authoritative execution plan as of 2026-05-14.
> **Audience:** Cowork primary (and all future primaries), Casey as operator, any dispatched agent (Cursor / Claude Code / sub-agent).
> **Supersedes (for execution sequencing):** `docs/STRATEGY_PIVOT_2026-05-12.md` §4 and §5. The pivot doc remains the strategic-direction-of-record; this plan is HOW we execute against it under the 2026-05-14 build-first amendment.
> **Lives alongside:** all 8 architectural design memos in `docs/maintainability/` (see §3 below).
> **How to use:** Read §0 → §3 once for context. Then operate against §4 phase-by-phase. Update §10 (decision log) as decisions land. Update §9 (calendar) as phases ship.

---

## §0 How to use this doc

This is your operating plan for the next 6-9 months. It's not a strategy doc (the pivot doc is) and it's not a design memo (the 8 design memos in `docs/maintainability/` are). It's the sequenced execution sheet that says **what gets built when, by whom, with what dependencies, and what success looks like at each step**.

When in doubt about priorities: this doc wins. When this doc disagrees with a design memo on sequencing, this doc wins. When it disagrees with a design memo on architecture or implementation detail, the design memo wins (and this doc gets amended). When this doc disagrees with the strategy pivot doc on monetization or product framing, the pivot doc wins.

Update cadence: amend after each phase ships (ship-log style — keep old phase content + add new) plus when a strategic question surfaces that resolves in this doc rather than separately.

---

## §1 Strategic context (one paragraph each)

**What we're building.** Havasu Chat is a comprehensive hyperlocal directory and AI chat product for Lake Havasu City. Covers every useful business + place + event + program for every demographic (residents, snowbirds, tourists, vacation-rental guests, families, retirees, hobbyists). Three equal front doors: browse, search, ask Hava. Strategic bet: generic internet (Google/Yelp/Facebook groups) can't compete on hyperlocal context. Bootstrapped, solo-founder.

**Build-first / sell-after sequencing.** No sales until the site is functioning as a comprehensive directory + AI chat. Cold-pitch materials already written (`docs/sponsor_outreach/verified_presence_*.md`) sit on the shelf as default-plan artifacts until monetization is locked. Monetization model kept flexible through build; finalized via cold-pitch ground-truthing at launch.

**The defensible angle.** Hyperlocal context depth. Knowing English Village fills up after 5pm Fri-Sun. Knowing the bridge backs up Sunday afternoons. Knowing snowbird season changes which businesses are open. Knowing emergency plumbers in Havasu operate differently than what Phoenix Yelp suggests. The Generic Internet can't replicate this; the data is structurally inaccessible to them.

---

## §2 What's already shipped (current state, 2026-05-14)

- **Production:** `https://havasu-chat-production.up.railway.app`. Currently at origin `ec6869a` post-Opus-handoff push. Pytest 1476 passed.
- **Schema foundations:** Category model + 12 seeded categories + category_id FKs on Provider/Program + attributes JSON + district String + Provider.slug field + backfill migration. Alembic head `f1a2b3c4d5e6`.
- **Provider profile page:** `/provider/<slug>` shipped end-to-end (route + view-model + queries + full template + 18 tests). Includes hybrid call button, freshness bands at code level (rendering polish lands in Phase 6), Hava's pick badge, claim/upgrade CTAs, /chat?q= prefill working.
- **Rate-limiter:** Option A SourceLimiter live; Google Places routed through it; scripts collapsed to use it. 16 new tests.
- **Rate-limiter §8 decisions:** all 8 locked.
- **Sponsor outreach surface:** Verified Presence pitch + extended objection FAQ + leave-behind + Day-2/Day-7 follow-up emails + referral-ask script.
- **8 architectural design memos** (full catalog in §3).
- **Pivot doc amendments** for build-first sequencing.
- **5 pre-pivot entry-point docs** updated with pivot banners.
- **Dispatch playbook** updated with session-13 lessons (5 new gotchas).
- **Provider.category backfill mapping DRAFT** (sub-agent investigation; awaiting operator review pass).

---

## §3 Foundation inventory — design memos that drive this plan

The phase content below references these. Read each when starting the corresponding phase.

| # | Memo | Purpose |
|---|---|---|
| 1 | `architecture_gaps_for_full_vision_audit.md` | 22 gaps classified by build-phase + monetization-fit |
| 2 | `place_model_design.md` | Place schema (NOTE: superseded for table-shape by unified ENTITY; content carries forward as ENTITY extension fields) |
| 3 | `account_lite_v01_design.md` | Magic-link auth via Resend; 5 tables (User + MagicLinkToken + Session + UserFavorite + Claim) |
| 4 | `background_job_infrastructure_decision.md` | Railway scheduled-jobs + FastAPI BackgroundTasks + optional Outbox table |
| 5 | `layered_scrape_strategy.md` | 5-layer pull: Google → OSM → city/state → specialized → manual |
| 6 | `conditions_panel_and_alerts_design.md` | AirNow + NWS + USGS external API integrations + alert dispatch |
| 7 | `image_storage_design.md` | Cloudflare R2 + Pillow processing + Photo schema |
| 8 | `search_index_decision.md` | Postgres FTS + pg_trgm for V1 with clean Meilisearch upgrade path |
| 9 | `boat_access_mode_design.md` | Directory-wide mode (not just a filter); JSON schema per venue type |
| 10 | `manual_recovery_checklist.md` | Operator field-trip workflow for inventory no API covers |
| 11 | `category_backfill_mapping_DRAFT.md` | 41 legacy category strings → original 12 canonical slugs (now superseded for target slugs by new-taxonomy 12) |
| 11a | `category_backfill_mapping_audit_2026-05-14.md` | Audit of #11 against the locked new-taxonomy 12. Surfaces 5 strings that map CLEANER under new taxonomy + 5 professional-services strings that NULL out (V1.5 deferral). Master-plan-hole flag at §3 led to Phase 3 amendment 2026-05-14 absorbing category-seed rewrite + audited backfill. 2 of 5 §4 lock-now items resolved 2026-05-14; remaining 3 are trivial confirmations. 4 Phase-3 review questions queued for operator. |
| 12 | `phase2_5_rate_limiter_decisions_memo.md` | 8 locked decisions for rate-limiter (already implemented) |
| 13 | `pre_pivot_doc_banner_audit.md` | 13 docs need banners (5 done; 8 remain for Phase 10) |

Plus inputs:
- `outputs/chatgpt_taxonomy_research_synthesis.md` — locked 12-category Tier 1/2/3 taxonomy + sponsor packaging recommendations
- `outputs/opus_design_handoff/README.md` — unified Hava card grammar + 4-level browse + district context paragraphs + Events as ENTITY + freshness band
- `outputs/opus_47_feature_suggestions_response.md` — 7 locked features (conditions panel, heat-aware ranking, seasonal hours, boat-access mode, crowd context, mobile-services, alerts) + 1 deferred (peer recommendations V1.5)
- `outputs/chatgpt_response_eat_and_drink_strategic_review.md` — Eat & Drink-specific UX patterns
- `outputs/chatgpt_response_home_services_category_page_spec.md` — Home Services UX spec with locked decisions

---

## §4 Phase-by-phase build sequence

13 phases total. Phases overlap intentionally where there's no dependency conflict; the rough calendar view in §9 shows this.

### Phase 1 — ENTITY schema foundation (3-4 weeks)

**Goal:** Migrate the current Provider + Place (deferred) + Event + Program separate-tables architecture into the unified ENTITY core recommended by ChatGPT's taxonomy research (locked 2026-05-14).

**Why first:** Every subsequent phase depends on this. Scrapers write to ENTITY. Category pages query ENTITY. Chat retrieves from ENTITY. Search indexes ENTITY. Image storage references ENTITY. Doing this before any other work avoids painful production data migrations later.

**Deliverables:**
- New `entities` core table with `entity_type` discriminator (commercial / place / event / program), `slug`, `name`, `description`, `last_verified_at`, `source`, `is_active`, standard timestamps
- New extension tables: `entity_categories` (M:M), `locations`, `hours`, `seasonal_hours`, `contact_points`, `features`, `offerings`, `service_areas`, `schedules`, `source_evidence`, `sponsorship_slots`
- Migration script that moves existing Provider/Program/Event rows into entities + extensions (Provider rows become `entity_type="commercial"`, Program rows become `entity_type="program"`, Event rows become `entity_type="event"`)
- Application-layer updates: app/providers/queries.py, app/providers/view_models.py, app/chat/tier2_db_query.py, app/contrib/places_client.py, app/contrib/enrichment.py, scripts/places_load.py — all queries pivoted to entities table
- Sponsor.entity_type discriminator added (Sponsor.business_id already FK-less per audit; just need to disambiguate Provider vs Place ID)
- Pytest stays green throughout — extensive regression coverage

**Dependencies:** None. Foundational.

**Effort estimate:** L+ (3-4 weeks). Touches more app code than any other lane. Sequential dispatch (not parallelizable — too much overlap on app/db/models.py and app/chat/).

**Success criteria:** All existing pytest passes against the new schema. Provider profile page renders correctly using ENTITY queries. No chat-route regression.

**Open question for Casey:** should the ENTITY migration use Alembic's `op.execute` for the data move, or a separate Python script run post-migration? Recommend Alembic batch operations for atomicity.

---

### Phase 2 — Foundation infrastructure: account-lite + image storage + search index (3-4 weeks, two parallel lanes)

**Goal:** Land the three foundational systems that everything downstream depends on. Two parallel lanes possible because they touch different parts of the codebase.

**Lane 2A — Account-lite v0.1:**
- Per `account_lite_v01_design.md` Option A (server-side session table)
- 5 new tables: users, magic_link_tokens, sessions, user_favorites (now points to entities.id), claims (now points to entities.id)
- Auth routes: `/login`, `/api/auth/request-link`, `/auth/callback`, `/logout`, `/account`
- Resend integration (operator account creation + API key wiring)
- Session middleware attaching current_user to request state
- Admin role gating on `/admin/*` (currently unprotected past Railway basic auth)
- `viewer_is_owner` flag wired into ProviderProfileVM (pre-built hook per audit)
- Magic-link email template + dev-mode flag for local development
- Effort: M-L (5-7 days dispatch)

**Lane 2B — Image storage + search index:**
- Per `image_storage_design.md` (Cloudflare R2)
- Per `search_index_decision.md` (Postgres FTS + pg_trgm)
- Cloudflare R2 bucket + custom CDN domain (operator action)
- `photos` table with polymorphic (entity_id) reference
- Pillow image processing pipeline (thumbnail/medium/hero variants + EXIF strip + WebP conversion + dedup hash)
- Upload route `/api/entities/<id>/photos` with auth + claim ownership + MIME validation + size limit
- Postgres FTS: tsvector columns on `entities` (generated columns combining name/description/extension data with weights), GIN indexes, `pg_trgm` extension + trigram indexes on name
- Search ranking heuristic (verification +30, recency +15, featured +25, etc.)
- Chat tier 2 LIKE → FTS migration in `app/chat/tier2_db_query.py:33+` (preserving the existing `_category_needle_set` synonym expansion at `:469`)
- Search bar UI + endpoint
- Effort: M-L (7-10 days dispatch)

**Dependencies:** ENTITY schema (Phase 1) must be complete before Phase 2 starts. Both lanes can run in parallel within Phase 2.

**Success criteria:** Magic-link login works end-to-end. Photo uploads land in R2 + serve via CDN. Search bar returns ranked results across entities. Chat tier 2 uses FTS instead of LIKE. Pytest stays green.

---

### Phase 3 — v1.1 schema pass: operator-curated fields + districts table + alerts schema + category taxonomy rewrite (1-2 weeks)

**Goal:** Add the operator-curated data fields and supporting tables that the Opus features + ChatGPT taxonomy work assumes. Reshape the seeded `categories` table to match the locked new-taxonomy 12 (see "Category taxonomy rewrite" deliverable below — amended 2026-05-14 per `category_backfill_mapping_audit_2026-05-14.md` §3). Single additive migration; minimal app-layer changes.

**Deliverables (all in one migration):**
- `entities.heat_exposure` (enum: indoor / shaded / outdoor / water_adjacent) — for Opus #2
- `entities.crowd_notes` (JSON, operator-curated text per venue) — for Opus #5
- `entities.is_mobile_service` (bool) — for Opus #6
- `entities.boat_access` (JSON, shape varies per venue type) — for Opus #4
- `entities.seasonal_hours` (JSON, summer/winter/shoulder blocks) — for Opus #3
- New `districts` table: `slug`, `name`, `paragraph` (operator-written rich text), `display_order`, `created_at`, `updated_at` — for Opus design district context
- `entities.district_id` (FK to districts) — replaces the current `district: String(64)` column
- `entities.featured` (bool, the "Hava's pick" flag — moved from Provider.featured to entities)
- New `alert_subscriptions` table: user_id, alert_type (enum: heat_advisory / aqi_alert / lake_hazard / event_traffic), delivery_channel (email / sms — sms-ready, V1.5 wired), paused_until, created_at
- New `alerts_dispatched` table (audit log): subscription_id, alert_type, trigger_data (JSON), dispatched_at, delivery_status, body_snippet
- New `external_conditions_cache` table: source (string PK), fetched_at, data (JSON), ttl_seconds, last_error, error_count — for Opus #1 conditions panel
- `users.preferred_mode` enum (default / boat) — for boat-access mode persistence
- New `peer_recommendations` table (per Opus #7, ships disabled-by-flag for V1.5 pilot)
- **Category taxonomy rewrite (added 2026-05-14):** rename 7 surviving slugs (`eat-and-drink` → `eat-drink`, `home-services` → `home-property-services`, `health` → `health-wellness-care`, `outdoors-and-parks` → `outdoors-parks-trails`, `shopping` → `shopping-essentials`, `auto-and-gas` → `auto-rv-fuel`, `lodging` → `lodging-vacation-rentals`) with matching display-name updates; delete `family` + `community` rows (guarded by pre-flight check for FK references); insert `classes-sports-recreation` + `public-civic-resources` rows; reset `sort_order` per synthesis §1 Tier 1/2/3 ordering. Updates the parallel hard-coded slug list at `app/home/queries.py:27-55` (CATEGORY_LABELS) and validator vocab at `scripts/ingest/validate_enrichment_csv.py`.
- **Backfill of legacy `Provider.category` / `Program.activity_category` strings → `category_id` FKs (added 2026-05-14):** uses the audited mapping in `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md` §2 (NOT the original DRAFT, which targeted the now-superseded original 12). Audited mapping covers ~24 strings that carry forward cleanly + 5 strings that map cleaner under the new taxonomy + 5 professional-services strings that NULL out (V1.5 deferred per §10 decision 2026-05-14) + Phase-3-locked decisions for ambiguous strings (`beauty_personal_care`, `tourism`, K-12/charter schools, recreational-entertainment).

**App-layer changes:** minimal for the data-field additions. The category taxonomy rewrite touches `app/home/queries.py` CATEGORY_LABELS (~25 lines) and `scripts/ingest/validate_enrichment_csv.py` vocab. Admin form extensions land in Phase 5.

**Operator workload (NEW in this phase):** (a) author 8-12 district paragraphs (~1 hour). Suggested districts: English Village, Downtown / Main Street, North End, Lakefront, Mesquite Bay, Highway 95 corridor, Site Six, Pittsburgh Point, Castle Rock area, South side. Each gets a one-paragraph description per Opus design samples ("English Village fills up after 5pm Fri-Sun — parking lots near the bridge get tight by 6..."). (b) lock the four Phase-3 review questions from the audit memo §4 lock-during-Phase-3 list (~30 min): `beauty_personal_care` final home; `tourism` triage rule; K-12 / charter / public schools → Classes-Sports-Rec vs Public-Civic; bowling/arcades/mini golf → Classes-Sports-Rec vs different home. (c) run `SELECT DISTINCT category FROM providers` against production to confirm no new free-text strings have entered via the admin form since the DRAFT audit (~15 min). **Total operator hours bumped from ~1 hr to ~2-3 hr.**

**Dependencies:** Phase 1 (ENTITY schema) must be complete.

**Effort estimate:** M migration (~5-8 days dispatch, bumped from 3-5 to absorb category rewrite + backfill) + ~2-3 hours operator authoring + decision-locks.

**Success criteria:** Migration applies cleanly; districts table populated with operator paragraphs; categories table holds the locked new-taxonomy 12 (with sort_order reflecting Tier 1/2/3); every existing Provider/Program row has `category_id` populated per the audited mapping (or NULL for the 5 professional-services strings deferred to V1.5); pytest stays green.

---

### Phase 4 — Background-jobs + layered scrape infrastructure (2-3 weeks)

**Goal:** Wire the data-ingestion pipeline so subsequent data-gathering work can run on a schedule rather than operator-triggered.

**Deliverables:**
- Per `background_job_infrastructure_decision.md` (Option A — Railway scheduled jobs + FastAPI BackgroundTasks + optional Outbox)
- One wide Railway scheduled-job service that polls all condition sources on 15-min tick (per conditions+alerts design memo's recommendation over per-source crons)
- Existing `_hourly_cleanup_loop` pattern documented in a new `app/core/background_tasks.py` module
- BackgroundTasks integration for magic-link email send (Resend)
- BackgroundTasks integration for image processing (Pillow inline; externalize if volume justifies)
- Per `layered_scrape_strategy.md`:
  - Extract shared scrape logic from `places_discovery.py` + `places_enrichment.py` into `app/contrib/google_places_scraper.py` library
  - New `scripts/places_discovery_places.py` (or `--target-type=place` flag on existing script) writing to entities with `entity_type="place"`
  - `app/contrib/google_types_mapping.py` mapping Google types → Category slug + place_type discriminator
  - New `app/contrib/osm_overpass_client.py` for Layer 2 (OpenStreetMap)
  - `scripts/osm_overpass_pull.py` per-category Overpass queries
  - `app/contrib/lhc_open_data_client.py` for Layer 3 (City of Lake Havasu Parks & Rec + AZ ROC) — operator-confirmed sources only
  - `app/contrib/specialized_apis/` modules for Layer 4 (NPI already integrated; USAPickleball + PDGA as priority adds)
  - Shared `app/contrib/ingest_reconciler.py` for cross-layer deduplication (geo proximity + name normalization + stable IDs)
- Operator monitoring: per-run log files + scheduled-job failure alerts via email

**Dependencies:** Phase 1 (ENTITY schema for write target) + Phase 3 (operator-curated fields the scrapers populate where Google returns data).

**Effort estimate:** L (10-15 days dispatch) — most complex single phase. Several parallel-eligible sub-lanes; Casey may want to dispatch the OSM client + city open data clients separately.

**Operator workload:** confirm available Lake Havasu open-data sources (Parks & Rec facility list URL/format, business license database accessibility). ~2-4 hours research.

**Success criteria:** All four automated layers run on schedule. Reconciliation logic correctly merges duplicate entities. Operator can see per-run logs.

---

### Phase 5 — Tier 1 data gathering (4-8 weeks, parallel with Phase 6)

**Goal:** Populate Tier 1 categories (Home & Property Services + Health & Wellness + Eat & Drink + On the Water + Auto/RV/Fuel + Shopping). These are the resident-critical spine; making them dense first means the site is immediately useful for residents the moment Phase 6 UI ships.

**Workflow:**
1. **Run Layer 1 (Google Places) for each Tier 1 category** — operator-triggered single batch per category. Estimated 60-200 entities per category from Google.
2. **Run Layer 2 (OSM) where complementary** — primarily for On the Water (marinas + ramps + beaches), parks-adjacent commercial.
3. **Run Layer 3 (city open data) where applicable** — Home & Property gets AZ ROC license cross-referencing.
4. **Run Layer 4 (specialized APIs)** — Health gets NPI cross-reference (already integrated). Eat & Drink gets nothing meaningful (Tripadvisor not in scope).
5. **Manual recovery for Layer 5 gaps** — small mom-and-pop businesses, hobbyist venues, ephemeral locations. Per `manual_recovery_checklist.md` workflow. Estimated 20-40 manual-recovery items for Tier 1 categories.
6. **Operator-curated field entry** — heat_exposure, crowd_notes, boat_access details for restaurants and marinas, seasonal_hours where they differ. Each entity gets ~5-15 minutes of operator review.

**Estimated totals at end of Phase 5:**
- Home & Property Services: 120-220 entries
- Health, Wellness & Care: 30-70 entries
- Eat & Drink: 90-140 entries
- On the Water: 40-90 entries
- Auto, RV & Fuel: 50-100 entries
- Shopping, Grocery & Essentials: 60-120 entries
- **Total Tier 1: 390-740 entries**

**Dependencies:** Phase 4 (scrapers + admin form for operator entry). Runs in parallel with Phase 6 UI work.

**Effort estimate:** Operator workload ~60-100 hours spread over 4-8 weeks. Engineering effort minimal (admin form already shipping in Phase 4).

**Success criteria:** Each Tier 1 category has enough verified inventory that the corresponding category landing page (built in Phase 6) renders 15+ entries per default filter.

---

### Phase 6 — Tier 1 UI build (4-6 weeks, parallel with Phase 5)

**Goal:** User-facing pages for Tier 1 categories. This is when the directory starts to feel real.

**Critical first deliverable: Unified Hava card grammar.** Per Opus design handoff §6.1. Single Jinja partial `app/templates/components/hava_card.html` that renders any ENTITY (commercial / place / event) in any context (category page, search results, group landing, profile reference). Place vs event differentiation via status-line color (green vs lake-blue) + content ("Open until 10pm" vs "Tonight at 6:00pm"), NOT via separate templates or chrome. Same shell everywhere.

**Other deliverables (after card lands):**
- Honest freshness band on cards (colored dot) + on profile pages (colored band at top) per Opus design §6.3
- Category landing pages for Tier 1 (6 pages): each has the locked 3-row chip system (cuisine/sub-trade · district · operational+time), sort dropdown, sponsor slot, organic stream of unified Hava cards, editorial copy footer, map toggle, pagination
- District context paragraphs rendering on every entity profile in that district (single SQL join from entities → districts)
- Boat-access mode toggle in header (URL param + localStorage + user preference); map water-overlay when active; profile-page boat-access top-of-fold region when active
- Map view (Leaflet + OSM) with marker clustering
- Search bar in homepage hero + category page headers
- Time-aware default ranking + heat-aware bias (Opus #2)
- Seasonal hours rendering on profile pages (Opus #3)
- Homepage with hero + Ask Hava box + Today in Havasu conditions strip (data hookup deferred to Phase 8) + 8 themed group tiles for browse
- Themed group landing pages for Tier 1 groups (Eat & Drink, Health & Fitness, On the Water, Home & Auto) — bundle related categories under each
- Provider profile already has Phase A+B; extend with "What's on at this venue" region (Phase 9 hooks; renders empty until Phase 9)
- Mobile-first responsive throughout (bottom-sheet patterns, swipe gallery, sticky action elements)

**Dependencies:** Phase 1 (ENTITY) + Phase 2 (auth + photos + search) + Phase 3 (operator-curated fields + districts). Runs in parallel with Phase 5 data gathering.

**Effort estimate:** L+ (15-25 days dispatch). Multiple parallel sub-lanes possible: unified card (1 lane); category templates (1 lane per ~3 categories); map view (1 lane); homepage (1 lane); themed group landing (1 lane).

**Success criteria:** All 6 Tier 1 category pages render correctly with populated data. Unified Hava card renders identically across all surfaces. District context paragraph appears on every Tier 1 entity's profile.

---

### Phase 7 — Tier 2 UI + chat integration (3-4 weeks)

**Goal:** Extend the directory to Tier 2 categories + wire chat to the populated directory.

**Deliverables:**
- Category landing pages for Tier 2 (3 pages): Outdoors/Parks/Trails, Lodging & VR, Pets — same template pattern as Phase 6
- Themed group landing pages for Tier 2 groups (Outdoors, Stay)
- Chat tier 2 / tier 3 wired to query ENTITY table (replaces pre-pivot River Scene events catalog query at `app/chat/tier2_db_query.py:33+`)
- Chat awareness of boat-access mode (when active, queries filter by `boat_access IS NOT NULL`; tier 3 LLM prompt gets "user is in boat mode" preamble)
- Chat awareness of conditions (when heat advisory active, ranking shifts toward indoor venues per Opus #2; when AQI bad, similar)
- HALT 3 close-out work — confabulation guardrails ship; `FEATURE_FLAG_DISCLOSURE_RENDERER` flipped to `true` if validation passes
- Cross-entity chat queries ("where can I take my dog for breakfast?") work — chat returns dog-friendly restaurants AND dog parks interleaved
- Snowbird-return view on homepage (logged-in users active October-April see "what's reopened" panel)

**Operator workload:** run Tier 2 data gathering in parallel (same workflow as Phase 5 but smaller volume — 75-175 entries total across the 3 Tier 2 categories).

**Dependencies:** Phase 1 (ENTITY) + Phase 6 (unified card grammar). Tier 2 data gathering runs alongside.

**Effort estimate:** M-L (10-14 days dispatch).

**Success criteria:** Chat works across all Tier 1 + Tier 2 entities. HALT 3 close-out passes. Cross-category queries return interleaved results.

---

### Phase 8 — Trust layer + conditions panel + alerts (2-3 weeks)

**Goal:** Land the Public & Civic Resources category (the trust/retention layer per ChatGPT taxonomy) + the Opus #1 + #8 conditions infrastructure.

**Deliverables:**
- Public & Civic Resources category page (library, transit, visitor info, utilities, airport, senior resources, payment/licensing links, civic orgs) — entities populated via Layer 3 (city open data) primarily
- Conditions data fetching infrastructure: AirNow (AQI) + NWS (weather + heat advisory + sunset) + USGS (Lake Havasu gauge — operator confirms specific gauge ID) running on Railway scheduled job every 15 min
- `external_conditions_cache` table populated; reads transparently cached
- "Today in Havasu" conditions strip live on homepage with honest staleness indicators ("Updated 12 min ago")
- Alert dispatch evaluation job (every 15 min): reads cache, compares against trigger thresholds per alert_type, queries opted-in subscriptions, dispatches email via Resend BackgroundTasks
- Alert subscription UI on `/account/alerts`
- Alert email templates with the texture-moat venue-context mapping (heat advisory email lists indoor alternatives from user's favorites)
- Per-alert dedup: same alert_type not fired for same user more than once per 6 hours

**Dependencies:** Phase 2 (account-lite for User schema), Phase 3 (alert tables), Phase 4 (background jobs), Phase 6 (favorites system for venue-context mapping). Opus's hidden-dependency warning: Phase 5 + 6 must have tagged enough entities with `heat_exposure` for the alert venue-context mapping to fire (~30 entities minimum).

**Effort estimate:** M (5-8 days dispatch). Plus operator work to register AirNow API key, confirm USGS gauge ID, check City of Lake Havasu emergency-notification feed format.

**Success criteria:** Conditions panel updates every 15 min. Alerts fire correctly for heat advisory / AQI / lake hazard / event traffic. Alert emails include relevant venue-context recommendations.

---

### Phase 9 — Schedule-heavy expansion: Events + Classes/Sports/Recreation (3-4 weeks)

**Goal:** Tier 3 categories. These are deferred per ChatGPT taxonomy recommendation because refresh/expiry/cancellation tooling is real overhead — better to land them when the schedule infrastructure can support them properly.

**Deliverables:**
- Events as ENTITY type fully wired (already in schema from Phase 1; this phase wires the UX)
- RRULE-based recurrence handling (Python `dateutil.rrule` or `recurrent`)
- Event scraper subsystem: scrape Chamber community calendar + Go Lake Havasu events + RiverScene Magazine + city/library calendars
- Freshness anchor for scraped events is scrape timestamp (tighter decay curve: green <7 days / amber 7-21 / red >21)
- Capacity/availability OPTIONAL — only display when venue publishes real data; otherwise omit (NO manufactured scarcity)
- Events category page with date-aware filters (today / this weekend / next month / by date)
- Classes, Sports & Recreation category page — recurring schedules + age bands + drop-in vs registration filters
- "What's on at this venue" region on profile pages (the Phase 6 hook is filled in here)
- Integrated stream on themed group pages (Phase 6 ships static; Phase 9 makes it actually interleave events + places)
- Themed group landing for "Things to Do" group (was deferred from Phase 6)
- Event-card rendering via unified Hava card (status line: "Tonight at 6:00pm" lake-blue) — same card shell as place cards

**Dependencies:** All prior phases. Optional but ideally ships before launch.

**Effort estimate:** L (12-18 days dispatch). Event scraper subsystem is the longest sub-lane.

**Success criteria:** Events appear correctly in category pages, themed groups, profile "what's on" regions, and chat responses. RRULE recurrence handles weekly classes correctly. Schedule freshness band reflects scrape recency.

---

### Phase 10 — Polish + accessibility + pre-launch hardening (2-3 weeks)

**Goal:** Final pass before launch.

**Deliverables:**
- Mobile polish: bottom-sheet patterns finalized, swipe interactions tested across iOS Safari + Android Chrome, sticky elements behave correctly
- Accessibility audit: keyboard nav, screen reader testing, color contrast review, ADA-style audit
- Performance optimization: Cloudflare R2 CDN tuning, static asset serving moved off FastAPI workers (CDN edge), image lazy-loading, cache headers tuned, Postgres query EXPLAIN review
- Apply remaining 8 pivot-notice banners to less-critical pre-pivot docs (per `pre_pivot_doc_banner_audit.md` §2 priority list)
- Sponsor outreach folder banner audit: 6 pre-pivot files reference old $59/$179/$399 tier structure — either delete or banner-stamp as "pre-pivot historical"
- Final QA pass across all 12 categories + chat + map + boat-access mode + alerts
- Sub-trade taxonomy locked (the `attributes.sub_trades` shapes per category that scrapers populate)
- 8 open design questions from Opus handoff resolved + folded into final templates

**Dependencies:** Phase 9 complete. No new feature work in this phase — polish + harden only.

**Effort estimate:** M (5-8 days dispatch).

**Success criteria:** Mobile UX clean, accessibility audit passes, performance hits target (< 1.5s page load on 4G mobile for category pages).

---

### Phase 11 — Monetization decision + wiring (2-3 weeks)

**Goal:** Lock the monetization model and wire it. Casey has kept this flexible through build; this is the lock point.

**Deliverables:**
- Operator decision: which monetization model wins? Default fallback (Verified Presence + Category Visibility + Seasonal Takeover) is in hand. ChatGPT taxonomy recommended changes (intent-cluster pricing $499-$1,250+ for emergency/high-intent, $500-$1,500+ for water/boating peak, $249-$749 for dining/lodging/district, $99-$299 for long-tail; season + district + intent bundles for seasonal takeovers; sponsorship NEVER overrides trust-sensitive ranking in Health/Pets/Civic). Casey decides whether to take these or stick with the default.
- Stripe (or alternative) integration for subscription billing
- Sponsor claim flow + edit UI: merchant logs in via account-lite, claims their entity, verifies (Casey manually confirms via phone for V1 — automated verification is V2), edits their listing
- Per-merchant analytics dashboard: views, calls, directions, Ask Hava handoffs, conversion timeline. Visible value of paid tier.
- Sponsor slot rendering on category pages (already shipped in Phase 6 with no paying sponsors; this phase wires the actual sponsor assignment flow)
- Sponsor disclosure rendering via existing `disclosure_renderer` pipeline — already plumbed
- Test with friendly merchant cohort (3-5 merchants) before broader rollout

**Dependencies:** All UI phases complete (need a working product to demo). Account-lite (Phase 2) live.

**Effort estimate:** M-L (8-12 days dispatch) + operator decision time on monetization model.

**Success criteria:** Friendly cohort can claim, edit, view analytics, and (optionally) pay. End-to-end flow works.

---

### Phase 12 — Launch (1-2 weeks)

**Goal:** Ship to the public.

**Deliverables:**
- Final QA across the full product
- Domain + DNS setup (the actual product URL)
- Soft launch: limited promotion via Havasu News, local Facebook groups, Chamber of Commerce partnership, friend network
- Cold-pitch sales motion kickoff: Casey walks into businesses with the cold-pitch materials (verified_presence_pitch.md + companions) already on the shelf
- Operational dashboards confirmed working (sponsor pipeline, daily user metrics, error tracking)
- Production runbook for incidents
- Ramp to full launch as initial sponsors come online + word spreads

**Dependencies:** All prior phases.

**Effort estimate:** M (4-8 days) + operator field-work for soft launch.

**Success criteria:** Soft launch successful; first paying sponsor (or first 5 free claimed listings if monetization model defers payment). Site stable under load.

---

### Phase 13 — V1.5 features (post-launch, ongoing)

Items intentionally deferred from V1 to post-launch. Build as time + revenue allow:

- Peer recommendations (Opus #7) — 5-10 merchant pilot to test reciprocal-back-scratching risk
- SMS alerts via Twilio (schema is SMS-ready from Phase 3; just code switch + Twilio account)
- Accessibility profile data collection (structured ADA fields per Opus design deferral)
- Provider.category → category_id backfill (the OPEN P2 ticket in BACKLOG)
- Owner-uploaded video (deferred from image storage design)
- Bookings / reservations (if merchant demand justifies)
- Itinerary builder (Phase 3 of original pivot doc)
- Real-time fuel prices / room availability / launch conditions (dynamic data — research API options when justified)
- White-label for other small cities (genuinely V3; ignore unless inbound demand)
- Native review system (still deferred unless review-war dynamics in Havasu prove otherwise)

---

## §5 Dependency graph

```
Phase 1 (ENTITY) ─┬─→ Phase 2A (account-lite) ─┬─→ Phase 3 (v1.1 schema)
                  ├─→ Phase 2B (R2 + search)   ┤
                  └─→ Phase 3 (v1.1 schema) ────┘

Phase 3 ──→ Phase 4 (bg-jobs + scrapers) ──┬─→ Phase 5 (Tier 1 data gathering)
                                            └─→ Phase 6 (Tier 1 UI build)
                                              ↑ parallel ↑

Phase 6 ──→ Phase 7 (Tier 2 + chat)
Phase 6 ──→ Phase 8 (trust + conditions + alerts)

Phase 7, 8 ──→ Phase 9 (Events + Classes/Sports)

Phase 9 ──→ Phase 10 (polish + accessibility)
                ↓
              Phase 11 (monetization)
                ↓
              Phase 12 (launch)
                ↓
              Phase 13 (V1.5+)
```

Parallel-eligible:
- Phase 2A and Phase 2B run alongside each other
- Phase 5 (data gathering) and Phase 6 (UI build) overlap heavily
- Phase 7 and Phase 8 can run alongside each other
- Phase 9 sub-lanes (event scraper + classes/sports + integrated stream) can parallelize internally

---

## §6 Operator workload schedule

Engineering effort runs through dispatched lanes (Cursor / Claude Code / sub-agents). Casey's hands-on operator time is bounded but real. Major operator activities:

| Activity | Phase | Estimated time |
|---|---|---|
| Confirm available LHC open-data sources (Parks & Rec, business licenses) | Phase 4 prep | 2-4 hours |
| Register AirNow API key + confirm USGS Lake Havasu gauge ID + check city emergency-notification feed format | Phase 8 prep | 2-3 hours |
| Author district paragraphs (~8-12 paragraphs) | Phase 3 | ~1 hour |
| Lock 4 Phase-3 audit-memo review questions (`beauty_personal_care`, `tourism`, K-12 schools, recreational-entertainment) + run `SELECT DISTINCT category` against production | Phase 3 | ~1 hour |
| Review + lock Provider.category backfill mapping (audited 2026-05-14; 2 of 5 §4 lock-now questions resolved; remaining lock-now items 4 + 5 are trivial single-mapping confirmations) | Anytime (best at Phase 3 start) | ~30 min |
| Field-trip Layer 5 manual recovery for Tier 1 inventory gaps | Phase 5 | ~30-50 hours over 4-8 weeks |
| Field-trip Layer 5 for Tier 2 + Tier 3 inventory | Phases 7 + 9 | ~20-40 hours additional |
| Admin form data entry: boat_access details, heat_exposure tagging, crowd_notes, seasonal_hours where they differ | Phases 5 + 7 + 9 | ~40-80 hours over the build |
| Operator decision on monetization model | Phase 11 | 1-3 hours active decision time |
| Cold-pitch sales motion at launch | Phase 12 onward | 5-10 hours/week ongoing |

**Total estimated operator hours over the build: ~120-200 hours.** Spread over 7-9 months that's manageable alongside dispatching engineering lanes. Field-trip days are full-day blocks (~8 hours each) so Casey wants to batch them — Saturdays during cooler months especially.

---

## §7 Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Solo-founder burnout — engineering dispatch + operator field-work + sales over 6-9 months is significant load | High | Build-first sequencing means no sales pressure until month 7+. Sub-agent dispatches handle most engineering load. Field-trips batched into full-day blocks. Hire a Havasu-based BDR by month 6 if revenue justifies. |
| 2 | ENTITY schema migration introduces regression risk | High | Extensive pytest coverage required. Phase 1 dispatched as a single sequential lane (not parallel) to keep schema changes coherent. Staging environment validation before production migration. |
| 3 | User adoption — locals may continue using Google/Facebook groups | Medium-high | Hyperlocal context depth (district paragraphs + boat-access mode + conditions panel + crowd context) is the moat. Soft launch lets us measure adoption signals before full marketing push. If adoption clearly fails by month 9, pivot or pause. |
| 4 | Layer 5 manual recovery workload too large | Medium | Layer estimates show ~80-90% automated coverage via Layers 1-4. Manual recovery is the 10-20% gap. If gap turns out larger, defer Tier 3 categories or partner with Chamber for data sharing. |
| 5 | Sponsor packaging recommendations from ChatGPT (intent-cluster pricing) may not match what cold-pitch ground-truthing reveals | Medium | Monetization is flexible by design. Default fallback (Verified Presence $79 etc.) is also fine. Lock pricing after 10-20 cold-pitch reps in Phase 12. |
| 6 | Schedule-heavy expansion (Events + Classes) refresh burden | Medium | ChatGPT recommended deferring to Phase 9 specifically because of this. Schedule freshness band makes staleness visible. Scrape-timestamp anchor minimizes false-fresh signals. |
| 7 | HALT 3 close-out (chat confabulation guardrails) was deprioritized post-pivot and may be larger than expected | Medium | Audit confirmed the close-out scaffolding exists. Phase 7 includes the close-out work. Schedule it as a dispatch lane with explicit halt-and-report acceptance criteria. |
| 8 | Cloudflare R2 + custom CDN domain setup is operator action | Low | Documented in image_storage_design.md §8. ~2 hours operator work in Phase 2. |
| 9 | Production Postgres performance under 1000+ concurrent users | Medium (Phase 10/11) | DB connection pool sizing fix (S effort per audit). Slowapi Redis-backed store (post-Phase 4 once background-job infrastructure has Redis option). CDN for static assets handles most concurrency load. |
| 10 | Chat depends on accurate `heat_exposure` tagging for alert venue-context mapping (Opus hidden dependency) | Medium | Phase 5/6 operator workload prioritizes heat_exposure tagging for top ~30 entities by traffic before Phase 8 alerts ship. |

---

## §8 Open strategic questions

These need operator decision but most can fold into specific phases rather than blocking the master plan. Numbered for reference; recommended phase to resolve:

1. **City-bounded vs cross-border surfaces** (Parker, Havasu Landing, Topock for some intents) — Phase 4 scraper scope. Recommend city-bounded for V1; cross-border in V2 if user demand surfaces.

2. **Google Place ID + Yelp ID joining for dedupe and entity resolution** — Phase 4 scraper architecture. Recommend yes for Google Place IDs (we already store `google_place_id`); skip Yelp IDs unless we add Yelp Fusion API which isn't in current plan.

3. **Dynamic / semi-dynamic data (fuel prices, room availability, launch conditions)** — V1.5 or V2 question. Defer.

4. **Vacation-rental permits joined to lodging records** — Phase 7. Recommend yes if LHC publishes the data; check during Phase 4 source confirmation.

5. **Professional services as separate expansion layer (lawyers, accountants, insurance)** — V1.5 or V2. Currently absorbed into Home & Property + Community-replacing categories. Defer.

6. **Sponsorship strictness rules in Health / Pets / Civic** — Phase 11. Recommend per ChatGPT: NEVER override organic ranking on emergency or care-critical queries; sponsorship increases exposure within clearly disclosed bounds only.

7. **First-party neighborhood / district model (districts as entities vs strings)** — Phase 3. Recommend yes, full `districts` table per Opus design. Eight to twelve districts in Havasu means small table with high leverage.

8. **Themed group cuts (8 right? Real Estate as 9th?)** — Phase 6. Recommend stick with 8; Real Estate folds into Home & Auto for V1; revisit if user behavior shows the grouping is wrong.

9. **Place vs event visual differentiation** — Phase 6. Currently status-line color + content only (subtle). Fallback if user testing shows too subtle: add small "Event" word tag (NOT colored background).

10. **Persistent map vs toggle on desktop category pages** — Phase 6. Recommend default-on with collapse option.

11. **Ask Hava as search vs parallel surfaces** — Phase 6. Recommend keep separate Search input + Ask Hava button initially; collapse into single intelligent input is a V1.5 candidate after user data shows behavior.

12. **Capacity display on schedule entries** — Phase 9. Only honest if venue publishes real availability. Otherwise omit. No manufactured scarcity.

13. **SMS alerts in V1 or V1.5** — Phase 8. Recommend defer to V1.5 per `conditions_panel_and_alerts_design.md` §10. Schema is SMS-ready; just no Twilio integration in V1.

14. **Monetization model lock** — Phase 11. Operator decision based on cold-pitch ground-truthing.

---

## §9 Rough calendar view (6-9 months at solo-founder pace)

| Month | Phase(s) active | Major milestones |
|---|---|---|
| Month 1 | Phase 1 (ENTITY schema) | Schema migrated; app code on ENTITY; pytest stays green |
| Month 2 | Phase 2A + 2B parallel; Phase 3 toward end | Account-lite + R2 + search shipped; v1.1 schema migration applies |
| Month 3 | Phase 4 (scrapers); Phase 5 starts | Background jobs running; Tier 1 Layer 1 scrape complete |
| Month 4 | Phase 5 + 6 parallel | Tier 1 categories populated; unified Hava card grammar shipped |
| Month 5 | Phase 6 + Phase 7 starts | All Tier 1 category pages live; chat wired to ENTITY |
| Month 6 | Phase 7 + 8 parallel | Tier 2 categories live; HALT 3 close-out passes; conditions panel live |
| Month 7 | Phase 9 | Events + Classes/Sports/Recreation live; schedule integration complete |
| Month 8 | Phase 10 + 11 | Polish + accessibility + monetization wired |
| Month 9 | Phase 12 + Phase 13 starts | Launch + early V1.5 features |

This is aggressive but achievable if engineering output stays steady, no major rework hits, and operator field-trip workload doesn't drag. Realistic worst case: 11-12 months if any phase doubles its estimate.

---

## §10 Decision log

Decisions recorded as they're made. Each decision: date, what was decided, by whom, replaces what.

| Date | Decision | Decided by | Supersedes |
|---|---|---|---|
| 2026-05-12 | Pivot from chat-first to directory-first; three front doors (browse + search + ask) | Operator | Original chat-first product framing |
| 2026-05-13 | Pivot §8.1 — 12 categories locked (original list: eat-and-drink, events, family, home-services, etc.) | Operator | — |
| 2026-05-13 | Pivot §8.2 — Place model deferred to Phase 2 | Operator | — |
| 2026-05-13 | Pivot §8.3 — Resend for magic-link auth | Operator | — |
| 2026-05-13 | Pivot §8.4 — Leaflet + OSM tiles for maps | Operator | — |
| 2026-05-13 | Phase 2.5 rate-limiter §8 decisions (8 decisions locked) | Operator + Cowork primary | — |
| 2026-05-14 | Build-first / sell-after sequencing; full vision is everything Lake Havasu | Operator | Pivot §4/§5 parallel build-and-sell sequencing |
| 2026-05-14 | Place model promoted from Phase 2 to Phase 1 of build sequence | Operator | Pivot §8.2 (effective amendment to LOCKED status) |
| 2026-05-14 | Opus 4.7 first round — 7 of 8 features in V1 (conditions panel, heat-aware ranking, seasonal hours, boat-access mode, crowd context, mobile-services, alerts); peer recs deferred to V1.5 pilot | Operator | — |
| 2026-05-14 | Boat-access elevated from filter chip to directory-wide mode | Operator | Original Eat & Drink ChatGPT review framing |
| 2026-05-14 | ChatGPT taxonomy research — 12 categories restructured: deletes Family + Community; adds Classes/Sports/Rec + Public/Civic; Tier 1/2/3 sequencing | Operator | Original 12-category locked list (rename most, replace two) |
| 2026-05-14 | Unified ENTITY schema (single core table + extensions) | Operator | Place model design Option A (separate places table); supersedes the place_model_design.md recommendation |
| 2026-05-14 | Opus 4.7 second round — unified Hava card grammar + 4-level browse hierarchy + 8 themed groups + district context paragraphs + Events as third ENTITY type + honest freshness band | Operator (implicit acceptance via task completion) | — |
| 2026-05-14 | Revenue optimization deferred per build-first sell-after; cold-pitch ground-truthing at launch | Operator | — |
| 2026-05-14 | Category taxonomy rewrite + audited backfill mapping land in Phase 3 v1.1 schema pass (NOT Phase 1B, NOT a standalone Phase 1.5 ticket, NOT deferred to V1.5). Phase 3 effort bumps from ~3-5 days + 1 hr operator to ~5-8 days + 2-3 hr operator. Resolves the master-plan hole flagged by `category_backfill_mapping_audit_2026-05-14.md` §3. | Operator | Phase 3 deliverables list pre-audit (silent on category-seed rewrite) |
| 2026-05-14 | Professional-services strings (`insurance`, `financial`, `legal`, `real_estate`, `professional_services`) NULL category_id during Phase 3 backfill; deferred to V1.5+ per synthesis §7 Q5. NULL operator-queue is the honest disposition; do NOT force into `public-civic-resources` or `home-property-services` for V1. Phase 13 V1.5 lane revisits if cold-pitch demand justifies a dedicated Professional Services category. | Operator | DRAFT mapping's "community catch-all" target (the catch-all no longer exists under new taxonomy) |

---

## §11 Living-document principles

This doc gets updated. Specifically:

- **After each phase ships:** add a "Shipped:" line under the phase header with date + commit SHA + actual effort vs estimate. Don't delete the original phase content.
- **When a new strategic decision lands:** add to §10 decision log. Update affected phases inline if sequence/scope changes.
- **When a design memo gets superseded or amended:** update §3 with the supersession + reference the new doc.
- **When a risk materializes:** add to §7 with date observed and resolution; don't delete the original risk entry.
- **When a phase's effort estimate is clearly wrong (observed during build):** amend in place with a note explaining the delta.

The decision log (§10) is the audit trail. The phase content (§4) is the operating sheet. The risk register (§7) is the alert layer. Together they're the operating doc for the next 6-9 months.

If a future agent reads this doc and finds it badly outdated relative to the actual code state, that's a hygiene failure on whoever shipped the last phase without updating here.
