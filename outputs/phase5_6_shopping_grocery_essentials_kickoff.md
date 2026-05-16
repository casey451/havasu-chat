# Phase 5.6 Kickoff — Shopping, Grocery & Essentials (`shopping-essentials`)

> **What this is:** a single paste-and-go operator runbook for Phase 5.6,
> the sixth Tier 1 category. Mirrors
> `outputs/phase5_5_auto_rv_fuel_kickoff.md` shape with 5.6-specific
> overrides. **Single-layer scrape** (Google only — OSM scope is locked
> to on-the-water per brief §3.2.e).
>
> **GATE 1 — do not start until Phase 5.5 has closed** its acceptance
> gate (`outputs/phase5_5_gate_verification.py` outputs `ALL 7 ITEMS
> CLEARED`). Per brief §3.2.d, categories run one at a time.
> ✅ **Met at `08d5ff3` (Phase 5.5 SHIPPED), close-out doc co-committed in
> the same SHIPPED commit.**
>
> **GATE 2 — no pre-built verifier surface for 5.6** (no obvious public
> registry for retail businesses; the AZ retail-sales tax license is not
> exposed via a free API). Phase 5.6 will most likely repeat 5.5's
> Option C path (defer Layer-4 verifier to V1.5). This kickoff §3
> documents the build-or-defer choice.
>
> **GATE 3 — pre-flight integrity gotcha:** the
> `scripts/places_categories.json` file has been observed to drift
> locally (working tree 202 lines vs HEAD 211 lines, ends mid-token
> `"chil`) — twice in the 5.5 session alone. Cause unknown (suspect an
> external editor). The §0 pre-flight MUST verify this file is clean
> before §1 dispatch; restore via `git restore
> scripts/places_categories.json` if drifted.
>
> **Authored by:** Cowork primary, Phase 5 lane, end of Phase 5.5
> session (2026-05-16) post-`08d5ff3`. Hand-off to the next session.

---

## §0 Pre-flight (do once, at Phase 5.6 dispatch)

1. **`git log --oneline -15`** — origin should top at `08d5ff3` (Phase
   5.5 SHIPPED) or later if Phase 6 lane has shipped Amendment 5
   between sessions (in-line a la `0addb63` for 5.4 OR via Claude Code
   parallel dispatch).
2. **`git status`** — clean. **Sandbox bash note:** `git status` hits
   the index-format gotcha (`fatal: unknown index entry format
   0xffff0000`); run Windows-side via PowerShell. Carry-over untracked
   from 5.5: `hava_api_catalog.docx` + `~$va_api_catalog.docx` Word
   lock + 2 historical `outputs/ci_*_log_failed.txt` files — all
   unrelated to lane; operator prunes when comfortable.
3. **`python -m alembic current`** — confirm local `data/events.db` at
   `0a1b2c3d4e5f`. If behind, `python -m alembic upgrade head`. (No
   migrations expected on the 5.6 lane.)
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — record
   baseline. Phase 5.5 closed at **1920 collected** (5.4 baseline 1909
   + 2 drift accepted as 1911 + 9 in-lane regression guards for the
   `4d41944` fallback extension = 1920). Verify no drift.
5. **`python outputs/diagnose_category_id_gap.py`** — confirm Phase
   5.1, 5.2, 5.3, 5.4, and 5.5 categorization is intact and the
   `shopping-essentials` slug exists in the `categories` table.
6. **🚨 `git diff scripts/places_categories.json`** — MUST be empty.
   If the working tree shows a smaller file than HEAD (e.g., 202 vs
   211 lines, ending mid-token `"chil`), restore via `git restore
   scripts/places_categories.json` before §1. This corruption recurred
   twice in the 5.5 session; cause unknown but easily restorable.
7. **Google Places key + spend cap** — operator has deferred rotation
   until project end; still in `.env`, still capped. No mid-session
   rotation needed unless the operator opts in.
