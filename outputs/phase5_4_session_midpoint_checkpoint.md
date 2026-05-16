# Phase 5.4 — Health, Wellness & Care — Mid-session checkpoint (2026-05-16)

> **What this is:** a hand-off doc for the next Cowork primary agent to
> pick up Phase 5.4 at gates §4 + §5. The current session shipped
> §0–§3 (4 of 6 gate items cleared) across 10 commits but is being
> checkpoint'd here rather than pushed through — the remaining work is
> operator-curation-heavy (`crowd_notes` drafting + `heat_exposure`
> mechanical sweep with `OUTDOOR_OVERRIDES`) and benefits from a fresh
> context window.
>
> **Mirrors** `outputs/phase5_3_session_closeout.md` shape (the doc
> that primed this session) but for a mid-flight checkpoint rather
> than a SHIPPED close-out.
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.4 session
> (2026-05-16) post-`58bc580`. Hand-off to the next session.

---

## §1 Commit chain this session (`ef23456 → 58bc580`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `8d37b86` | `fix(tests)` — az_roc_verify google_primary_category | Cowork | red CI fix |
| 2 | `e6eceae` | `chore(outputs)` — Phase 6 Amendment 3 dispatch artifact | Cowork | parallel-dispatch prep |
| 3 | `eb8f74b` | `docs(phase5)` — Phase 5.3 SHIPPED ledger entries (Amendment 3) | Claude Code | parallel |
| 4 | `b683ad7` | `fix(scripts)` — places_load filter_by_zip ZIP+4 normalization | Cowork | dispatch fix |
| 5 | `fc51940` | `fix(scripts)` — _DISCOVERY_DOMAIN_FALLBACK extends for health_medical + fitness_sports | Cowork | sustainability |
| 6 | `0cf7f1d` | `fix(tests)` — ruff I001 auto-format on Phase 5.4 fallback regression file | Cowork | red CI follow-up |
| 7 | `f92ff53` | `chore(outputs)` — Phase 5.4 §2 audit -- ambig-queue review + diagnostic + logs | Cowork | gate-2 |
| 8 | `fbdd002` | `fix(scripts)` — npi_verify processor=utils.default_process (rapidfuzz 3.x case-fix) | Cowork | dispatch fix |
| 9 | `700fa3f` | `fix(scripts)` — npi_verify token_set_ratio → token_sort_ratio (subset false-positive fix) | Cowork | dispatch fix |
| 10 | `58bc580` | `fix(tests)` — npi_verify case-mismatch test uses realistic NPI name shape | Cowork | post-fix test repair |

