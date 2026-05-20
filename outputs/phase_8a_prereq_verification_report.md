# Phase 8a prereq verification report — live web checks of USGS + Nixle (P0 findings)

> **What this is:** the post-`1e3f291` verification of the 3 Phase 8a operator prereqs from `outputs/phase_8_operator_prereq_checklist.md`. Live web-fetch verification of USGS sites 09427500 + 09427520 + Nixle agency 3726 RSS feed surfaced **three substantive scope-changing findings** that block Lane I from dispatching as currently wrapped. The wrapper at `outputs/cursor_dispatch_prompt_phase_8.md` + the prereq checklist + the architecture design at `outputs/phase_8_architecture_design.md` all need amendments before Cursor sees the brief.
>
> **Author:** Cowork primary, 2026-05-19 (working date per env; project calendar reads post-`1e3f291`).
>
> **TL;DR:** **1 of 3 prereqs YELLOW with scope-change; 1 of 3 prereqs HARD-RED (dead site); 1 of 3 prereqs YELLOW-to-RED (silent feed); 1 of 3 prereqs operator-action-pending (AirNow registration).** **Lane I is NOT safe to dispatch** until the wrapper is amended and the operator decides on replacement sources for the dead/silent surfaces.
>
> **Companion docs:** `outputs/phase_8_operator_prereq_checklist.md` (the original status board this report supersedes); `outputs/phase_8_nixle_agency_id_lookup.md` (the agency-ID research that did NOT verify recency); `outputs/phase_8_architecture_design.md` (1050-line Plan-agent output that references the same sources); `outputs/cursor_dispatch_prompt_phase_8.md` (the wrapper Cursor would consume).

---

## §1 Executive summary

| Prereq | Status | Finding |
|---|---|---|
| USGS primary site `09427500` (Lake Havasu near Parker Dam) | ✅ GREEN for liveness / ⚠️ RED on parameter assumptions | Site is active + reporting; latest reading 2026-05-19 15:30 MST. **BUT only reports `00054` (reservoir storage, acre-ft) + `00065` (gauge height, ft). NO `00010` (water temperature). NO `00060` (discharge).** Wrapper assumes all 3 of gauge height + temp + discharge available; reality is 2-of-3 with one being storage-not-discharge. |
| USGS secondary site `09427520` (Colorado River below Parker Dam) | ❌ HARD-RED | Site is **historic-only since 2006**. iv-API returns the timeSeries metadata with method note `[Historic 10/1987 to 09/2006]` and **empty values array**. Wrapper's planned secondary site is dead. |
| LHC Nixle RSS at agency `3726` (LHC Fire Department) | ⚠️ YELLOW-to-RED | RSS feed responds HTTP 200 with valid XML; agency confirmed as LHCFD. **BUT lastBuildDate = Wed, 01 Sep 2021 16:46:18 -0700.** Most-recent item dates back to **2021-09-01**. Feed has been **silent for ~4 years 8 months.** Phase 8's lake_hazard trigger plan (keyword-match on Nixle RSS) will receive zero new signal indefinitely. |
| AirNow API key registration | ⚠️ OPERATOR-ACTION-PENDING | Not verified live (requires operator account creation + email-activation). Walkthrough at `phase_8_operator_prereq_checklist.md §2` is still correct; standalone-blocker on the operator path. |

**Net Lane I posture:** the wrapper currently encodes `USGS_LAKE_HAVASU_PRIMARY_SITE = "09427500"` + `USGS_LAKE_HAVASU_SECONDARY_SITE = "09427520"` + `LHC_NIXLE_FIRE_AGENCY_ID = "3726"` with the assumption that all three provide live signal. **Two of three do not.** Dispatching as-is would build production code paths against a dead historical site + a silent feed.

**Amendment status (2026-05-19):** §6 wrapper amendments **LANDED** in `outputs/cursor_dispatch_prompt_phase_8.md`, `outputs/phase_8_operator_prereq_checklist.md`, and `outputs/phase_8_architecture_design.md` using recommended options (USGS §2 Option A single-site `00065`+`00054`; Nixle §4 Option A dropped from V1; `lake_hazard` reframed to NWS + USGS gauge-drop). Lane I dispatch-ready **after AirNow key** is operator-smoke-tested.