8. **CI state** — check GitHub Actions on the top commit. Should be
   ✅ green. If red, investigate before starting 5.6
   (`outputs/claude_code_dispatch_red_ci_investigation.md` pattern).
9. **DB state spot-check** — `auto-rv-fuel` should show **140 entries
   / 131 indoor + 9 outdoor / 126 False + 14 True is_mobile_service /
   10 long-form crowd_notes** (the 5.5 SHIPPED state).

---

## §1 The scrape sequence — Google only

Phase 5.6 is **single-layer** (no OSM; OSM scope is locked to
on-the-water only per brief §3.2.e). Layer 1 Google Places handles
the discovery. **Larger sweep than 5.5** — 23 labels in the `retail`
discovery domain per `app/contrib/google_places_scraper.py:85`
(`"shopping-essentials": frozenset({"retail"})`).

### Layer 1 — Google Places

```
python -m scripts.places_discovery --category shopping-essentials --dry-run
python -m scripts.places_discovery --category shopping-essentials
python -m scripts.places_enrichment --limit 600
python -m scripts.places_load --category shopping-essentials --dry-run
python -m scripts.places_load --category shopping-essentials
```

**Why `--limit 600` on enrichment?** 23 labels × ~30 per label ≈ 690
raw hits; the cumulative enrichment cache (5.0/5.1/5.2/5.3/5.4/5.5)
is already large enough (2618 records post-5.5) that most of those
will cache-hit. Expected new enrichments: ~30-60 (slightly more than
5.5's 23 because retail has less overlap with the prior auto + marine
+ home-services + medical sets).

The 23 discovery labels (from `scripts/places_categories.json` lines
67-89, all `domain: "retail"`):

| Bucket | Labels |
|---|---|
| **Groceries & essentials** (5) | grocery stores, supermarkets, convenience stores, liquor stores, pharmacies |
| **Apparel & accessories** (5) | clothing stores, thrift stores, consignment stores, shoe stores, jewelry stores |
| **Home & garden** (4) | furniture stores, home decor stores, hardware stores, garden centers |
| **Books, gifts, hobbies** (5) | bookstores, gift shops, florists, sporting goods stores, outdoor gear stores |
| **Specialty retail** (4) | electronics stores, music stores, toy stores, smoke shops |

**Volume projection** (estimate based on retail mix in a town the size
of LHC):

| Stage | Expected |
|---|---|
| Discovery requests | ~50-69 (23 × 2-3 pages; smaller specialty labels likely 1-page) |
| Discovery cost | ~$1.60-$2.20 |
| Unique places (raw) | ~300-500 |
| After ZIP filter | ~200-400 |
| Inserts (new) | ~100-250 |
| Ambig-skips | ~30-100 |
| Enrichment cost | ~$0.70-1.50 (most cache-hits) |
| **Total Layer 1 cost** | **~$2.50-4.00** |

**Sustainability layer extension expected.** The `retail` domain will
likely surface catch-all primary_types — `store` definitely (Google's
generic retail tag), possibly `point_of_interest`, `establishment`,
`supplier`, and `None`. Anticipated entries to add to
`_DISCOVERY_DOMAIN_FALLBACK` in `scripts/places_load.py` after Layer
1 surfaces specific gaps:

```python
# Anticipated 5.6 fallback entries (extend after Layer 1 surfaces specific gaps)
(None, "retail"): "shopping-essentials",
("store", "retail"): "shopping-essentials",
("point_of_interest", "retail"): "shopping-essentials",
("establishment", "retail"): "shopping-essentials",
("supplier", "retail"): "shopping-essentials",
```

Mirror the `7c994aa` (5.3) / `fc51940` (5.4) / `4d41944` (5.5)
surgical-fix shape exactly. +regression tests in
`tests/test_phase5_6_places_load_resolver.py`.

### Layer 5 — Manual recovery (deferred to operator)

Per `docs/maintainability/manual_recovery_checklist.md`. Surface for
5.6:

