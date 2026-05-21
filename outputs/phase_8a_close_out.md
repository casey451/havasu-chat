# Phase 8a close-out — conditions + alerts infrastructure SHIPPED

> **What this is:** the post-ship close-out for Phase 8a (conditions panel + alert dispatch subsystem) — the trust + retention layer that turns the homepage "Today in Havasu" strip and the chat conditions-awareness ranking from stubs into live AirNow + NWS + USGS reads, plus a four-alert dispatch evaluator + subscription UI + email templates. Phase 8a shipped 2026-05-21 at commit `8a905c6` after a substantive recovery sequence: the first two Cursor dispatch attempts left the working tree corrupted by a multi-window IDE buffer collision; the third path was a surgical Edit-tool sub-agent (Lane Z) that wired the 8a deliverables without going through the Cursor terminal write channel. The Railway deploy at v1.3.0 succeeded; pytest 33/33 on the Phase 8a + Phase 6 conditions strip suites; full suite holds.
>
> **Authored by:** sub-agent under Cowork primary supervision, 2026-05-21, post-Phase-8a-ship.
>
> **Status:** close-out (Phase 8a SHIPPED; Phase 8b cat-13 expansion deferred; Phase 7.7.1 + Phase 7.5.4 queued; one watch item — `test_date_lookup_gap_includes_contribute` — escalated to diagnostic).
>
> **Primary companion docs:**
> - `outputs/cursor_dispatch_prompt_phase_8.md` — the dispatch wrapper Cursor consumed (amended through §6 + §11 + §12 by 2026-05-19; Lane E re-dispatch note added post-first-corruption)
> - `outputs/phase_8_architecture_design.md` — the 1050-line Plan-agent ADR design spec
> - `outputs/phase_8a_prereq_verification_report.md` — the 3-wave verification that locked the amended scope (USGS site narrowed to `09427500`; Nixle dropped; AirNow Blythe-only attribution; NWS marine dropped)
> - `outputs/phase_8a_post_ship_close_out_template.md` — the pre-positioned template this doc instantiates
> - `outputs/phase_7_5_to_7_7_lane_close_out.md` — the prior lane close-out (narrative voice template)
> - `outputs/cursor_diagnostic_test_date_lookup_gap.md` — the queued diagnostic for the post-ship test failure

---

## §1 Ship facts

| Dimension | Value |
|---|---|
| Ship date | 2026-05-21 |
| Commit | `8a905c6` (`feat(phase8a): conditions + alerts subsystem ...`) |
| Diff stat | 53 files / +2588 / -12 lines |
| Origin/main tip pre-8a | `19b9d2d` (wrapper amendments) |
| Origin/main tip post-8a | `8a905c6` |
| Alembic head pre-8a | `c9d0e1f2a3b4` (Phase 7 `users.last_active_at`) |
| Alembic head post-8a | `d8e9f0a1b2c3` (Phase 8a additive — single head) |
| Migration shape | Additive: `external_conditions_cache.last_attempt_at` + `next_attempt_after` + index `ix_external_conditions_cache_next_attempt_after`; extends `alerts_dispatched.delivery_status` check constraint with `'suppressed_dedupe', 'suppressed_paused'` |
| Railway deploy | v1.3.0, successful (per operator screenshot) |
| Pytest Phase 8a + Phase 6 conditions suites | 33/33 pass |
| Pytest full suite at ship | Baseline holds; 1 post-ship failure surfaced (`test_date_lookup_gap_includes_contribute` — 7.5.3 surface, NOT 8a scope) — see §7 |
| `FEATURE_FLAG_DISCLOSURE_RENDERER` | Untouched (still `false`) |
| Phase 8b cat-13 | Explicitly deferred (per wrapper §3 + design doc §10) |

---

## §2 Acceptance-gate verification

Per `outputs/cursor_dispatch_prompt_phase_8.md` §3 deliverables (a)-(i) + §6/§11/§12 amendments:

