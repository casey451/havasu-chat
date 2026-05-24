# AZ TPT license verifier — operator action package (#22)

> **Status:** dispatch-blocked at autonomous level; deferred from V1.5 wave 4
> (2026-05-24). Sibling ship in the same lane: **#23 BBB verifier** (shipped
> clean). Ticket #22 remains open in `outputs/v1_5_carries_inventory.md` §2.3.
>
> **Why this isn't a code ship today:** Chrome MCP recon
> (`outputs/chrome_mcp_captcha_recon_v22.md`) confirmed two independent blockers
> on the public AZTaxes verifier at
> `https://www.aztaxes.gov/Home/LicenseVerification`:
>
> 1. **Scope mismatch** — the form accepts only an **8-digit TPT license
>    number**. It does not accept business names. Wave 4 planned a name-based
>    fuzzy-match verifier (mirror BBB / AZ MVD bulk roster); no public
>    name→license bridge or bulk roster exists.
> 2. **Google reCAPTCHA v2** — checkbox gate on page load; Submit stays disabled
>    until passed. Auto-solving would require paid captcha services (new deps),
>    violating wave 4 §8 ZERO-new-deps rule.

---

## §1 Why this verifier matters

Per V1.5 inventory `outputs/v1_5_carries_inventory.md` §2.3 ticket **#22**:
**AZ TPT (Transaction Privilege Tax) license — cat-8 retail trust signal.**

Every lawful retail business operating in Arizona must hold an active TPT
license. Stamping `Provider.verified = True` +
`attributes['aztpt'] = {tpt_license_number, business_status, match_score, ...}`
for `shopping-essentials` providers would extend Layer-4 trust-signal coverage
beyond BBB accreditation (#23).

Relevant TPT business class codes for retail (per AZ DOR schedules; filter when
a bulk roster is obtained):

- **011** — Retail (general merchandise)
- **012** — Retail (food for home consumption — grocery)
- **013** — Retail (restaurants — usually cat-7, exclude from cat-8 scope)
- **017** — Retail (other — hardware, gifts, etc.)

Use class codes only when parsing a bulk export; the public verifier UI does
not expose them without a known license number.

---

## §2 Why autonomous-code-ship is blocked

| Blocker | Evidence | Implication |
|---|---|---|
| License-number-only UI | Chrome MCP DOM inspection 2026-05-24; page text: "Enter the eight digit transaction privilege tax license number" | Cannot implement name-based `rapidfuzz` match against live registry |
| No bulk roster | Wave 4 §3.1 probe + web search; unlike AZ MVD Valid Dealer Report (#20) | No offline CSV/HTML table to walk |
| reCAPTCHA v2 | Checkbox on load; Submit disabled until solved; expires ~2 min | Playwright headless cannot yield live matches without captcha solver dep |
| No `tpt_license_number` upstream | `Provider` model has no pre-populated license field for shopping-essentials | Even license-number lookup path needs external seed |

**HALT classification:** wave 4 §7 — "no usable public verifier" for the
planned name-search use case (technically a verifier exists, but not for this
plan).

---

## §3 Path A — public records request (recommended; one-time bulk seed)

AZ DOR honors public-records requests for TPT licensee rosters under Arizona
Public Records Law (A.R.S. § 39-121 et seq.).

**Action:**

1. Email `taxpayerinformation@azdor.gov` (or the contact at
   `https://azdor.gov/contact-us/public-records-requests`):

   ```
   Subject: Public records request — TPT licensee extract for Mohave County retail businesses

   Hello,

   Under Arizona Public Records Law (A.R.S. § 39-121 et seq.), I am requesting an
   electronic export (CSV or Excel) of all currently-active TPT licensees with a
   physical or mailing address in Mohave County (ZIP codes 86403–86406 and other
   Mohave County ZIPs) whose business class includes retail TPT codes (e.g. 011,
   012, 017 — exclude transient lodging 025/125 unless combined request).

   For each licensee, please include:
   - TPT License Number (8 digits)
   - Business Name (DBA) and legal entity name if available
   - Mailing and physical addresses
   - License status (Active / Cancelled / Suspended)
   - All business class codes on the license

   Output format: CSV or Excel preferred.

   Thank you,
   [Operator name]
   ```

2. Expected turnaround: **3–10 business days**.

3. When the CSV arrives, save to e.g. `data/aztpt_mohave_retail.csv` and ship
   a **CSV-import verifier** (mirror `scripts/azmvd_verify.py` bulk pattern,
   NOT live Playwright):

   - `app/contrib/aztpt_client.py` — parse local CSV / cached export
   - `scripts/aztpt_verify.py` — fuzzy-match `provider_name` against export;
     idempotency on `attributes['aztpt']['tpt_license_number']`
   - `tests/test_phase5_aztpt_verify.py` — mock CSV rows; no live AZTaxes calls

4. Schedule quarterly refresh requests.

---

## §4 Path B — manual spot-check (Chrome MCP or operator browser)

When a provider **already has** an 8-digit TPT license number (e.g. from owner
claim, invoice, or Path A CSV), an operator can confirm status manually:

1. Open `https://www.aztaxes.gov/Home/LicenseVerification` in a normal browser.
2. Complete the reCAPTCHA v2 checkbox.
3. Enter the 8-digit license number; click Submit.
4. Record status from the result page.
5. Optionally stamp the provider in admin tooling:
   `attributes['aztpt'] = {tpt_license_number, business_status, verified_via: 'manual'}`.

This path does **not** scale to batch name-based verification; use Path A for
that.

---

## §5 Path C — license-number-only automation (future, if upstream exists)

If Path A or owner claims populate `attributes['aztpt']['tpt_license_number']`
(or a dedicated column), a future script could:

1. Read candidates with a known license number but `verified=False`.
2. Use operator-driven Chrome MCP (not headless Playwright) to submit each
   number after manual captcha solve — same robots.txt rationale as
   `docs/operations/azdor_lodging_verifier_action_package.md` §4.

Do **not** author this until license numbers exist in the catalog.

---

## §6 Recommended sequencing

1. **Wave 4 close (done):** ship #23 BBB only; defer #22 per §11 deviation.
2. **Operator action:** send Path A public-records request for Mohave retail TPT.
3. **When CSV arrives:** ship CSV-import verifier (~3h; mirror AZ MVD bulk shape).
4. **Inventory:** keep #22 open; re-tag from "Playwright" to "bulk CSV import OR
   operator manual; live name-search blocked."

---

## §7 Cross-references

- `outputs/chrome_mcp_captcha_recon_v22.md` — scope mismatch + reCAPTCHA evidence
- `outputs/cursor_dispatch_prompt_v1_5_wave4_layer4_verifiers.md` — wave 4 §7 HALT
- `outputs/azdor_lodging_verifier_action_package.md` — sibling AZDOR TPT package (#18, lodging)
- `scripts/bbb_verify.py` — wave 4 #23 shipped verifier (name-match pattern that *does* work)
- `scripts/azmvd_verify.py` — bulk-download fuzzy-match template for future Path A ship
- `outputs/v1_5_carries_inventory.md` §2.3 ticket #22

---

*Authored 2026-05-24 after Cowork primary Chrome MCP recon redirected wave 4
#22 from functional-but-inert Playwright ship to operator-action deferral.*