- LHC chamber of commerce specialty retailers not on Google
- Boutique / pop-up retailers without Google listings
- Farmer's market vendors (LHC Farmer's Market on McCulloch may have
  vendors without standalone listings)
- Specialty grocery (ethnic, organic, halal) sometimes underindexed

Not gate-blocking for V1 ship.

---

## §2 Ambiguous-queue review — expect moderate volume + cross-category overlaps

Shopping is the **sixth non-empty-DB load** (after 5.1+5.2+5.3+5.4+5.5).
Reconciler will match against **1,041 existing entities** (287
eat-drink + 119 on-the-water + 230 home-property-services + 265
health-wellness-care + 140 auto-rv-fuel). Expected ambiguous hits:
**30-100 per run** (range covers both light strip-mall density and
heavy — retail clusters on McCulloch Blvd / Lake Havasu Ave will
produce strip-mall false-ambigs similar to 5.4 medical-plaza + 5.5
auto-industrial pattern).

**Special audit categories expected for 5.6:**

| Existing entity | 5.6 candidate it'll likely match | V1 policy |
|---|---|---|
| Gas station + convenience store (in cat-9) | grocery / convenience candidate (in cat-8) | likely **stay in cat-9** (primary use is fuel-purchase + impulse-snack) unless the convenience store is clearly the primary draw |
| Restaurant + market (in cat-1) | grocery / specialty-food (in cat-8) | likely **stay in cat-1** if the food-service is primary; flip to cat-8 if it's a market with prepared-food bar |
| Auto parts store (in cat-9) | hardware / sporting goods (in cat-8) | edge case — auto parts is a retail surface but already in cat-9 from 5.5 |
| Boat-related retail (in cat-6) | sporting goods / outdoor gear (in cat-8) | likely **stay in cat-6** if marine-specific; flip if generic outdoor |

Mirror the 5.5 audit pattern: post-load audit pulls cross-category +
same-category, and an apply-script batches the misroute decisions if
any. **Expected outcome based on 5.4 + 5.5 history: 0 real misroutes,
all reviewed-and-cleared as benign strip-mall adjacency.**

If a single load produces **>100** ambiguous hits, consider tuning
`GEO_PROXIMITY_THRESHOLD_M` (currently `50.0`) per brief §4.g — but
prior phases have all stayed under the tune threshold despite
exceeding 50.

---

## §3 Layer-4 verifier surface — likely Option C deferred