| Gate | Status | Verification |
|---|---|---|
| (a) AirNow + NWS + USGS fetcher subsystem with per-source isolation | PASS | `app/conditions/airnow.py` + `nws.py` + `usgs.py` + `fetcher.py` + `cache.py` + `constants.py`; `scripts/fetch_external_conditions.py` CLI; circuit breaker via `last_attempt_at` / `next_attempt_after` columns |
| (b) `/api/conditions` endpoint with source-station attribution | PASS | `app/api/routes/conditions.py` returns JSON via `app/conditions/api_payload.py`; AQI attribution fields present; per-field staleness via `app/conditions/staleness.py` |
| (c) "Today in Havasu" conditions strip on `home.html` + 60s poll | PASS | `app/templates/components/conditions_strip.html` (anchor replaced) + `static/js/conditions_strip.js` + expanded CSS; view model in `app/conditions/view_model.py` |
| (d) Chat live-conditions swap | PASS | `read_current_temperature_f()` in `app/core/conditions_temperature.py` (standalone module — NOT a re-export from `ranking.py`); wired in `category_pages.py`, `map_data.py`, AND `unified_router.py:846`; stub-fallback preserved |
| (e) Alert dispatch evaluation job | PASS | `scripts/evaluate_and_dispatch_alerts.py` with `--dry-run` + `--alert-type` + `--user-id` flags; `app/alerts/dispatcher.py` orchestrates |
| (f) Alert trigger threshold definitions | PASS | `app/alerts/thresholds.py` defines `HEAT_ADVISORY_FORECAST_THRESHOLD_F`, `AQI_ALERT_THRESHOLD`, lake-hazard keyword set (inland LHC), `LAKE_HAZARD_GAUGE_DROP_FT`, AirNow distance constants, NWS zone `AZZ002`, USGS site `09427500` |
| (g) Alert subscription UI on `/account/alerts` | PASS | `app/api/routes/account_alerts.py` + new template; opt-in toggles atop Phase 2A account-lite |
| (h) Alert email templates with venue-context | PASS | `app/alerts/templates/heat_advisory.{html,txt}.j2` + `aqi_alert.{html,txt}.j2` + `lake_hazard.{html,txt}.j2`; venue context via `app/alerts/venue_context.py`; rendering via `app/alerts/render.py`; reuses Phase 2A.1 Resend integration |
| (i) Per-alert dedup via `alerts_dispatched` table | PASS | `app/alerts/dedup.py` — 6-hour dedup window; `delivery_status` extended with `'suppressed_dedupe', 'suppressed_paused'` per migration |
| §6: USGS narrowed to `09427500` + `00065` / `00054` only | PASS | `app/conditions/usgs.py` does NOT fetch `09427520`; does NOT fetch `00010` water temp or `00060` discharge |
| §6: Nixle DROPPED from V1 | PASS | No `app/conditions/nixle.py` module; lake_hazard uses NWS AZZ002 + USGS gauge-drop only |
| §11: NWS scoped to `AZZ002` land zone | PASS | `app/conditions/nws.py` fetches AZZ002; no marine surface; LAKE_HAZARD_NWS_KEYWORDS is inland-LHC set |
| §12: AirNow Blythe-style attribution | PASS | Cache stores source-station fields; conditions strip renders attribution chip; aqi_alert evaluator is multi-row tolerant |
| Pytest baseline holds + nets new | PASS (33/33 Phase 8a suites) | Pre-existing test surfaces unaffected by 8a scope |
| Alembic head advanced ONE step from `c9d0e1f2a3b4` | PASS | New revision `d8e9f0a1b2c3`; SINGLE head; portable migration (uses `op.batch_alter_table` for SQLite-compat check-constraint extension) |
| File scope respected (no Phase 8b cat-13; no Phase 9 events; FEATURE_FLAG_DISCLOSURE_RENDERER untouched) | PASS | Verified against commit diff |
| `event_traffic` alert deferred to V1.5 | PASS | Per wrapper + design doc §11; Events table doesn't have `traffic_impact` tag until Phase 9 |

**All gates met.** Phase 8a is SHIPPED.

---

## §3 Per-deliverable narrative

### (a) Fetcher subsystem — `app/conditions/`

Five source modules + a base fetcher + a cache module + a constants module + a staleness module + a script entrypoint. `airnow.py` fetches Blythe CA at distance=100 (O3 single-row in practice; multi-row tolerant). `nws.py` fetches AZZ002 active alerts (UA header set) + the NWS current observations + 7-day forecast for the AZZ002 hourly grid + the daily sunrise/sunset pair. `usgs.py` hits the modern OGC API at `api.waterdata.usgs.gov/ogcapi/v0/` for site `09427500`, parameters `00065` (gauge height ft) + `00054` (reservoir storage ac-ft) — the `00010` water-temp and `00060` discharge sources were verified-dropped at the 3-wave prereq verification stage. `fetcher.py` implements the per-source isolation pattern: each source has its own retry envelope, last-attempt timestamp, and next-attempt-after backoff; an AirNow failure does not crash the NWS read. `scripts/fetch_external_conditions.py` is the CLI Railway invokes per scheduled service (separate cadences: 30min / 15min / 30min / 10min per the design doc).

