# Cursor Dispatch Prompt — Phase 8 (conditions panel + alert dispatch + chat live-conditions wiring; optional 8a/8b split for cat-13)

> Paste-into-Cursor prompt for Phase 8 per master plan §4 Phase 8 (lines 401–419) + `outputs/phase_8_architecture_design.md` (1050-line Plan-agent ADR-level design) + `outputs/phase_8_operator_prereq_checklist.md` (patched 2026-05-20 with research corrections + LHC Nixle agency ID resolution). Phase 8 ships the trust + retention layer: real conditions data driving the homepage "Today in Havasu" strip + the chat ranking that's been reading a stub since Phase 6.3 + the alert subscription + dispatch subsystem that Opus #1 + #8 originally designed.
>
> **DISPATCH STATUS — BLOCKED pending prereq amendments (2026-05-19).** Live verification at `outputs/phase_8a_prereq_verification_report.md` surfaced P0 scope changes: USGS `09427500` reports only `00065` gauge height + `00054` reservoir storage (no water temp / discharge); USGS `09427520` is historic-only since 2006; LHC Nixle agency `3726` RSS silent since 2021-09-01. **Do NOT paste this wrapper until operator confirms amended scope below.** Phase 7 SHIPPED at `0a305e0`; Phase 7.5 SHIPPED at `b701759` (2026-05-20); Phase 7.5.1 SHIPPED at `fd695d2` (2026-05-19, prod-divergence routing fixes); Phase 7.5.2 SHIPPED at `64799d5` (2026-05-20, HALT 3 validator hardening); docs ledger at `c81f0d0`. Phase 7.6 in flight at time of audit (tier-2 LLM-parser divergence). Alembic head still `c9d0e1f2a3b4` (no migrations shipped since Phase 7). Phase 7 close-out at `outputs/phase_7_close_out.md`. Lane E dispatch-readiness re-check 2026-05-20: file scope disjoint from 7.5.1/7.5.2/7.6; STUB_CURRENT_TEMPERATURE_F constant + compute_card_rank signature unchanged; alembic head unchanged; pytest baseline now ~2193 (see body §0 update below).
>
> **Phase 7 ship caveats Phase 8 should be aware of:**
> - HALT 3 `FEATURE_FLAG_DISCLOSURE_RENDERER` is still `false`. Phase 7.5 polish lane will flip it after closing the 10 validator failures. **Phase 8 does NOT touch the flag.**
> - Chat conditions-awareness only fires through the ENTITY catalog path (`prefers_entity_catalog()` returns True). `open_now` + `entity_name-only` queries route through the legacy events/programs SQL path and don't get heat-bias applied. When Phase 8 swaps `STUB_CURRENT_TEMPERATURE_F` → `read_current_temperature_f()`, the swap is automatic for ENTITY-catalog queries; legacy-path queries continue using the stub fallback (acceptable; legacy-path queries don't typically need conditions-aware ranking).
> - Phase 7 + Phase 6.4 collision was operationalized via the alembic-collision gotcha. Phase 8's migrations chain off `c9d0e1f2a3b4`; verify SINGLE head before authoring.
>
> **Gating dependencies:** Phase 6.1 SHIPPED (`fd16e7a`) + 6.2 (`3948add`) + 6.3 (`5ebee46`) + 6.4 (`96c915d`); Phase 5 multi-phase data-population COMPLETE at `dcf3dd4` (1,314 active entities; cat-13 thin at 4 entries); Phase 7 SHIPPED at `0a305e0` (chat ENTITY wiring + boat-mode + conditions-awareness via STUB + HALT 3 + cross-entity + snowbird-return view); parks-rec-scrapes sidecar `f6a7b8c9d0e1` SHIPPED at `532d48b`. **Phase 8 consumes:** Phase 4 background-jobs framework (`with_retry`, Outbox); Phase 3.1 schema (`external_conditions_cache` table + `alerts_dispatched` table both already exist per design doc §2 — verify); Phase 6.5 "Today in Havasu" conditions strip empty-placeholder anchor at `<!-- conditions-strip-anchor -->`; Phase 6.3 `app/core/ranking.py` `STUB_CURRENT_TEMPERATURE_F` constant (swapped for live read in Phase 8); Phase 7's chat-conditions-awareness import chain (also swapped for live read); Phase 2A account-lite for `/account/alerts` subscription UI; Phase 4 Outbox + Resend email surface for alert dispatch.
>
> **No parallel lane planned with Phase 8.** Per the 2026-05-20 alembic-collision gotcha (`outputs/dispatch_channels_alembic_collision_gotcha_draft.md`), Phase 7 + Phase 8 dispatching in parallel risks alembic revision-DAG collision (Phase 8 ships at least one new migration; Phase 7's User.last_active_at migration question if it lands also chains off `f6a7b8c9d0e1`). **Recommended posture: serialize.** Phase 7 ships first; Phase 8 dispatches against post-Phase-7 head.
>
> **Operator prereq status (per `outputs/phase_8a_prereq_verification_report.md` + `outputs/phase_8_operator_prereq_checklist.md`):**
> 1. **AirNow API key** — operator-action-pending (register + smoke-test per checklist §2)
> 2. **USGS single site `09427500`** — ✅ live; parameters **`00065` (gauge height, ft) + `00054` (reservoir storage, acre-ft)** only. **Dropped:** `00010` water temp, `00060` discharge, secondary site `09427520` (historic-only since 2006)
> 3. **LHC Nixle** — **DROPPED FROM V1** per verification report §4 Option A (RSS silent since 2021; staff-recall content only). `lake_hazard` trigger uses NWS AZZ002-zone keyword match (`nws_alerts_lhc_zone` cache surface, inland-LHC keyword set per §11.2) + USGS gauge-height-delta heuristic instead. Marine surface also dropped per §11 (NWS marine zones cover Coastal + Great Lakes only; inland LHC not in scope).
>
> HALT if AirNow key unresolved. USGS/Nixle scope is locked to the amended constants below — do not restore dropped surfaces without operator re-lock.
>
> **Operator decision-lock status:** the 6 Phase 8-relevant decisions are locked per the architectural design (`outputs/phase_8_architecture_design.md`):
>
> 1. **Sub-phase split — 8a (conditions + alerts) + 8b (cat-13 expansion).** This wrapper covers **Phase 8a only**. Lane A (conditions data infrastructure + Today in Havasu strip + chat live-conditions wiring) + Lane B (alert dispatch + subscription UI + email templates + venue-context mapping + dedup). Lane C (cat-13 Public & Civic Resources expansion via Layer 3 + Layer 5) is **Phase 8b** — separate micro-dispatch after 8a ships. Per design doc §1 split recommendation.
> 2. **Fetcher subsystem shape — per-source Railway scheduled jobs.** Four services with different cadences: AirNow (30 min), NWS alerts (15 min), USGS (30 min), NWS forecast (10 min — see §3.2.4 below). Source-isolation pattern: AirNow failure doesn't crash NWS reads. Reuses Phase 4 `with_retry` envelope.
> 3. **External conditions cache schema reuse** — `external_conditions_cache` table from Phase 3.1 already exists per design doc §2. Phase 8 verifies + uses; no new migration UNLESS the existing schema needs additive columns. Design doc §2 enumerates expected columns; verify at step 1.
> 4. **Threshold definitions** — per design doc §6 (amended post-verification): heat_advisory fires on NWS Heat Advisory / Excessive Heat Warning / Heat Watch; aqi_alert fires on AirNow AQI > 150; **lake_hazard** fires on NWS marine forecast OR Special Weather Statement keywords {flood, drowning, capsize, rescue, evacuation, advisory, small craft} OR optional USGS gauge-height drop > `LAKE_HAZARD_GAUGE_DROP_FT` (default 2.0 ft in 24h) at site `09427500`; **no Nixle ingest**; event_traffic deferred to V1.5 per master plan §8 OQ #12.
> 5. **Per-alert dedup window** — 6 hours per user per alert_type. Uses existing `alerts_dispatched` table (Phase 3.1).
> 6. **STUB swap pattern** — `STUB_CURRENT_TEMPERATURE_F = 105.0` in `app/core/ranking.py` becomes `read_current_temperature_f()` function reading from `external_conditions_cache`. Phase 6.3 ranking + Phase 7 chat tier-3 preamble both swap atomically via this single-source-of-truth helper.
>
> **Author note:** authored 2026-05-20 by Cowork primary at the post-`616fd8b` Cursor-Phase-7-in-flight session. Two SHA-patch slots — fill post-Phase-7-ship. Architecture design at `outputs/phase_8_architecture_design.md` (1050 lines) is the authoritative scope spec. Prereq checklist at `outputs/phase_8_operator_prereq_checklist.md` (post-research patches) is the operator-side status board. Nixle agency ID lookup at `outputs/phase_8_nixle_agency_id_lookup.md` provides the deep verification.
>
> **Clipboard pipeline** (PowerShell 5.1 truncates large payloads; uses Notepad as synchronous router per session-2026-05-19 lesson #3; offsets need recomputation post-SHA-patch since authoring may have shifted line counts):
> ```powershell
> # Verify offsets after SHA-patch by counting fence positions:
> # python3 -c "import sys; lines = open('outputs/cursor_dispatch_prompt_phase_8.md').readlines(); fences = [i+1 for i, ln in enumerate(lines) if ln.strip() in ('```', '````')]; print('Fences at lines:', fences, 'Total:', len(lines))"
> Get-Content outputs\cursor_dispatch_prompt_phase_8.md | Select-Object -Skip 50 | Select-Object -SkipLast 60 | Out-File -FilePath $env:TEMP\phase_8_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_8_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-2026-05-19 lesson #2):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~24000–30000 bytes. <1000 bytes = truncation; redo Notepad.

---

````
Read outputs/phase_8_architecture_design.md end-to-end (1050 lines, Plan-
agent ADR-level design; sec1 scope split, sec2 external_conditions_cache
schema, sec3 fetcher subsystem, sec4 conditions strip + chat live-read
wiring, sec5 alert dispatch evaluation, sec6 threshold definitions, sec7
subscription UI, sec8 per-alert dedup, sec9 email templates + venue-
context mapping, sec10 cat-13 expansion DEFERRED to 8b, sec11 what's NOT
in scope, sec12 risk register, sec13 success criteria, sec14 effort, sec15
sequencing). Also read outputs/phase_8_operator_prereq_checklist.md (post-
patches with the 3 resolved prereqs) and outputs/phase_8_nixle_agency_id_
lookup.md (the deep findings on LHC Nixle agency ID 3726).

Phase 6.1 SHIPPED on origin at fd16e7a (unified Hava card grammar).
Phase 6.2 SHIPPED at 3948add (category landing template). Phase 6.3
SHIPPED at 5ebee46 (breadth pass + district chip + ranking + seasonal
hours). Phase 6.4 SHIPPED at 96c915d (Leaflet+OSM map + boat-access via
preferred_mode reuse + 4 themed group landing pages + search bar). Phase 5
multi-phase data-population COMPLETE at 5.11 (1,314 active entities).
Phase 7 SHIPPED at 0a305e0 (chat ENTITY wiring + boat-mode
+ conditions-awareness via STUB + HALT 3 + cross-entity + snowbird-return
view).

Pytest baseline going in is post-Phase-7.5.3+7.7 (origin/main `1e0d17a`).
Verify per python -m pytest --collect-only -q | tail -3 BEFORE starting
work. **Expected ~2224** (Phase 6.3 baseline 2060 + Phase 6.4 +25 +
Phase 6.5 +16 + Phase 7 +50 + Phase 7.5 +15 + Phase 7.5.1 +12 +
Phase 7.5.2 +13 + Phase 7.6 +9 + Phase 7.5.3 +16 + Phase 7.7 +6 =
2222; tolerance ±5). Alembic head is c9d0e1f2a3b4 (Phase 7
users.last_active_at migration; no Phase 7.5.x / 7.6 / 7.7 migrations
shipped). Verify per python -m alembic current BEFORE starting work and
REPORT THE OBSERVED VALUE (do NOT copy dispatch-body-claimed value).

CRITICAL — RUN BOTH:
- python -m alembic current   (returns SINGLE head)
- python -m alembic heads     (returns ALL heads; should be EXACTLY ONE)
If python -m alembic heads returns MULTIPLE heads, you have a multi-head
state. HALT immediately and report. This is the alembic-collision pattern
from the 2026-05-20 Phase 6.4/Phase 7 parallel-session collision -- see
outputs/dispatch_channels_alembic_collision_gotcha_draft.md for context.
Do NOT proceed with Phase 8 against a multi-head DB.

Ship Phase 8a ONLY per outputs/phase_8_architecture_design.md sec1 split
(Lane A + Lane B; cat-13 = Lane C = Phase 8b is a SEPARATE later dispatch
out of scope here):

(a) AirNow + NWS + USGS fetcher subsystem -- 3 source families, per-source
    Railway scheduled services (AirNow 30min / NWS alerts 15min / USGS 60min /
    NWS forecast 10min) writing to external_conditions_cache. **No Nixle
    fetcher in V1** (dropped per phase_8a_prereq_verification_report.md).
    Reuse Phase 4 with_retry envelope. Source-isolation pattern: AirNow
    failure doesn't crash NWS reads. New module app/conditions/ with
    per-source fetcher submodules. New scripts/fetch_external_conditions.py
    CLI entrypoint (Railway invokes per service).

(b) /api/conditions endpoint reads from external_conditions_cache; serves
    Today in Havasu strip + chat live-read. Returns JSON with current_aqi
    + current_aqi_parameter (e.g. "O3") + aqi_source_station_name (e.g.
    "Blythe") + aqi_source_state_code (e.g. "CA") + aqi_source_distance_mi
    (e.g. 60) + current_temp_f + active_nws_alerts (AZZ002-zone-scoped)
    + lake_gauge_ft + lake_storage_acft + per-field updated_at_iso for
    honest staleness display. **No lake_water_temp_f or nixle fields in
    V1; no active_nws_marine_alerts** (USGS site does not report 00010;
    Nixle dropped; NWS marine zones don't cover inland LHC per
    phase_8a_prereq_verification_report.md §11). **AQI is single-parameter
    O3 from Blythe CA ~60mi south per §12** (no PM2.5 / PM10 monitor
    within 100mi of LHC); conditions strip renders attribution chip
    "AQI 47 (O3) — from Blythe, CA ~60mi south" to be honest about
    source-station distance.

(c) "Today in Havasu" conditions strip on home.html wires up to /api/
    conditions; replaces the Phase 6.5 empty placeholder at <!-- conditions-
    strip-anchor -->. Renders staleness indicators ("Updated 12 min ago")
    per-field. Mobile-friendly compact shape vs desktop expanded.

(d) Chat live-conditions swap -- app/core/ranking.py STUB_CURRENT_
    TEMPERATURE_F replaced with read_current_temperature_f() function that
    reads from external_conditions_cache (with stub-fallback for env
    without cache populated yet, e.g. test fixtures). Phase 6.3 ranking +
    Phase 7 chat tier-3 preamble both swap atomically via this single
    helper. Update Phase 6.3 + Phase 7 import chains accordingly.

(e) Alert dispatch evaluation job -- every 15 min reads cache + evaluates
    per-alert-type thresholds + queries alert_subscriptions + dispatches
    via Resend BackgroundTasks (Phase 4 surface). New script
    scripts/evaluate_and_dispatch_alerts.py CLI entrypoint with --dry-run
    + --alert-type + --user-id flags for testing.

(f) Alert trigger threshold definitions per alert_type at
    app/alerts/thresholds.py:
    - heat_advisory: (NWS Excessive Heat Warning active) OR (forecast > 110F).
      Operator-tunable: HEAT_ADVISORY_FORECAST_THRESHOLD_F = 110.0
    - aqi_alert: AirNow AQI > 150 (Unhealthy) on ANY ParameterName row
      returned in the response (multi-row tolerant; LHC's nearest monitor
      Blythe returns O3-only per §12 verification, but evaluator should
      not assume single-parameter). Operator-tunable:
      AQI_ALERT_THRESHOLD = 150. Treats PM2.5/PM10 absence as
      data-not-available (no firing), NOT as safe-condition zero.
    - lake_hazard: NWS AZZ002-zone alert keyword match (inland-LHC set
      per phase_8a_prereq_verification_report.md §11.2: flash flood /
      flood warning / flood advisory / lake wind / high wind / wind
      advisory / blowing dust / dust storm / severe thunderstorm)
      OR USGS gauge-height drop > LAKE_HAZARD_GAUGE_DROP_FT (default
      2.0) in 24h at site 09427500 (no Nixle; no marine; no water-temp
      signal)
    - event_traffic: DEFERRED to V1.5 per master plan sec8 OQ #12

(g) Alert subscription UI on /account/alerts -- minimal form atop Phase 2A
    account-lite auth; user checks/unchecks per alert_type; opt-in via
    email confirmation per alert_subscriptions schema; new template
    app/templates/account_alerts.html.

(h) Alert email templates with venue-context mapping -- heat advisory
    email lists indoor alternatives from user's UserFavorite records
    (texture-moat per Opus #1+#8). New templates at app/templates/
    emails/heat_advisory.html + aqi_alert.html + lake_hazard.html.
    Reuses Phase 2A.1 Resend integration.

(i) Per-alert dedup -- write alerts_dispatched row per (user_id,
    alert_type, dispatched_at) per design doc sec8. 6-hour dedup window
    via lookback query at evaluation time. Existing alerts_dispatched
    table from Phase 3.1 may need additive column; verify before
    migration.

LOCKED OPERATOR PREREQS (amended 2026-05-19 per phase_8a_prereq_verification_report.md):
- AirNow API key: operator registers + smoke-tests before deploy; store in
  secrets vault + .env; Railway env var AIRNOW_API_KEY. **2026-05-19
  verification confirmed key works; nearest monitor = Blythe CA at ~60mi
  south of LHC; O3 only (no PM2.5 / PM10); per §12 of
  phase_8a_prereq_verification_report.md.**
- AirNow query scope:
  AIRNOW_ZIP = "86403"  # Lake Havasu City
  AIRNOW_DISTANCE_MI = int(os.environ.get("AIRNOW_DISTANCE_MI", "100"))
  # distance=25 returns empty; distance=60 returns empty; distance=100
  # returns Blythe CA (~60mi south of LHC) per §12 recheck. 100 default
  # leaves headroom; operator-tunable down to 75 if tighter scope wanted.
- AirNow response shape: 0..N rows; iterate ParameterName values
  (LHC currently single-row O3 from Blythe); cache stores all rows
  + the source-station attribution columns (aqi_source_station_name +
  aqi_source_state_code + aqi_source_distance_mi).
- USGS single-site model:
  USGS_LAKE_HAVASU_SITE = "09427500"   # Lake Havasu near Parker Dam
  USGS_PARAMETER_CODES = ("00065", "00054")  # gauge height ft + storage ac-ft
  # DROPPED: USGS_LAKE_HAVASU_SECONDARY_SITE "09427520" (historic-only 2006)
  # DROPPED: 00010 water temp, 00060 discharge at 09427500
  USGS modern OGC API at https://api.waterdata.usgs.gov/ogcapi/v0/ (legacy
  waterservices.usgs.gov sunsetting early 2027 -- DO NOT target legacy for prod)
- Nixle: **DROPPED FROM V1** -- feed silent since 2021-09-01; V1.5 carry to
  research Mohave County SO / ein.az.gov / lhcaz.gov RSS replacement
- NWS zone scope: **LHC_NWS_ZONE_ID = "AZZ002"** (Lake Havasu and Fort
  Mohave; served by NWS Las Vegas KVEF). Land zone -- marine zones don't
  cover inland LHC per phase_8a_prereq_verification_report.md §11. All
  active-alerts fetches scoped to AZZ002:
  api.weather.gov/alerts/active?zone=AZZ002
- NWS: api.weather.gov is open (no key); User-Agent header convention
  required (e.g. "havasu-chat/1.0 contact-email-here")
- Resend: existing key from Phase 2A.1 reused for alert dispatch

ORDER MATTERS WITHIN PHASE 8a:

1. First: read the design doc end-to-end + phase_8a_prereq_verification_report.md
   + the prereq checklist. Critical reads in the codebase:
   - app/db/models.py (verify external_conditions_cache + alert_subscriptions
     + alerts_dispatched tables ALREADY EXIST from Phase 3.1; verify
     column shapes match design doc sec2; flag any drift)
   - app/core/ranking.py (Phase 6.3 STUB_CURRENT_TEMPERATURE_F + heat-bias
     constants; Phase 8 swaps the stub)
   - app/chat/tier3_handler.py + tier2_db_query.py (Phase 7 chat-
     conditions-awareness imports; Phase 8 swap point)
   - app/background/ (Phase 4 with_retry, Outbox, BackgroundTasks)
   - app/auth/email_sender.py (Phase 2A.1 Resend integration; reused)
   - app/api/routes/ (mount pattern for new conditions + alerts routes)
   - app/templates/home.html (Phase 6.5 conditions-strip-anchor location)
   - app/templates/components/ (Phase 6.1 hava_card.html pattern; new
     conditions_strip.html follows same anchored-include shape)
   - docs/maintainability/conditions_panel_and_alerts_design.md (Opus
     design memo; design doc sec1 says Phase 8 is the implementation-time
     refinement)
   - docs/operations/railway_scheduled_jobs_runbook.md (Phase 4 runbook;
     Phase 8 adds 4 services to it)

2. Then: schema verification + optional migration. Verify
   external_conditions_cache + alert_subscriptions + alerts_dispatched
   tables exist with expected shape from Phase 3.1 + design doc sec2. If
   any additive column is needed (e.g. external_conditions_cache.source
   needs a new value enum), ship ONE alembic migration chaining from
   c9d0e1f2a3b4. CRITICAL: use python -m alembic heads to
   verify SINGLE head before authoring. Migration upgrade + downgrade
   cycle tested in tests/test_phase8_conditions_schema.py with DYNAMIC
   head capture (script.get_current_head() + script.get_revision(head_rev).
   down_revision) per session-2026-05-19 lesson #4. NEVER hardcode head
   literals.

3. Then: per-source fetcher subsystem. New app/conditions/ module with:
   - app/conditions/airnow.py -- fetches AirNow current AQI for
     AIRNOW_ZIP="86403" with AIRNOW_DISTANCE_MI=100 (§12 verification:
     LHC has no monitor <60mi; Blythe CA O3-only at ~60mi south is the
     nearest); iterates 0..N response rows; tolerates parameter-set
     heterogeneity (don't assume PM2.5 + PM10 present); stores source-
     station attribution (name + state + distance) alongside AQI values
   - app/conditions/nws_alerts.py -- fetches active NWS alerts scoped to
     LHC_NWS_ZONE_ID "AZZ002" via api.weather.gov/alerts/active?zone=AZZ002
     (User-Agent header required; cache key nws_alerts_lhc_zone)
   - app/conditions/nws_forecast.py -- fetches NWS forecast (10-min cadence)
   - app/conditions/usgs.py -- fetches USGS 09427500 only; parameters 00065
     (gauge height) + 00054 (reservoir storage ac-ft) via modern OGC API
   # NO app/conditions/nixle.py in V1 (Nixle dropped per verification report)
   - app/conditions/base.py -- shared SourceFetcher interface; with_retry
     envelope; per-source last-success tracking; staleness-aware cache
     writes
   - scripts/fetch_external_conditions.py -- CLI entrypoint per service
     (e.g. python -m scripts.fetch_external_conditions --source airnow)

4. Then: cache reader + /api/conditions endpoint. New
   app/api/routes/conditions.py with GET /api/conditions returning the
   live JSON shape per design doc sec4. Cache-aware reads (transparently
   reads-cached; staleness indicators per-field).

5. Then: conditions strip wiring on home.html. Anchored edit replacing
   the Phase 6.5 placeholder at <!-- conditions-strip-anchor --> with the
   live data-bound element. New app/templates/components/conditions_
   strip.html partial. New app/static/js/conditions_strip.js for poll-
   refresh (every 60s when page is visible). New app/static/styles/
   components/conditions_strip.css with mobile-stacked / desktop-expanded
   shapes.

6. Then: chat live-conditions swap. Anchored edit on app/core/ranking.py
   replacing STUB_CURRENT_TEMPERATURE_F constant with read_current_
   temperature_f() function reading from external_conditions_cache.
   Maintain backward-compat default for tests (env without cache
   populated). Update Phase 6.3 + Phase 7 import chains -- ACTUAL stub
   import sites (per Lane E re-check 2026-05-20): app/chat/chat_request_
   context.py:8, app/api/routes/category_pages.py:22, app/api/routes/
   map_data.py:12. (NOT tier2_db_query.py or tier3_handler.py -- those
   import ChatRequestContext, not the stub directly. Run `grep -rn
   STUB_CURRENT_TEMPERATURE_F app/` for any others added after 2026-05-20.)

7. Then: alert evaluation + dispatch subsystem. New app/alerts/ module
   with:
   - app/alerts/thresholds.py -- per-alert-type threshold definitions +
     operator-tunable constants
   - app/alerts/evaluator.py -- evaluates current cache state vs
     thresholds; returns dispatch candidates
   - app/alerts/dispatcher.py -- queries alert_subscriptions + per-
     alert dedup via alerts_dispatched + email send via Resend
   - app/alerts/venue_context.py -- queries UserFavorite + matches to
     alert_type-appropriate indoor alternatives
   - scripts/evaluate_and_dispatch_alerts.py -- CLI entrypoint with
     --dry-run / --alert-type / --user-id flags

8. Then: alert subscription UI. New app/api/routes/alerts.py with
   /account/alerts route. New app/templates/account_alerts.html
   extending Phase 2A account-lite chrome. Form posts to /account/alerts
   for opt-in toggles per alert_type.

9. Then: alert email templates with venue-context. New templates at
   app/templates/emails/heat_advisory.html + aqi_alert.html +
   lake_hazard.html. Heat advisory template lists indoor venues from
   UserFavorite; AQI template lists low-particulate alternatives; lake
   hazard template lists land-based alternatives. Reuses Phase 2A.1
   Resend send_email helper.

10. Then: 6+ new test files:
    - tests/test_phase8_conditions_schema.py (~6-10 tests)
    - tests/test_phase8_fetcher_airnow.py (~6-10 tests; mocks AirNow API)
    - tests/test_phase8_fetcher_nws.py (~8-12 tests; mocks NWS alerts +
      forecast)
    - tests/test_phase8_fetcher_usgs.py (~6-10 tests; mocks USGS OGC API)
    # NO test_phase8_fetcher_nixle.py in V1 (Nixle dropped)
    - tests/test_phase8_conditions_endpoint.py (~6-10 tests; /api/
      conditions response shape + caching)
    - tests/test_phase8_conditions_strip.py (~6-10 tests; home.html render)
    - tests/test_phase8_chat_live_swap.py (~8-12 tests; ranking +
      tier3-preamble swap from stub to read_current_temperature_f())
    - tests/test_phase8_alert_thresholds.py (~10-14 tests; per-alert-type
      threshold evaluation)
    - tests/test_phase8_alert_dispatch.py (~10-14 tests; dispatch + dedup
      + venue-context mapping)
    - tests/test_phase8_alert_subscription_ui.py (~6-10 tests; opt-in
      form roundtrip)
    - tests/test_phase8_alert_emails.py (~8-12 tests; template render +
      venue-context substitution)

11. After all of the above: confirm full pytest stays green (post-Phase-7
    baseline + 80-130 net-new = ~2220-2330), ruff clean, alembic head
    matches expected (either c9d0e1f2a3b4 if no migration
    shipped, or the new revision SHA chaining off it). Manual smoke
    deferred-to-operator:
    - python -m fastapi run app.main:app + browse to / verify conditions
      strip renders with real AQI/temp/alerts (after manually running
      scripts/fetch_external_conditions.py --all once to populate cache)
    - Toggle conditions strip mobile-vs-desktop responsive shapes
    - Run scripts/evaluate_and_dispatch_alerts.py --dry-run --alert-type
      heat_advisory --user-id <test-user> + verify dispatch candidate
      shape
    - Browse to /account/alerts (logged-in) verify opt-in form renders
    - Test email send flow against a single test recipient

POSTGRES COMPATIBILITY (carry-forward from brief sec0 + Phase 1A lesson):
- Phase 8a likely ships ZERO new migrations IF external_conditions_cache
  + alert_subscriptions + alerts_dispatched tables already exist with
  expected shape from Phase 3.1. Verify at step 1. If a column add is
  needed (e.g. enum extension), ship ONE migration with sa.true() /
  sa.false() for booleans + sa.func.now() for timestamps. NEVER hardcode
  alembic head literals in test code. NEVER use sa.text("1")/sa.text("0")
  for Boolean defaults (Phase 1A Postgres lesson).
- python -m alembic heads MUST return SINGLE head at start AND at end of
  dispatch. If multi-head detected mid-flight, HALT and report.

DEVIATION INVITATIONS (per design doc + master plan sec4 Phase 8):

- Fetcher cadences: design locks 30min AirNow / 15min NWS alerts / 30min
  USGS / 10min NWS forecast. If operator wants different rates (e.g.
  AirNow rate-limit anxiety + 60min cadence), flag in sec13.
- AQI alert threshold: design locks > 150 (Unhealthy). Operator may want
  > 100 (Unhealthy for Sensitive Groups; more conservative). Flag.
- Heat advisory threshold: design locks > 110F (Excessive Heat Warning
  semantics). Operator may want > 105F (more conservative). Flag.
- lake_hazard NWS AZZ002-zone keyword matcher + USGS gauge-drop threshold:
  tune LAKE_HAZARD_GAUGE_DROP_FT if false positives on reservoir ops;
  tune keyword set if false-pos/false-neg pattern surfaces in shoulder
  seasons.
- USGS modern OGC API vs legacy: design strongly recommends modern (legacy
  sunsetting 2027). If modern OGC API has gotchas not yet documented,
  flag.
- Conditions strip poll cadence: design locks 60s when page visible. If
  WebSocket push reads cleaner, that's V1.5 (don't ship in Phase 8).
- Email send strategy: design locks Resend BackgroundTasks. If Resend
  rate limits problematic, flag.
- Venue-context for AQI alerts: design locks "indoor venues from
  UserFavorite". If user has no favorites, render fallback copy. Flag if
  fallback shape feels brittle.
- Cat-13 expansion (Lane C): DEFERRED to Phase 8b per design doc sec1
  split. Do NOT pull forward to this dispatch.

WHAT NOT TO DO (per master plan sec4 Phase 8 + design doc sec11):

- Don't ship Twilio SMS. Master plan sec8 OQ #13 + design doc sec11
  defer to V1.5.
- Don't ship event_traffic alert type. Master plan sec8 OQ #12 + design
  doc sec11 defer to Phase 9 (when Events surface lands).
- Don't ship cat-13 Public & Civic Resources expansion. Phase 8b
  (separate later micro-dispatch).
- Don't ship Phase 9 event scraper subsystem.
- Don't ship monetization. Phase 11.
- Don't ship district paragraph rendering. V1.5.
- Don't add new Python dependencies beyond what's needed for RSS XML
  parsing (feedparser OR feedfinder) + the OGC client (httpx already
  present).
- Don't bash heredoc commit messages. PowerShell-safe multi-line `-m`
  flags or here-string per session-2026-05-19 lesson #1.
- Don't hardcode alembic head literals in test code (session-2026-05-19
  lesson #4).
- Don't proceed if `python -m alembic heads` returns multiple heads.
  HALT.
- Don't dispatch Phase 8b or Phase 9 in the same Cursor session. HALT
  at the sec3 Phase 8a boundary.

HALT at the sec3 Phase 8a boundary. After Phase 8a ships + commits +
pushes, halt for operator re-dispatch in a fresh session for Phase 8b
(cat-13 expansion) OR Phase 9 (events scraper + Classes/Sports
schedule UX + Things to Do themed group + RRULE recurrence).

Same constraints as Phase 6.1 + 6.2 + 6.3 + 6.4 + Phase 7:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 sec12 final report format adapted for Phase 8
- Re-verify python -m alembic current AND python -m alembic heads and
  report the observed values
- If alembic heads returns multiple heads, HALT and report

Pre-dispatch checklist (verify before paste):

- Phase 6.1 SHIPPED on origin (fd16e7a)
- Phase 6.2 SHIPPED on origin (3948add)
- Phase 6.3 SHIPPED on origin (5ebee46)
- Phase 6.4 SHIPPED on origin (96c915d)
- Phase 7 SHIPPED on origin (0a305e0)
- Phase 7.5 SHIPPED on origin (b701759, 2026-05-20, HALT 3 validator triage)
- Phase 6.5 SHIPPED on origin (bdca0bd, 2026-05-20, homepage rebuild + tiles)
- Phase 7.5.1 SHIPPED on origin (fd695d2, 2026-05-19, prod-divergence routing fixes)
- Phase 7.5.2 SHIPPED on origin (64799d5, 2026-05-20, HALT 3 validator hardening)
- Phase 7.6 SHIPPED on origin (975e83f, 2026-05-20, tier-2 OPEN_NOW shortcut)
- Phase 7.5.3 SHIPPED on origin (ac7c2fc, 2026-05-20, F-gap polish F1/F4/F5)
- Phase 7.7 SHIPPED on origin (eb489a7, 2026-05-20, honest tier-2 empty listing)
- Docs ledger close-outs on origin (c81f0d0, 19b6c8f, 44ca1c6, fe997ee, 1e0d17a)
- **Lane E re-dispatch 2026-05-20:** Phase 8a was attempted previously; Cursor session's saves stomped on committed code with a stale snapshot (truncated tier2_handler.py, ranking.py, chat_request_context.py mid-write). Stashed at `8a-collision-corrupted-tree-2026-05-20` for forensics; this is a fresh dispatch from clean tree at `1e0d17a`.
- Sidecar migration SHIPPED on origin (532d48b)
- Phase 5 ledger SHIPPED on origin (3a2d895)
- c9d0e1f2a3b4 is the current SINGLE alembic head on
  origin (verify via `python -m alembic current` AND `python -m alembic
  heads`)
- Pytest baseline going in matches reality per `python -m pytest
  --collect-only -q | tail -3` (expected ~2224 post-7.5.3+7.7+7.6 stack on origin/main `1e0d17a`; verify and REPORT the observed count — do NOT assume the dispatch-body number).
- AirNow API key registered + smoke-test passed (operator)
- USGS site 09427500 live-verified (00065 + 00054 only); 09427520 dropped
- Nixle dropped from V1 per phase_8a_prereq_verification_report.md
- The 6 operator decisions are LOCKED at design-doc-defaults: 8a
  scope (Lane A + Lane B), per-source Railway services, schema reuse
  (verify Phase 3.1 existence), threshold definitions, 6-hour dedup,
  STUB swap pattern
- Master plan sec4 Phase 8 reviewed + acceptance gates noted (per
  design doc sec13)
- Phase 9 is NOT in scope (deferred); 8b cat-13 expansion is NOT in
  scope (deferred)
````

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phase ships: paste back to Cowork primary chat, primary reviews against design doc §13 success criteria + master plan §4 Phase 8 acceptance gates, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 0 OR 1 new alembic migration (only if schema additive needed; verify at step 1)
- 1 new module dir `app/conditions/` (~5 files: base.py, airnow.py, nws_alerts.py, nws_forecast.py, usgs.py)
- 1 new module dir `app/alerts/` (~4 files: thresholds.py, evaluator.py, dispatcher.py, venue_context.py)
- 2 new scripts: `scripts/fetch_external_conditions.py` + `scripts/evaluate_and_dispatch_alerts.py`
- 1 new `app/api/routes/conditions.py` (~60-100 lines)
- 1 new `app/api/routes/alerts.py` (~80-150 lines)
- 1 new `app/templates/components/conditions_strip.html` (~40-80 lines)
- 1 new `app/templates/account_alerts.html` (~80-150 lines)
- 3 new email templates in `app/templates/emails/` (~80-150 lines each)
- 1 new `app/static/js/conditions_strip.js` (~60-100 lines)
- 1 new `app/static/styles/components/conditions_strip.css` (~30-60 lines)
- 1 modified `app/main.py` (anchored edit; +~5-10 lines mounting 2 new routers)
- 1 modified `app/core/ranking.py` (anchored edit; STUB → read_current_temperature_f swap + backward-compat fallback)
- 1 modified `app/chat/tier3_handler.py` + `tier2_db_query.py` (anchored edits; import-chain update for the swap)
- 1 modified `app/templates/home.html` (anchored edit; conditions strip slot replacement at `<!-- conditions-strip-anchor -->`)
- 1 modified `app/static/styles/home.css` (anchored edit; +~2 lines `@import` for conditions_strip.css)
- 11-12 new test files

Expected pytest delta: +80-130 net-new tests. Pre-existing tests must remain green.

Expected effort: 5-8 days dispatch per master plan §4 Phase 8 (Lane A + Lane B; Lane C cat-13 is Phase 8b separate). CURSOR MAY SPLIT INTO TWO SUB-SESSIONS:
- Phase 8a-A: conditions fetcher subsystem + cache reader + strip wiring + chat swap (~3-4 days; file scope = app/conditions/ + app/api/routes/conditions.py + scripts/fetch_external_conditions.py + conditions_strip.* + ranking.py swap + chat handler imports + tests/test_phase8_fetcher_*.py + tests/test_phase8_conditions_*.py + tests/test_phase8_chat_live_swap.py)
- Phase 8a-B: alert evaluation + dispatch + subscription UI + email templates (~2-4 days; file scope = app/alerts/ + app/api/routes/alerts.py + scripts/evaluate_and_dispatch_alerts.py + account_alerts.html + emails/*.html + tests/test_phase8_alert_*.py)

HALT between 8a-A and 8a-B at the natural §3 work-unit boundary; operator commits + pushes 8a-A; 8a-B dispatches fresh against 8a-A HEAD SHA.

Expected pragmatic deviations:

1. Fetcher cadence tuning (operator rate-limit anxiety)
2. AQI alert threshold tuning (150 vs 100 conservatism)
3. Heat advisory threshold tuning (110F vs 105F)
4. lake_hazard NWS AZZ002-zone keyword matcher false-positive/negative pattern
5. USGS modern OGC API edge cases
6. Conditions strip poll cadence (60s vs alternatives)
7. Email send rate limit handling
8. AQI venue-context fallback when user has no favorites

## After Phase 8a ships

Update master plan §4 Phase 8 — append SHIPPED line. Update STATE.md "Recently shipped" prepend with Phase 8a close-out narrative. Update alembic head reference if a migration shipped.

After Phase 8a is durable, **operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true`** out-of-band IF Phase 7's HALT 3 eval-set validator was green (Phase 7 close-out should have noted that gate passed). Phase 8 doesn't directly touch the flag but Phase 8's live conditions data closes the loop on the chat-conditions-awareness honesty surface that HALT 3 was guarding.

Phase 8b (cat-13 Public & Civic Resources expansion) dispatch wrapper to be authored after Phase 8a ships — likely a smaller micro-dispatch focused on Layer 3 (LHC open data) + Layer 5 (operator-typed entries) for the cat-13 catalog. Per design doc §10.

Phase 9 (events scraper + Classes/Sports schedule UX + Things to Do themed group + RRULE recurrence) dispatch wrapper to be authored after Phase 8a OR Phase 8b ships — chains off whichever shipped last. Architectural design pre-positioned at `outputs/phase_9_architecture_design.md` (1620 lines, Plan-agent ADR-level design).

---

*Authored by Cowork primary at the post-`616fd8b` session (2026-05-20). Lives at `outputs/cursor_dispatch_prompt_phase_8.md`. SHA-patch slots `0a305e0` + `c9d0e1f2a3b4` need filling post-Phase-7-ship. Per the 2026-05-20 alembic-collision gotcha (`outputs/dispatch_channels_alembic_collision_gotcha_draft.md`), Phase 8 is the next post-Phase-7 dispatch; Phase 7 + Phase 8 do NOT run in parallel. Architectural design at `outputs/phase_8_architecture_design.md`, prereq checklist at `outputs/phase_8_operator_prereq_checklist.md`, Nixle agency ID lookup at `outputs/phase_8_nixle_agency_id_lookup.md` are the upstream artifacts.*
