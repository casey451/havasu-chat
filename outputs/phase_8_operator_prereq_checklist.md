# Phase 8 Operator Prereq Checklist — AirNow + USGS + LHC Emergency Feed

> **What this is:** the operator-side prereq surface for Phase 8 (trust layer + conditions panel + alerts) per master plan §4 Phase 8 + §6 operator workload schedule (line 570: "~2-3 hours"). Pre-positioned 2026-05-20 during Cursor's Phase 6.4 + Phase 7 parallel grind so the operator can knock out these prereqs IN PARALLEL — most importantly the AirNow API key (1-2 business day approval lag historically) which would otherwise block Phase 8 dispatch the moment Phase 7 ships.
>
> **Author:** Cowork primary, 2026-05-20 post-`99eb12c`. **PATCHED 2026-05-20 post-research** (see `outputs/phase_8_prereq_research_findings.md`) — three material corrections folded in: (a) USGS canonical site changed `09422500 → 09427500` (09422500 was wrong; that's Lake Mohave at Davis Dam ~70mi north, NOT Lake Havasu); (b) LHC emergency feed: Nixle CONFIRMED (LHC Fire Department @ `local.nixle.com/lake-havasu-city-fire-department`) — Phase 8 will INGEST via Nixle RSS, not defer; (c) AirNow approval lag softened to "1–2 business days worst-case; may be near-instant via email-activation flow."
>
> **Why now:** Phase 8 dispatches against Phase 7's HEAD SHA. If Phase 7 ships in 5-8 days and the operator hasn't registered the AirNow key yet, there could be approval-lag drag between "Phase 7 ready to commit" and "Phase 8 ready to dispatch". Pre-positioning now eliminates that risk window — register the key TODAY, complete by Day 2 (most likely instant via email activation; worst case 1-2 business days), and Phase 8 dispatches the moment Phase 7 ships.
>
> **Independence from current Cursor work:** This checklist is 100% disjoint from Phase 6.4 (Lane D) and Phase 7 (Lane E) Cursor sessions. All operator actions happen out-of-band via web browsers + email; zero code touches; zero git operations.

---

## §1 What Phase 8 needs (deliverables that require these prereqs)

Per master plan §4 Phase 8 deliverables:

- **Conditions data fetching infrastructure** running every 15 min via Railway scheduled job pulls from THREE external sources:
  - **AirNow** (AQI / particulate matter / ozone) — requires API key
  - **NWS** (weather + heat advisory + sunset) — no API key required (api.weather.gov is open)
  - **USGS** (Lake Havasu gauge — water level + temperature) — no API key required but operator picks the canonical gauge ID
- **Alert dispatch evaluation job** reads `external_conditions_cache` + compares against trigger thresholds per `alert_type` + dispatches emails via Resend → requires the alert subscriptions table populated (already exists from Phase 3) + email templates (Phase 8 ships these)
- **City of Lake Havasu emergency-notification feed** integration — only feasible if LHC publishes a structured feed; operator checks format + availability

These 3 prereqs are the operator-side blockers:

| # | Prereq | Estimated time | Blocking calendar lag |
|---|---|---|---|
| 1 | AirNow API key registration | ~10 min request + email-activation (often near-instant; worst-case 1–2 business days) | **MEDIUM — register today; mostly likely instant** |
| 2 | USGS gauge ID confirmation (canonical: `09427500`) | ~10 min browser verify | No lag; pre-researched |
| 3 | LHC Nixle RSS verify (Fire Dept agency ID **`3726`** resolved 2026-05-20 via HTML-source inspection by sub-agent) | ~30 seconds browser-check of RSS URL | RESOLVED — just operator browser-verify |
| – | **Total** | ~35 min active + email-activation wait (near-instant likely) | |

Master plan §6 estimate is "2-3 hours" — this checklist trims that by giving exact URLs + decision criteria up front.

---

## §2 Prereq #1 — AirNow API key registration

**Why:** AirNow is the EPA's air-quality data clearinghouse. Phase 8's conditions panel + heat-advisory alerts need real AQI data; the AirNow API is the canonical source.

**Where:** [airnowapi.org/account/request/](https://docs.airnowapi.org/account/request/)

**Process:**

1. Visit the request page. Fill in:
   - **Name:** Casey Solomon
   - **Organization:** havasu-chat (or your preferred org name; "personal project" is fine)
   - **Email:** `casey.l.solomon@gmail.com`
   - **Intended use:** Brief description, something like: "Hyperlocal directory site for Lake Havasu City, AZ. Will display current AQI + 24h history + heat advisory cross-reference on a 'Today in Havasu' panel. Approximately 15-min polling cadence. Estimated <1,000 calls/day."
   - **Estimated daily calls:** AirNow's free tier is 500 calls/hour. A 15-min cadence is 96 calls/day per metric; even with 4 metrics that's 384/day, well under the rate limit.
2. Submit. AirNow uses an **email-based activation flow** — you receive a confirmation email with an activation code; clicking through activates the account, and the API key appears in your AirNow Web Services dashboard upper-right. **This is typically near-instant**, not 1-2 business days as our knowledge cutoff suggested (no SLA explicitly published on the AirNow docs; "1-2 business days" is the worst-case upper bound). Check email immediately after submitting + try the smoke test below — if it works, the prereq is done.
3. When the key arrives, store it in your local `.env`:
   ```
   AIRNOW_API_KEY=<your-key-here>
   ```
4. Add the same key to Railway production env vars (Phase 8 dispatch handles the wiring; the env var just needs to exist when Phase 8 ships).

**Acceptance check:** once you have the key, a quick smoke test:
```powershell
$key = "<your-key-here>"
Invoke-RestMethod "https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=86403&distance=25&API_KEY=$key"
# Expected: JSON array with current AQI for ZIP 86403 (Lake Havasu City).
# If you get { "WebServiceError": [{...}] } the key isn't active yet.
```

**Save the API key in a password manager** (1Password / Bitwarden / equivalent) — Phase 8's commit recipe won't include the key in plaintext.

---

## §3 Prereq #2 — USGS Lake Havasu gauge ID confirmation (CORRECTED 2026-05-20)

**Why:** USGS Water Data provides public lake/river gauge readings (water level + temperature + flow). Lake Havasu has multiple measurement sites; you pick the canonical one for the "Today in Havasu" conditions strip.

**CORRECTION:** The original draft of this checklist recommended site **09422500** as canonical — that was WRONG. Site 09422500 is actually **"Lake Mohave at Davis Dam, AZ-NV"** — a different reservoir ~70 miles NORTH of Lake Havasu, not Lake Havasu itself. Research findings (`outputs/phase_8_prereq_research_findings.md`) surfaced this error 2026-05-20.

**Canonical sites near Lake Havasu City (corrected):**

| Site ID | Name | Location | Reads | Notes |
|---|---|---|---|---|
| **09427500** | **Lake Havasu near Parker Dam, AZ-CA** | Lake Havasu reservoir itself | Gauge height + water temp + discharge | **RECOMMENDED CANONICAL — represents Lake Havasu directly. What users mean when they ask "how's the lake".** |
| 09427520 | Colorado River below Parker Dam, AZ-CA | Below Parker Dam (downstream outflow) | Gauge height + discharge confirmed; water temp unconfirmed | **Recommended SECONDARY** for outflow/downstream-flow queries. Operator should browser-confirm water-temp availability before Phase 8 architecture finalizes. |
| ~~09422500~~ | ~~Lake Mohave at Davis Dam~~ | ~70 mi NORTH of Lake Havasu | (irrelevant) | **DO NOT USE** — geographically wrong; different reservoir. |
| 09424150 | Colorado River Aqueduct near Parker Dam | Aqueduct diversion | Various | Not user-facing-relevant; informational |

**Decision recommendation: lock canonical = `09427500` + secondary = `09427520`.** Phase 8 dispatch wrapper will encode as:
```python
USGS_LAKE_HAVASU_PRIMARY_SITE = "09427500"   # Lake Havasu near Parker Dam
USGS_LAKE_HAVASU_SECONDARY_SITE = "09427520"  # Colorado River below Parker Dam (outflow)
```

**Process:**

1. Visit [waterdata.usgs.gov/monitoring-location/USGS-09427500/](https://waterdata.usgs.gov/monitoring-location/USGS-09427500/) — confirm currently active + reporting.
2. Verify the 3 parameters are reporting: gauge height (`00065`), water temperature (`00010`), discharge (`00060`).
3. (Recommended) Also visit [waterdata.usgs.gov/monitoring-location/USGS-09427520/](https://waterdata.usgs.gov/monitoring-location/USGS-09427520/) and confirm whether water temperature (`00010`) is reported there too — this determines whether the secondary site can also answer "river temperature" queries.

**API SUNSET WARNING (architectural decision):**

USGS has announced that the legacy `waterservices.usgs.gov` API is being **decommissioned in early 2027** (less than 12 months from now). Applications must migrate to the modern OGC API at `https://api.waterdata.usgs.gov/ogcapi/v0/`. Phase 8 should **build against the modern OGC API directly** rather than the legacy endpoint, to avoid forced migration within months of V1 launch.

**Legacy API (sunsetting; use only for quick browser-style smoke tests):**
```powershell
Invoke-RestMethod "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09427500&parameterCd=00065,00010,00060&period=P1D"
# Expected: JSON with timeSeries array containing recent readings.
```

**Modern OGC API (recommended for Phase 8 implementation):**
- Docs: [api.waterdata.usgs.gov/docs/ogcapi/](https://api.waterdata.usgs.gov/docs/ogcapi/)
- Operator browser-check: load the docs page + confirm the OGC API supports site-by-ID queries with the same parameter codes.

No API key needed — both USGS API surfaces are fully open.

---

## §4 Prereq #3 — LHC Nixle RSS verify (RESOLVED 2026-05-20)

**Why:** Phase 8 ingests LHC official emergency notifications (lake hazards, road closures, evacuations, etc.) into the alert subsystem so subscribers get LHC-issued notifications alongside the AirNow / NWS / USGS-derived alerts. Research confirmed 2026-05-20 that **LHC uses Nixle** (Everbridge product), NOT CodeRED, and Nixle publishes public RSS feeds. Phase 8 will INGEST via Nixle RSS.

**Confirmed (full findings at `outputs/phase_8_nixle_agency_id_lookup.md`):**
- **LHC Fire Department Nixle agency ID: `3726`** (HIGH confidence; resolved via HTML-source inspection by sub-agent — two independent signals: agency-logo S3 path `user25134-1336013322-3726_cceefa_138_83_PrsMe_.jpeg` + email-forward link `local.nixle.com/email_forward_agency/3726/`; cross-corroborated by the city landing page logo path).
- **Canonical RSS URL: `https://rss.nixle.com/pubs/feeds/latest/3726/`** (alternate: `https://agency.nixle.com/pubs/feeds/latest/3726/`)
- **LHC Police Department: NO Nixle presence** (HIGH confidence negative). The `/city/az/lake-havasu-city/municipal/` page lists EXACTLY ONE municipal agency — LHC Fire Dept. Phase 8 plans a single feed, not two. Downgrades the prior research's MEDIUM-confidence "PD might use Nixle" guess.
- Public subscription path (for reference): text ZIP code (86403 / 86404 / 86405 / 86406) to `888777`.

**Caveat:** Nixle's public RSS only includes "Nixle Wire" messages — not private/closed-group messages. For public-safety emergency alerts (lake hazards, evacuations, road closures), Wire distribution is typical, so V1 ingest will capture the substantive emergency surface. Phase 8 close-out should document this as a known limitation.

**Your job: browser-verify the RSS URL responds (~30 seconds).** The sub-agent couldn't directly fetch the RSS URL due to `web_fetch` provenance restrictions, so a quick operator-side browser check closes the verification gap.

**Acceptance check:**

```powershell
# Open in browser (cleanest):
Start-Process "https://rss.nixle.com/pubs/feeds/latest/3726/"
# OR via PowerShell direct fetch:
Invoke-RestMethod "https://rss.nixle.com/pubs/feeds/latest/3726/" | Select-Object -First 1
# Expected: RSS XML with recent alerts from LHC Fire Department (e.g., titles mentioning Lake Havasu / LHCFD / fire / road closure).
# If empty / 404 / unrelated content: try the alternate at https://agency.nixle.com/pubs/feeds/latest/3726/
# If both 404: email support@nixle.com asking for confirmation of the LHC Fire Dept agency ID.
```

**Record finding format (mostly pre-filled):**

```
Phase 8 prereq §4 — LHC Nixle: RESOLVED 2026-05-20
  - Provider: Nixle (Everbridge) — NOT CodeRED
  - LHC Fire Dept agency ID: 3726
  - LHC Fire Dept RSS URL: https://rss.nixle.com/pubs/feeds/latest/3726/
  - LHC Police Dept Nixle: NO PRESENCE (single municipal agency listed)
  - Wire-only RSS caveat: yes, acknowledged
  - Browser smoke test: <passed / failed — fill in after 30-second check>
```

This is encoded in the Phase 8 dispatch wrapper as `LHC_NIXLE_FIRE_AGENCY_ID = "3726"` alongside the AirNow + NWS + USGS surfaces. See full sub-agent findings at `outputs/phase_8_nixle_agency_id_lookup.md`.

---

## §5 Where to record your findings (template — updated 2026-05-20)

Suggested format — paste these into a personal notes file or a fresh sticky note:

```
Phase 8 prereq notes — 2026-05-XX

AirNow API key:
  - Requested: 2026-05-XX at <time>
  - Activated: 2026-05-XX (likely instant via email-activation; worst-case 1-2 days)
  - Key stored in: 1Password vault "havasu-chat secrets" / .env locally
  - Smoke test: passed / failed

USGS gauges (CORRECTED 2026-05-20):
  - Canonical: USGS_LAKE_HAVASU_PRIMARY_SITE = "09427500" (Lake Havasu near Parker Dam)
  - Secondary: USGS_LAKE_HAVASU_SECONDARY_SITE = "09427520" (Colorado River below Parker Dam)
  - Water-temp at 09427520: confirmed / unconfirmed (browser check)
  - API surface decision: modern OGC API (api.waterdata.usgs.gov) vs legacy (waterservices.usgs.gov; sunsetting early 2027) — recommend modern
  - Smoke test on canonical: passed / failed

LHC Nixle RSS:
  - Provider: Nixle (Everbridge)
  - LHC Fire Dept agency ID: <numeric>
  - LHC Fire Dept RSS URL: https://rss.nixle.com/pubs/feeds/latest/<numeric>/
  - LHC Police Dept Nixle: <agency ID if found, else "not found">
  - Smoke test: passed / failed
```

When Phase 7 ships + you're ready to dispatch Phase 8, the Phase 8 dispatch wrapper will read your findings here and bake them into the dispatch body's locked decisions. The Phase 8 architectural design at `outputs/phase_8_architecture_design.md` (Plan agent output, 2026-05-20) provides additional context on how these constants flow into the conditions cache schema + fetcher subsystem.

---

## §6 What this checklist does NOT cover

- **Code changes.** Phase 8 dispatches all the wiring (cache table migration, scheduled job, conditions endpoint, alert dispatch, email templates) when Cursor runs against the prereq-completed state.
- **Twilio / SMS.** Per master plan §8 OQ #13, SMS alerts via Twilio defer to V1.5. Phase 8 is email-only via Resend.
- **NWS API key.** api.weather.gov is fully open, no key required. The Phase 8 wrapper will document the User-Agent header convention NWS requires but that's just a code-side concern.
- **Resend API key.** Already set up at Phase 2A.1 + 2A.3 for magic-link auth + claim flow. Phase 8 reuses the existing key for alert emails.
- **Cloudflare R2.** Already set up at Phase 2B.1 for photo storage. Phase 8 doesn't touch storage.
- **Heat advisory threshold lock.** Phase 8 will need an operator-locked threshold for "when does heat advisory alert fire?" — likely something like "NWS issues an Excessive Heat Warning OR forecast high > 110°F". That's a Phase 8 dispatch-time decision, not a prereq.

---

## §7 Calendar fit

**Optimal sequence:**

| Day | Activity | Status |
|---|---|---|
| Day 0 (today, 2026-05-20) | Operator submits AirNow API key request | Pending operator action |
| Day 0-1 | Operator does §3 (USGS gauge) + §4 (LHC feed) decisions — ~50 min total | Independent of AirNow lag |
| Day 1-2 | AirNow approval email arrives | Out-of-operator-hands |
| Day 2 | Operator smoke-tests AirNow key + records findings per §5 | ~10 min |
| Day 2-8 | Cursor's Phase 6.4 + Phase 7 sessions grind | (in flight) |
| Day 8 (or wherever Phase 7 ships) | Phase 7 SHIP commit lands; Phase 8 dispatch wrapper authored against prereq findings | Cowork-side ~45-60 min |
| Day 9+ | Phase 8 Cursor session starts; no prereq drag | Pre-empted via this checklist |

**Worst-case absent this checklist:** Phase 7 ships at Day 8, operator then learns AirNow needs registration + 1-2 day approval, Phase 8 idle until Day 10. Two days of unnecessary calendar slip.

---

*Authored by Cowork primary at the post-`99eb12c` dispatch-pre-position session (2026-05-20). Lives at `outputs/phase_8_operator_prereq_checklist.md`. Independent of current Cursor work (Lane D / Lane E); operator runs at convenience. Recommend starting §2 (AirNow key request) TODAY to bake the 1-2 day approval lag during Cursor's Phase 7 grind window.*
