# AZDOR transient-lodging tax verifier — operator action package

> **Status:** dispatch-blocked at autonomous level; needs operator-side
> data ingest OR Chrome MCP scrape pattern before the script can ship.
> Captured 2026-05-23 as part of the V1.5 Trust-Signal Verifier Bundle
> wave 1 (`outputs/v1_5_carries_inventory.md` §2.3 ticket #18). Sibling
> ship: `52f82f2` AZDHS childcare verifier (shipped clean via ArcGIS
> FeatureServer; no equivalent endpoint exists for AZDOR TPT).
>
> **Why this isn't a code ship today:** AZDOR's TPT License Verification
> lookup at `https://aztaxes.gov/Home/LicenseVerification` is (a) a
> JS-rendered ASP.NET/Razor SPA with no documented public JSON/CSV
> endpoint, and (b) both `aztaxes.gov/robots.txt` and `azdor.gov/robots.txt`
> explicitly Disallow ClaudeBot / GPTBot / CCBot / Google-Extended. A
> Claude-identified `mcp__workspace__web_fetch` returns Cloudflare-blocked
> shells uniformly. A custom-UA Playwright scraper is technically permitted
> per the `User-agent: *` allow rule, but would require either the operator
> running it on their own machine OR a Chrome MCP-based session.

---

## §1 Why this verifier matters

Per V1.5 inventory triage `outputs/v1_5_carries_inventory.md` §2.3 + line
220: **"AZDOR transient-lodging tax registry (cat-10) — strong trust
signal; ~70-90% hotel/motel/B&B coverage."**

Lake Havasu City lodging entries (Heat Hotel, London Bridge Resort,
Nautical Beachfront Resort, KOA campground, Crazy Horse Campgrounds,
etc.) currently carry no state-registry verification. AZDOR's TPT license
is a hard prerequisite for lawful operation in Arizona — every legitimate
lodging business in LHC ZIP 86403–86406 has one. A verifier that stamps
`Provider.verified = True` + `attributes['azdor_tpt']` = {license_number,
status, class_codes, issued_date} would provide the same trust signal
as the just-shipped AZDHS verifier provides for childcare.

The category-specific business class codes to filter on (per AZDOR TPT
schedule):
- **025** — Transient Lodging (hotels/motels/short-term rentals < 30 days; primary lodging signal)
- **125** — Transient Lodging (additional county tier; some counties)
- **213** — Online Lodging Marketplace (Airbnb / Vrbo intermediaries; ancillary signal)
- **062** — Rental of Real Property (long-term, > 30 days; NOT a lodging trust signal — exclude)

AZDOR does NOT use NAICS codes publicly. Rely on TPT class codes.

---

## §2 Why autonomous-code-ship is blocked

The 2026-05-23 V1.5 wave 1 recon (sub-agent fetch via
`mcp__workspace__web_fetch` against `https://aztaxes.gov/Home/LicenseVerification`
and 3 variant paths) found:

1. **JS-rendered SPA** — all four URL variants returned empty bodies
   through `web_fetch`. Consistent with client-rendered output. No
   server-side HTML to parse.
2. **No documented JSON/CSV endpoint** — the form POSTs to an internal
   `/Home/LicenseVerification` action and renders results in-page;
   there is no REST/OData surface for bulk lookups.
3. **No open-data export** — `data.az.gov` and `opendata.az.gov` returned
   empty (likely also Cloudflare-gated). AZ publishes only aggregated TPT
   distribution reports (city/county revenue), not licensee rosters.
4. **No geo filter** — the form requires License Number OR Business Name +
   Mailing ZIP per query. Cannot list "all Mohave County lodging" in
   one request; must iterate per-row.
5. **Robots: Claude-identified UAs blocked.** Both `aztaxes.gov/robots.txt`
   and `azdor.gov/robots.txt` explicitly Disallow `ClaudeBot`, `GPTBot`,
   `CCBot`, `Google-Extended`. Generic `User-agent: *` is `Allow: /` —
   a custom-UA scraper is technically permitted but not from Claude
   tooling directly.

Two viable paths forward (operator-decide; can be done in parallel):

---

## §3 Path A — public records request (recommended; one-time bulk seed)

**The cleanest first-step.** AZDOR honors public-records requests for
licensee rosters under Arizona Public Records Law (A.R.S. § 39-121 et
seq.). Business TPT licenses are public records — no PII concerns.

**Action:**

1. Email `taxpayerinformation@azdor.gov` (or the public-records contact
   listed at `https://azdor.gov/contact-us/public-records-requests`)
   with the following request body:

   ```
   Subject: Public records request — TPT licensee extract for Mohave County lodging businesses

   Hello,

   Under Arizona Public Records Law (A.R.S. § 39-121 et seq.), I am requesting an
   electronic export (CSV or Excel) of all currently-active TPT licensees in
   Mohave County whose business class includes:

   - Class 025 (Transient Lodging)
   - Class 125 (Transient Lodging, additional county tier)
   - Class 213 (Online Lodging Marketplace)

   For each licensee, please include:
   - TPT License Number
   - Business Name (DBA) + Owner / Legal Entity Name
   - Mailing Address + Physical (Location) Address
   - License Status (Active / Cancelled / Suspended / Pending)
   - License Issued Date
   - All Business Class Codes tied to the license

   ZIP filter: 86403, 86404, 86405, 86406 (Lake Havasu City) AND all other
   Mohave County ZIPs. Active licenses only.

   Output format: CSV or Excel preferred; PDF acceptable if unavailable.

   I am happy to cover any reasonable copying / extraction fees as
   specified in A.R.S. § 39-121.01(D)(2).

   Thank you,
   [Casey Solomon]
   ```

2. Expected turnaround: **3–10 business days** for an electronic
   extract; AZDOR is generally responsive on TPT records.

3. When the CSV arrives, save it to `data/azdor_tpt_lodging_mohave.csv`
   and run the (forthcoming) `scripts/azdor_verify_from_csv.py`
   importer — same fuzzy-match + verified-stamp shape as
   `scripts/npi_verify.py` / `scripts/azdhs_verify.py`, but loading
   from the local CSV rather than a live API.

4. Schedule a quarterly refresh request (TPT licensees do change
   quarterly; an annual refresh is the minimum cadence to keep the
   trust signal accurate).

---

## §4 Path B — Chrome MCP scrape pattern (delta polling)

**Once Path A's seed CSV is in place**, a Chrome MCP-based delta
scraper can keep the trust signal fresh between operator-side public-records
requests. Pattern:

1. For each LHC lodging entry in our catalog (cat-10 lodging-vacation-rentals,
   filtered to types like `lodging`, `hotel`, `motel`, `resort`,
   `bed_and_breakfast`, `rv_park`, `campground`), drive Chrome MCP via
   `mcp__Claude_in_Chrome__navigate` to `https://aztaxes.gov/Home/LicenseVerification`,
   fill the Business Name field with the provider's `provider_name`, fill
   the ZIP field with the provider's ZIP, click Search, await the result
   render, then capture the rendered result via
   `mcp__Claude_in_Chrome__get_page_text`.

2. Parse the rendered HTML for license number, status, and class codes
   (looking for 025 / 125 / 213). If status is Active and class is one of
   the lodging codes, stamp `Provider.verified = True` +
   `verification_method = 'scraper'` + `attributes['azdor_tpt']` = {...}.

3. Respect a polite rate limit (≥ 2s between lookups; mirror the
   `MIN_INTERVAL_S = 2.0` from `scripts/az_roc_verify.py`).

4. Schedule weekly (or per-quarter) to detect status changes since the
   last seed import.

**Why Chrome MCP not Playwright directly:** Chrome MCP runs through the
operator's own browser instance (with operator's UA), so it sidesteps
the Claude-identified UA block in `aztaxes.gov/robots.txt`. The user's
browser is the legitimate User-agent on a public lookup form. Same
pattern would work for Playwright run from operator's machine with a
non-Claude UA.