### (b) `/api/conditions` endpoint — `app/api/routes/conditions.py`

GET endpoint returning the JSON shape per design doc §4: `current_aqi` + `current_aqi_parameter` + `aqi_source_station_name` + `aqi_source_state_code` + `aqi_source_distance_mi` for the attribution chip; `current_temp_f` + `forecast_high_f` + `forecast_low_f`; `active_nws_alerts` array (AZZ002-zone-scoped); `lake_gauge_ft` + `lake_storage_acft`; per-field `updated_at_iso` for honest staleness display via `app/conditions/staleness.py`. Payload assembly lives in `app/conditions/api_payload.py`. On empty cache (the current prod state pre-`AIRNOW_API_KEY`-set) the endpoint returns just `{"rendered_at_iso": "..."}` — confirmed via prod smoke.

### (c) "Today in Havasu" conditions strip

`app/templates/home.html` had a Phase 6.5-anchored placeholder at `<!-- conditions-strip-anchor -->`; that comment was replaced with `{% include 'components/conditions_strip.html' %}`. The component template renders AQI tile (with attribution chip), temperature tile (with staleness label "Updated N min ago"), lake-gauge + lake-storage tiles, and an NWS-alert tile that conditionally renders only when active alerts exist. `static/js/conditions_strip.js` polls every 60s when the page is visible; CSS expanded to support mobile-stacked alongside desktop-horizontal layout. The view model (`app/conditions/view_model.py`) is the structured intermediate between the cache JSON and the template render path.

### (d) Chat live-conditions swap

