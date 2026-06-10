# Hava Site Audit — Code-Verified Triage

**Date:** 2026-06-03 · **Method:** every audit item checked against actual repo source (no code changed).
The original audit was done from rendered output only and explicitly asked that each root cause be
treated as a hypothesis. This document is the confirmation pass.

## Verdict legend
- ✅ **ALREADY FIXED** — code already handles it correctly; the audit reflects an older/undeployed state.
- 🔴 **CONFIRMED REAL** — bug exists in code; safe to fix.
- 🟡 **NEEDS LIVE-CHECK** — code looks correct; the symptom can only be confirmed against the deployed
  site/prod data (likely a data-quality or deploy-lag issue, not a code fix).
- 🟣 **DESIGN CHOICE / DECISION** — works as currently built; "fixing" it is a product call, not a bug.

## Tally
- ✅ Already fixed: **7** (S3 in code, S5, S6, G-1, G-4, CB-1, CL-1)
- 🔴 Confirmed real: **14** (S1, S2, E-1, E-5, ED-1, ED-5, C-1, C-2, C-3, P-1, P-2, P-4, M-1, G-2)
- 🟡 Needs live-check: **9** (S3 symptom, S4, C-4, H-1, P-3, P-5, M-2, G-3, CB-2)
- 🟣 Design/decision: **5** (ED-2, ED-3, ED-4, E-2, P-6)

**Headline:** the four "root causes" are not equal. R2 (multi-parent membership) is **real and is the
structural core** of the category mess. R4 (timezone) is **already correct in code** — the live "everything
Closed" symptom is a data/deploy issue, not a code fix. R1 (no canonical taxonomy) is real but *narrower*
than stated: the repo already has a deterministic `Provider.subcategory` system; the problem is that
**listing pages ignore it** and filter on the legacy `Provider.category` string instead.

---

## Root causes, reassessed

| # | Audit claim | Verdict | Reality in code |
|---|---|---|---|
| **R1** | No canonical taxonomy | 🔴 Real, narrower | Three label sets exist (Home 12 / Explore 15 / Map 7 — `app/home/queries.py:47`, `app/categories/queries.py:64`, `app/v1/categories.py`). BUT a deterministic subtype system already exists in `app/categories/subcategories.py`. |
| **R2** | Multi-parent membership, no primary | 🔴 **Real — core issue** | `CATEGORY_FILTERS` (`app/categories/queries.py:64`) filters listings on legacy `Provider.category`; the *same slug is reused across routes* (`religion_community` → things-to-do + public-civic-resources; `fitness_sports` → 3 routes). No test enforces single membership. |
| **R3** | Leaky ingest classifier / catch-all buckets | 🔴 Real | `Specialty`/`Venues`/`Boutiques`/`Home Goods` are live subtypes (`subcategories.py:73-92`); a card's subtype is never validated against the page's chip set → off-taxonomy labels (C-1). |
| **R4** | Time not localized to America/Phoenix | ✅ **Already fixed in code** | `app/core/timezone.py`, `app/contrib/hours_helper.py:is_open_at`, `is_open_now`, `_hours_status` all use `now_lake_havasu()`. Missing hours render "Hours on profile", not "Closed". The live symptom needs a deploy/data check, not a TZ patch. |

---

## Part A — systemic

| Item | Verdict | Evidence | Fix sketch |
|---|---|---|---|
| **S1** three taxonomies | 🔴 | Home labels `home/queries.py:47`; Explore routes `categories/queries.py:64`; Map buckets `v1/categories.py` via `api/routes/map_data.py` | Single source of truth consumed by all surfaces (the Part-C work). |
| **S2** multi-parent, no primary | 🔴 | `categories/queries.py:64-138` — overlapping slugs across routes; no single-membership test | Introduce a primary category/subtype and filter listings on it only; add invariant test. |
| **S3** "open now" wrong site-wide | ✅ code / 🟡 live | `timezone.py`, `hours_helper.py:is_open_at`, `home/queries.py:382` | Code is correct & in Phoenix time. **Verify live**: is the fix deployed? Do prod providers have structured hours? Likely data-quality, not code. |
| **S4** counts don't reconcile | 🟡 | `category_count()` `categories/queries.py:438`; home tiles `home/queries.py:698` use a different `group_by COUNT` query | Centralize counts on one query; label what each number means. Confirm the live deltas against data first. |
| **S5** conditions strip differs per page | ✅ | `app/conditions/cache.py:38` — single shared `ExternalConditionsCache`, 5-min TTL, all surfaces | No code change. Live deltas would be the 5-min cache window. |
| **S6** stale hardcoded date on Explore | ✅ | `categories/router.py:236` builds `today_label` from `now_lake_havasu()` — dynamic, not literal | No hardcoded date in code. The "May 29" the audit saw is a caching/CDN artifact — verify live. |

