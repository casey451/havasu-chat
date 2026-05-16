# Phase 5.4 — Health, Wellness & Care — Session close-out (2026-05-16)

> **What this is:** the close-out for the session that picked up Phase 5.4
> at `ef23456` (Phase 5.3 close-out + Phase 5.4 kickoff hand-off) and
> pushed 12 commits to land the data plane + **ALL 6 acceptance gate
> items**. Phase 5.4 SHIPPED at `c13dfff`.
>
> Spans two sub-sessions joined by `outputs/phase5_4_session_midpoint_checkpoint.md`
> (mid-session hand-off doc committed at `2858f8a`):
> - **Sub-session A** (pre-`2858f8a`): §1 scrape + §2 audit + §3 NPI
>   verification + 4 of 6 gate items cleared.
> - **Sub-session B** (post-`2858f8a`): §4 `crowd_notes` top-10 + §5
>   `heat_exposure` sweep + ship sequence (gate-verification + scrape
>   log + Phase 6 dispatch + SHIPPED commit).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.4 session B
> (2026-05-16) post-`c13dfff`.

---

## §1 Commit chain (origin `ef23456 → c13dfff`)

| # | Commit | Subject | Source | Task |
|---|---|---|---|---|
| 1 | `8d37b86` | `fix(tests)` — az_roc_verify google_primary_category | Cowork | red CI unblock |
| 2 | `e6eceae` | `chore(outputs)` — Phase 6 Amendment 3 dispatch artifact | Cowork | parallel-dispatch prep |
| 3 | `eb8f74b` | `docs(phase5)` — Phase 5.3 SHIPPED ledger entries (Amendment 3) | Claude Code | parallel |
| 4 | `b683ad7` | `fix(scripts)` — places_load filter_by_zip ZIP+4 normalization | Cowork | dispatch fix |
| 5 | `fc51940` | `fix(scripts)` — _DISCOVERY_DOMAIN_FALLBACK extends for health_medical + fitness_sports | Cowork | sustainability |
| 6 | `0cf7f1d` | `fix(tests)` — ruff I001 auto-format on Phase 5.4 fallback regression file | Cowork | red CI follow-up |
| 7 | `f92ff53` | `chore(outputs)` — Phase 5.4 §2 audit -- ambig-queue review + diagnostic + logs | Cowork | gate-2 |
| 8 | `fbdd002` | `fix(scripts)` — npi_verify processor=utils.default_process (rapidfuzz 3.x case-fix) | Cowork | dispatch fix |
| 9 | `700fa3f` | `fix(scripts)` — npi_verify token_set_ratio → token_sort_ratio (subset false-positive fix) | Cowork | dispatch fix |
| 10 | `58bc580` | `fix(tests)` — npi_verify case-mismatch test uses realistic NPI name shape | Cowork | post-fix test repair |
| 11 | `2858f8a` | `chore(outputs)` — Phase 5.4 mid-session checkpoint -- 4 of 6 gates cleared, hand-off | Cowork | mid-session checkpoint |
| 12 | `c13dfff` | `chore(outputs)` — Phase 5.4 SHIPPED -- all 6 gate items cleared | Cowork | **SHIP** |

**Pytest baseline:** 1882 collected (pre-session) → **1909 collected post-session** (+27). Breakdown: 6 new in `tests/test_places_load.py` (ZIP+4 fix #4), 20 new in `tests/test_phase5_4_places_load_resolver.py` (fallback fix #5; parametrized over 11+7 keys × 2 assertions), 3 new in `tests/test_phase5_npi_verify.py` (case-fix + subset + informational, #8/#9/#10). No new tests added in sub-session B (the SHIPPED commit added artifacts only, no test files).

**Ruff:** previously red on `main` at session start (`ef23456` post-`bff4a79`) due to the `8d37b86` AZ ROC fixture issue. Cleared at `8d37b86` and again at `0cf7f1d` (I001 on the new fallback regression file). CI ✅ green from `58bc580` through `c13dfff`. The combined SHIPPED commit's apply-scripts were F401-audited in-sandbox before commit — no follow-up lint commit needed (compare 5.3's `bff4a79` post-SHIPPED clean-up).

**CI:** ✅ Green on `c13dfff`. One sibling workflow `parks-rec-scrapes` continues to X on scheduled cron triggers — pre-existing, not in Phase 5.4 scope; soft-edge for Phase 5.5+.

