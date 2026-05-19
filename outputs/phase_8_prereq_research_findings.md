# Phase 8 Prereq Research Findings

**Date:** 2026-05-19
**Researcher:** general-purpose subagent
**Purpose:** Resolve three open factual questions in `outputs/phase_8_operator_prereq_checklist.md` so the operator can act without further investigation.

---

## Research Method & Caveats

- **Tools used:** `WebSearch` only. `web_fetch` (workspace MCP) was unavailable for these domains — its provenance set rejected every requested URL (including URLs returned by WebSearch in the same session), so direct page fetches of `lhcaz.gov`, `waterdata.usgs.gov`, and `docs.airnowapi.org` could not be performed. Chrome MCP extension is not connected. Bash `curl`/`wget` fallbacks are disallowed by operator policy.
- **Confidence:** Findings rely on search-result snippets and titles. Citations are URLs surfaced by search. Where a finding was confirmed by multiple independent results, I mark it **HIGH confidence**; single-source findings are **MEDIUM**.
- **Recommendation:** Before Phase 8 ingest code lands, operator should load the canonical URLs in a browser and visually confirm the two snippets that drive architectural choices (USGS site number; LHC Nixle agency ID).

---

## Question 1 — Lake Havasu City emergency-notification feed format

**Restated:** Does LHC publish a structured public feed (RSS / JSON / Twitter / Nixle) for emergency notifications, or is it CodeRED-only (subscriber-gated, no public feed)?

### What I checked
- General web searches for `lhcaz.gov` + emergency alerts / CodeRED / Nixle / Twitter
- `site:lhcaz.gov` search for emergency / notifications pages
- Direct searches for `@LakeHavasuCity`, `@LHCPolice`, `@LHCFireDept` social handles
- Searches for LHC Nixle agency presence + Nixle public feed format

### Findings

**Primary system: Nixle (Everbridge).** Multiple search results confirm:
- **Lake Havasu City Fire Department** has an active Nixle presence at `https://local.nixle.com/lake-havasu-city-fire-department` (HIGH confidence — confirmed by direct page titles in two independent search result sets, including a real alert URL `https://local.nixle.com/alert/5081278/`).
- Public subscription path: text ZIP code (86403 / 86404 / 86405 / 86406) to **888777**.
- A category landing page exists at `https://local.nixle.com/city/az/lake-havasu-city/municipal/` — implies multiple municipal agencies post under the Lake Havasu City umbrella, not just Fire.
- A Lake Havasu City Police Department Nixle account was NOT directly confirmed in search results (the city/municipal landing page suggests it exists, but I could not get a direct hit on a `local.nixle.com/lake-havasu-city-police-department` URL). **MEDIUM confidence** that LHC PD also uses Nixle.

**Nixle public feed format (CRITICAL — this enables Phase 8 ingest):**
- Nixle Support Center confirms public **RSS feeds** at the URL pattern:
  `https://rss.nixle.com/pubs/feeds/latest/<agency-id>/`
  (alternate: `https://agency.nixle.com/pubs/feeds/latest/<agency-id>/`)
- Caveat documented by Nixle: *"only Nixle Wire messages appear in this field, not other private/public group messages."* — Phase 8 may receive a subset of total agency posts; this is acceptable for public-safety emergency alerts which are typically Wire-distributed.
- **Agency ID is NOT publicly discoverable from the `local.nixle.com/lake-havasu-city-fire-department` URL alone.** The operator must look up the numeric agency ID either by:
  1. Inspecting the HTML source of `local.nixle.com/lake-havasu-city-fire-department` for an `agency-id` data attribute or RSS `<link>` tag.
  2. Emailing Nixle support (support@nixle.com) and asking for the LHC Fire Dept agency ID.
  3. Inspecting one of the alert permalinks (e.g., `/alert/5081278/`) for embedded agency metadata.

**CodeRED:** No direct evidence LHC uses CodeRED. Search results for "Lake Havasu City CodeRED" returned generic CodeRED documentation pages (Crisis24, Buncombe County NC, Truckee CA) — none specific to LHC. **Working assumption: LHC does NOT use CodeRED.**

**Twitter/X:** No verified LHC emergency-alert account confirmed. Search results for `@LakeHavasuCity` / `@LHCPolice` / `@LHCFireDept` returned LA-area accounts and generic alert info — no LHC-specific verified handles surfaced. Phase 8 should NOT plan to ingest from Twitter for LHC.