## Part B / category template

| Item | Verdict | Evidence | Fix sketch |
|---|---|---|---|
| **C-1** leakage + off-taxonomy subtype labels | 🔴 | Multi-parent (`queries.py:78`) + subtype derive (`subcategories.py:296`) with no bucket validation; card subtype set at `queries.py:357` | Validate `Provider.subcategory ∈` page bucket's chip set; resolves once R2 lands. |
| **C-2** no cuisine drill-down | 🔴 | No `cuisine` field/tag anywhere; food chips capped at restaurants/bars/cafes/quick-bites (`subcategories.py:54`) | Add `cuisine` tag + 2nd-level chip row; same pattern serves Auto/Health. |
| **C-3** default sort = wall of "Closed" | 🔴 | `categories/queries.py:682` sorts `(-favorites_score, name)` — no open-now tiebreak | Add `is_open_now(p)` as a tiebreak after the favorites score. |
| **C-4** possible dupes | 🟡 | `core/dedupe.py` is event-only; Provider merge is manual (`contrib/provider_merge.py`); `google_place_id` nullable/non-unique (`db/models.py`) | Confirm dupes live, then dedupe on place_id/address — not name. |
| **C-5** missing/partial sub-filters | 🟡 | `subcategories_for_category_route()` — `public-civic-resources` & `things-to-do` DO return chips; the 8 *tile* routes return `[]` | Audit said Community had zero chips; code returns 8. Verify live (may be deploy lag). Tile routes genuinely show no 2nd level — fold into Part-C. |

## Events

| Item | Verdict | Evidence | Fix sketch |
|---|---|---|---|
| **H-1** recurring classes bury one-offs | 🟡 | `home/queries.py` `this_week` has no per-venue cap (`tonight` does, via `seen_locations`); series collapse at render in `home/router.py` | Add per-venue/category cap to the `this_week` slice; confirm symptom live. |
| **E-1** time-buckets off by a window | 🔴 | `app/events/queries.py:19-46` `event_window_for_chip` — `(6-weekday)%7` collapses to 0 on Sunday; weekend window math drifts on Sat | Fix boundary math; anchor to `now_lake_havasu().date()`. |
| **E-2** description leaks into venue slot | 🟣→🔴 | Template shows separate fields (`event_permalink.html`); the leak is upstream — ED-1. Add `"Location TBD"` fallback when `location_name` null | Real fix is ED-1 + a null fallback. |
| **E-3** calendar non-functional | 🟡 | Grid is client-JS rendered (`events_lake_light.js`); **note: Lake Light may be superseded by Sandstone** — verify which event template is actually routed before fixing | Render day cells + preselect today *in the live template*. |
| **E-4** duplicate Farmers Market / raw address as venue | 🟡 | Dedup handles one-off collisions, not recurring-series instances; raw address stored when venue resolve fails | Dedupe recurring series; never use raw address as display venue (ED-1 adjacent). |
| **E-5** "Events 25" reads as total | 🔴 | `events_sandstone.html:9` `{{ events_total }} upcoming` = sum of near-term windows | Relabel ("25 coming up"). |
| **ED-1** parser field corruption | 🔴 **priority** | `events/scrapers/go_lake_havasu.py:80-86` — `venue = loc.get("name") or loc.get("address")`; JSON-LD `address` object leaks into venue; no `LOCATION:` line parse | Parse JSON-LD address object into structured fields; backfill; stop writing description into venue/address. |
| **ED-2** detail page raw field dump | 🟣 | `event_permalink.html` is a real (sparse/editorial) template, not a debug dump | Optional richer template — product call, not a bug. |
| **ED-3** image not rendered | 🟣 | No image field surfaced in template | Add `<img>` only if events carry an image field — verify model. |
| **ED-4** sign-up CTA is plain text | 🟣 | `main.py` wraps `event_url` as a link with the URL as its label | Cosmetic: relabel the anchor. |
| **ED-5** og:url uses http:// | 🔴 | `main.py:688` `permalink_url=str(request.url)` — http in dev; depends on `X-Forwarded-Proto` in prod | Coerce https (a `BASE_URL` env already exists, unused here). |

## Provider / Map / Gas / Misc