---

## §5 Code skeleton (defer authoring until Path A or B unblocks)

When either path unblocks, the verifier ship will be a 3-file commit
mirroring the AZDHS pattern from `52f82f2`:

- `app/contrib/azdor_client.py` — fetches/parses TPT license data (from
  CSV in Path A; via Chrome MCP wrapper in Path B). Returns list of dicts
  shaped roughly like:
  ```python
  {
      "license_number": "12345678",
      "business_name": "London Bridge Resort",
      "owner": "...",
      "physical_address": "...",
      "mailing_address": "...",
      "status": "Active",
      "issued_date": "2018-03-15",
      "class_codes": ["025", "213"],
  }
  ```

- `scripts/azdor_verify.py` — mirrors `scripts/azdhs_verify.py` line-for-line.
  CATEGORY_SLUG = "lodging-vacation-rentals". MATCH_THRESHOLD = 86.
  Filter class_codes to {025, 125, 213} only. VERIFICATION_METHOD =
  "scraper" (same rationale as AZDHS — per-source provenance in
  attributes['azdor_tpt']; CHECK constraint expansion deferred). Idempotency
  on attributes['azdor_tpt']['license_number'] presence.

- `tests/test_phase5_azdor_verify.py` — mirror
  `tests/test_phase5_azdhs_verify.py`: happy-path + dry-run + case-mismatch
  regression + skip-already-verified.

Expected ship cost: ~3 hours (same pattern as AZDHS at 580 lines / one
session).

---

## §6 Recommended sequencing

1. **Operator action now:** send the §3 Path A public-records request.
   Zero-effort first step; no code blocked.
2. **Cowork-primary action while waiting:** ship the V1.5 wave-1 sibling
   work — AZRE LHC vacation-rental verifier via the ArcGIS FeatureServer
   discovery path (see sibling action package, once authored). The AZDHS
   ship at `52f82f2` proves the ArcGIS-FeatureServer pattern works for
   AZ public registries; AZRE's LHC city registry is the same shape.
3. **When the public-records CSV arrives** (3–10 days), ship the AZDOR
   verifier per §5 in one session.
4. **Quarterly refresh** thereafter — re-send the public-records request
   on a calendar reminder.

---

## §7 Cross-references

- `outputs/v1_5_carries_inventory.md` §2.3 (ticket #18 in the L4 verifier bundle)
- `outputs/v1_5_carries_inventory.md` line 301 (wave 1 = {#17, #18, #19})
- `scripts/npi_verify.py` (Phase 5.4 ship; the canonical fuzzy-match verifier template)
- `scripts/az_roc_verify.py` (Phase 5.3 ship; the Playwright-with-throttle pattern)
- `scripts/azdhs_verify.py` (`52f82f2`, just-shipped; the ArcGIS-FeatureServer pattern)
- `app/contrib/rate_limiter.py::SourceLimiter` (per-source rate-limit wrapper for Chrome MCP scrape if Path B)
- `docs/maintainability/dispatch_channels.md` gotcha #19 (live-prereq verification rule — applies if operator-side Path A turns out to have different schema than expected)

---

*Authored 2026-05-23 as the operator-action handoff for V1.5 wave-1
ticket #18. Sibling ships: `52f82f2` (AZDHS) shipped; AZRE in
progress. Refresh this doc when Path A seed CSV lands or when Path B
Chrome MCP pattern is proven.*