**Other notable LHC channels (informational, not for Phase 8 V1):**
- `lhcaz.gov/news` — City News page offers email alerts on news article publication (low-signal for emergencies, but RSS may exist).
- `havasuscannerfeed.com` and `havasunews.com` — third-party scanner/news feeds; NOT official, NOT recommended as Phase 8 sources (provenance + reliability concerns).
- NOAA Weather Radio — recommended in LHC's 2019 Emergency Preparedness Guide; out of scope for Phase 8 (it's a hardware channel).

### Recommendation

**INGEST in Phase 8** — feed is public and consumable.

- Source: **Lake Havasu City Fire Department Nixle RSS** at `https://rss.nixle.com/pubs/feeds/latest/<agency-id>/`
- **Blocker before code:** operator must resolve the Fire Dept agency ID (see lookup paths above). Add to Phase 8 prereq checklist as a new operator action item.
- **Stretch:** if LHC Police Dept Nixle presence is confirmed during agency-ID lookup, add it as a second feed (likely a different agency ID).
- **Caveat to document:** Nixle's Wire-only RSS restriction means some private-group posts may not appear. For V1 this is acceptable; flag as a known-limitation in Phase 8 close-out.
- **Defer to V1.5:** Twitter/X ingestion (no verified handles), `lhcaz.gov/news` ingestion (low emergency signal), CodeRED (no evidence of LHC use).

---

## Question 2 — USGS gauge 09422500 status verification

**Restated:** Is USGS 09422500 currently active, reporting gauge height (00065) / water temp (00010) / discharge (00060), and is it the right canonical Phase 8 source?

### What I checked
- Direct searches for site 09422500 status/history
- Searches for "Colorado River below Parker Dam" + site number cross-reference
- Searches for nearby active sites: 09427520, 09427500, 09424150
- USGS waterservices.usgs.gov API format documentation

### Findings — Site Number Correction (CRITICAL)

**The Phase 8 prereq checklist has the WRONG site number.** Authoritative finding from USGS Water Data for the Nation:

| Site # | Name | Location | Status |
|--------|------|----------|--------|
| **09422500** | **Lake Mohave at Davis Dam, AZ-NV** | Davis Dam, ~70 miles north of Lake Havasu City | Active — has 2026 water-year summaries |
| **09427500** | **Lake Havasu near Parker Dam, AZ-CA** | Lake Havasu reservoir itself | Active — current conditions reporting |
| **09427520** | **Colorado River below Parker Dam, AZ-CA** | Below Parker Dam (downstream outflow) | Active — current conditions reporting (last data ~2026-03-11) |
| 09424150 | Colorado River Aqueduct near Parker Dam, AZ-CA | Aqueduct diversion | Active |

The checklist labeled 09422500 as "Colorado River below Parker Dam, AZ-CA" but 09422500 is actually **Lake Mohave at Davis Dam**, a different reservoir north of Lake Havasu. The correct site for "Colorado River below Parker Dam" is **09427520**. The site most relevant to Lake Havasu *itself* is **09427500**.

**HIGH confidence** — confirmed by multiple search results from `waterdata.usgs.gov/monitoring-location/USGS-09427520/`, `waterdata.usgs.gov/monitoring-location/USGS-09427500/`, and `waterdata.usgs.gov/monitoring-location/USGS-09422500/`.

### Parameter availability

For **09427500 (Lake Havasu near Parker Dam)** — recommended canonical:
- Gauge height (00065): YES
- Water temperature (00010): YES (confirmed by RiverApp summary citing this gauge for "real-time streamflow, water level & temperature")
- Discharge (00060): YES

For **09427520 (Colorado River below Parker Dam)** — useful for downstream-flow questions:
- Gauge height (00065): YES — confirmed reading of 65.46 ft
- Discharge (00060): YES — confirmed reading of 2,300 cfs (10-day avg 3,745 cfs)
- Water temperature (00010): UNCONFIRMED from search snippets — operator should verify

For **09422500 (Lake Mohave at Davis Dam)** — outside Lake Havasu scope:
- Gauge height (00065): YES
- Other parameters: unconfirmed
- Geographically wrong for Lake Havasu user queries

### API format — CRITICAL SUNSET WARNING

USGS announced that **`waterservices.usgs.gov` will be decommissioned in early 2027.** Applications must migrate to the modernized OGC API at `https://api.waterdata.usgs.gov/`. This is a Phase 8 architectural decision point:

- **Option A (low risk, short-lived):** use legacy `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=...` for V1, accept the migration cost in 2026 Q4/2027 Q1.
- **Option B (build right the first time):** target the new OGC API at `https://api.waterdata.usgs.gov/ogcapi/v0/` for Phase 8 V1.