| Item | Verdict | Evidence | Fix sketch |
|---|---|---|---|
| **P-1** breadcrumb → /categories | 🔴 | `provider_profile.html:15` hrefs `/categories` (Explore) | Link to the actual parent category page. |
| **P-2** per-review stars hardcoded ★★★★★ | 🔴 | `provider_profile.html:91` literal `★★★★★` next to `{{ snippet.text }}` | Render real per-review rating or drop per-excerpt stars. |
| **P-3** address stray leading fragment | 🟡 | `providers/queries.py:284` `derive_display_address` returns raw `loc.address` uncleaned | Clean leading-fragment in the pipeline; confirm pattern live. |
| **P-4** "While you're here" mislabels | 🔴 | `providers/queries.py:523` labels nearby cards from single `Provider.category` | Resolves with R2/primary category. |
| **P-5** three claim prompts | 🟡 | `provider_profile.html` has cover-lock + side CTA + Ask-Hava link | Consolidate; partly intentional (owner vs visitor). Confirm intent. |
| **P-6** Google review excerpts on profile | 🟣 DECISION | `provider_profile.html:91` renders `{{ snippet.text }}` unlabeled | Casey's call: keep + label "From Google", or drop. |
| **M-1** duplicate map scope rows | 🔴 | `home/router.py:458` group_scopes + category_scopes resolve to same labels | Label the tiers or collapse. |
| **M-2** pins/cluster/empty-state | 🟡 | `map_c.html` Leaflet+MarkerCluster, JS-only | Verify live or via e2e. |
| **G-1** raw ISO timestamp | ✅ | `api/routes/gas.py:59` `_format_fetched_at` humanizes already | No change; verify live deploy. |
| **G-2** staleness threshold too tight | 🔴 | `conditions/constants.py` gas TTL 86400s but `staleness.py` marks stale at ≥2h | Raise threshold for daily feeds (~26-28h) or change copy. |
| **G-3** some stations unlinked | 🟡 | `gas_prices.html` gates link on `s.provider_slug`; data-dependent | Ensure Provider records/slugs exist for those stations. |
| **G-4** city avg 3 decimals | ✅ | `gas_prices.html:35` uses `'%.2f'` (2 decimals) | No change; verify live deploy. |
| **CL-1** collection page | ✅ GOOD | `home/collections.py:124` loads curated JSON, not category membership | Keep; build future collections from tags. |
| **CH-1** chat taxonomy | 🟡 | `chat/entity_catalog_query.py:67` reads legacy `provider.category` w/ `Entity.categories` fallback — not `.subcategory` | After Part C, point chat retrieval at the canonical category. |
| **CB-1** contribute event fields always shown | ✅ | `claim_form.html` is notes-only; no event fields to gate | No change. |
| **CB-2** required-field markers | 🟡 | `claim_form.html` no visible markers; may rely on HTML5 | Add markers if desired. |

---

## What changes in the execution plan

1. **Drop from scope (already fixed):** S5, S6, G-1, G-4, CB-1 — and the *code* half of S3.
2. **Wave 1 shrinks** to genuinely-broken, small-blast-radius items: **ED-1** (parser + backfill, gated prod-data),
   **E-1** (bucket math), **E-5** (label), **ED-5** (https), and a **live-verification pass** for S3/S6/G-1/G-4
   to confirm prod actually reflects the fixed code (i.e. is a redeploy or a data backfill the real fix?).
3. **Wave 2 (the main event) is real and confirmed:** R2 multi-parent is the structural bug. The key decision
   narrows to **extend the existing `subcategory` system into the single primary-category model vs. build the
   audit's richer `primary_category`+tags+LLM model**. Stage 0-2 of Part D *already exist* deterministically —
   no LLM is currently needed for the bulk. Gated on DECISION-1/2/3 + the reclassification backfill (prod-data op).
4. **Caveats to resolve before coding:**
   - Confirm **which event template is actually routed** (Sandstone vs Lake Light) — E-3/E-2/E-5 evidence
     spans both; fixing a dead template wastes effort.
   - Confirm whether events carry an **image field** in the model (gates ED-3).
   - The live-only items (S3 symptom, S4, C-4, C-5, H-1, P-3, M-2, G-3) need a deployed-site/prod-data look —
     several may evaporate as deploy-lag.

## Items genuinely needing a live/prod look (can't resolve from code)
S3 symptom · S4 counts · C-4 dupes · C-5 (Community chips) · H-1 · P-3 · M-2 · G-3 · CB-2 — plus confirming
the ✅ already-fixed items are actually live (S5/S6/G-1/G-4).
