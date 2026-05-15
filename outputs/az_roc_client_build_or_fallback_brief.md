# AZ ROC Client — Build-or-Fallback Research Brief (Task #6)

> **What this is:** the research input for the operator decision on task #6 —
> turning `app/contrib/az_roc_client.lookup_contractor` from a stub into a working
> lookup. **This is a decision brief, not a dispatch.** Cowork researched the
> options; the operator picks the path. Needed before Phase 5.3
> (`home-property-services`), whose acceptance gate requires "AZ ROC
> cross-reference coverage on every licensed-trade entry."
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat
> (post-`d34d4c3`, 2026-05-15). Brand-new `outputs/` file — safe under the
> parallel-chat scope lock. Web research via WebSearch/WebFetch.

---

## §1 Current state

`az_roc_client.lookup_contractor(client, business_name) -> AzRocMatch | None` is a
v1 stub that **always returns `None`**. `AzRocMatch` carries `license_number`,
`classification`, `status`, `raw`.

It's consumed by `scripts/az_roc_verify.py`, which already has the full scaffold
built around it: iterates `home-property-services` providers, looks up by business
name, memoizes by normalized name, throttles to ≥2.0s between live calls, and on a
match stamps `verified=True` / `verification_method='scraper'` /
`attributes['az_roc']`. **The consumer is done — only the lookup itself is missing.**

The stub's docstring guesses the blocker is "results not reliably present in the
initial HTML shell." The research below refines that: the results *are* in the DOM
— but only *after* a JavaScript-driven search action runs. A plain `httpx` GET of
the search URL will never see them.

**Phase 5.3 gate dependency:** the `home-property-services` acceptance gate
(`cursor_brief_phase_5_tier_1_data.md` §3.3) requires AZ ROC cross-reference
coverage on every licensed-trade entry. A pure stub does not meet that gate; one of
the options below (or a manual process) has to land first. Volume is modest and
**one-time**: ~120–220 providers, verified once — not a recurring scrape.

## §2 What the research found

- **No official AZ ROC API.** Confirmed across multiple sources. The agency runs
  its public portal on Salesforce Experience Cloud (`azroc.my.site.com`) with
  Lightning Web Components. There is no documented public API and no bulk JSON/CSV
  endpoint.
- **The portal is server-rendered HTML — after the search action.** The search
  page returns a paginated results `<table>` in the DOM once the LWC search runs.
  Pagination is **purely DOM-level** — clicking Next re-renders from an
  already-loaded result set and triggers *no* network request. So the search
  server-action returns the whole result set at once.
- **Bot protection exists.** Salesforce applies standard rate-limiting; third-party
  scrapers recommend residential proxies + delays for production reliability.
- **A bulk download exists only via formal Public Records Request.** `roc.az.gov`
  has PRR forms; records are obtainable as a download but through a manual,
  fee-bearing, appointment-based process — not automatable, not fresh-on-demand.
- **A third-party scraper exists** — an Apify actor
  (`haketa/az-roc-contractor-license-scraper`, ~$6/1,000 results) that does
  company-name search and returns exactly the fields `AzRocMatch` needs. **Caveat:
  it is brand-new and unproven** — 0 reviews, 2 total users, last modified hours
  before this research. Its README is, however, a detailed and useful technical
  spec of the portal's DOM (selectors, pagination buttons, rowspan layout).

## §3 The options

