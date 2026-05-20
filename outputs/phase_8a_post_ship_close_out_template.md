# Phase 8a Post-Ship Close-Out Template

> **What this is:** the reusable Cowork-primary rhythm for closing out Phase 8a (conditions + alerts infrastructure: AirNow + NWS-AZZ002 + USGS-09427500 + cache + conditions strip + chat live-swap + alert dispatch + thresholds + subscription UI + email templates + dedup) when Cursor returns with the §12 final report. Pre-positioned 2026-05-19 post-`7143976` so the close-out cycle is fast when Phase 8a ships.
>
> **Author:** Cowork primary, 2026-05-19.
>
> **Instantiate as:** `outputs/phase_8a_close_out.md` when Cursor returns with its §12 report.
>
> **Companion docs (authoritative for acceptance gates):**
> - `outputs/cursor_dispatch_prompt_phase_8.md` — the dispatch wrapper Cursor consumed (amended through §6 + §11 + §12 by 2026-05-19 + 5350977)
> - `outputs/phase_8_architecture_design.md` — design spec (1050+ lines; §4 cache schema + §6 alert evaluator + §6.3 thresholds + §9 conditions strip)
> - `outputs/phase_8_operator_prereq_checklist.md` — prereqs status board (RESOLVED 2026-05-19)
> - `outputs/phase_8a_prereq_verification_report.md` — the 3-wave verification + amendment justifications (§1 + §11 + §12)

---

## §1 Pre-flight verification (do this BEFORE declaring ship)

Run these checks against the working tree where Cursor left files:

```powershell
# 1. Confirm Cursor did NOT git-commit
git status --short
# Expected: M lines on the Phase 8a touched files (new app/conditions/* + new
# app/alerts/* + new scripts/* + new templates/* + new alembic/versions/*);
# verify Cursor did NOT push or amend.

# 2. Confirm alembic head advanced by ONE
python -m alembic current
# Expected: a new revision ID chaining from c9d0e1f2a3b4 (Phase 7).
# Phase 8a ships ONE additive migration extending the existing
# external_conditions_cache table with source-station attribution columns
# (per phase_8_architecture_design.md §3.1).
python -m alembic heads
# Expected: SINGLE head. If multiple heads: alembic-collision pattern
# (gotcha #18 in dispatch_channels.md). HALT and report.

# 3. Confirm pytest passes
python -m pytest -q
# Expected: 2166 → ~2210+ passed + 2 skipped (Phase 8a likely adds ~40-60 tests
# across fetcher subsystems + alert evaluator + thresholds + dedup + cache
# migration + view-model construction + attribution chip rendering).

# 4. Confirm ruff clean
ruff check app/ tests/ scripts/
# Expected: 0 errors

# 5. THE GATES — verify the substantive surfaces work end-to-end
python -m scripts.fetch_external_conditions --source airnow_86403 --dry-run
# Expected: returns Blythe CA row (or whatever the current nearest AirNow
# station within AIRNOW_DISTANCE_MI=100). Verify source-station attribution
# fields are populated.

python -m scripts.fetch_external_conditions --source nws_alerts_lhc_zone --dry-run
# Expected: returns 0..N active alerts for AZZ002. May be empty if no active
# weather alerts at fetch time — that's a valid response, not a failure.

python -m scripts.fetch_external_conditions --source usgs_09427500 --dry-run
# Expected: returns gauge_height (00065) + reservoir_storage (00054).
# Does NOT include 00010 (water temp) or 00060 (discharge) — neither is
# available at 09427500 per §12 verification.

python -m scripts.evaluate_and_dispatch_alerts --dry-run
# Expected: logs evaluator output for all 4 alert_types (heat_advisory,
# aqi_alert, lake_hazard, event_traffic-deferred); reports candidate
# subscriptions; does NOT actually send emails.
```

**If any of 1–5 diverges from Cursor's §12 claim:** STOP. Cursor's report and reality disagree. Either re-dispatch with the discrepancy as context, OR the operator triages the gap manually.

---

## §2 Acceptance-gate verification

Per `outputs/cursor_dispatch_prompt_phase_8.md` §3 deliverables (a)-(i) + §6/§11/§12 amendments:

| Gate | Status | Verification |
|---|---|---|
| (a) AirNow + NWS + USGS fetcher subsystem with per-source Railway services | ✅ / ❌ | New `app/conditions/airnow.py` + `nws_alerts.py` + `nws_forecast.py` + `usgs.py` + `base.py`; new `scripts/fetch_external_conditions.py`; with_retry envelope applied |
| (b) /api/conditions endpoint with source-station attribution fields | ✅ / ❌ | New `app/api/routes/conditions.py`; JSON response includes `current_aqi` + `current_aqi_parameter` + `aqi_source_station_name` + `aqi_source_state_code` + `aqi_source_distance_mi` + others per wrapper |
| (c) Today in Havasu conditions strip on home.html + anchored at `<!-- conditions-strip-anchor -->` | ✅ / ❌ | New `app/templates/components/conditions_strip.html` + `static/js/conditions_strip.js` + amended `home.css`; renders attribution chip |
| (d) Chat live-conditions swap (`STUB_CURRENT_TEMPERATURE_F` → `read_current_temperature_f()`) | ✅ / ❌ | `app/core/ranking.py` modified; Phase 6.3 + Phase 7 import chains updated; stub-fallback preserved for tests |
| (e) Alert dispatch evaluation job | ✅ / ❌ | New `scripts/evaluate_and_dispatch_alerts.py` with --dry-run + --alert-type + --user-id flags |
| (f) Alert trigger threshold definitions at `app/alerts/thresholds.py` | ✅ / ❌ | New file; constants for heat_advisory + aqi_alert + lake_hazard + AIRNOW_DISTANCE_MI + LHC_NWS_ZONE_ID + USGS_LAKE_HAVASU_SITE + LAKE_HAZARD_NWS_KEYWORDS (inland-LHC set) |
| (g) Alert subscription UI on /account/alerts | ✅ / ❌ | New `app/templates/account_alerts.html` + minimal form atop Phase 2A account-lite auth |
| (h) Alert email templates with venue-context mapping | ✅ / ❌ | New `app/templates/emails/heat_advisory.html` + `aqi_alert.html` + `lake_hazard.html`; reuses Phase 2A.1 Resend integration |
| (i) Per-alert dedup via alerts_dispatched table | ✅ / ❌ | 6-hour dedup window via lookback query at evaluation time; additive column added to alerts_dispatched if needed |
| §6: USGS narrowed to 09427500 + 00065/00054 only | ✅ / ❌ | `app/conditions/usgs.py` does NOT fetch 09427520; does NOT fetch 00010 / 00060 |
| §6: Nixle DROPPED from V1 | ✅ / ❌ | No `app/conditions/nixle.py` module; lake_hazard trigger uses NWS-zone + USGS-gauge-drop only |
| §11: NWS scoped to AZZ002 land zone | ✅ / ❌ | `app/conditions/nws_alerts.py` fetches `api.weather.gov/alerts/active?zone=AZZ002`; no marine cache surface; LAKE_HAZARD_NWS_KEYWORDS is inland-LHC set |
| §12: AirNow Blythe-style attribution | ✅ / ❌ | Cache stores source-station fields; conditions strip renders attribution chip ("from Blythe, CA ~60mi south"); aqi_alert evaluator is multi-row tolerant |
| Pytest baseline holds + nets new | ✅ / ❌ | `python -m pytest -q`; baseline 2166 → expected ~2210+ |
| Ruff clean | ✅ / ❌ | `ruff check app/ tests/ scripts/` |
| Alembic head advanced ONE step from `c9d0e1f2a3b4` | ✅ / ❌ | New revision ID; SINGLE head; portable migration (no Postgres-only types per Phase 4.1 precedent) |
| File scope respected (no Phase 8b cat-13 work; no Phase 9 events; no master plan §4 edits beyond what Cursor was instructed) | ✅ / ❌ | Verify Cursor's modified file list |

**All gates met:** Phase 8a is SHIPPED. Proceed to §3.
**Any gate fails:** Phase 8a is NOT SHIPPED. Re-dispatch or re-investigate.

---

## §3 Per-deliverable disposition triage (Cursor's §12 must include)

Cursor 8a's §12 report should include the following:

### §3.1 Per-source fetcher behavior verification

| Source | Expected disposition | Verify |
|---|---|---|
| `airnow_86403` | Returns 1-row Blythe CA at distance=100 (single O3 param) | Cursor's smoke-test output + `app/conditions/airnow.py` source-station extraction logic |
| `nws_alerts_lhc_zone` | Fetches AZZ002 with UA header; handles 0..N alerts; parses CAP shape | Cursor's smoke-test output + UA header in `app/conditions/nws_alerts.py` |
| `nws_forecast_lhc_zone` | 10-min cadence; returns hourly + 7-day for AZZ002 | Cursor's smoke-test output |
| `usgs_09427500` | Returns 00065 (gauge ft) + 00054 (storage ac-ft); does NOT fail on missing 00010/00060 | Cursor's smoke-test output + handling of "parameter not measured" case |

### §3.2 Alert evaluator behavior verification

