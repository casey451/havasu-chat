# Phase 5 Lane B — External Data-Source Verification Briefing

> **Purpose:** Make Lane B (operator browser work, ~3-4h) faster + structured. For each of the 10 §4 external verifications from `outputs/phase5_prereq_checklist.md`, this doc lists: **what to test, what question to answer, how to record the finding, pass/fail/blocked criteria, and the fallback if blocked**. Operator fills the "Finding" + "Date verified" cells inline as they work through the list, turning this briefing into the **Phase 5 Lane B audit artifact**.
>
> **Status:** authored by Cowork primary at new-chat-post-`54ca07d` session (2026-05-13) as Phase 5 Lane B prep. Lives at `outputs/phase5_lane_b_verification_briefing.md` per the parallel-chat lock at `8fe6321` (Phase 5 chat = outputs/ + app/contrib/ + scripts/ + app/db/).
>
> **Workflow:** operator opens this doc + works through §1-§10 in any order (recommended: §5/§6/§7/§9 first — all <20 min each, get quick wins; then §1/§4 — 30-45 min each, deepest dives; then §2/§3/§8/§10 — operator-context-dependent). Each item has a checkbox + finding field — fill inline + commit at end of session OR per-batch.
>
> **URLs in this doc are best-guess starting points.** Cowork primary doesn't have live-web access in this chat; some URLs may have moved since the project's training cutoff. Operator confirms or updates the starting URL when they open each item. If a URL has moved, please record the actual URL in the Finding cell so future Cowork sessions can use it.

---

## §0 Pass/fail/blocked semantics

Each item has one of four outcomes recorded by operator:

| Outcome | Meaning | Phase 5 impact |
|---|---|---|
| ✅ **Verified** | Endpoint exists, returns expected shape, no rate-limit / auth blockers | Phase 5 layer/source is GO |
| ⚠️ **Verified-with-caveats** | Endpoint works but has known limitations (rate limit, partial data, format quirk) | Phase 5 proceeds with documented caveat applied |
| ❌ **Blocked** | Endpoint gone / requires auth / unusable in current shape | Phase 5 falls back to the documented fallback below; brief §3 per-category playbook updated |
| ⏸ **Deferred** | Operator decides to skip this verification (low priority, low risk) | Phase 5 proceeds without the supplemental layer; document the gap |

---

## §1 AZ ROC (Arizona Registrar of Contractors)

**Why it matters:** Phase 5 §3.3 Home & Property Services uses AZ ROC as Layer 3 license cross-reference — every Google-discovered contractor gets checked for AZ ROC license + status. Verified entries land with `verified=True` + `verified_field="az_roc_license"`.

**Starting URL (operator confirms):** `https://azroc.my.site.com/AZRoc/s/contractor-search` — Salesforce-hosted public license lookup. If moved, search "AZ ROC license search" on Google to find current.

**Test procedure (~30-45 min):**

1. Open starting URL. Verify the search form loads.
2. Search by city: enter "Lake Havasu City" in the city field (or use "Search by Location" if the form requires it). Submit.
3. Inspect the result list. Does it return contractor names + license numbers + class (e.g., "CR-11 General Commercial") + status (Active / Suspended / Cancelled)?
4. Click into 1-2 individual contractor result rows. Are license dates + classifications + bonding info exposed on the detail page?
5. Estimate rate-limit posture: do 5-10 rapid searches in a row. Any CAPTCHA, throttling message, or temp-block? Note time-to-throttle if hit.
6. Inspect the HTML / network tab briefly to see if results render server-side (scrapable via static HTML) OR are XHR-loaded (require JS execution / Playwright-style scrape).

**Question to answer:** Is AZ ROC publicly searchable, with license + status + classification per row, at a tolerable rate-limit for Phase 5 Layer 3 cross-reference (~100-200 lookups across all home-property entries)?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ Verified [ ] ⚠️ Caveats [ ] ❌ Blocked [ ] ⏸ Deferred
- Actual URL used: ___
- Result shape (HTML vs XHR): ___
- Throttling observed (yes/no, at what request count): ___
- Notes: ___