---

## §2 Phase 5.4 acceptance gate — ALL 6 CLEARED ✅

| # | Gate item | Status | Where |
|---|---|---|---|
| 1 | 80+ entries in `health-wellness-care` post-load | ✅ **265** | Layer 1 (282 inserted, 114 ambig-skipped) + fallback re-load cleared the 111-row operator queue |
| 2 | All Google ↔ existing-entity ambiguous reconciler hits reviewed | ✅ **114 reviewed** | `outputs/phase5_4_health_wellness_pre_load_audit.md` §1-5 — no misroutes; medical-plaza false-ambig pattern documented |
| 3 | NPI verification run completed for licensed sub-trades | ✅ **85 verified** | `python -m scripts.npi_verify` against 265 → 85 matched at threshold 86 (32% rate, all top-15 score=100). Concentrated in doctor/dentist/chiropractor/medical_clinic/health categories |
| 4 | Top-10 by reviews have long-form `crowd_notes` | ✅ **10** | Drafted from `Provider.google_review_snippets` (own column, not `attributes` — corrected mid-session); see `outputs/phase5_4_health_wellness_crowd_notes_top10_staged.md` |
| 5 | `heat_exposure` non-NULL on every entry | ✅ **0 NULL** | 263 indoor + 2 outdoor (Sand Volleyball at Rotary Park `97636ff6`; Stormy Wade Tennis Courts `c514b766`) |
| 6 | `/category/health-wellness-care` renders ≥15 | ✅ **265** | trivially met at gate-1 count |

Final gate verification at `outputs/phase5_4_gate_verification.py` —
6/6 PASS, "ALL 6 ITEMS CLEARED — READY TO SHIP" line.

---

## §3 Notable surgical fixes shipped this session

**Six bugs caught + shipped mid-session** (5.3 pattern shipped 3; 5.4
ran twice that volume because (a) larger label sweep — 28 vs 17 —
surfaced more dispatch-time issues, and (b) the new NPI verifier
surface had two distinct rapidfuzz 3.x gotchas):

### `8d37b86` — AZ ROC test fixture repair (red CI unblock, carry-over from Phase 5.3)

Pytest had been red across the entire Phase 5.3 commit chain
(`b71cf0e`/`81cd70c`/`f0a46f8`/`805a38c`/`bff4a79`/`ef23456`) due to
`tests/test_phase5_az_roc_verify.py::test_az_roc_verify_marks_provider_and_name_cache`
returning 0 matches instead of 3. Cursor's regression test at `6ef5ea8`
built Provider fixtures without `google_primary_category`, but the
post-`420f893` AZ ROC verifier filters by
`google_primary_category ∈ AZ_ROC_LICENSED_PRIMARY_TYPES`. Test fixtures
were excluded. Fix: set `google_primary_category="plumber"` on all 3
fixture Providers.

### `b683ad7` — places_load ZIP+4 normalization

Phase 5.4 load dry-run surfaced 3 LHC ZIP+4 codes (`864035889`,
`864036710`, `864035647`) being dropped as non-LHC because the filter
did exact string match against `LHC_ZIPS = {"86403", "86404", "86405", "86406"}`.
Google sometimes returns ZIP+4 with the dash stripped. Fix: normalize
via `str(zip).replace('-','')[:5]` before membership check. +6
regression tests in `tests/test_places_load.py`.

### `fc51940` — `_DISCOVERY_DOMAIN_FALLBACK` extension for health domains

Phase 5.4 §1 load surfaced 111 of 282 inserts at `category_id=None`,
dominated by `('health_medical', 'health')` ×47 and
`('health_medical', 'medical_clinic')` ×36 catch-all primary_types.
Added 18 new entries to `_DISCOVERY_DOMAIN_FALLBACK` (11 health_medical
+ 7 fitness_sports). Re-run load cleared the operator queue to 0. +20
regression tests in `tests/test_phase5_4_places_load_resolver.py`.
Lint fix follow-up at `0cf7f1d` (ruff I001 auto-format on the new
regression file). Soft-edge: `medical_clinic` + `dental_clinic`
arguably belong in `google_types_mapping.py` directly — left in
fallback for the surgical-fix shape.

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

### **NOT shipped this session: JSON-column double-encoding (5.3 `f35d5e4`)**