| Alert type | Expected behavior | Verify |
|---|---|---|
| `heat_advisory` | Fires on NWS Heat Advisory / Excessive Heat Warning / Heat Watch in AZZ002 | Cursor's `app/alerts/evaluator.py` matches keyword set against `nws_alerts_lhc_zone.data` |
| `aqi_alert` | Multi-row tolerant; fires on ANY ParameterName row category NOT IN {Good, Moderate}; treats PM2.5/PM10 absence as data-not-available | Cursor's evaluator iterates rows array; LHC currently single-row O3; verify the row iteration logic |
| `lake_hazard` | Fires on NWS-AZZ002 keyword match (inland set: flash flood / flood warning / flood advisory / lake wind / high wind / wind advisory / blowing dust / dust storm / severe thunderstorm) OR USGS gauge drop > 2.0 ft in 24h | Cursor's evaluator + keyword set in `thresholds.py` |
| `event_traffic` | DEFERRED to V1.5 / Phase 9.5 | Verify evaluator skips event_traffic with a "deferred" log line |

### §3.3 Conditions strip rendering verification

Cursor's §12 should include a screenshot OR HTML snippet showing:

- AQI tile with **attribution chip** ("AQI 47 (O3) — from Blythe, CA ~60mi south")
- Temperature tile with staleness label ("Updated 12 min ago")
- Lake-level tile (gauge height in ft)
- Lake-storage tile (reservoir storage in ac-ft)
- NWS-alert tile (only renders when active alert in AZZ002)
- Mobile-stacked layout shown alongside desktop horizontal layout

If attribution chip is missing from AQI tile, **STOP**: §12 amendment was supposed to land this. Re-investigate before declaring ship.

### §3.4 Chat live-conditions swap verification

Cursor's §12 should include:

- `app/core/ranking.py` diff showing `STUB_CURRENT_TEMPERATURE_F = 105.0` → `read_current_temperature_f()` function
- Test: confirm Phase 6.3 ranking still ranks by heat-bias; Phase 7 chat tier-3 preamble still receives current-temperature; test fixtures use stub-fallback when cache not populated
- Integration test confirming the swap is atomic (single helper used by both Phase 6.3 + Phase 7 import chains)

---

## §4 Commit batch recommendation (Rule 8)

**Two substantive commits + 0–1 fixup commits.**

### §4.1 Phase 8a substantive commit

```powershell
# Stage Cursor's Phase 8a changes
git add app/conditions/ `
        app/alerts/ `
        app/api/routes/conditions.py `
        app/api/routes/alerts.py `
        app/core/ranking.py `
        app/templates/components/conditions_strip.html `
        app/templates/account_alerts.html `
        app/templates/emails/ `
        app/static/js/conditions_strip.js `
        app/static/styles/components/conditions_strip.css `
        scripts/fetch_external_conditions.py `
        scripts/evaluate_and_dispatch_alerts.py `
        alembic/versions/<new_revision_id>_phase8a_*.py `
        tests/test_phase8a_*.py

# Verify scope
git status

# Commit
git commit -m "feat(phase8a): conditions + alerts infrastructure -- AirNow + NWS-AZZ002 + USGS-09427500 fetchers; conditions strip with source-station attribution chip; chat live-conditions swap; alert dispatch + thresholds + subscription UI + email templates + dedup"

git push
```

### §4.2 Docs close-out commit

```powershell
git add outputs/phase_8a_close_out.md `
        docs/maintainability/master_build_plan.md `
        docs/STATE.md

git commit -m "docs(phase8a): close-out + ledger -- Phase 8a SHIPPED <SHA>; pytest 2166 → <new_count>; alembic <new_head>; conditions strip live; alerts evaluator wired"