**5.6 has no pre-built verifier** (unlike 5.3's `az_roc_verify` and
5.4's `npi_verify`). Three options for gate item 3, mirroring 5.5's
shape:

### Option A — AZ retail-sales tax license lookup (Playwright)

URL: `https://azdor.gov/business/transaction-privilege-tax-tpt`. The
AZ TPT (Transaction Privilege Tax) license is required for any
retailer; the AZDOR public search exposes business name + license
number + status. Playwright build:

- `scripts/az_tpt_verify.py` — mirrors `az_roc_verify` (5.3) pattern.
- Sub-trade allowlist: all retail primary types (`store`,
  `clothing_store`, `grocery_or_supermarket`, `convenience_store`,
  `liquor_store`, `pharmacy`, etc.).
- 15s no-results timeout per row.
- Sets `Provider.verified=True`,
  `verification_method='az_tpt'`,
  `attributes.az_tpt={'license_number': str, 'status': str}`.
- Expected match rate: high — TPT is mandatory for any retail business
  in AZ (so ~85-95% verified).

**Cost-of-build:** ~3-5 hours (AZ TPT search UI is more complex than
AZ ROC). Recommended only if operator wants gate-3 to mirror 5.3 +
5.4's "verification run completed" phrasing.

### Option B — BBB (Better Business Bureau) cross-reference (light)

BBB exposes business reputation + accreditation. Cross-reference
against `https://www.bbb.org/local-bbb/bbb-of-southern-arizona`. Sets
`Provider.attributes.bbb={'rating': str, 'accredited': bool}`.
Narrower coverage (~20-50% of retail), more reputational than
license-verification.

### Option C — Defer verifier surface to V1.5

Gate item 3 rephrased to **"Layer-4 verifier surface scoped — built
or explicitly deferred to V1.5"**. Document the AZ TPT + BBB paths in
this kickoff and ship 5.6 without verifier surface. Lowest-friction
shape; mirrors 5.5's outcome.

**Recommended:** Option C unless the operator has strong "verify
everything" preference. Same rationale as 5.5: retail-license
verification is lower-stakes for a directory-discovery V1; consumer
discovery doesn't need an AZ TPT badge to be useful.

---

## §4 Operator-curated field entry — Shopping rubric

Lighter operator surface than 5.5 (no `is_mobile_service` to curate —
retail is brick-and-mortar by definition); roughly on par with 5.3/5.4
shape:

- **`heat_exposure`** — `indoor` for nearly all retail (stores,
  malls, pharmacies, specialty shops). Exceptions: **garden centers**
  (outdoor plant lots), **farmer's market** stalls (if surfaced),
  **outdoor flower stands** (florists with outdoor displays). Mirror
  `outputs/apply_phase5_5_auto_rv_fuel_heat_exposure.py` exactly;
  populate `OUTDOOR_OVERRIDES` for the 2-8 garden-center / outdoor
  market entities.
- **`crowd_notes`** — short-form for typical entries; long-form for
  the top-10 by review count. Retail reviewer signals tend to be:
  staff names (clerks, managers — common in pharmacies and specialty
  stores), price competitiveness, selection breadth, store layout,
  parking availability (Walmart/Target/Walgreens cluster), checkout
  speed, return policy experience. For grocery: produce quality,
  meat-department staff, deli/bakery specialty items. For specialty
  (sporting goods, electronics): expert staff knowledge,
  in-stock-vs-online comparison.

Drafts source: **`Provider.google_review_snippets` (own column, not
`attributes`)** — per the 5.4 close-out §4 source-path correction.
Expected snippet coverage: ~80-90% based on 5.4 (70.6%) and 5.5
(85%) curves; retail reviews are abundant.

**`is_mobile_service`** is NOT a gate item for 5.6 (no retail
business is meaningfully "mobile" — pop-up retailers are edge cases
not worth a gate). Skip the `is_mobile_service` apply-script for 5.6.

**`attributes`** JSON — can be extended with retail-specific keys
like `accepts_ebt` (bool, relevant for grocery + convenience),
`accepts_wic` (bool), `accepts_returns` (bool). Brief §3.4 has
suggested keys.

---

## §5 Daily / weekly rhythm (brief §5)

Similar cadence to 5.5:

| Day | Work |
|---|---|
| 1 | Google scrape run + scrape log (`docs/scrape_logs/shopping-essentials_<YYYY-MM-DD>.md`) + sustainability layer extension if needed |
| 2 | Ambiguous-queue triage + data-quality audit (cross-category review per §2) |
| 3 | Verifier surface decision (Option A/B/C — operator picks upfront like 5.5) |
| 4-5 | `crowd_notes` for top-10 + `heat_exposure` sweep (no `is_mobile_service` for 5.6) |
| 6 | Optional Layer 5 manual recovery (chamber-of-commerce specialty retailers) |
| 7 | QA spot-check — 10 random entries vs. the §4 rubric |

**Expected Phase 5.6 total: 8-14 hours over 1 week.** Similar to 5.5
because of the lighter operator surface (no mobile-service curation),
offset by the larger label sweep (23 vs 14) and the larger reconciler
match-against set (1,041 vs 869).

---

## §6 Acceptance gate — Phase 5.6 closes when ALL of:

- [ ] **40+ entries** in `shopping-essentials` post-load (slightly
      higher than 5.5's 30+ because retail is broader; aligned with
      master plan ledger; the existing pre-load count is 21 per
      `outputs/diagnose_category_id_gap.py` so the scrape must add
      ≥19 new entries)
- [ ] All Google ↔ existing-entity ambiguous reconciler hits reviewed
      (with cross-category review per §2 — especially gas station ↔
      convenience store on the cat-9/cat-8 axis)
- [ ] Layer-4 verifier surface scoped — **built (Option A/B) or
      explicitly deferred to V1.5 (Option C)**. If built: verification
      run completed for retail-licensed sub-trades.
- [ ] Top-10 by review count have long-form `crowd_notes`
- [ ] `heat_exposure` set on every entry (`indoor` for most, `outdoor`
      for garden centers / outdoor markets — same shape as 5.4/5.5)
- [ ] Phase 6 `/category/shopping-essentials` renders **≥15** per
      default filter

**Note: 6 gate items (not 7).** `is_mobile_service` was 5.5-specific
and is dropped for 5.6 — retail is brick-and-mortar by definition.

When the gate is met: commit the scrape log, Phase 5.6 gets its
SHIPPED ledger line on `master_build_plan.md` §4 (coordinate with
Phase 6 lane via `outputs/claude_code_dispatch_phase6_amend6.md`),
and **Phase 5.7 (Outdoors, Parks & Trails)** dispatches next.

---

## §7 Reference

- `outputs/phase5_5_session_closeout.md` (the just-shipped 5.5 state
  index — read first; carries the apply-script + audit + sustainability
  layer playbooks 5.6 reuses verbatim)
- `outputs/phase5_5_auto_rv_fuel_kickoff.md` (the 5.5 runbook this
  document mirrors)
- `outputs/phase5_5_gate_verification.py` (template for the
  equivalent 5.6 gate-verification script — note: 6 items not 7;
  no `is_mobile_service` check)
- `outputs/phase5_5_auto_rv_fuel_pre_load_audit.md` (combined pre+post
  audit template for the equivalent 5.6 audit doc)
- `docs/scrape_logs/auto-rv-fuel_2026-05-16.md` (template for the
  equivalent 5.6 scrape log)
- `app/contrib/google_types_mapping.py` (retail types — extend if new
  types surface)
- `scripts/places_load.py` (`_resolve_category_id` sustainability
  layer + 5.3 + 5.4 + 5.5 fallback extensions; extend
  `_DISCOVERY_DOMAIN_FALLBACK` for `retail` catch-alls — likely
  needed)
- `outputs/diagnose_category_id_gap.py` (re-usable diagnostic)
- `outputs/apply_phase5_5_auto_rv_fuel_heat_exposure.py` (5.5 heat
  sweep template — for 5.6 add `OUTDOOR_OVERRIDES` for garden centers
  / outdoor markets)
- `outputs/apply_phase5_5_auto_rv_fuel_crowd_notes.py` (5.5
  crowd_notes template — pass dict directly to JSON column per 5.3
  `f35d5e4` gotcha, F401-clean imports per 5.3 `bff4a79` lesson)
- `outputs/phase5_5_ambig_audit_dump.py` (5.5 ambig audit dump
  script — direct copy with paths/slug swap for 5.6)

---

## §8 Hand-off context from the Phase 5.5 session

**Important context that's NOT in this kickoff but the new agent
should read in the 5.5 close-out:**

- 3-4-commit chain from `7c96ec9` → `08d5ff3` with 1 surgical fix
  shipped mid-session (`4d41944` `_DISCOVERY_DOMAIN_FALLBACK`
  extension for `auto` domain). No NPI/AZ-ROC-style verifier
  build because operator picked Option C (defer).
- **5.5 §0 pre-flight surfaced `scripts/places_categories.json`
  corruption** (working tree 202 lines / HEAD 211 lines, ends
  mid-token `"chil`). Restored via `git restore`. **Recurred at the
  end of 5.5 session** during 5.6 kickoff authoring. Cause unknown
  (suspect external editor). The §0 pre-flight item #6 above
  documents the required check.
- **5.3 `f35d5e4` JSON-column gotcha was avoided in 5.4 + 5.5** by
  passing dict directly to `Entity.crowd_notes` — no `json.dumps()`.
  Internalize.
- **5.3 `bff4a79` F401 footgun:** `# noqa: E402` silences E402 only.
  Audit apply-script imports for unused `json` / `Category` /
  `EntityCategory` before committing. Both 5.4 and 5.5 avoided this
  by pre-commit ruff check Windows-side.
- **Sandbox bash git-index gotchas** — use `git rev-parse` / `git
  show HEAD:` for index-free reads. Operator runs index-dependent
  ops Windows-side via PowerShell.
- **Sandbox bash MOUNT-STALENESS gotcha** (new in 5.5): after a Read
  tool Edit, sandbox `wc -l` / `tail` may serve a stale view of the
  file for several seconds. The Read tool is authoritative; never
  trust sandbox bash file-shape queries for post-Edit verification.
  The 5.5 session had a false-alarm where a properly-applied Edit
  appeared to truncate the file from 601 to 199 lines per bash but
  was actually fine per Read tool.
- **DB-write apply-scripts:** stop the FastAPI dev server if running
  (events.db lock).
- **`Provider.google_review_snippets` is its OWN COLUMN** — not
  inside `attributes` JSON. The 5.4 close-out §4 documented this
  correction; drafts for top-10 long-form `crowd_notes` source from
  this column. 187/265 5.4 providers had non-empty snippets; 119/140
  5.5 providers had non-empty snippets; expect similar coverage
  (~80-90%) for 5.6.
- **PowerShell `git commit -m "" ...` footgun:** empty `-m ""`
  between multiple `-m "..."` flags is treated as a pathspec by some
  shells. Use multiple `-m "..."` flags WITHOUT empty separators; git
  inserts blank lines between them automatically.
- **CI can be flaky on intermediate commits** — 5.5 `6fb74ac` (audit
  + apply-scripts commit) initially showed X red but a rerun went
  green; root cause was transient (gh run view --log-failed returned
  empty, suggesting runner-orchestration not code). If a single
  intermediate commit is red on CI, try `gh run rerun <ID>` before
  shipping a fix commit.

**Carry-forwards from the 5.5 session** the new agent should action:

- 🚨 **Phase 6 lane — Phase 5.5 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend5.md` is ready (operator
  may have already landed in-line per 5.4 `0addb63` precedent OR
  dispatched to Claude Code parallel agent — check `git log` for
  Amendment 5 commit).
- **V1.5 Layer-4 verifier surface for 5.5** — AZ MVD Dealer Locator
  (Playwright) + AZCC towing carrier (REST) paths documented in
  `outputs/phase5_5_auto_rv_fuel_pre_load_audit.md` §3 carry-forward
  + kickoff §3 for V1.5 pickup.
- **86 of 265 HWC providers remain `verified=False`** — carry-over
  from 5.4. Operator-driven DBA→NPI follow-up surface (optional
  V1.5).
- **Operator: prune `data/events.db.bak-*` files** when comfortable
  — carry-over from 5.3 + 5.4 + 5.5.
- **`parks-rec-scrapes` scheduled CI** — X on cron throughout 5.3 +
  5.4 + 5.5. Likely pre-existing. **Phase 5.7 (Outdoors, Parks &
  Trails) will likely surface this** — that scheduled workflow may
  be directly relevant to 5.7's scope.
- **Google Places API key rotation** — deferred per operator ("all
  keys will be changed at conclusion of this project").
- **`outputs/phase5_5_load_real.log` `.gitignore` exclusion** — the
  PowerShell Tee'd log was excluded by `.gitignore` and not
  committed; audit-trail-completeness gap vs 5.4 but the structured
  JSON (`phase5_5_ambig_audit_data.json`) DID land. `git add -f` if
  full parity wanted; otherwise benign.

---

*Authored by Cowork primary, Phase 5 lane, end of Phase 5.5 session
(2026-05-16) post-`08d5ff3`. Hand-off artifact only — Cowork primary
for the next session picks up at §0 pre-flight after reading
`outputs/phase5_5_session_closeout.md` first.*
