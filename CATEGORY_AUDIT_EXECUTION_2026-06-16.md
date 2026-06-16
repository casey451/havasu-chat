# Category Coverage Audit — Execution Log (2026-06-16)

Session record of taking the **2026-06-15 category coverage audit** live: recategorizations, web-sourced adds, routing fixes, and a duplicate-cleanup remediation. All prod data ops were gated `dry-run → counts → Casey approval → apply`. Nothing was merged to `main`; all code lives on PR **[#350](https://github.com/casey451/havasu-chat/pull/350)** (`chore/category-coverage-audit-2026-06-15`).

---

## 1. Summary

| Area | Result |
|---|---|
| Recategorizations (`Provider.subcategory`) | **40** moves live (35 exact + 4 fuzzy + 1 manual Elks) |
| Stale-primary fixes (recat'd rows) | **11** `primary_category` corrections |
| Adds → live providers | **79** created → **55 live** after dedup (22 marine + 39 high + 18 med, minus 24 dups) |
| Duplicates remediated | **24** (23 deactivated + 1 kept where prior was draft) |
| Originals re-leafed during remediation | 15 recat + 2 primary-fix |
| Contributions rejected | **33** (23 remediation + Horizon + 8 name-dups + Sky Shark) |
| Review queue (operator_backfill providers) | **0 pending** (55 approved / 33 rejected) |
| Scripts delivered to PR #350 | 8 scripts + 2 CSVs, ruff + pytest green |

---

## 2. What was done, in order

### 2.1 Recategorizations — 35 moves (`apply_recategorizations.py`)
Reviewed `category_recategorizations_2026-06-15.csv` (52 rows). Exact, case-insensitive name match on active, non-draft providers; zero/multiple matches reported and skipped (never guessed).
- **Applied: 35** subcategory moves. 8 already-correct, 8 unmatched, 1 no-target skip.
- Live on `/lake-havasu/{subcategory}` pages immediately; reversible.

### 2.2 Adds → review queue — 88 pending (`load_candidates_to_review_queue.py`)
Funneled `category_coverage_candidates_2026-06-15.csv` (90 rows) through `create_contribution` as **pending, unverified** suggestions (marine batch of 22 first, then full set).
- **Submitted: 88** (2 omitted: `Propeller CO` shared a generic Yelp URL with `Gibbs`; `Lake Havasu City Aquatic Center` pre-existing dup).
- Gotcha logged: dry-run can't see intra-CSV URL collisions (it never writes, so the first never lands to block the second).

### 2.3 PR #350 opened
Branched off `main` (clean), committed the 2 scripts + 2 CSVs.

### 2.4 Resolved the 8 unmatched recats (`apply_recategorizations_fuzzy.py`)
Punctuation-insensitive key + containment + token-subset match for the 8 names that the exact pass missed.
- **4 confident moves applied** (golf E/W courses → golf, Desert Experience UTV → trails-offroad, London Bridge Harley → auto).
- **3 already-correct** (Elite Martial Arts, LH Black Belt Academy, Reflections Steakhouse — name mismatch was the only issue).
- **1 manual move**: `Lake Havasu, AZ Elks Lodge #2399` → civic-community (a middle "AZ" token broke automated matching; found via `%elk%` probe, applied with a single-match guard).

### 2.5 Marine batch live — 22 providers (`approve_marine_contributions.py`)
Approved via `approve_contribution_as_provider` (the admin-form path), then set `subcategory`+`primary_category` (the approval service sets only `category`).
- **Routing combo learned:** a row appears on `/lake-havasu/{sub}` when `subcategory == slug` AND `primary_category` is in the bucket route's primary set. Marine subcats route via `on-the-water` (primaries `{on-the-water, outdoors-parks-trails}`); `category=lake_recreation` matched 8/8 existing marine rows.
- Gibbs Propeller Service description repaired ("Propeller sales/repair") — its CSV row had an unescaped comma in the Yelp URL that split at ingest.
- All four marine pages verified live.

### 2.6 Horizon duplicate resolved (first pass)
The marine-batch add `#1099` duplicated the recat-curated original `Horizon MotorSports`, whose primary was stale (`home-property-services`) so it was invisible on marine-dealers. Fix: deactivated the add, set the original's primary → `on-the-water`, marked `#1099` rejected/duplicate. marine-dealers then showed a single Horizon.

### 2.7 Non-marine high-confidence live — 39 providers (`approve_nonmarine_contributions.py`)
Generalized per-subcategory derivation: `primary = primary_for_subcategory(hint)` (taxonomy); legacy `category` = dominant existing value per subcategory (peer-consistent), with reviewed overrides for thin/mis-filed subcats (`biking→recreation`, `golf→recreation`, `rv-parks→lodging`).
- **Confidence gate:** joined to the CSV by name; approved **only** `confidence=high`. 27 med/low held.
- 39 approved across 23 subcategories; counts matched predictions; rv-parks/pets/attractions verified live.

### 2.8 Recat stale-primary fix — 11 corrections (`fix_recat_stale_primary.py`)
A read-only audit found **112** active rows where `primary_category != primary_for_subcategory(subcategory)`. Fixed **only the 11** that were recat'd this session (subcategory = curated truth) with a stale non-null primary — the cross-primary recats that left a stale routing field (Altitude Trampoline, CVS, Walgreens, London Bridge Harley, Winners Circle Storage, ShopWildThings, The Springs Dining, Reflections Steakhouse, Elks Lodge, American Legion, Quick Stop Title). Verified live.
- The other ~100 were **left untouched** — pre-existing drift, not blanket-fixable (often the *subcategory* is the wrong field, not the primary; e.g. "Movies Havasu" subcat=restaurants but correctly primary=events). Routed to chip `task_c054a318` + the targeted `recategorize_*.py` cluster scripts.

### 2.9 Med-tier adds — 18 live (`approve_nonmarine_contributions.py --confidence med`)
Added a `--confidence` flag **and a same-name dedup guard**.
- **18 med providers live.** The guard skipped **8** already-existing businesses (audit mis-flagged as missing). 1 low (Sky Shark) held.

### 2.10 ⚠️ Duplicate incident + remediation — 24 dups (`fix_add_duplicates.py`)
**Root cause / mistake:** the marine (22) and high (39) batches ran **before** the dedup guard existed, so they minted a **second** live provider for **24** businesses that already existed (D1 Performance, Savage Marine, Cypress Park, Crazy Horse, Amici Pools, …). Earlier marine/high before→after landing counts were inflated by these dups.

**Remediation (Casey-approved, after halt-and-report):**
- **Deactivated 23** of my duplicate providers + rejected their contributions. Kept mine for **Grand Island Disc Golf** (its prior was a draft / invisible).
- **Reconciled the 23 surviving originals:** 15 recat to the audit's leaf (marine shops in on-the-water/specialty/auto → marine-*; Amici → home-services; Crazy Horse + State Park Campground → rv-parks; Arizona Coast → studios; Makai → cafes-coffee), 2 stale-primary fixes (Cypress Park, Wet Monkey), 6 left as-is (already correct or kept-better: Sunset stays on-the-water, West Marine stays marine-supply).
- **Folded the dedup guard into `approve_marine_contributions.py`** (root-cause fix).
- Re-run found **0 remaining dups**; verified live. (One verify scare — "Anderson Powersports x0" — was a case-sensitive regex vs prod's "Anderson **PowerSports**"; it is listed.)

### 2.11 Queue cleanup — 9 rejections (`reject_duplicate_pending.py`)
- **8 name-duplicate** pending contributions rejected (Thai Food Restaurant, Barnet Dulaney, LH Family Eyecare, Huffman Chiropractic, Knochel Law, Havasu Community Credit Union, Havasu Realty, LH Property Management).
- **Sky Shark Hobbies** rejected (`unverifiable`): confirmed `Bass Tackle Master` is active at the same address (260 London Bridge Rd) the CSV listed — the dup risk the audit note flagged.
- **Review queue now 0 pending** operator_backfill providers.

---

## 3. Production data operations (all dry-run → approval → apply)

| Op | Script | Count |
|---|---|---|
| Subcategory recats (exact) | `apply_recategorizations.py` | 35 |
| Subcategory recats (fuzzy) | `apply_recategorizations_fuzzy.py` | 4 (+3 already-correct) |
| Elks manual recat | inline (guarded) | 1 |
| Adds → review queue | `load_candidates_to_review_queue.py` | 88 pending |
| Marine providers live | `approve_marine_contributions.py` | 22 |
| Non-marine high providers live | `approve_nonmarine_contributions.py` | 39 |
| Med providers live | `approve_nonmarine_contributions.py --confidence med` | 18 |
| Stale-primary fixes (recats) | `fix_recat_stale_primary.py` | 11 |
| Duplicate remediation | `fix_add_duplicates.py` | 23 deactivated + 15 recat + 2 primary + 1 kept |
| Horizon dedup (first) | inline (guarded) | 1 deactivate + 1 primary + 1 reject |
| Queue dedup rejections | `reject_duplicate_pending.py` + inline | 8 + 1 (Sky Shark) |

**Net live adds:** 79 created − 24 dups (23 deactivated + Horizon) = **55 live**, all correctly categorized and routed.

---

## 4. Scripts delivered (PR #350, all ruff + pytest green)

1. `scripts/apply_recategorizations.py` — exact-name subcategory recats.
2. `scripts/load_candidates_to_review_queue.py` — web-sourced candidates → pending contributions.
3. `scripts/apply_recategorizations_fuzzy.py` — fuzzy resolver for unmatched recats.
4. `scripts/approve_marine_contributions.py` — marine batch approval (+ dedup guard).
5. `scripts/approve_nonmarine_contributions.py` — generalized approval + confidence gate + dedup guard.
6. `scripts/fix_recat_stale_primary.py` — stale `primary_category` fix for recat'd rows.
7. `scripts/fix_add_duplicates.py` — duplicate remediation.
8. `scripts/reject_duplicate_pending.py` — reject already-existing pending contributions.

Plus: `category_recategorizations_2026-06-15.csv`, `category_coverage_candidates_2026-06-15.csv`.

---

## 5. Git commits (branch `chore/category-coverage-audit-2026-06-15`)

| SHA | Summary |
|---|---|
| `2d4f1d49` | add coverage-audit loader scripts + CSVs |
| `652303ea` | add fuzzy resolver for unmatched recats |
| `f7925cf1` | marine-batch approval script |
| `eb3e15b3` | generalized non-marine approval + confidence gate |
| `ec38bc8c` | fix stale primary_category on recat'd rows |
| `e3007994` | dedup guard + med-tier adds + duplicate remediation |
| `91294df7` | reject duplicate pending contributions |

(Commits `13128148`/`54a2665b`/`96830cf2` are from a **parallel Casey session** on the same branch — a stale-primary re-audit that added then dropped scripts duplicating `fix_recat_stale_primary.py`, net-zero file change. All fast-forwarded cleanly; this session's commits remained intact and linear.)

---

## 6. Verification performed (live, against askhava.com)
- Marine: marine-repair / marine-dealers / marine-supply / on-the-water pages — new shops present incl. D1 Performance.
- Non-marine: rv-parks (0→2), pets, attractions — new businesses present.
- Stale-primary fixes: CVS/Walgreens on health-medical, Quick Stop on professional, American Legion on civic-community.
- Dedup remediation: re-run found 0 remaining dups; rv-parks/home-services/marine-repair/marine-dealers show single, correctly-listed records.

---

## 7. Remaining follow-ups (not done — by design)
1. **~100 pre-existing drift rows** (`primary != primary_for_subcategory(subcategory)`): **must not** be blanket-fixed — a blanket primary reset would corrupt ~75 (the subcategory is often the wrong field). Handled by chip `task_c054a318` + the targeted `recategorize_*.py` cluster scripts.
2. **Pre-existing name-variant dup** (not created this session): `Anderson Powersports Lake Havasu` (specialty) vs `Anderson PowerSports` (marine-dealers).
3. **PR #350**: 8 scripts + 2 CSVs, unmerged — awaiting review/merge.

---

## 8. Notes & lessons
- **Mistake owned:** approving adds without a dedup guard created 24 duplicate live providers; caught when the guard was later added, halted, reported, and fully remediated. Root cause fixed (guard now in both approval scripts).
- **Routing model:** `/lake-havasu/{sub}` pages filter `Provider.subcategory == slug` AND require `primary_category` in the bucket route's primaries. Recats that set `subcategory` but not `primary_category` mis-route (the Horizon/CVS class of bug).
- **Concurrency:** a parallel session was active on this checkout/branch (the repo's "one session per directory" hazard). It resolved cleanly here, but worth ensuring a single session drives this checkout.
- **Process:** every prod write was dry-run-gated and Casey-approved; verification used the same `route_provider_filter` + subcategory facet the live pages use, then confirmed on askhava.com.