git push
```

### §4.3 Optional ruff/test fixup commit

If Cursor's PR has lint issues OR a test needs adjustment, ship a separate `chore(phase8a)` fixup commit per Rule 8.

---

## §5 STATE.md + master plan ledger updates

### §5.1 STATE.md "Recently shipped" prepend

Prepend a new top-level entry above the Phase 6.5 entry (~line 148):

```markdown
- **Phase 8a — Conditions + alerts infrastructure SHIPPED on origin (2026-05-XX).** Commit `<SHA>`. (a) AirNow + NWS-AZZ002 + USGS-09427500 fetcher subsystem with per-source Railway services (AirNow 30min / NWS alerts 15min / USGS 30min / NWS forecast 10min); (b) /api/conditions endpoint with source-station attribution; (c) Today in Havasu conditions strip live + attribution chip ("from Blythe, CA ~60mi south") + honest staleness; (d) chat live-conditions swap (STUB_CURRENT_TEMPERATURE_F → read_current_temperature_f()); (e-i) alert dispatch + thresholds + subscription UI + email templates + 6-hour dedup. **3-wave amendments executed per §6 + §11 + §12 of `outputs/phase_8a_prereq_verification_report.md`:** USGS narrowed to 09427500 (00065+00054 only); 09427520 dropped (dead since 2006); Nixle dropped V1 (silent since 2021); NWS marine dropped (inland LHC); AZZ002-scoped land alerts via KVEF Las Vegas; AirNow Blythe ~60mi O3-only with multi-row tolerance + attribution chip. Pytest 2166 → <new_count> (+<delta> net-new). Alembic head <new_head>. Ruff clean. **CI:** ✅ green at SHIP. **Phase 7.5's FEATURE_FLAG_DISCLOSURE_RENDERER flip + Phase 8a SHIP completes the Phase 7 + 8 trust-layer narrative arc.** Close-out at `outputs/phase_8a_close_out.md`. Next: **Phase 8b** (cat-13 expansion) + **Phase 9** (events + RRULE + Things to Do).
```

### §5.2 master_build_plan.md §4 Phase 8 ship-line

Find the existing Phase 8 deliverables block. Insert a `**SHIPPED <SHA> 2026-05-XX**` line at the bottom of the deliverables section (before §4 Phase 9), mirroring the Phase 7 + Phase 7.5 ship-line shape.

---

## §6 Carries forward (post-ship)

Expected V1.5 carries that should be documented in Cursor's §12:

- **Water temperature data source** — USGS 09427500 has no 00010; V1.5 candidates per `outputs/phase_8a_prereq_verification_report.md §11`
- **LHC public-safety alert source replacement** — Nixle dropped; V1.5 alt-source research
- **Tighter local AirNow fidelity** — Blythe at ~60mi; V1.5 PurpleAir / AZDEQ / BLM candidates
- **NWS API User-Agent header explicit-lock** — Cursor's `app/conditions/nws_alerts.py` should set UA per §11.5 of verification report
- **`hint_extractor` token-budget perf** — Phase 7.5 carry; not Phase 8a-blocking but worth tracking

Add any new V1.5 carries surfaced during Phase 8a execution (e.g., Resend rate-limit edge cases, NWS API rate-limit gotchas, USGS modern OGC API quirks).

---

## §7 Post-Phase-8a unblocks

| Lane | Status |
|---|---|
| Lane J — Phase 8b (cat-13 expansion) | UNBLOCKED — wrapper at `outputs/cursor_dispatch_prompt_phase_8b.md`; SHA-patch against Phase 8a HEAD before dispatch |
| Lane K — Phase 9 (events + RRULE + Things to Do) | UNBLOCKED — wrapper at `outputs/cursor_dispatch_prompt_phase_9.md`; SHA-patch against Phase 8a HEAD before dispatch; Phase 9 Source 2 (golakehavasu.com) absorbed per Lane M §8 #2 lock |
| Conditions strip on production homepage | LIVE — populated from `external_conditions_cache` table; updates per fetcher cadence |
| Heat advisory + AQI alert + lake_hazard alerts | LIVE — evaluator runs every 15 min; emails dispatched via Resend |

---

## §8 If something goes wrong

| Symptom | Action |
|---|---|
| `python -m alembic heads` returns multiple heads | Alembic-collision per gotcha #18. Identify which migration is unique; revert the non-shipping one; re-attempt. |
| Conditions strip renders blank tiles | Likely cache empty (fetchers haven't run yet OR Railway scheduled jobs not yet configured). Run `python -m scripts.fetch_external_conditions --source airnow_86403` manually; verify cache populated; reload homepage. |
| AirNow returns empty even at distance=100 | Either monitor outage at Blythe OR rate-limit hit. Check airnowapi.org service status; check rate-limit logs in the fetcher output. |
| NWS alerts API returns 403 | UA header missing or malformed. Verify `app/conditions/nws_alerts.py` sets `User-Agent: havasu-chat/1.0 <contact-email>` per §11.5 V1.5 carry. |
| USGS 09427500 returns empty | Site temporarily offline OR USGS API outage. Cache should preserve last-known-good state with staleness flag. |
| Alert dispatch fires false-positive (e.g., heat_advisory on 70°F day) | Verify NWS data path; `nws_alerts_lhc_zone.data` should contain a heat advisory `event` field. If not, evaluator threshold logic has a bug. |
| Conditions strip attribution chip missing | §12 amendment not actually wired. Re-check `ConditionsTile.attribution_chip` field is populated by `app/conditions/view_model.py` from `aqi_source_*` cache fields. |
| Pytest below 2166 | Cursor broke a pre-existing test. Bisect to find the offending diff; either fix or escalate. |

---

*Authored by Cowork primary at the post-`7143976` Lane T pre-positioning step. Lives at `outputs/phase_8a_post_ship_close_out_template.md`. Instantiated as `outputs/phase_8a_close_out.md` when Cursor 8a returns §12 — reduces close-out friction by ~30-45 min per ship. Models Phase 7.5's template shape adapted for Phase 8a's 9-deliverable + 3-wave-amendment surface.*