Recommendation: **Option B**, because Phase 8 has not yet shipped — the cost of writing against the modern API now is much lower than the cost of a forced migration in <12 months.

### Recommendation

1. **Change canonical Phase 8 USGS site from 09422500 to 09427500** ("Lake Havasu near Parker Dam, AZ-CA"). This is the site that directly represents Lake Havasu reservoir conditions — what a user asking about "the lake" actually means.
2. **Add 09427520 as a secondary site** for "Colorado River outflow below Parker Dam" queries (relevant for downstream conditions, flow rate Qs).
3. **Drop 09422500 entirely** from the Lake Havasu scope — it's a different reservoir (Lake Mohave) ~70 miles north.
4. **Confirm water temperature (00010) availability at 09427520** in a manual browser check before Phase 8 architecture finalizes.
5. **Choose API surface deliberately:** strongly prefer `api.waterdata.usgs.gov` (OGC API) over the legacy `waterservices.usgs.gov` given the 2027 sunset.

---

## Question 3 — AirNow API key approval lag (current as of mid-2026)

**Restated:** Is "1–2 business days" still the accurate approval lag for AirNow API keys? Have free-tier rate limits changed since May 2025? Are there better alternatives?

### What I checked
- Direct searches for AirNow API key approval timeline, FAQ, account request page
- Forum / developer experience searches for 2025–2026 timeframe
- Comparison searches for OpenAQ, PurpleAir, and other AQI APIs

### Findings

**Approval lag:** Search results do NOT contain a specific stated approval-time SLA on AirNow's official docs. The closest concrete signal:
- Account creation flow is **email-based**: user gets a confirmation email with an activation code; API key appears in the Web Services page upper-right after activation. (Source: `docs.airnowapi.org` references in search results.)
- This is consistent with an **automated approval flow** (activate via email link), which would typically be **near-instant** rather than 1–2 business days.
- **However**, no 2025–2026 developer forum post in search results confirmed observed approval times either way.
- **Recommendation:** keep "1–2 business days" as the *worst-case* checklist estimate, but add a note: "approval may be instant via email-activation flow — operator should attempt registration and check email immediately." If approval is instant, the prereq lead-time shrinks significantly and Phase 8 timeline can compress.
- For escalation/clarification: AirNow Data Management Center contact: `dmc@airnowtech.org`. **LOW confidence** on the specific timeline — this is a workflow inference, not a documented SLA.

**Rate limits:** **No change confirmed** since May 2025. Search results corroborate the **500 requests/hour** limit per API key on the free tier. Quote-supported by official docs language: "users must limit web service calls for a given API key to the maximum permitted for the web service, and if this limit is met within a specific hour, the web service will not return data until the next hour." The 500/hour figure was the only number that surfaced. **MEDIUM confidence** — could not directly confirm against `docs.airnowapi.org/faq` page content because direct fetch failed.

**Alternative AQI APIs — evaluation for Lake Havasu use case (current AQI + heat advisory cross-reference):**

| API | Coverage | Pros for LHC | Cons / Why not |
|-----|----------|--------------|----------------|
| **AirNow** (EPA) | US, all states | Official EPA source. Same AQI scale as government heat advisories cite. Free. ZIP-code endpoint matches LHC user mental model. | 500/hr limit (sufficient for V1). Approval lag (unverified). |
| **OpenAQ** | Global, harmonized | Free, open-source, multi-provider (aggregates AirNow + others). Bulk historical data on AWS Open Data registry. | Provides raw measurements in physical units, NOT AQI directly — would require client-side AQI calculation (additional code surface). Same upstream as AirNow for US data, so no fresh-data advantage. |
| **PurpleAir** | Crowdsourced, low-cost sensors | Hyperlocal sensor density possible | LHC sensor density unverified. Sensor calibration / data quality varies. Not the same AQI as EPA — would create cross-reference inconsistency with heat-advisory framing. |
| **Ambee / Breezometer / paid APIs** | Commercial | Higher rate limits, SLAs | Cost. Overkill for V1. |

### Recommendation

1. **Stick with AirNow as Phase 8 canonical AQI source.** It's the right semantic match for "current AQI + heat advisory" cross-reference because government heat-related health advisories use the EPA AQI scale that AirNow returns directly. OpenAQ would require client-side AQI computation; PurpleAir would create scale-mismatch.
2. **Update the prereq checklist approval-lag note:** "1–2 business days worst-case, but approval may be near-instant via email-activation flow. Operator should attempt registration on Day 1 and check email."
3. **Keep the 500 calls/hour free-tier limit assumption.** Document this in the Phase 8 cache layer design: with naive direct queries, 500/hour means ≤8 requests/minute, so a 30-second cache TTL on the AQI lookup would safely cover any realistic chat-load burst.
4. **No need to evaluate alternatives for V1.** Add OpenAQ to V1.5 backlog as a *backup/redundancy* source (not a replacement) if AirNow ever has uptime issues.

