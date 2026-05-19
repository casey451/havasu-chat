# Phase 8 Operator Prereq Checklist — AirNow + USGS + LHC Emergency Feed

> **What this is:** the operator-side prereq surface for Phase 8 (trust layer + conditions panel + alerts) per master plan §4 Phase 8 + §6 operator workload schedule (line 570: "~2-3 hours"). Pre-positioned 2026-05-20 during Cursor's Phase 6.4 + Phase 7 parallel grind so the operator can knock out these prereqs IN PARALLEL — most importantly the AirNow API key (1-2 business day approval lag historically) which would otherwise block Phase 8 dispatch the moment Phase 7 ships.
>
> **Author:** Cowork primary, 2026-05-20 post-`99eb12c`.
>
> **Why now:** Phase 8 dispatches against Phase 7's HEAD SHA. If Phase 7 ships in 5-8 days and the operator hasn't registered the AirNow key yet, there's a 1-2 day idle window between "Phase 7 ready to commit" and "Phase 8 ready to dispatch" while we wait for AirNow approval. Pre-positioning now eliminates that idle window — register the key TODAY, let it bake during the 5-8 day Phase 7 window, and Phase 8 dispatches the moment Phase 7 ships.
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
| 1 | AirNow API key registration | ~10 min request + 1–2 business days approval | **HIGH — register today** |
| 2 | USGS Lake Havasu gauge ID confirmation | ~30 min research + decision | No lag; operator picks |
| 3 | LHC emergency-notification feed format check | ~20 min check + decision | No lag; operator checks |
| – | **Total** | ~1 hour active + 1–2 day passive wait for #1 | |

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
2. Submit. AirNow emails an API key after manual review — historically 1-2 business days, sometimes same-day.
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

## §3 Prereq #2 — USGS Lake Havasu gauge ID confirmation

**Why:** USGS Water Data provides public stream/lake gauge readings (water level + temperature + flow). Lake Havasu has multiple measurement sites; you pick the canonical one for the "Today in Havasu" conditions strip.

**Decision criteria:** for V1, the canonical gauge should give a representative reading for "what the lake feels like today" — primarily water temperature (boat-mode users care) + lake level (RV park / launch ramp users care). Flow rate matters less for a directory site.

**Candidate sites near Lake Havasu City:**

| Site ID | Name | Lat/Lng | Reads | Notes |
|---|---|---|---|---|
| **09422500** | Colorado River below Parker Dam, AZ-CA | 34.296°N / 114.137°W | Gauge height + temperature + flow | **Most likely the V1 default — upstream feed into Lake Havasu; well-instrumented; long history.** |
| 09427520 | Colorado River below Parker Dam (alt) | varies | Gauge height + flow | Frequently retired/active — verify status before locking. |
| 09427000 | Colorado River near Topock, AZ | 34.722°N / 114.482°W | Gauge height + temperature | Downstream of Lake Havasu; less representative of lake conditions. |
| NOAA CW2856 | Lake Havasu State Park weather station | varies | Air temperature + wind | Weather station, not water gauge — useful for cross-ref but NWS API covers this. |

**Recommended:** **USGS site 09422500** (Colorado River below Parker Dam). It's the canonical upstream-of-Lake-Havasu USGS gauge, has both gauge height + water temperature readings, and has decades of historical data. The Parker Dam release is also what drives Lake Havasu's level dynamics.

**Process:**

1. Visit [waterdata.usgs.gov/nwis/uv?site_no=09422500](https://waterdata.usgs.gov/nwis/uv?site_no=09422500) — confirm the site is currently active + reporting.
2. Check what parameters are available (gauge height = `00065`, water temperature = `00010`, discharge = `00060`).
3. Decide: lock site 09422500 as the canonical Phase 8 gauge ID, OR pick an alternative if it's been retired / data is sparse.
4. Record the decision in your notes (Phase 8 dispatch wrapper will encode this as a config constant `USGS_LAKE_HAVASU_GAUGE_ID = "09422500"`).

**Acceptance check:**
```powershell
Invoke-RestMethod "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=09422500&parameterCd=00065,00010,00060&period=P1D"
# Expected: JSON with timeSeries array containing recent readings.
# If empty or 404, the site may be retired — pick an alternative.
```

No API key needed — USGS Water Services is fully open.

---

## §4 Prereq #3 — City of Lake Havasu emergency-notification feed format check

**Why:** Master plan §4 Phase 8 mentions checking "City of Lake Havasu emergency-notification feed format" — the question is whether LHC publishes a structured emergency-alert feed (RSS, JSON, Twitter API, etc.) that Phase 8 can ingest. If yes, alerts can route LHC official notifications (lake hazards, road closures, evacuations) directly to subscribers. If no, alerts are limited to AirNow + NWS + USGS-derived triggers only.

**Process:**

1. Visit [lhcaz.gov](https://www.lhcaz.gov) — look for "Emergency Notifications" / "Alerts" / "CodeRED" page.
2. Check if there's a public-facing feed link (typically labeled "Subscribe to alerts" or "RSS feed" or "API"). Common patterns:
   - **CodeRED** (a paid notification service many cities use) — typically NO public feed; subscribers receive via phone/SMS/email only. If LHC uses CodeRED, this prereq returns "no feed available; V1 alerts are AirNow + NWS + USGS only".
   - **Nixle** — sometimes has a public RSS feed at `nixle.com/<city>/feed`
   - **Twitter** — LHC may post emergency notifications to a city Twitter account; Twitter API access requires a developer account (cost + complexity).
   - **City website RSS** — some cities publish a "news" or "alerts" RSS feed; check for it.
3. If a structured feed exists, capture the URL + format (RSS XML, JSON, etc.) and confirm it has a stable schema.
4. If no structured feed exists, record "no feed available — V1 alerts use AirNow + NWS + USGS only" and move on. This is fine — it just means the "city emergency alert" path is V1.5 / V2.

**Possible outcomes:**

| Outcome | Phase 8 implication |
|---|---|
| LHC has a public RSS / JSON / API feed | Phase 8 ingests + alerts route LHC notifications |
| LHC uses CodeRED only (no public feed) | V1 alerts skip LHC; users sign up directly for CodeRED separately |
| LHC has a Twitter account with alerts | V1.5 — Twitter API costs $100/mo minimum; defer |

Decision is a one-line entry in your notes — no commitment + no fallback work needed if no feed exists.

---

## §5 Where to record your findings

Suggested format — paste these into a personal notes file or a fresh sticky note:

```
Phase 8 prereq notes — 2026-05-XX

AirNow API key:
  - Requested: 2026-05-XX at <time>
  - Approved: 2026-05-XX (or "pending")
  - Key stored in: 1Password vault "havasu-chat secrets" / .env locally
  - Smoke test: passed / failed

USGS gauge ID:
  - Decision: USGS_LAKE_HAVASU_GAUGE_ID = "09422500" (Colorado River below Parker Dam)
  - Alt considered: <if any>
  - Smoke test: passed / failed

LHC emergency feed:
  - Format: <RSS / JSON / Twitter / CodeRED-only-no-feed>
  - URL: <if applicable>
  - V1 disposition: <ingest into Phase 8 / defer to V1.5 / skip>
```

When Phase 7 ships + you're ready to dispatch Phase 8, the Phase 8 dispatch wrapper will read your findings here and bake them into the dispatch body's locked decisions.

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