The Phase 5.4 `crowd_notes` apply-script avoided the 5.3 `f35d5e4` bug
from the start by passing the dict directly to `Entity.crowd_notes`
(no `json.dumps()`). The 5.3 close-out §3 pattern was internalized
during the mid-session hand-off — no follow-up needed.

---

## §4 Mid-session source-of-truth correction (`crowd_notes`)

The mid-session checkpoint §3 plan said operator drafts from
`attributes.google_review_snippets`. The reality: `google_review_snippets`
is its **own JSON column on `Provider`** (per `app/db/models.py:84`,
populated by `scripts/places_load.py:146` from the scraper's
`review_snippets` emission at `app/contrib/google_places_scraper.py:464`).
Coverage is good: **187 / 265 HWC providers** have non-empty snippets;
all top-10 had n=5 each. Sub-session B corrected the path; drafts are
sourced from real reviewer text. This pattern correction should be
applied to any future Phase 5.X kickoff doc referencing the snippets
field — the canonical source is the **column**, not the attributes JSON.

---

## §5 Sustainability layer update (post-`fc51940`)

`_DISCOVERY_DOMAIN_FALLBACK` extended for both `health_medical` and
`fitness_sports` domains — 18 new entries beyond the 5.3 set
(`7c994aa`). All future Phase-5.4-style re-pulls will auto-categorize
the same shape.

### Sustainability matrix (updated)

| Field | Auto on re-pull? | Auto for new business? |
|---|---|---|
| `Provider.category_id` from `_resolve_category_id` | ✅ preserved if set | ✅ resolved at INSERT |
| `EntityCategory` linkage | ✅ via `_ensure_entity_category` | ✅ via dual-write hook |
| `Provider.verified` + `attributes.npi_number` (5.4-specific) | ✅ not overwritten by re-pull | ❌ needs re-run of `npi_verify` |
| `heat_exposure` | ✅ not overwritten | ❌ lands NULL — needs periodic sweep |
| `crowd_notes` | ✅ not overwritten | ❌ — needs operator curation |

**Phase 5.5 (Auto, RV & Fuel)** anticipated catch-all primary_types
per kickoff §5: `('auto_rv_fuel', 'car_dealer')`,
`('auto_rv_fuel', 'service')`, etc. Likely some 5.5-specific verifier
surface (no equivalent of NPI; auto industry doesn't have a single
national licensing API like AZ ROC). Phase 5.5 kickoff doc to be
authored at session start by the next agent.

---

## §6 Remaining work for next session (Phase 5.5)

### Gate-blocking (0) — Phase 5.4 SHIPPED at `c13dfff`

All 6 gate items met per `outputs/phase5_4_gate_verification.py`. The
SHIPPED commit landed on `origin/main` at `c13dfff` 2026-05-16.

### 🚨 Carry-over for operator-side action

- **Phase 6 lane dispatch: Phase 5.4 SHIPPED ledger amendment** —
  `outputs/claude_code_dispatch_phase6_amend4.md` is ready for operator
  to paste into Claude Code. Pattern mirrors Amendment 3 (which shipped
  at `eb8f74b` in sub-session A). The dispatch artifact has
  `[SHIP-COMMIT]` placeholders that Claude Code resolves at runtime by
  `git log` against `c13dfff`.