| Option | What it is | Effort | Ongoing risk | Gate fit |
|---|---|---|---|---|
| **A — Build a Playwright lookup in-house** | Headless Chromium fills the search box, clicks Search, parses the results `<table>`. The Apify README documents the exact DOM (`.right-btn`/`.left-btn` pagination, `<select class="slds-select">` page size, `rowspan` business blocks, `data-label="line"` separators) — effectively a free spec. | Medium — new `playwright` dependency, ~a day of work + a test file. `az_roc_verify.py`'s throttle/memoize scaffold is already there. | DOM-brittle (breaks if Salesforce changes markup); needs residential proxies for reliability at volume. But this is a *one-time* low-volume pass, so brittleness exposure is small. | ✅ Meets the gate. |
| **B — Reverse-engineer the Salesforce Aura endpoint** | The search server-action is an Aura/`apexremote` POST. If replicated, `lookup_contractor` stays a pure `httpx` call — which is exactly what the current signature anticipates. | High — Aura POSTs need `aura.token` + `aura.context` (framework UID changes per Salesforce deploy); guest-user lockdowns are common. Significant reverse-engineering, easy to get stuck. | Fragile — re-derivation needed whenever Salesforce redeploys. | ✅ If it works — but feasibility is uncertain until you try. |
| **C — Use the Apify actor as the backend** | `lookup_contractor` becomes a thin client calling the Apify API with `companyNames: [business_name]`. No browser, no proxies, no DOM maintenance in-house. ~$1 total for the whole 5.3 pass. | Low — wire an API key + a small client. | Third-party dependency on an **immature, unproven** actor (0 reviews, 2 users). Vendor + key to manage. Could also use the Bright Data plugin already in this environment as a more-established scraping backend. | ✅ Meets the gate, lowest effort — *if* you trust the vendor. |
| **D — Manual / keep stub** | `az_roc_verify.py` already treats `None` as "no match" gracefully. Operator manually looks up licensed-trade providers in the portal and records the license. | Low (code) / High (operator time) | None technical. | ⚠️ Only meets the gate if the operator actually does the manual pass — ~120–220 lookups by hand. Viable as a stopgap given the one-time, modest volume. |

## §4 Cowork recommendation

**Lead with Option A (build the Playwright lookup), with Option D as the explicit
stopgap if Phase 5.3 arrives before A is built.**

Reasoning:
- Option C is the lowest *effort*, but the only available actor is too immature to
  take a gate dependency on. If you want to revisit C, the Bright Data plugin
  already in this environment is a more-established backend than the Apify actor —
  worth a look before committing to a brand-new vendor.
- Option B is the cleanest *result* (pure `httpx`, no browser) but the worst
  *effort-to-confidence* ratio — Aura reverse-engineering can swallow a day and
  still not land. Not worth it for a one-time pass.
- Option A is the proven approach (the Apify actor demonstrates it works), the
  README hands you the DOM spec, and the consumer scaffold is already built. The
  brittleness concern is real but *bounded* — this is a one-time verification pass,
  not a cron job, so a DOM change after the pass completes costs nothing.
- Because volume is low and one-time, **Option D is a legitimate stopgap**: if
  Phase 5.3 dispatches before the scraper is built, the operator can hand-verify
  the licensed trades and the gate is still met. Don't block 5.3 on the scraper.

This is the operator's call — all four are defensible. If you pick A, it's a clean
Cursor dispatch (new `playwright` dep + `az_roc_client.py` body + a test); say the
word and I'll draft it.

## §5 Whichever path: the contract is already right

No matter which option lands, the integration surface doesn't change:
- `AzRocMatch` (`license_number` / `classification` / `status` / `raw`) maps cleanly
  onto every source — the Apify field reference confirms `licenseNumber`,
  `licenseStatus`, `primaryClassification` are all available.
- `scripts/az_roc_verify.py` needs **no changes** — it already throttles, memoizes,
  and stamps. It just needs `lookup_contractor` to start returning real matches.
- For Option A or B, keep the `httpx.Client` parameter in the signature even if
  Playwright ignores it (Option A) — `az_roc_verify.py` passes it positionally and
  changing the signature would ripple. Or update both together in one dispatch.

## §6 Sources

- [Arizona Registrar of Contractors — home](https://roc.az.gov/)
- [AZ ROC Contractor Search portal](https://azroc.my.site.com/AZRoc/s/contractor-search)
- [AZ ROC search (roc.az.gov)](https://roc.az.gov/search)
- [AZ ROC Public Records Request forms](https://roc.az.gov/public-records-request-forms)
- [Apify — Arizona ROC Contractor License Scraper (README = portal DOM spec)](https://apify.com/haketa/az-roc-contractor-license-scraper)
- [Salesforce customer story — Arizona Registrar of Contractors on Salesforce Platform](https://www.salesforce.com/customer-success-stories/arizona-registrar-of-contractors/)

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.1 field-entry chat (post-`d34d4c3`,
2026-05-15). Lives at `outputs/az_roc_client_build_or_fallback_brief.md` — brand-new
`outputs/` file, safe under the parallel-chat scope lock. Research-only; the
build-or-fallback decision is the operator's.*