---

## Summary of recommended Phase 8 checklist patches

The operator should fold the following changes into `outputs/phase_8_operator_prereq_checklist.md`:

1. **LHC emergency notifications — INGEST in V1, not defer:**
   - Replace any "defer to V1.5 — CodeRED only" disposition with "ingest via Nixle RSS"
   - Add operator action item: "Resolve LHC Fire Dept Nixle agency ID" (lookup paths: HTML source of `local.nixle.com/lake-havasu-city-fire-department`, or email support@nixle.com)
   - Document Wire-only RSS caveat as a known limitation
   - Optional: check for LHC Police Nixle presence and add as a secondary feed

2. **USGS canonical site — CORRECT the site number:**
   - Change canonical site from **09422500 → 09427500** ("Lake Havasu near Parker Dam, AZ-CA")
   - Add secondary site **09427520** ("Colorado River below Parker Dam, AZ-CA") for outflow/downstream questions
   - Remove all references to 09422500 from Lake Havasu scope (it's Lake Mohave at Davis Dam, ~70 mi north)
   - Add architecture note: USGS legacy `waterservices.usgs.gov` is being **decommissioned early 2027** — target the modern OGC API at `https://api.waterdata.usgs.gov/ogcapi/v0/` instead
   - Operator verification step: browser-check water-temperature (parameter 00010) availability at 09427520 before architecture finalizes

3. **AirNow approval-lag note:**
   - Soften "1–2 business days" to "1–2 business days worst-case; may be near-instant via email-activation flow"
   - Confirm 500/hour free-tier limit still applies (no documented change since May 2025)
   - Keep AirNow as canonical AQI source — alternatives (OpenAQ, PurpleAir) don't beat it for the heat-advisory cross-reference use case
   - Add to V1.5 backlog: OpenAQ as redundancy/backup, NOT replacement

---

## Open items for operator verification (before Phase 8 architecture lock)

| # | Item | Why | Who |
|---|------|-----|-----|
| 1 | Look up LHC Fire Dept Nixle agency ID | Required for RSS URL construction; blocks ingest implementation | Operator (browser + Nixle support email) |
| 2 | Check if LHC Police Dept has Nixle account | Could be 2nd ingest source; not blocking but nice-to-have | Operator (browser) |
| 3 | Browser-confirm USGS 09427520 reports water temp (00010) | Determines whether downstream-flow site can also answer "river temperature" questions | Operator (waterdata.usgs.gov) |
| 4 | Decide between legacy waterservices.usgs.gov vs. modern api.waterdata.usgs.gov | Architecture decision; 2027 sunset on legacy | Plan agent / operator |
| 5 | Register an AirNow API key and measure actual approval time | Calibrates prereq lead-time estimate; unblocks Phase 8 testing | Operator |

---

## Source URLs (for operator verification)

- `https://www.lhcaz.gov/` — official LHC website
- `https://local.nixle.com/lake-havasu-city-fire-department` — LHC Fire Dept public Nixle page (confirmed)
- `https://local.nixle.com/city/az/lake-havasu-city/municipal/` — LHC municipal Nixle landing
- `https://supportcenter.nixle.com/hc/en-us/articles/19077429082011-Nixle-RSS-Feeds` — Nixle RSS feed format docs
- `https://waterdata.usgs.gov/monitoring-location/USGS-09427500/` — Lake Havasu near Parker Dam (recommended canonical)
- `https://waterdata.usgs.gov/monitoring-location/USGS-09427520/` — Colorado River below Parker Dam (recommended secondary)
- `https://waterdata.usgs.gov/monitoring-location/USGS-09422500/` — Lake Mohave at Davis Dam (DO NOT use for Lake Havasu)
- `https://waterservices.usgs.gov/` — legacy USGS API (sunsetting early 2027)
- `https://api.waterdata.usgs.gov/docs/ogcapi/` — modernized USGS OGC API (recommended)
- `https://docs.airnowapi.org/` — AirNow API docs
- `https://docs.airnowapi.org/faq` — AirNow API FAQ
- `https://www.airnowapi.org/account/request/` — AirNow API account request form
- `https://openaq.org/` — OpenAQ (alternative AQI; V1.5 backup candidate)