**Fallback if blocked:** Drop Layer 3 AZ ROC from the home-property playbook. `home-property-services` entries land with `verified=False` by default; operator manually verifies the top-30 contractors via direct AZ ROC search during field-entry. Brief §3.3 acceptance gate softens from "AZ ROC coverage on every licensed-trade entry" to "AZ ROC coverage on top-30 highest-traffic contractors."

---

## §2 City of Lake Havasu City Parks & Recreation

**Why it matters:** Phase 5 §3.2 On the Water uses LHC Parks & Rec facility list as Layer 3 city source (boat ramps + public beaches + parks). The existing `parks-rec-scrapes.yml` GitHub Actions cron pulls this — Lane B verifies the source URL is still live + format unchanged since session-22's `18a4100` re-enable.

**Starting URL (operator confirms):** `https://www.lhcaz.gov/parks-recreation` OR similar — the city's parks department landing page. The actual scrape target (specific facility-list page or PDF) is in `parks-rec-scrapes.yml`; operator opens that file to confirm the target before testing.

**Test procedure (~20-30 min):**

1. Open `.github/workflows/parks-rec-scrapes.yml` in the repo + identify the URL(s) being scraped.
2. Open each URL in a browser. Does it load? Is the facility list (or PDF / table / iframe) in the same shape the scraper expects?
3. Cross-reference: open GitHub Actions tab for `havasu-chat` repo → find `parks-rec-scrapes` workflow → check last 5 runs. All green? Any new failures since session-22 baseline run #26 (1m 5s end-to-end)?
4. Spot-check the most recent successful scrape's output (committed to `data/parks_rec_scrapes/` or similar — check repo structure). Does it have current row counts that match what the source URL shows today?

**Question to answer:** Is the LHC Parks & Rec facility-list URL live + unchanged in format, and is the `parks-rec-scrapes.yml` workflow currently producing fresh data?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- URL(s) tested (from workflow): ___
- Last successful workflow run (date + duration): ___
- Source format change since session-22 baseline (yes/no): ___
- Notes: ___

**Fallback if blocked:** Disable the cron + drop the Layer 3 LHC city source from on-the-water playbook. `on-the-water` entries depend on Google + OSM Layer 1+2 only; Layer 5 manual recovery covers the public-ramps the city source would have caught. Brief §3.2 supplemental-layers section updated to reflect the drop.

---

## §3 Lake Havasu City Business Licenses

**Why it matters:** Master plan §4 Phase 5 names city business licenses as a maybe-source for cross-referencing home-property + shopping-essentials. Lane B determines if a public search endpoint exists; if not, defer to Layer 5 manual recovery + AZ ROC for the home-property subset.

**Starting URL (operator confirms):** `https://www.lhcaz.gov/` → navigate to Finance / Business Licensing / similar department. Some cities expose a search; others require in-person / phone records request.

**Test procedure (~20-30 min):**

1. Open lhcaz.gov. Navigate to "Business" or "Finance" or "Licenses" — site structure varies, look for the licensing entry point.
2. Look for a public search interface (often labeled "Business License Search" or "Business Lookup" or similar).
3. If found: test a search for a known LHC business (e.g., a well-known restaurant or grocery store). Does it return business name + license number + license type + status?
4. If no public search: check if the city posts a downloadable list (CSV / PDF / annual report) of licensed businesses. If yes, that's a partial source.
5. If neither: document the gap.

**Question to answer:** Does LHC publish business-license data in any machine-readable or browsable form?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- URL or path found (if any): ___
- Search vs downloadable-list vs neither: ___
- Sample query result (if testable): ___
- Notes: ___

**Fallback if blocked:** Document the gap. `home-property-services` falls back to AZ ROC (§1 above) for license verification; `shopping-essentials` falls back to Layer 5 (downtown walking surveys, McCulloch corridor drive-by per manual_recovery_checklist.md §3). No Phase 5 blocker.

---

## §4 Mohave County GIS