---

## §2 USGS site 09427500 — primary (✅ GREEN liveness / ⚠️ RED parameter assumptions)

### Verification

Fetched `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&period=P1D` (legacy API, no parameterCd filter → returns all available parameters).

**Site metadata confirmed:**
- siteName: `LAKE HAVASU NEAR PARKER DAM, AZ-CA`
- siteType: `LK` (lake)
- Lat/lon: `34.31612564 / -114.1571702`
- HUC: `15030101`
- Timezone: MST (does NOT observe DST per `siteUsesDaylightSavingsTime: false`)

**Parameters actually reported (post-fetch 2026-05-19 22:58 UTC):**

| Variable code | Variable name | Latest value | Latest timestamp |
|---|---|---|---|
| `00054` | Reservoir storage, acre-ft | 589,100 ac-ft | 2026-05-19 15:30 MST |
| `00065` | Gauge height, ft | 49.02 ft | 2026-05-19 15:30 MST |

**Parameters NOT reported (despite being requested in a follow-up explicit-parameterCd query):**

- `00010` — Water temperature (the wrapper's heat-hazard signal)
- `00060` — Discharge / streamflow (the wrapper's lake-outflow signal)

When the iv API is queried with `parameterCd=00065,00010,00060`, only the `00065` timeSeries comes back — confirming `00010` + `00060` are not measured at this site.

### Implications for Phase 8a

The wrapper at `outputs/cursor_dispatch_prompt_phase_8.md` §3.2.3 plans `app/conditions/usgs.py` to fetch gauge height + water temperature + discharge. **Water temperature is not available at 09427500.** Reservoir storage (acre-ft) is available + meaningful for lake-fullness UX but isn't in the wrapper's planned schema.

### Recommended wrapper amendment

Pick ONE:

**Option A — Narrow scope to lake-level only.** Update Phase 8a to fetch + cache only `00065` gauge height + `00054` reservoir storage at site 09427500. Drop water temperature + discharge from the V1 conditions schema. Re-frame the design doc's "lake hazards" section to remove the discharge-based extreme-reading trigger; replace with a gauge-height delta heuristic if a lake-hazard surface is still desired (e.g., "level drop > 2ft in 24h → notify city"). Re-frame water temperature as a V1.5 carry — operator can add a secondary source (Bureau of Reclamation? NDBC? local sensor partnership?) in V1.5.

**Option B — Add a second USGS site for water temperature.** Web search surfaced USGS site `09426630` (Bill Williams River at Lake Havasu, Abv HWY-95, AZ) as a candidate. I attempted to verify its current parameter list via `waterservices.usgs.gov/nwis/iv/?sites=09426630` but the URL was outside web_fetch provenance — **operator browser-verify required.** If 09426630 reports `00010`, encode it as a tertiary site dedicated to water-temp; if it doesn't, fall back to Option A or Option C.

**Option C — Drop USGS entirely from Phase 8a; defer to a Phase 8c follow-on.** If the available USGS surface (lake-level + storage) doesn't justify the ingest infrastructure, defer USGS entirely to a future phase. Phase 8a still ships AirNow + NWS without USGS dependency. This is the least-effort path but also drops the design doc's "lake conditions" pillar of the trust layer.

**Recommendation: Option A (narrow scope).** The fact that 09427500 actively reports gauge height + storage is real and useful — both are end-user-meaningful ("the lake is at 49.0 ft" or "the lake is 589k ac-ft full"). Dropping water-temp + discharge is honest scope-narrowing, not capability loss. The design doc's lake-hazard trigger needs reframing; the gauge-height-delta heuristic is defensible.

---

## §3 USGS site 09427520 — secondary (❌ HARD-RED; historic-only since 2006)

### Verification

Fetched `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427520&parameterCd=00065,00010,00060&period=P1D`.

**Site metadata confirmed:**
- siteName: `COLORADO RIVER BELOW PARKER DAM, AZ-CA`
- siteType: `ST` (stream)
- Lat/lon: `34.29558497 / -114.14023`
- HUC: `15030104`

**Critical finding from the API response:**

The `timeSeries[0].values[0]` is structured but contains **`value: []`** (empty array). The associated method object reads:

```json
"method": [{"methodDescription": "[Historic 10/1987 to 09/2006]", "methodID": 210026}]
```

This means USGS retired active measurement at site 09427520 in **September 2006**. The iv-API still responds with the site shape (because the historic record exists) but the live-values payload is permanently empty. No backfill, no recent values. **Dead for our purposes.**

### Implications for Phase 8a

The wrapper encodes `USGS_LAKE_HAVASU_SECONDARY_SITE = "09427520"` with an explicit purpose ("outflow/downstream-flow queries"). That purpose cannot be served by a dead site. The prereq checklist's §3 step 3 anticipated this risk ("Operator should browser-confirm water-temp availability before Phase 8 architecture finalizes") but the recommendation defaulted to "browser-verify" without the verification actually happening pre-wrapper-authoring. **This report closes that gap and surfaces the hard-RED state.**

### Recommended wrapper amendment

Drop `USGS_LAKE_HAVASU_SECONDARY_SITE` from the wrapper. Either:

- **Replace with `09426630` (Bill Williams River at Lake Havasu)** if operator browser-verify confirms it reports current iv-values. Re-purpose it as a "river-flow into the lake" signal rather than the original "downstream outflow" framing.
- **Or drop the secondary-site concept entirely.** With Option A above for 09427500 (narrow scope), the architecture simplifies to a single-USGS-site model. Less code path; cleaner failure modes.

**Recommendation: drop the secondary-site concept.** Combined with §2's Option A recommendation, this is the cleanest amendment — Phase 8a becomes "single USGS site, two parameters: lake-level + storage." Operator can re-introduce a second site in V1.5 if a substantive use case appears.

---

## §4 LHC Nixle RSS (agency 3726) — ⚠️ YELLOW-to-RED; silent since 2021

### Verification

Fetched `https://rss.nixle.com/pubs/feeds/latest/3726/`.

**Feed metadata confirmed:**
- HTTP 200; Content-Type `application/rss+xml; charset=utf-8`
- `<title>`: `Lake Havasu City Fire Department`
- `<description>`: `Messages from Lake Havasu City Fire Department`
- **`<lastBuildDate>`: `Wed, 01 Sep 2021 16:46:18 -0700`**

**20 items returned**, ranging from **July 2019 → September 2021**. Most-recent item:

> **"Recall for residential assignment"** — Wed, 01 Sep 2021. Body: "Recall for residential assignment 3784 Hiawatha Dr. All off duty personnel report to assigned stations."

**Content character of the feed:** 18 of 20 items are **internal off-duty-recall messages** ("RECALL FOR RESIDENTIAL ASSIGNMENT"), not public-facing safety alerts. These are the kind of messages a dispatcher sends to staff via Nixle Wire, not the kind a citizen would subscribe to for lake-hazard or evacuation alerts. The 2 non-recall items reference a "CANCEL RECALL" and a fire-under-control update — same staff-internal character.

**Cross-check:** WebSearch returned `local.nixle.com/lake-havasu-city-fire-department` still live as the LHCFD landing page, but no evidence in search results of LHCFD migrating to Everbridge or CodeRED (those system-replacements appeared in other counties; Los Alamos + Fall River). The LHCFD landing page may itself be vestigial.

### Implications for Phase 8a

The design doc §6 + wrapper §3.2.3 plan `app/conditions/nixle.py` to fetch the RSS + keyword-match on `{flood, drowning, capsize, rescue, evacuation, advisory}` to trigger `lake_hazard` alerts. **None of the 6 keywords appear in any of the 20 historical items.** Even if LHCFD resumed Nixle Wire posting, the historical content character (staff-recall messages) doesn't include the lake-hazard surface the wrapper assumes.

Two separate risks compound:
1. **Recency:** feed silent for ~4 years 8 months → no signal at runtime
2. **Content fit:** the historical messages don't match the keyword-matcher's design intent

### Recommended wrapper amendment

Pick ONE:

**Option A — Drop Nixle entirely from Phase 8a.** Remove the Nixle fetcher, the `lake_hazard` keyword-matcher, the `LHC_NIXLE_FIRE_AGENCY_ID` constant. The `lake_hazard` alert type stays in the schema but its trigger gets reframed in terms of USGS gauge-height-delta + NWS marine forecast (if applicable) — same source-isolation pattern; one less external dependency. Net positive for V1 stability.

**Option B — Defer Nixle to V1.5 + replace with a different LHC alert source for V1.** Possible candidates:
- Mohave County Sheriff's Office alerting platform (if LHCFD is silent but the county-level coverage may be active)
- LHC city website's RSS (if any) at `lhcaz.gov` for press releases / road closures
- Arizona Emergency Information Network (`ein.az.gov`) — the search result confirmed it covers LHCFD events
- NWS Special Weather Statements scoped to the LHC zone (already in scope via NWS alerts fetcher; no new dependency)

Operator browser-research required to pick a candidate before wrapper amendment.

**Option C — Keep Nixle as a low-priority surface "in case it resurrects".** Ship Phase 8a with the Nixle fetcher in place; document the silent-feed risk in the close-out; treat any future LHCFD Nixle activity as a windfall.

**Recommendation: Option A + Option B blend.** Drop Nixle from V1 (Option A) — the silent-feed risk + content-fit risk is enough to disqualify it. Add an item to the V1.5 carry inventory: "research current LHC alert channel; possibly Mohave County SO + ein.az.gov + lhcaz.gov RSS; pick a replacement source for Phase 8c-or-V1.5." NWS Special Weather Statements (already in scope) cover the substantive lake-hazard surface for V1.

---

## §5 AirNow API key registration — ⚠️ operator-action-pending

Not verified live (the verification requires the operator to register an account + receive activation email + smoke-test the issued key). The walkthrough at `outputs/phase_8_operator_prereq_checklist.md §2` is still correct and complete:

1. Visit [airnowapi.org/account/request/](https://docs.airnowapi.org/account/request/)
2. Submit registration with org "havasu-chat" + email `casey.l.solomon@gmail.com` + ~15-min polling cadence + ZIP 86403
3. Wait for email activation (often near-instant)
4. Smoke-test the key:
   ```powershell
   $key = "<your-key>"
   Invoke-RestMethod "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=86403&distance=25&API_KEY=$key"
   ```
5. Store in `.env` locally + Railway env var

This prereq is operator-side execution only. No wrapper amendment needed — AirNow remains the canonical AQI source.

---

## §6 Wrapper amendments needed before Lane I dispatch

The following files need patches before `outputs/cursor_dispatch_prompt_phase_8.md` is paste-ready for Cursor:

| File | Patch required |
|---|---|
| `outputs/cursor_dispatch_prompt_phase_8.md` | §3.2.3 USGS section: narrow to single site `09427500` + parameters `00054` + `00065` (per §2 Option A); drop secondary-site constant (per §3); §3.2.3 Nixle section: remove entirely + amend `lake_hazard` trigger to use NWS-only signal (per §4 Option A) |
| `outputs/phase_8_operator_prereq_checklist.md` | §3 USGS: amend the "RECOMMENDED CANONICAL" table to drop 09427520 + amend parameter list at 09427500 to 00054 + 00065; §4 Nixle: mark entire section "DROPPED FROM V1 per `outputs/phase_8a_prereq_verification_report.md` §4 Option A" |
| `outputs/phase_8_architecture_design.md` | Re-flow §6 conditions schema to match narrowed scope; §7 alert triggers: rewrite `lake_hazard` trigger to drop Nixle keyword-match + replace with NWS marine forecast + USGS gauge-height-delta heuristic |
| `outputs/cursor_dispatch_prompt_phase_8b.md` | Likely no impact — Phase 8b is cat-13 expansion, scope-disjoint from conditions infrastructure. Verify on amendment pass. |
| `outputs/cursor_dispatch_prompt_phase_9.md` | Likely no impact — Phase 9 is events scraper, scope-disjoint. Verify on amendment pass. |

**Effort estimate for amendments:** ~45-90 min Cowork-side. Most of it is on the architecture design doc (1050 lines; needs a careful §6 + §7 re-flow). The wrapper + prereq checklist amendments are smaller (~15-20 min each).

---

## §7 Recommended next steps for the operator

In priority order:

1. **Decide on §2 USGS Option A vs B vs C.** This is the biggest scope decision. Recommended: Option A (narrow scope to single site, 2 parameters). If Option B is preferred (add Bill Williams River for temp), browser-verify `09426630` first via `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09426630&period=P1D` before the wrapper amendment.
2. **Decide on §4 Nixle Option A vs B vs C.** Recommended: Option A (drop from V1) + add V1.5 carry to research current LHC alert channel.
3. **Decide on §6 amendment-author timing.** Options: (a) author the amendments now in a single Cowork session (~45-90 min) → Lane I becomes dispatch-ready; (b) defer amendments until after Lane H (flag flip) completes and you have momentum back on Lane I.
4. **AirNow registration** — independent of all above; chip away anytime.

**Recommended sequencing per operator's cadence rule:** Lane H first (~20 min total; the flag-flip narrative arc closure); then operator confirms §2 + §4 decisions; then Cowork authors the wrapper amendments; then Lane I dispatch-ready check.

---

## §8 V1.5 carries surfaced by this verification

Add to next-session V1.5 inventory:

- **Water temperature data source for Lake Havasu** — USGS 09427500 doesn't measure it. Candidates: USGS 09426630 (Bill Williams River, browser-verify pending), Bureau of Reclamation Lower Colorado Region gauges, NDBC buoy (none at Havasu currently), partnership with a marina-side sensor, NWS lake-temperature climatology
- **LHC public-safety alert source for V1.5** — Nixle dead since 2021; need to research Mohave County SO + ein.az.gov + lhcaz.gov RSS + AzDPS alerts for a replacement signal
- **Reservoir-storage-based UX** — site 09427500 reports storage in acre-ft; could surface as "Lake Havasu is X% full" or "current capacity 589k ac-ft / 619k ac-ft max" — V1 UX nicety not in current design doc
- **Gauge-height-delta heuristic for lake_hazard trigger** — design doc currently relies on Nixle keyword-match; reframing requires a small research pass on what gauge-height delta historically corresponds to a hazardous lake state (likely never since Lake Havasu is a reservoir, but worth documenting the bound)

---

## §9 Commit suggestion

This report is a Cowork-side artifact that surfaces findings; no code changes; no DB touches. The follow-on wrapper amendments per §6 would be a separate commit once operator decisions are locked.

If you want a ledger commit for this report alone:

```
git add outputs/phase_8a_prereq_verification_report.md
git commit -m "docs(phase8a): live web prereq verification -- USGS secondary dead; Nixle silent since 2021; primary site missing temp+discharge -- wrapper amendments needed before Lane I dispatch"
git push
```

Docs-only; alembic head unchanged at `c9d0e1f2a3b4`; pytest count unchanged.

---

## §10 Sources

- USGS instantaneous-values API: [https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&parameterCd=00065,00010,00060&period=P1D](https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&parameterCd=00065,00010,00060&period=P1D)
- USGS instantaneous-values API (09427520): [https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427520&parameterCd=00065,00010,00060&period=P1D](https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427520&parameterCd=00065,00010,00060&period=P1D)
- USGS instantaneous-values API (09427500 all params): [https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&period=P1D](https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&period=P1D)
- Nixle LHC Fire Department RSS: [https://rss.nixle.com/pubs/feeds/latest/3726/](https://rss.nixle.com/pubs/feeds/latest/3726/)
- USGS monitoring location 09426630 (Bill Williams River candidate): [https://waterdata.usgs.gov/monitoring-location/USGS-09426630/](https://waterdata.usgs.gov/monitoring-location/USGS-09426630/)
- Go Lake Havasu water temp/level page: [https://www.golakehavasu.com/plan/water-temperature-level/](https://www.golakehavasu.com/plan/water-temperature-level/)
- LHCFD Nixle public landing (still live): [https://local.nixle.com/lake-havasu-city-fire-department](https://local.nixle.com/lake-havasu-city-fire-department)
- LHCFD main page: [https://www.lhcaz.gov/fire-department](https://www.lhcaz.gov/fire-department)
- AZ Emergency Information Network LHCFD keyword: [https://ein.az.gov/keywords/lake-havasu-city-fire%C2%A0department](https://ein.az.gov/keywords/lake-havasu-city-fire%C2%A0department)

---

## §11 Follow-up correction: NWS marine product type doesn't cover Lake Havasu (2026-05-19 post-§6-amendment)

**Context:** After the §6 amendments landed (USGS Option A + Nixle Option A), a follow-up check on the wrapper's "NWS marine forecast" framing surfaced a substantive product-type mismatch. The amended `lake_hazard` trigger relies on `nws_marine_alerts` as one of two signal sources — but **Lake Havasu is not in any NWS marine zone**. The marine-zone framework covers coastal waters + Great Lakes ONLY; inland reservoirs like Lake Havasu are not in scope.

### §11.1 Findings

**Finding A — NWS marine zones are Coastal + Great Lakes ONLY.** The NWS Marine, Tropical and Tsunami Services Branch landing page (`https://www.weather.gov/marine/usamz`) titled "Coastal/Great Lakes Forecasts by Zone" is explicit: marine zones cover "Coastal" + "Great Lakes" only. Lake Havasu is an inland reservoir on the lower Colorado River (Arizona/California border); it is neither coastal nor Great Lakes. There is no NWS marine zone code that covers it.

**Finding B — Lake Havasu's canonical NWS public zone is AZZ002** ("Lake Havasu and Fort Mohave"). Verified via WebSearch result: `https://forecast.weather.gov/MapClick.php?zoneid=AZZ002`. AZZ002 is a standard land-based public-forecast zone, NOT a marine zone. AZZ002 alerts flow through `api.weather.gov/alerts/active?zone=AZZ002` (the same endpoint pattern as any other AZZ zone).

**Finding C — The current `LAKE_HAZARD_NWS_KEYWORDS` list includes marine-only terms.** The amended wrapper at `outputs/phase_8_architecture_design.md` line 489 defines `LAKE_HAZARD_NWS_KEYWORDS = (...)` per the line 443 spec `{flood, drowning, capsize, rescue, evacuation, advisory, small craft}`. Of these:

- `small craft` is a marine-only product reference (Small Craft Advisory exists for marine zones; the inland equivalent is "Lake Wind Advisory")
- `capsize` is marine-flavored language; doesn't appear in standard NWS inland alert products
- `drowning` and `rescue` are local-news language, not NWS product vocabulary; will never match
- `advisory` is too broad — matches Heat Advisory, Wind Advisory, etc. (high false-positive risk)
- `flood` and `evacuation` are valid for inland alerts (Flash Flood Warning, Areal Flood Advisory)

**Net implication:** the amended wrapper's `lake_hazard` trigger has two signal sources (`nws_marine_alerts` + `usgs_09427500` gauge-drop). The `nws_marine_alerts` source will return empty data for LHC indefinitely (no marine zone coverage), leaving only the gauge-drop secondary — same single-source posture as if we'd picked §4 Option A "Drop Nixle + drop marine; rely solely on land-zone alerts + gauge". The keyword list is also miscalibrated for inland-zone alerts.

### §11.2 Recommended wrapper amendments (2 files)

**File 1: `outputs/cursor_dispatch_prompt_phase_8.md`**

Three changes:

1. **Replace `nws_marine_alerts` cache surface with `nws_alerts_lhc_zone`** scoped to AZZ002. Specifically, the wrapper's §3.2.3 NWS fetcher should fetch `https://api.weather.gov/alerts/active?zone=AZZ002` rather than any marine endpoint. Cache key: `nws_alerts_lhc_zone`. Cadence: 15 min (same as `nws_alerts_active` in the original design).
2. **Add `LHC_NWS_ZONE_ID = "AZZ002"` constant** alongside the existing AirNow + USGS constants. Use throughout the conditions module rather than hardcoding the zone string.
3. **Update the `lake_hazard` trigger description** (line 134-135) from "NWS marine/SWS keyword match" to "NWS AZZ002-zone alert keyword match" (or equivalent inland-appropriate phrasing).

**File 2: `outputs/phase_8_architecture_design.md`**

Four changes:

1. **§4 cache table — rename `nws_marine_alerts` → `nws_alerts_lhc_zone`** with the AZZ002 zone scope.
2. **§6 alert evaluator (line 379)** — update the cache-key tuple from `(airnow_86403, nws_alerts_active, usgs_09427500, nws_marine_alerts)` to `(airnow_86403, nws_alerts_lhc_zone, usgs_09427500)` (collapses to 3 sources; nws_alerts_lhc_zone IS the AZZ002-scoped subset of nws_alerts_active).
3. **§6 `lake_hazard` trigger spec (line 443)** — replace `(nws_marine_alerts OR nws_alerts_active SWS)` with `nws_alerts_lhc_zone` (single zone-scoped surface).
4. **§6 `LAKE_HAZARD_NWS_KEYWORDS` constant (line 489)** — replace with inland-appropriate keyword set:

```python
LAKE_HAZARD_NWS_KEYWORDS = (
    "flash flood",
    "flood warning",
    "flood advisory",
    "lake wind",
    "high wind",
    "wind advisory",
    "blowing dust",
    "dust storm",
    "severe thunderstorm",
)
# Note: dropped "drowning", "rescue", "capsize", "small craft" (marine-only or
# non-NWS-vocabulary). "advisory" too broad; replaced with specific advisory types.
# Heat-advisory keywords stay in their own constant (heat_advisory trigger).
```

Optional follow-up: also drop the Risk 2 update language in the architecture design's risks section if it references marine forecasts; reframe to "NWS zone-scoped alerts may have gaps during pre-event windows; mitigate via gauge-drop secondary."

### §11.3 Recommended secondary check (~5 min operator)

Before applying the amendments, browser-verify AZZ002 alerts feed responds:

1. Open `https://api.weather.gov/alerts/active?zone=AZZ002` in browser. Expected: GeoJSON FeatureCollection (possibly empty if no active alerts right now — that's normal for a quiet weather day).
2. Open `https://forecast.weather.gov/MapClick.php?zoneid=AZZ002` in browser. Expected: page renders with "Lake Havasu and Fort Mohave" zone forecast.

If either fails, fall back to verifying via the `alerts.weather.gov/cap/az.php?x=2` Arizona-statewide RSS feed for sanity.

### §11.4 Effort estimate

Amending the 2 files: ~20-30 min Cowork-side. Lower than the §6 amendment work because (a) only 2 files affected (not 5); (b) changes are scoped to product-type substitution + keyword list rewrite; (c) no schema rewrite required (the cache key rename is one column-name change).

### §11.5 V1.5 carry surfaced

- **NWS API User-Agent header convention** — `api.weather.gov` requires a User-Agent header identifying the requester (per their docs). The wrapper currently doesn't explicitly call out the convention; worth a one-line note in the `app/conditions/nws_alerts.py` module-doc to avoid 403s in production. Not a blocker (Cursor will likely set a default UA), but explicit-lock is cheap.

### §11.6 Sources for §11

- [NWS Coastal/Great Lakes Forecasts by Zone (marine-zone scope)](https://www.weather.gov/marine/usamz)
- [NWS forecast for AZZ002 "Lake Havasu and Fort Mohave"](https://forecast.weather.gov/MapClick.php?zoneid=AZZ002)
- [NWS Arizona Watch/Warning RSS feeds by zone](https://alerts.weather.gov/cap/az.php?x=2)

---

*Authored by Cowork primary at the post-`1e3f291` Lane I prereq-verification step. Lives at `outputs/phase_8a_prereq_verification_report.md`. Three P0 substantive findings; Lane I NOT safe to dispatch as currently wrapped. Operator decisions required on §2 USGS scope option + §4 Nixle scope option before wrapper amendments can land. §11 added post-§6-amendment to flag a substantive NWS product-type mismatch in the amended wrapper. Companion docs: `outputs/phase_8_operator_prereq_checklist.md` (superseded by this report's §1 status table); `outputs/cursor_dispatch_prompt_phase_8.md` (wrapper requires §6 + §11.2 amendments); `outputs/phase_8_architecture_design.md` (design doc requires §6 + §7 re-flow plus §11.2 corrections).*