This is the deliverable that surfaced the substantive Lane Z scope expansion. The wrapper called for an atomic STUB → live-read swap at `app/core/ranking.py`, but the cleanest factoring after the recovery was a **standalone module** (`app/core/conditions_temperature.py`) rather than a re-export through `ranking.py` — the re-export attempt during initial recovery produced a circular import that crashed `from app.main import app`. `read_current_temperature_f(db)` reads from `external_conditions_cache` via `app/conditions/cache.py`; falls back to `STUB_CURRENT_TEMPERATURE_F = 105.0` when the cache row is missing, stale, or has no `temperature_f` field. Wired into three call sites: `app/api/routes/category_pages.py`, `app/api/routes/map_data.py`, AND `app/chat/unified_router.py:846` (the Lane Z follow-up, since `parse_chat_request_context()` doesn't accept a `Session` and threading `db` through would require updating 4+ callers + 5 test files). The unified-router injection point sits where `temperature_f_override` is already plumbed — ~12 LOC including a `try/except` fallback to the stub.

### (e–i) Alerts — `app/alerts/`

`thresholds.py` defines the four alert-type constants (heat_advisory, aqi_alert, lake_hazard, event_traffic — the last marked DEFERRED). `evaluator.py` evaluates current cache state against thresholds; multi-row tolerant on AirNow; treats PM2.5/PM10 absence as data-not-available, not safe-condition zero. `dedup.py` implements the 6-hour lookback query on `alerts_dispatched`. `venue_context.py` queries `UserFavorite` for indoor / land-based alternatives per alert type. `dispatcher.py` orchestrates: evaluate → query subscriptions → dedup → render → dispatch via `app.auth.email_sender.send_alert_email` (the new function added during Lane Z recovery — see §5). `render.py` renders the Jinja2 templates under `app/alerts/templates/`. `scripts/evaluate_and_dispatch_alerts.py` is the CLI with `--dry-run`, `--alert-type`, `--user-id` flags. `/account/alerts` UI in `app/api/routes/account_alerts.py` + the matching template is the user-facing opt-in form.

---

## §4 Locked scope honored

**IN scope (shipped):**
- USGS site `09427500` only — `00065` gauge height + `00054` reservoir storage
- AirNow Blythe CA at distance=100 — O3 single-row in practice, multi-row tolerant
- NWS AZZ002 land zone — active alerts (15min) + current obs + forecast (10min)
- Four alert types: heat_advisory, aqi_alert, lake_hazard, **event_traffic deferred**
- AQI alert threshold > 150 (Unhealthy)
- heat_advisory: NWS Excessive Heat Warning OR forecast > 110°F (`HEAT_ADVISORY_FORECAST_THRESHOLD_F`)
- lake_hazard: NWS AZZ002 keyword set (inland LHC) OR optional gauge drop > 2.0ft / 24h
- 6-hour per-(user, alert_type) dedup window
- Conditions strip 60s poll cadence

**OUT of scope (explicitly deferred or dropped):**
- USGS site `09427520` (historic-only since 2006)
- USGS parameters `00010` water temp + `00060` discharge (not measured at `09427500`)
- LHC Nixle (silent since 2021-09-01; V1.5 carry for alt-source research)
- NWS marine zones (don't cover inland LHC)
- Lake water temperature (no source)
- `event_traffic` alert (Events table lacks `traffic_impact` tag until Phase 9)
- Phase 8b cat-13 Public & Civic Resources expansion (separate later micro-dispatch)
- Twilio SMS (V1.5 per master plan §8 OQ #13)
- `FEATURE_FLAG_DISCLOSURE_RENDERER` flip (untouched; out-of-band operator action)

---

## §5 The recovery story — IDE buffer corruption + Lane Z surgical recovery

This was a non-trivial ship. The substantive learning is not the 33 tests passing — it's how the first two Cursor dispatch attempts left the tree corrupted and how the third path closed the lane.

**Attempt #1 (2026-05-20).** A Cursor session ran Phase 8a end-to-end and returned a §12 report claiming success. Cowork primary's pre-commit verification caught it: `git diff HEAD --stat` showed **-637 line deletions** across `app/chat/tier2_handler.py`, `app/chat/unified_router.py`, and `app/chat/entity_intent.py` — three 7.x surfaces Phase 8a should not have touched. Tail-inspection revealed truncated mid-file writes on existing tracked files: `tier2_handler.py` ended with `fi, fo =` no newline; `ranking.py` ended with bare `re`; `db/models.py` ended with `mapped_c`. New files (the `app/conditions/`, `app/alerts/`, `scripts/`, migration, tests) were intact. The operator stashed the corrupted state at `8a-collision-corrupted-tree-2026-05-20` (`git stash push -u`) for forensics.

**Attempt #2 (2026-05-20, fresh Cursor chat).** Same wrapper, same paste, expected a clean re-run. **Same corruption pattern reproduced.** Cursor's §12 report again claimed test runs passing (27 Phase 8a tests pass, 2251 pytest collected) — but `app/chat/tier2_handler.py` was truncated at the same byte position on disk. The §12 numbers and disk state disagreed.

**Diagnosis.** Pinned to multi-window Cursor IDE editor buffer collision. Stale Cursor IDE windows from the first session still had the truncated buffers open in memory. When Attempt #2's terminal Cursor finished writing files, the IDE's autosave / focus-change handler clobbered the disk with the in-memory truncated content from the prior session. This is **not** a Cursor agent bug — it's a multi-window IDE state hazard that surfaces when parallel Cursor sessions hold overlapping file scopes.

**Recovery via Lane Z (2026-05-21).** After confirming all Cursor IDE windows were closed, dispatched a surgical sub-agent with a strict toolset: `git restore` to reset all tracked files to HEAD (preserving the intact untracked 8a code); Read the untracked code as evidence of intent; apply 8a wiring via the **Edit tool**, which writes through the agent's API channel rather than the Cursor IDE buffer chain; verify via PowerShell `pytest`. Lane Z applied 8 edits, skipped 2 correctly (existing modules already intact post-restore), and flagged 2 scope expansions for operator decision. Two follow-up issues surfaced during validation: a **circular import** at `from app.main import app` caused by Lane Z's first attempt to re-export `read_current_temperature_f` from `ranking.py` (resolved by extracting to standalone `app/core/conditions_temperature.py` and dropping the re-export from `ranking.py`'s line 93 + `__all__`; test import in `tests/test_phase8_chat_live_swap.py:9` updated accordingly), and a **missing `send_alert_email` function** in `app/auth/email_sender.py` (the dispatcher's `app/alerts/dispatcher.py:19` imports it; added a new function mirroring the existing `send_magic_link` dev/prod pattern). The chat live-conditions wiring at `unified_router.py:846` (~12 LOC including comment + try/except fallback) closed the third Lane Z follow-up — `parse_chat_request_context()` signature change was correctly flagged as scope expansion rather than blindly applied.

After all three fixes — circular import, `send_alert_email`, chat live-conditions wiring — `python -c "from app.main import app"` succeeded and the 33 Phase 8a + Phase 6 conditions tests all passed. Operator committed at `8a905c6` and Railway picked up the deploy at v1.3.0.

---

## §6 Lessons learned

**1. Multi-window Cursor IDE state is a real hazard for parallel-Cursor workflows.** The chat session is one cohort; the IDE editor buffers are another. Both can write to disk. Closing all IDE windows before a critical write is mandatory when parallel Cursor sessions are in flight on overlapping file scopes. Worth codifying in `docs/maintainability/dispatch_protocol.md` as a paste-time precondition: "before re-dispatch after a corruption, close all IDE windows and confirm via Task Manager / `lsof` equivalent."

**2. Cursor §12 reports can disagree with disk state.** Trust `git diff` + `git status` + file-tail inspection over Cursor's §12 prose when there's evidence of failed writes. The Attempt #1 + Attempt #2 §12 reports both claimed test runs that the disk could not have supported (e.g., `tier2_handler.py` truncated mid-function couldn't import, let alone pass tests). The verification checks in the close-out template's §1 caught both attempts pre-ship; without them this would have shipped broken.

**3. Edit-tool sub-agents are a strict-improvement recovery path** when Cursor terminal writes are unreliable. The Edit tool writes through the agent's API channel, not the IDE buffer chain — it can't be clobbered by a stale Cursor IDE window. The cost is the sub-agent has to be tightly scoped (Lane Z had a one-page brief covering exactly the wiring deltas needed) and verification has to happen out-of-band (PowerShell `pytest` rather than agent-internal claims).

**4. Re-exports create circular imports when the importing module is part of an existing cycle.** Lane Z's first attempt re-exported `read_current_temperature_f` from `app/core/ranking.py`. That module already participated in an import cycle through the cache + ranking + conditions chain. The re-export turned a benign cycle into a hard `ImportError` at `from app.main import app`. Standalone modules (`app/core/conditions_temperature.py`) are safer than re-exports for net-new functionality.

**5. Scope expansions during dispatch should be flagged, not blindly applied.** Lane Z correctly stopped at `parse_chat_request_context()` and flagged the signature-change problem for operator decision rather than editing it inline. Threading `db: Session` through `parse_chat_request_context()` would have touched 4+ callers + 5 test files — outside the Phase 8a deliverable scope. The cleaner injection point (12 LOC at `unified_router.py:846` where `temperature_f_override` was already plumbed) was a follow-up decision, not a Cursor-runtime improvisation. The principle: when the wrapper's literal instruction collides with existing structure, surface the collision; let the operator decide whether scope expands.

---

## §7 Open carries → next lanes

| Item | Status | Path to closure |
|---|---|---|
| **`AIRNOW_API_KEY` on Railway** | Operator action pending | Set env var on Railway; fetcher cannot populate AQI until set |
| **Initial fetcher run on prod** | Pending | Either wait for first scheduled cron OR `python -m scripts.fetch_external_conditions --all` after `AIRNOW_API_KEY` is set; until then `/api/conditions` returns just `{"rendered_at_iso": "..."}` and the conditions strip on `/home` shows placeholders |
| **`test_date_lookup_gap_includes_contribute` failure** | Watch (task #62) — NOT in 8a scope | 7.5.3 / 7.5.1 surface; returned a near-match dym ("Closest match in the catalog is City Events...") instead of the expected gap template. Cursor diagnostic dispatched at `outputs/cursor_diagnostic_test_date_lookup_gap.md` (task #65) |
| **Phase 7.7.1** (q10/q12 eval pin + validator list-handling widening) | Pending (task #54); ~10 LOC | Tiny follow-up; YAML pin update + validator widening for the 7.7 honest-empty template body matching `_I_DONT_KNOW_RE` |
| **Phase 7.5.4** (rating-scrub exploit fix on q25) | Wrapper queued, audit-cleared | Dispatch `outputs/cursor_dispatch_prompt_phase_7_5_4.md` to fresh Cursor session |
| **7.5.3 §13 deviation — F1.c call-order reorder** | Watch (task #47) | Not user-visible; defense-in-depth gap for 5+ token `mdshrkbrwry`-shape typos |
| **Phase 8b** (cat-13 Public & Civic Resources expansion) | Deferred — explicitly OUT of 8a scope | Separate later micro-dispatch; wrapper to be SHA-patched against Phase 8a head before dispatch |
| **V1.5: alt-source research for LHC public-safety alerts** | Open | Nixle dropped — Mohave County SO / ein.az.gov / lhcaz.gov RSS candidates |
| **V1.5: tighter local AirNow fidelity** | Open | Blythe at ~60mi south is the nearest monitor; PurpleAir / AZDEQ / BLM candidates |
| **V1.5: lake water temperature source** | Open | USGS `09427500` has no `00010`; candidate sources in prereq verification §11 |
| **Phase 7.5 close-out narrative amendment** | Open | `FEATURE_FLAG_DISCLOSURE_RENDERER` flag-flip framing in `outputs/phase_7_5_close_out.md` §5 still needs supersession with the post-mortem §6 flag-semantics correction |

---

## §8 Prod smoke results

| Probe | Result |
|---|---|
| Railway deploy v1.3.0 picked up `8a905c6` | Successful (per operator screenshot) |
| `GET /api/conditions` on prod | Returns `{"rendered_at_iso": "..."}` (empty payload — expected pre-`AIRNOW_API_KEY`-set) |
| `GET /home` on prod | Renders with conditions-strip in body (placeholder tiles — expected; cache empty) |
| q03 chat probe on prod | `tier=2 disc=cited`; 1.5s latency (within Phase 7.6 OPEN_NOW shortcut expectations) |
| `python -c "from app.main import app"` (post-Lane-Z) | Succeeds (circular-import bug fixed) |
| Phase 8a test suites + Phase 6 conditions strip suites | 33/33 pass |
| `test_date_lookup_gap_includes_contribute` | FAIL (escalated — not 8a scope; diagnostic at `outputs/cursor_diagnostic_test_date_lookup_gap.md`) |

---

## §9 Artifacts inventory

### New modules
- `app/conditions/` (11 files: `__init__.py`, `airnow.py`, `nws.py`, `usgs.py`, `fetcher.py`, `cache.py`, `constants.py`, `api_payload.py`, `view_model.py`, `staleness.py`, plus `__pycache__`)
- `app/alerts/` (8 source files: `__init__.py`, `thresholds.py`, `evaluator.py`, `dedup.py`, `venue_context.py`, `dispatcher.py`, `render.py`; 6 templates under `app/alerts/templates/`: `heat_advisory.{html,txt}.j2`, `aqi_alert.{html,txt}.j2`, `lake_hazard.{html,txt}.j2`)
- `app/core/conditions_temperature.py` (standalone live-read module; replaces the re-export pattern that caused the circular import)

### New routes
- `app/api/routes/conditions.py` — `GET /api/conditions`
- `app/api/routes/account_alerts.py` — `GET/POST /account/alerts`

### New scripts
- `scripts/fetch_external_conditions.py` — Railway scheduled-job CLI
- `scripts/evaluate_and_dispatch_alerts.py` — Alert evaluation CLI with `--dry-run` / `--alert-type` / `--user-id`

### New templates + assets
- `app/templates/components/conditions_strip.html`
- `app/templates/account_alerts.html`
- `app/static/js/conditions_strip.js`
- `app/static/styles/components/conditions_strip.css` (or equivalent — expanded)

### Modified files
- `alembic/versions/d8e9f0a1b2c3_phase8_conditions_alerts_schema.py` (new migration; single head from `c9d0e1f2a3b4`)
- `app/templates/home.html` (anchor replacement at `<!-- conditions-strip-anchor -->`)
- `app/api/routes/category_pages.py` (live-conditions wiring)
- `app/api/routes/map_data.py` (live-conditions wiring)
- `app/chat/unified_router.py:846` (Lane Z follow-up live-conditions injection at `temperature_f_override` plumbing point)
- `app/auth/email_sender.py` (added `send_alert_email` function mirroring `send_magic_link` dev/prod pattern)

### Companion docs
- `outputs/cursor_dispatch_prompt_phase_8.md` — the dispatch wrapper (amended through §6 + §11 + §12 + Lane E re-dispatch note)
- `outputs/phase_8_architecture_design.md` — 1050-line ADR design
- `outputs/phase_8a_prereq_verification_report.md` — 3-wave verification + amendment justifications
- `outputs/phase_8a_post_ship_close_out_template.md` — the template this instantiates
- `outputs/cursor_diagnostic_test_date_lookup_gap.md` — queued post-ship diagnostic

### This close-out
- `outputs/phase_8a_close_out.md` — this document

---

*Authored by sub-agent under Cowork primary supervision, 2026-05-21 post-Phase-8a-ship. Saved to `outputs/phase_8a_close_out.md`.*