**Pytest baseline:** 1882 collected (pre-session) → **1909 collected post-session** (+27). Breakdown: 6 new in `tests/test_places_load.py` (ZIP+4 fix #4), 18 new in `tests/test_phase5_4_places_load_resolver.py` (fallback fix #5; parametrized over 11+7 keys × 2 assertions ≈ 18 named tests + 2 defensive = 20), 3 new in `tests/test_phase5_npi_verify.py` (case-fix + subset + informational, #8/#9/#10).

**Ruff:** green on `58bc580` and back through `b683ad7`. Two ruff-related red CIs cleared this session: `25966278375` (X on lint pre-`bff4a79`) and `25968308220` (X on I001 in the new fallback test — cleared at `0cf7f1d`).

**CI:** ✅ Green on `58bc580` (run `25969687662`, 1m43s). One sibling workflow `parks-rec-scrapes` is X on its scheduled cron triggers — **not in Phase 5.4 scope** and likely a pre-existing condition (missing repo secret or path issue). Soft-edge for Phase 5.5+.

---

## §2 Phase 5.4 acceptance gate — 4 of 6 CLEARED ✅

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 80+ entries in `health-wellness-care` post-load | ✅ **265** | Layer 1 (282 inserted, 114 ambig-skipped) + fallback re-load filled the 111-row operator queue |
| 2 | All Google ↔ existing-entity ambiguous reconciler hits reviewed | ✅ **114 reviewed** | `outputs/phase5_4_health_wellness_pre_load_audit.md` §1-5 — no misroutes; medical-plaza false-ambig pattern documented |
| 3 | NPI verification run completed for licensed sub-trades | ✅ **85 verified** | `python -m scripts.npi_verify` against 265 → 85 matched at threshold 86 (32% rate, all top-15 score=100). Concentrated in doctor/dentist/chiropractor/medical_clinic/health categories |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ⏭ **pending** | §3 below — operator drafts from `google_review_snippets`; mirror `outputs/apply_phase5_3_home_property_crowd_notes.py` |
| 5 | `heat_exposure` non-NULL on every entry | ⏭ **pending** | §4 below — mechanical sweep (mostly `indoor`) + `OUTDOOR_OVERRIDES` for pools/courts; mirror `outputs/apply_phase5_3_home_property_heat_exposure.py` |
| 6 | `/category/health-wellness-care` renders ≥15 | ✅ **265** | Trivially met at gate-1 count |

---

## §3 Remaining work — §4 `crowd_notes` for top-10

**Acceptance:** top-10 by `google_review_count` (descending) in
`health-wellness-care` have long-form `crowd_notes` populated under the
locked `{"short": str, "long"?: str}` JSON shape.

**Approach (mirrors 5.3 pattern at `outputs/apply_phase5_3_home_property_crowd_notes.py`):**

1. Identify top-10 via SQL:

   ```sql
   SELECT p.id, p.provider_name, p.google_review_count,
          json_extract(p.attributes, '$.google_review_snippets') AS snippets
   FROM providers p
   JOIN entity_categories ec ON ec.entity_id = p.entity_id
   JOIN categories c ON c.id = ec.category_id
   WHERE c.slug='health-wellness-care'
   ORDER BY p.google_review_count DESC NULLS LAST
   LIMIT 10
   ```

2. For each, draft a 1-2 sentence `long` form synthesizing what review
   snippets emphasize — for doctors: bedside manner, wait times, specific
   provider names (Dr. X, NP Y), scheduling availability. For fitness:
   class quality, instructor names, equipment age, locker room.

3. Write `outputs/apply_phase5_4_health_wellness_crowd_notes.py` mirroring
   the 5.3 apply-script exactly. **CRITICAL gotcha** from 5.3's `f35d5e4`:
   `Entity.crowd_notes` is a JSON-typed SQLAlchemy column. **Pass the
   dict directly to `.crowd_notes = {...}`; do NOT `json.dumps()` first.**
   The 5.3 close-out §3 has the full bug write-up.

4. Verify via SQL after the real run:

   ```sql
   SELECT COUNT(*) FROM entities e
   JOIN entity_categories ec ON ec.entity_id = e.id
   JOIN categories c ON c.id = ec.category_id
   WHERE c.slug='health-wellness-care'
     AND json_extract(e.crowd_notes, '$.long') IS NOT NULL
   -- expect: 10
   ```

5. Lint guard: when the apply-script lands, audit imports for F401
   (the bug at `bff4a79` was unused `json` + `Category` imports — see
   5.3 close-out §3 for the pattern). `# noqa: E402` silences E402 only,
   not F401.

**Time estimate:** ~30-45 min including the operator deciding what each
long-form blurb says.

---

## §4 Remaining work — §5 `heat_exposure` mechanical sweep

**Acceptance:** every entry in `health-wellness-care` has non-NULL
`heat_exposure`. Indoor for essentially all medical/dental/fitness
venues; outdoor for the handful of outdoor pools / tennis / pickleball
courts.

**Approach (mirrors 5.3 pattern at `outputs/apply_phase5_3_home_property_heat_exposure.py`):**

1. Identify outdoor candidates by `google_primary_category`:

   ```sql
   SELECT p.id, p.provider_name, p.google_primary_category
   FROM providers p
   JOIN entity_categories ec ON ec.entity_id = p.entity_id
   JOIN categories c ON c.id = ec.category_id
   WHERE c.slug='health-wellness-care'
     AND p.google_primary_category IN ('tennis_court', 'athletic_field', 'swimming_pool')
   ORDER BY p.provider_name
   ```

   Likely 3-8 rows. Operator may add a few by name (outdoor public
   pickleball / Sara Park tennis / etc.).

2. Write `outputs/apply_phase5_4_health_wellness_heat_exposure.py`. Set
   all `health-wellness-care` entities to `heat_exposure='indoor'`,
   except those in an `OUTDOOR_OVERRIDES: dict[entity_id_prefix, str]`
   set to `'outdoor'`.

3. Per kickoff §4: `boat_access` stays NULL for all health entries
   (n/a for inland health venues).

4. Verify all 265 entries land non-NULL.

**Time estimate:** ~15-20 min. Mostly mechanical with a small operator
decision on which outdoor venues to override.

---

## §5 Phase 5.4 ship sequence (when both §4 + §5 close)

Mirror the 5.3 pattern at `805a38c`:

1. `outputs/phase5_4_gate_verification.py` — runnable script printing the
   6-item gate scorecard with "ALL 6 ITEMS CLEARED — READY TO SHIP" line.
   Mirror `outputs/phase5_3_gate_verification.py` exactly.

2. `docs/scrape_logs/health-wellness-care_2026-05-16.md` — single-layer
   Google Places scrape log. Pre-populated facts to drop in (from this
   session):
   - 28 labels (17 health_medical + 11 fitness_sports), 45 requests,
     387 unique places, $1.44 spend, 63s wall
   - Enrichment: 387 input / 16 new / 371 cache hits / $0.27 spend / 8.5s
   - Load: 396 ZIP-filtered / 282 inserted / 114 ambig-skipped / 265 final
     after fallback re-load
   - NPI: 85 verified / 32% match rate / threshold 86 token_sort_ratio

3. Phase 6 lane dispatch for Phase 5.4 SHIPPED ledger amendment (same
   shape as `outputs/claude_code_dispatch_phase6_amend3.md` did for
   Phase 5.3). Adds a new SHIPPED bullet to `docs/STATE.md` + a SHIPPED
   line under `docs/maintainability/master_build_plan.md` §4 Phase 5.4.

4. SHIPPED commit: `chore(outputs): Phase 5.4 SHIPPED -- all 6 gate items cleared`

5. Likely a `bff4a79`-style lint follow-up (audit imports of the apply-
   scripts before the SHIPPED commit lands).

---

## §6 Notable surgical fixes shipped this session

Five fixes mid-session — matches 5.3 pattern (3 fixes) on volume:

### `8d37b86` — AZ ROC test fix (red CI unblock)

Pytest had been red across the entire Phase 5.3 commit chain
(`b71cf0e`/`81cd70c`/`f0a46f8`/`805a38c`/`bff4a79`/`ef23456`) due to
`tests/test_phase5_az_roc_verify.py::test_az_roc_verify_marks_provider_and_name_cache`
returning 0 matches instead of 3. Cursor's regression test at `6ef5ea8`
built Provider fixtures without `google_primary_category`, but the
post-`420f893` AZ ROC verifier filters by
`google_primary_category ∈ AZ_ROC_LICENSED_PRIMARY_TYPES`. Test fixtures
were excluded. Fix: set `google_primary_category="plumber"` on all 3
fixture Providers.

### `b683ad7` — ZIP+4 false-drop in `filter_by_zip`

Phase 5.4 load dry-run surfaced 3 LHC ZIP+4 codes (`864035889`,
`864036710`, `864035647`) being dropped as non-LHC because the filter
did exact string match against `LHC_ZIPS = {"86403", "86404", "86405", "86406"}`.
Google sometimes returns ZIP+4 with the dash stripped. Fix: normalize
via `str(zip).replace('-','')[:5]` before membership check. +6
regression tests in `tests/test_places_load.py`.

### `fc51940` — `_DISCOVERY_DOMAIN_FALLBACK` extension

Phase 5.4 §1 load surfaced 111 of 282 inserts at `category_id=None`,
dominated by `('health_medical', 'health')` ×47 and
`('health_medical', 'medical_clinic')` ×36 catch-all primary_types.
Added 18 new entries to `_DISCOVERY_DOMAIN_FALLBACK` (11 health_medical
+ 7 fitness_sports). Re-run load cleared the operator queue to 0. +20
regression tests in `tests/test_phase5_4_places_load_resolver.py`.
Soft-edge: `medical_clinic` + `dental_clinic` arguably belong in
`google_types_mapping.py` directly — left in fallback for the
surgical-fix shape.

### `fbdd002` + `700fa3f` — NPI rapidfuzz dual fix

Phase 5.4 §3 first dry-run returned 0/20 matches. Two distinct bugs:

**Fix #1 (`fbdd002`):** rapidfuzz 3.x removed default preprocessing.
`fuzz.token_set_ratio(a, b)` without `processor=` is case-sensitive +
punctuation-sensitive. "Acacia" vs "ACACIA" scored 25 instead of 95.
The `MATCH_THRESHOLD=86` was tuned for rapidfuzz 2.x default behavior.
Fix: `processor=utils.default_process`.

**Fix #2 (`700fa3f`):** post-#1 the match rate jumped 0/25 → 13/25 but 3
were false positives via `token_set_ratio`'s documented "subset" trap.
'LAKE HAVASU CITY' (3-token NPI org) scored 100 against every health
provider containing those 3 tokens. Switched to `token_sort_ratio`
which preserves token counts and aligns with the original kickoff §3
spec ("token-sort similarity"). Final landscape: 8/25 diagnostic
samples → 85/265 actual matches at score 86+.

### `58bc580` — NPI case-mismatch test repair

The `test_npi_verify_handles_case_mismatch` regression test added in
`fbdd002` used a too-short NPI variant (`'ACACIA FAMILY PRACTICE GROUP, LLC'`)
that broke with `token_sort_ratio` (length penalty). Fix: use the
realistic LHC NPI shape (`'ACACIA FAMILY PRACTICE GROUP OF LAKE HAVASU, INC'`,
NPI=1295469641) which scores 90 in the live diagnostic.

---

## §7 Sustainability layer (updated)

`_DISCOVERY_DOMAIN_FALLBACK` extended for both `health_medical` and
`fitness_sports` domains — 18 new entries beyond the 5.3 set. All future
Phase-5.4-style re-pulls will auto-categorize the same shape.

### Sustainability matrix (updated)

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| `verified` + `attributes.npi_number` (5.4-specific) | ✅ not overwritten by re-pull | ❌ needs re-run of `npi_verify` |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |

**Phase 5.5 (Auto, RV & Fuel)** anticipated catch-all primary_types
(per kickoff §5): `('auto_rv_fuel', 'car_dealer')`, `('auto_rv_fuel', 'service')`,
etc. Likely some 5.5-specific verifier surface (no equivalent of NPI;
auto industry doesn't have a single national licensing API like AZ ROC
covers).

---

## §8 Operator carry-forwards (action items)

- **Phase 6 lane — Phase 5.4 SHIPPED ledger amendment** — dispatch
  artifact deferred until §4+§5 close. Will mirror the
  `outputs/claude_code_dispatch_phase6_amend3.md` shape (which itself
  shipped at `eb8f74b` this session).
- **`parks-rec-scrapes` scheduled CI workflow** — X on cron runs
  throughout this session and likely pre-existing. Not in Phase 5.4
  scope. Operator/Phase 5.5+ to investigate.
- **Google Places API key** — operator declined rotation mid-session
  ("all keys will be changed at the conclusion of this project").
  Confirmed acceptable risk for the remaining Phase 5.x budget.
- **86 of 265 health-wellness-care providers remain `verified=False`** —
  no NPI match found. Mostly DBA-only practices that aren't registered
  as individual NPIs under that exact name. Kickoff §3 anticipated this
  and noted a follow-up DBA→NPI manual mapping surface. Not gate-blocking.
- **Phase 5.4 §2 audit soft-edges (3 deferred)** —
  `outputs/phase5_4_health_wellness_pre_load_audit.md` §5 documents:
  optional force-insert apply-script for 87 cross-category candidates;
  optional `GEO_PROXIMITY_THRESHOLD_M` tune (50 → 25); optional
  same-discovery-domain bypass in reconciler. None gate-blocking.

---

## §9 Read order for the next session

1. **This document** — the state of play (mid-session checkpoint).
2. `outputs/phase5_3_session_closeout.md` — Phase 5.3 close-out for the
   apply-script + audit + sustainability layer playbooks 5.4 §4+§5
   reuse verbatim.
3. `outputs/phase5_4_health_wellness_care_kickoff.md` §4 + §5 — the
   original §4 (`crowd_notes`) + §5 (`heat_exposure`) rubric for 5.4.
4. `outputs/phase5_4_health_wellness_pre_load_audit.md` — §2 audit
   findings (the medical-plaza false-ambig pattern).
5. `outputs/apply_phase5_3_home_property_crowd_notes.py` — template for
   the equivalent 5.4 apply-script. **Watch the JSON-column gotcha**
   per close-out §3 (`f35d5e4`).
6. `outputs/apply_phase5_3_home_property_heat_exposure.py` — template
   for the equivalent 5.4 apply-script.
7. `outputs/phase5_3_gate_verification.py` — template for
   `outputs/phase5_4_gate_verification.py`.
8. `docs/scrape_logs/home-property-services_2026-05-15.md` — template
   for `docs/scrape_logs/health-wellness-care_2026-05-16.md`.

---

## §10 Pre-flight for the next session

1. **`git log --oneline -12`** — origin top should be `58bc580` or
   later. Local in sync.
2. **`git status`** — clean.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across
   all 5.x phases).
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — expect
   **1909 collected** (1882 baseline + 27 new from §1-§3 fixes).
5. **`gh run list --branch main --limit 3`** — top run should be ✓ on
   `58bc580` (run `25969687662`). Note that `parks-rec-scrapes`
   scheduled jobs may show X — out of scope.
6. **DB state spot-check** — `health-wellness-care` should show
   **265 entries / 85 verified** in `entity_categories` + provider
   verified-flag query.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.4 session
(2026-05-16) post-`58bc580`. 10 commits shipped on `origin/main` since
`ef23456`. 4 of 6 gate items cleared. Hand-off to next session for
gates §4 + §5 + SHIPPED commit + Phase 6 ledger amendment.*