**Why it matters:** Master plan names Mohave County GIS as a potential parcel + commercial-business data source. Lane B determines if it serves anything beyond parcel data (Phase 5 doesn't need parcel data; it needs business/entity data).

**Starting URL (operator confirms):** `https://www.mohavecounty.us/` → navigate to Departments → GIS, OR direct `https://www.mohavecounty.us/depts/gis/`. The county may also expose an open-data portal at `data.mohavecounty.us` or similar.

**Test procedure (~20-30 min):**

1. Open the GIS portal. Identify available datasets / map layers.
2. Look specifically for: (a) commercial business listings, (b) business addresses or property-use designations, (c) any commercial-business search beyond parcel ownership.
3. If commercial business data exists: sample a query for LHC. Does it return business name + address + activity type?
4. If only parcel data: not useful for Phase 5; mark deferred.

**Question to answer:** Does Mohave County GIS publish commercial-business data (beyond parcel ownership) that Phase 5 can cross-reference?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- Portal URL: ___
- Commercial-business datasets found (yes/no, names): ___
- Sample query result (if testable): ___
- Notes: ___

**Fallback if blocked:** Defer to V1.5. Phase 5 proceeds without county GIS as a supplemental source. If parcel data alone becomes interesting later (e.g., for Phase 8 alerts or V1.5 geographic enrichment), revisit.

---

## §5 NPI Registry (already integrated)

**Why it matters:** Phase 5 §3.4 Health, Wellness & Care uses NPI registry as Layer 4 specialized source. Already integrated in `app/contrib/npi/` per master plan §4 Phase 4. Lane B verifies the current LHC NPI search query still returns expected practitioners post-Phase 4 SHIPPED.

**Starting URL (operator confirms):** `https://npiregistry.cms.hhs.gov/search` — official CMS endpoint. Also accessible via API: `https://npiregistry.cms.hhs.gov/api/`.

**Test procedure (~15-20 min):**

1. Open the search page. Try a sample query: "City: Lake Havasu City, State: AZ". Submit.
2. Inspect result count + sample 2-3 results. Does it return practitioner name + NPI number + specialty + practice address?
3. Read the existing `app/contrib/npi/` surface (`ls app/contrib/npi/`; spot-read the main client file). Does it match the current endpoint shape?
4. Optional: try the API endpoint directly (`https://npiregistry.cms.hhs.gov/api/?city=Lake+Havasu+City&state=AZ&version=2.1` or similar). 200 OK?

**Question to answer:** Is the NPI registry currently accessible + returning expected shape for LHC queries + still compatible with the existing `app/contrib/npi/` client?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- Sample result count for LHC + AZ: ___
- Existing client still matches endpoint (yes/no): ___
- Notes: ___

**Fallback if blocked:** Layer 4 NPI drops from health-wellness-care playbook. Health entries land with `npi_number=NULL`; operator manually adds NPI for top-20 practitioners during field-entry via direct search. Brief §3.4 acceptance gate softens.

---

## §6 USAPickleball Courts Directory

**Why it matters:** Phase 5 may use USAPickleball as a supplemental source for `classes-sports-recreation` pickleball courts. Lane B determines if LHC has meaningful coverage in their directory (informs Layer 4 priority).

**Starting URL (operator confirms):** `https://usapickleball.org/places-2-play/` — their official "Places to Play" finder. Also accessible via state/city search.

**Test procedure (~10-15 min):**

1. Open the Places-to-Play search. Filter by location: "Lake Havasu City, AZ" or just "AZ".
2. Count LHC results. 0? 1-2? 5+?
3. Inspect a result: court name + address + indoor/outdoor + court count + access (public/private)?
4. Cross-reference against the heat_exposure priority-30 list (`outputs/heat_exposure_priority_30_list.md` §1 row 9 — "primary outdoor pickleball complex"). Does the directory surface that venue?

**Question to answer:** Does USAPickleball list meaningful LHC pickleball venues, and is the data shape useful (court count, public/private, address)?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- LHC result count: ___
- Data shape per result: ___
- Notes: ___

**Fallback if blocked:** Drop USAPickleball from Phase 5 Layer 4. Pickleball venues land via Google Places only (with the new `(None, None)` types or generic gym/recreation types). Layer 5 manual recovery covers public courts not on Google.

---

## §7 PDGA (Professional Disc Golf Association)

**Why it matters:** Same shape as §6 — supplemental source for `classes-sports-recreation` disc-golf courses. Lane B determines if LHC has registered courses.

**Starting URL (operator confirms):** `https://www.pdga.com/course-directory` — their official course directory.

**Test procedure (~10-15 min):**

1. Open the course directory. Search by state: AZ, or city: Lake Havasu City.
2. Count results. Most likely a handful of courses in LHC (SARA Park is a known disc-golf venue per the heat_exposure priority-30 list §1 row 1).
3. Per result: course name + hole count + difficulty + address?

**Question to answer:** Does PDGA list LHC disc-golf courses, and is the data shape useful?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- LHC result count: ___
- Sample course names: ___
- Notes: ___

**Fallback if blocked:** Drop PDGA. Disc-golf courses land via Google Places only + Layer 5 manual recovery. Low-volume category; not a Phase 5 blocker.

---

## §8 Google Places API Billing Posture

**Why it matters:** Phase 5 spend depends on Google Places billing being live + within budget. Discovery is ~$5-9 per category (cheap); enrichment scales with row count — estimated ~$100 per category at 100 rows = ~$600 total enrichment across 6 categories. Lane B confirms the API key is active + spend cap is set.

**Starting URL (operator confirms):** Google Cloud Console at `https://console.cloud.google.com/` → select the havasu-chat project → APIs & Services → Credentials, then Billing → Budgets & alerts.

**Test procedure (~30-45 min):**

1. Open Google Cloud Console. Confirm the correct project is selected (matches `GOOGLE_PLACES_API_KEY` in Railway).
2. APIs & Services → Credentials: find the Places API key. Restrictions still match expected (HTTP referrer / IP / API restrictions)?
3. APIs & Services → Library: confirm Places API (New) is enabled.
4. Billing → Reports: spot-check current month spend on Places API. Is there any usage? Is it within expected baseline (~$0 if no scrapes have run yet)?
5. Billing → Budgets & alerts: is there a spend cap set? If not, set one — recommended ceiling: $200/month during Phase 5 (~$50 safety margin above the $600/6-week enrichment estimate amortized to monthly).
6. Verify the key still works: from Railway, run a single Text Search query (use `python -m scripts.places_discovery --dry-run` against eat-drink). Does it return results without 403/429?

**Question to answer:** Is the Google Places API key active, the API enabled, billing in good standing, and is a spend cap configured?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- Current month spend (USD): ___
- Spend cap set (yes/no, amount): ___
- Dry-run test result: ___
- Notes: ___

**Fallback if blocked:** Phase 5 cannot dispatch without Google Places. If billing is suspended / key revoked, operator + Cowork primary triage urgent fix BEFORE any Phase 5 lane starts. This is the only Lane B item that's a hard Phase 5 blocker.

---

## §9 OSM Overpass Rate Posture

**Why it matters:** Phase 5 §3.2 On the Water uses OSM Overpass as Layer 2 supplemental for marinas / piers / beaches. Lane B confirms the public Overpass endpoint handles the expected query volume without rate-limiting Phase 5 runs.

**Starting URL (operator confirms):** `https://overpass-turbo.eu/` — the visual Overpass query builder (uses the public Overpass API endpoint at `https://overpass-api.de/api/interpreter` under the hood).

**Test procedure (~15-20 min):**

1. Open overpass-turbo.eu.
2. Paste this query (approximate LHC bounding box):
   ```
   [out:json][timeout:25];
   (
     node["leisure"="marina"](34.40,-114.45,34.60,-114.25);
     way["leisure"="marina"](34.40,-114.45,34.60,-114.25);
     relation["leisure"="marina"](34.40,-114.45,34.60,-114.25);
   );
   out body;
   >;
   out skel qt;
   ```
3. Run. Note response time + result count. Expected: <5s, handful of results (Lake Havasu State Park marina + a few private marinas).
4. Re-run 3-5 times in quick succession to test rate-limit. Any throttling?
5. Test the other tag pairs: `man_made=pier`, `natural=beach` (swap the inner filter). All return results without errors?
6. Read the existing `app/contrib/osm_overpass_client.py` `OSM_OVERPASS_LIMITER` config — should be qps=0.5 (conservative). Confirm Phase 5 runs respect this.

**Question to answer:** Does the public Overpass endpoint handle the Phase 5 LHC query volume + tag-pair set without rate-limiting at the conservative qps=0.5 we currently enforce?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- Marina query response time (sec): ___
- Marina result count: ___
- Pier query result count: ___
- Beach query result count: ___
- Throttling observed (yes/no): ___
- Notes: ___

**Fallback if blocked:** Layer 2 OSM drops from on-the-water playbook. Marinas + piers + beaches land via Google Places only. Brief §3.2 acceptance gate stays at 25+ entries (low end of 40-90 estimate) but the high end gets harder to hit without OSM supplement.

---

## §10 parks-rec-scrapes.yml Workflow Health

**Why it matters:** Cheapest leading indicator for Layer 3 LHC viability. Session-22's `18a4100` re-enabled this cron at `15 */6 * * *` (every 6 hours). If it's been failing silently since then, Lane B catches it now before §2 above tries to consume the output.

**Starting URL (operator confirms):** `https://github.com/casey451/havasu-chat/actions` → filter by `parks-rec-scrapes` workflow.

**Test procedure (~15-20 min):**

1. Open the Actions tab on the GitHub repo.
2. Filter for `parks-rec-scrapes` workflow. List the last 20 runs (covers ~5 days at 6-hour cron).
3. Count green vs red runs. Expected: nearly all green; intermittent red is OK (transient network) but persistent red is a problem.
4. If any red runs: open the most recent failure. Inspect the failed step + stack trace. Is it a transient network blip, a source-URL change (caught also by §2 above), or a script-side bug?
5. Cross-check: open `.github/workflows/parks-rec-scrapes.yml` + confirm the schedule + the script invocation match expectation.

**Question to answer:** Is the parks-rec-scrapes cron running green at the expected ~`15 */6 * * *` cadence since session-22's re-enable at `18a4100`?

**Finding:**
- Date verified: ___
- Outcome: [ ] ✅ [ ] ⚠️ [ ] ❌ [ ] ⏸
- Last 20 runs: __ green / __ red
- Most recent failure date + cause (if any): ___
- Schedule still matches expected: ___
- Notes: ___

**Fallback if blocked:** If the cron is persistently red, file a small Cursor dispatch to fix the underlying script + re-enable. Phase 5 §3.2 on-the-water can dispatch without this (Layer 3 city source is supplemental, not blocking) but the §2 verification above becomes less useful.

---

## §11 Lane B close-out checklist

When all 10 §1-§10 items are filled in:

1. [ ] Every item has an outcome marked (✅ / ⚠️ / ❌ / ⏸)
2. [ ] Every item has a finding date + notes (even if the note is just "no caveats")
3. [ ] §8 specifically is ✅ (this is the only hard Phase 5 blocker)
4. [ ] Any ❌-blocked items have their fallback documented in this file's notes section OR the brief §3 per-category playbook has been updated to reflect the drop
5. [ ] Cowork primary or operator updates `outputs/phase5_prereq_checklist.md` §4 to mark each row with the outcome icon
6. [ ] Commit this file + the prereq update with a body like *"docs: Phase 5 Lane B section-4 verifications complete -- N verified, M caveats, K blocked"*

After Lane B closes + Lane D Railway redeploy lands + the heat_exposure priority-30 list is operator-amended (§3.3.g), Phase 5 §3.1 Eat & Drink first scrape dispatches.

---

## §12 Reference

- Phase 5 prereq checklist `outputs/phase5_prereq_checklist.md` §4 (the source for these 10 items)
- Phase 5 brief `outputs/cursor_brief_phase_5_tier_1_data.md` §0.5 + §3 (per-category playbooks consume the Lane B outcomes)
- Master plan §4 Phase 5 (named the supplemental layers)
- `parks-rec-scrapes.yml` workflow (the canonical Layer 3 LHC scraper)
- `app/contrib/npi/` (existing NPI client; §5 verifies still compatible)
- `app/contrib/osm_overpass_client.py` (Layer 2 client; §9 verifies endpoint posture)

---

*Authored by Cowork primary at the new-chat post-`54ca07d` session (2026-05-13). Lives at `outputs/phase5_lane_b_verification_briefing.md` — outputs/-only per the parallel-chat lock at `8fe6321`. Operator fills §1-§10 findings inline during the ~3-4h Lane B browser session, then commits the populated doc as the Phase 5 Lane B audit artifact.*