- **Google Places API key rotation** still deferred — operator declined
  mid-session ("all keys will be changed at the conclusion of this
  project"). Risk accepted for the remaining Phase 5.x budget.
- **86 of 265 health-wellness-care providers remain `verified=False`** —
  no NPI match found. Mostly DBA-only practices not registered as
  individual NPIs under that exact name. Kickoff §3 anticipated this
  pattern and noted a DBA→NPI mapping follow-up surface. Not gate-
  blocking; operator-curated follow-up.

### Soft-edges (3 deferred per `phase5_4_health_wellness_pre_load_audit.md` §5)

- Optional force-insert apply-script for 87 cross-category candidates
- Optional `GEO_PROXIMITY_THRESHOLD_M` tune (50 → 25)
- Optional same-discovery-domain bypass in reconciler

None are gate-blocking. Phase 6 cross-list pass can revisit.

### `parks-rec-scrapes` scheduled CI (carry-over)

X on cron triggers throughout this session. Likely pre-existing
(missing repo secret or path issue). Not in 5.4 scope. **Phase 5.5+
to investigate** — likely relevant to Phase 5.5 (auto/RV/fuel) or
Phase 5.6 (parks/rec/trails) wiring.

### `data/events.db.bak-*` files (carry-over from Phase 5.3)

11 backup files from the 5.3 session + new ones may accumulate from
this session's apply-scripts (the apply-scripts don't auto-snapshot,
but the operator's local routine may). Operator prunes when comfortable.

---

## §7 Coordination summary (one-line)

| Lane | Coordination need |
|---|---|
| Phase 6 (parallel agent) | Amend `master_build_plan.md` + `STATE.md` with Phase 5.4 SHIPPED at `c13dfff` via `outputs/claude_code_dispatch_phase6_amend4.md` |
| Cursor | No dispatches pending (Phase 5.4 produced its own regression tests in-lane: +6 ZIP+4 + 20 fallback + 3 NPI = +27 total at 1909) |
| Operator | API key rotation (deferred per ops choice), 86 unverified-flag DBA→NPI follow-up (optional), `.bak` file prune (when ready) |

---

## §8 Read order for the next session (Phase 5.5)

1. **This document** — the state of play (close-out + commit chain).
2. `outputs/phase5_4_session_midpoint_checkpoint.md` — mid-session
   hand-off (still useful for context on sub-sessions A vs B, the
   §2 audit findings, and the sustainability layer extension).
3. `outputs/phase5_5_auto_rv_fuel_kickoff.md` — Phase 5.5 runbook
   (authoritative for the §6 acceptance gate definitions; **next agent
   authors this if not yet present**, mirroring
   `outputs/phase5_4_health_wellness_care_kickoff.md` shape).
4. `outputs/phase5_4_health_wellness_pre_load_audit.md` — pre+post
   audit doc (template the 5.5 audit will mirror).
5. `docs/scrape_logs/health-wellness-care_2026-05-16.md` — Layer 1
   actuals + commit chain (template for Phase 5.5's scrape log).
6. `scripts/npi_verify.py` + `app/contrib/npi_client.py` — the 5.4
   verification surface, REST-based. Phase 5.5 will likely need a
   new verifier surface; this one is the cleanest non-Playwright
   reference.
7. `outputs/apply_phase5_4_health_wellness_heat_exposure.py` /
   `_crowd_notes.py` — template apply-scripts that 5.5 equivalents
   will mirror. Note: `crowd_notes` correctly passes dict directly to
   the JSON column (5.3 `f35d5e4` gotcha avoided).
8. `outputs/phase5_4_gate_verification.py` — template for
   `outputs/phase5_5_gate_verification.py`.

---

## §9 Pre-flight for the next session

1. **`git log --oneline -15`** — origin should top at `c13dfff` or
   later (Phase 6 lane may push `eb8f74b`-shape Amendment 4 between
   sessions).
2. **`git status`** — clean. Note: sandbox bash hits a git-index
   gotcha (`fatal: unknown index entry format 0xffff0000`) — run
   `git status` Windows-side.
3. **`python -m alembic current`** — `0a1b2c3d4e5f` (unchanged across
   all 5.x phases).
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — expect
   **1909 collected**. Verify no drift.
5. **`gh run list --branch main --limit 3`** — top run should be ✓ on
   `c13dfff`. Note that `parks-rec-scrapes` scheduled jobs continue
   to X — out of scope through 5.4, may become 5.5+ scope.
6. **DB state spot-check** — `health-wellness-care` should show
   **265 entries / 85 verified / 263 indoor + 2 outdoor / 10 long-form
   crowd_notes** (the 5.4 SHIPPED state).
7. **Phase 5.5 sub-trade scope** — Phase 5.5 (Auto, RV & Fuel) kickoff
   doc should land first. Anticipated label set: car dealers, RV
   dealers, RV parks (some overlap with 5.2 on-the-water for boat
   ramps adjacent to RV parking), gas stations, auto repair, tire
   shops, oil change. Likely 12-18 labels per
   `scripts/places_categories.json`.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.4 session
(2026-05-16) post-`c13dfff`. Phase 5.4 SHIPPED with all 6 gate items
cleared; 12 commits on origin/main from `ef23456` → `c13dfff`.
Mid-session checkpoint at `2858f8a` (`outputs/phase5_4_session_midpoint_checkpoint.md`)
joins sub-sessions A and B. Hand-off to Phase 5.5 (Auto, RV & Fuel)
next session.*
