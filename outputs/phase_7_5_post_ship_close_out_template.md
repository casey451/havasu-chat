# Phase 7.5 Post-Ship Close-Out Template

> **What this is:** the reusable Cowork-primary rhythm for closing out Phase 7.5 (HALT 3 validator triage + flag-flip closure) when Cursor returns with the §12 final report. Pre-positioned 2026-05-20 post-`36405c0` so the close-out cycle is fast when Phase 7.5 ships. Distinct from `outputs/lane_d_e_post_ship_close_out_template.md` (which was generic-to-Lane-D-or-E) because Phase 7.5's success surface is narrower: validator goes 22/22 PASS + 10 specific failure dispositions documented + flag-flip operator action sequenced.
>
> **Author:** Cowork primary, 2026-05-20.
>
> **Instantiate as:** `outputs/phase_7_5_close_out.md` when Cursor returns with its §12 report.

---

## §1 Pre-flight verification (do this BEFORE declaring ship)

Run these checks against the working tree where Cursor left files:

```powershell
# 1. Confirm Cursor did NOT git-commit
git status --short
# Expected: M lines on app/chat/halt3_eval_set.yaml + maybe 1-4 other app/chat/*.py files + 0 alembic/ changes
# Verify NO untracked alembic/versions/ files (Phase 7.5 ships no migration)

# 2. Confirm alembic head UNCHANGED at c9d0e1f2a3b4
python -m alembic current
# Expected: c9d0e1f2a3b4 (head; same as pre-7.5)
python -m alembic heads
# Expected: c9d0e1f2a3b4 (SINGLE head; no multi-head)

# 3. Confirm pytest passes
python -m pytest -q
# Expected: 2133+ passed + 2 skipped; ruff clean

# 4. THE GATE — re-run the HALT 3 validator
python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml
# Expected:
#   cited_coverage=100% missing_confab_max=0.00 all_passed=True
#   22 PASS / 0 FAIL
# If anything less than 22/22 PASS: STOP. Phase 7.5 is NOT shipped.
#   Re-read Cursor's §12 report for the discrepancy; either Cursor over-claimed OR
#   the validator behavior differs from Cursor's local environment.
```

**If any of 1–4 diverges from Cursor's §12 claim:** STOP. Cursor's report and reality disagree. Either re-dispatch with the discrepancy as context, OR the operator triages the gap manually.

---

## §2 Acceptance-gate verification

Per `outputs/cursor_dispatch_prompt_phase_7_5.md` + `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` §4:

| Gate | Status | Verification |
|---|---|---|
| Validator returns 22/22 PASS | ✅ / ❌ | `python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml` output |
| `cited_coverage = 100%` | ✅ / ❌ | Same |
| `missing_confab_max = 0.00` | ✅ / ❌ | Same — q07's 0.50 confab rate must be down to 0 |
| `all_passed = True` | ✅ / ❌ | Same |
| Per-query disposition documented (10 originally-FAILing queries) | ✅ / ❌ | Cursor's §12 report has the table |
| Pytest stays at ≥2133 passed | ✅ / ❌ | `python -m pytest -q` |
| Ruff clean | ✅ / ❌ | `ruff check app/ tests/` |
| Alembic head unchanged at `c9d0e1f2a3b4` (single head; no Phase 7.5 migration) | ✅ / ❌ | `python -m alembic current` + `python -m alembic heads` |
| File scope respected (no Phase 6.5 / Phase 8a / other-lane touches) | ✅ / ❌ | Verify Cursor's modified file list |

**All gates met:** Phase 7.5 is SHIPPED. Proceed to §3.
**Any gate fails:** Phase 7.5 is NOT SHIPPED. Re-dispatch or re-investigate.

---

## §3 Per-query disposition triage (Cursor's §12 must include this)

Cursor 7.5's §12 report should include a per-query disposition table for the 10 originally-FAILing queries. Verify each entry against the actual code/yaml changes:

| Query | Cursor's disposition | Verify |
|---|---|---|
| q02 | CODE-FIX (tier classifier) OR EVAL-PATCH (expected_tier) | Check if `intent_classifier.py` was modified OR `halt3_eval_set.yaml` q02 entry's `expected_tier` changed |
| q03 | CODE-FIX (matching) OR EVAL-PATCH (entity not in catalog) | Check `entity_catalog_query.py` modifications OR yaml q03 entry |
| q06 | CODE-FIX (disclosure_render i_dont_know routing) | Should be CODE-FIX — missing-data leakage is a real bug. Verify `disclosure_render.py` modified. |
| **q07** | **CODE-FIX (confabulation; P0)** | **Must be CODE-FIX.** Verify `entity_intent.py` OR `tier3_handler.py` OR `disclosure_render.py` modified for confab guards. Eval-patch is NOT acceptable — this is the smoking-gun bug. |
| q10 | CODE-FIX or EVAL-PATCH | Per-query reasoning |
| q14 | CODE-FIX or EVAL-PATCH | Per-query reasoning |
| q16 | CODE-FIX or EVAL-PATCH | Per-query reasoning |
| q17 | CODE-FIX or EVAL-PATCH | Per-query reasoning |
| q21 | CODE-FIX or EVAL-PATCH | Per-query reasoning |
| q22 | CODE-FIX (disclosure_render i_dont_know routing) | Should be CODE-FIX — same as q06. Verify `disclosure_render.py` modified. |

**Red flag:** if Cursor disposed q07 as EVAL-PATCH (i.e., "the eval set was wrong about expecting i_dont_know"), that's a no-go. q07's 0.50 confabulation rate means the chat genuinely fabricated citations; eval-patching that away is suppressing a real bug. Re-dispatch with explicit guidance.

**Yellow flag:** if Cursor disposed many P1 cases (q03 / q10 / q14 / q16 / q17 / q21) as EVAL-PATCH, the eval set was too strict — that's defensible but document the reasoning carefully in the close-out doc.

**Green flag:** P0 cases (q07 + q06 + q22) all CODE-FIX + mixed dispositions on P1 cases + 22/22 PASS = clean ship.

---

## §4 Commit batch recommendation (Rule 8)

**Single substantive commit + 0–1 fixup commits.**

### Phase 7.5 commit (typical)

```powershell
# Stage Cursor's Phase 7.5 changes
git add app/chat/halt3_eval_set.yaml `
        app/chat/halt3_validator.py `
        app/chat/disclosure_render.py `
        app/chat/entity_catalog_query.py `
        app/chat/entity_intent.py `
        app/chat/tier3_handler.py `
        tests/test_phase7_halt3_validation.py

# Verify nothing unexpected staged (no app/templates/ or app/conditions/ etc.)
git diff --cached --name-only

# Commit
git commit `
  -m "feat(phase7.5): HALT 3 validator triage + flag-flip closure (22/22 PASS)" `
  -m "Closes the 10 HALT 3 validator failures from Phase 7's initial run (cited_coverage 42->100; missing_confab_max 0.50->0.00; all_passed True). Per-FAIL disposition: q02 <CODE-FIX or EVAL-PATCH per Cursor>; q03 <...>; q06 CODE-FIX (disclosure_render i_dont_know routing); q07 CODE-FIX (confabulation; entity_intent + tier3_handler + disclosure_render tightening); q10/q14/q16/q17/q21 <per-query>; q22 CODE-FIX (matches q06 pattern). <NARRATIVE OF WHAT WAS TIGHTENED IN EACH FILE>." `
  -m "Pytest <PRE_COUNT> -> <POST_COUNT> (delta zero or small for new guards). Alembic head unchanged at c9d0e1f2a3b4 (no Phase 7.5 migration). Ruff clean. <DEVIATIONS_NARRATIVE>. File scope held to app/chat/halt3_* + disclosure_render.py + entity_catalog_query.py + entity_intent.py + tier3_handler.py + halt3_eval_set.yaml + tests/test_phase7_halt3_validation.py per gotcha #18. Phase 6.5 + Phase 8a (if running in parallel) unaffected."
```

### Fixup commit pattern (if ruff red post-feat)

```powershell
ruff check --fix app/ tests/
git add <fixed_files>
git commit `
  -m "fix(phase7.5): ruff <RULE> in <PATH> (CI follow-up to <FEAT_SHA>)"
```

---

## §5 STATE.md + master plan ledger updates

### STATE.md prepend (top of "Recently shipped")

```markdown
- **Phase 7.5 — HALT 3 validator triage + flag-flip closure SHIPPED on origin (2026-05-XX, post-Phase-7).** Closes the 10 HALT 3 validator failures from Phase 7's initial run (commit `0a305e0`) per `outputs/phase_7_halt3_initial_run_report.md`. Commit `<SHA>` (single feat + close-out chain). **Validator now returns 22/22 PASS:** `cited_coverage=100% missing_confab_max=0.00 all_passed=True`. <PER-QUERY DISPOSITION NARRATIVE: which were CODE-FIX vs EVAL-PATCH; what was tightened in each file>. **Per-FAIL summary:** q07 confabulation (P0; CODE-FIX in `entity_intent.py` + `tier3_handler.py` + `disclosure_render.py`); q06 + q22 missing-data leakage (P0; CODE-FIX in `disclosure_render.py`); q02 + q03 + q10 + q14 + q16 + q17 + q21 mixed CODE-FIX / EVAL-PATCH (P1-P2; per-query disposition in close-out doc). Pytest `2133` → `<POST>` (delta zero or +1-3 for new guards). Alembic head unchanged at `c9d0e1f2a3b4` (no migration). Ruff clean. Close-out at `outputs/phase_7_5_close_out.md`. **CI:** ✅ green at SHIP. **Operator flipped `FEATURE_FLAG_DISCLOSURE_RENDERER=true` on Railway production 2026-05-XX out-of-band** (post-validator-green; Phase 7's HALT 3 deliverable (d) now fully complete + user-facing). Next: **Phase 6.5** (homepage rebuild) + **Phase 8a** (conditions + alerts) — either or both, parallel-eligible per gotcha #18 (no migration race in this pair).
```

### master_build_plan.md §4 Phase 7 sub-entry append

The Phase 7 SHIPPED line already lives in §4 Phase 7 (added at `a494946`). Phase 7.5 appends a sub-entry under it (similar to how Phase 6.x has sub-entries):

```markdown

**Phase 7.5 SHIPPED `<SHA>` 2026-05-XX** — HALT 3 validator triage + flag-flip closure. Closes the 10 failures from Phase 7's initial validator run (12/22 PASS → 22/22 PASS). [Then 2-3 sentences narrating the per-FAIL disposition + flag-flip action.] Pytest `2133` → `<POST>`. Alembic head unchanged at `c9d0e1f2a3b4`. Phase 7.5 lane commit chain: `<SHA>` (single feat + docs commit). Close-out at `outputs/phase_7_5_close_out.md`. Operator flipped `FEATURE_FLAG_DISCLOSURE_RENDERER=true` on Railway production 2026-05-XX — Phase 7's deliverable (d) now fully complete and user-facing.
```

---

## §6 Post-ship operator action — FLAG FLIP

This is the substantive operator action that closes the HALT 3 narrative arc:

```powershell
# On Railway dashboard for havasu-chat-production service:
# 1. Navigate to Environment Variables
# 2. Set: FEATURE_FLAG_DISCLOSURE_RENDERER = true
# 3. Save (triggers redeploy)
# 4. Wait for deploy to complete (~3-5 min)

# Smoke check post-deploy:
# - Browse to production chat surface
# - Verify the chat now uses the full disclosure-renderer pipeline (cited responses + i_dont_know routing + no confabulation)
# - Sample 2-3 of the originally-FAILing queries (q07 + q03 + q22 are good picks) — verify the responses match the eval-set expectations

# STATE.md update — after flag flip, the "Recently shipped" entry should note:
# "Operator flipped `FEATURE_FLAG_DISCLOSURE_RENDERER=true` on Railway production <DATE> out-of-band (post-validator-green)."
```

**Why flag-flip is operator out-of-band (not in commit body):** flipping an env var on Railway is not a git operation. It's a configuration change. The commit body can NOTE the flip date but the flip itself isn't a commit.

---

## §7 Post-ship verification

```powershell
# After commits land, push
git push origin main

# Re-confirm head + alembic + log shape
git log --oneline -5
python -m alembic current
python -m pytest --collect-only -q | tail -3
python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml
# Last line should still be: cited_coverage=100% missing_confab_max=0.00 all_passed=True

# CI sanity (GitHub Actions runs automatically on push)
# Verify the next GitHub Actions run is ✓ green within ~5 minutes
```

---

## §8 Deviation triage (Cursor's §13 flags)

Common Phase 7.5 deviations to expect (per dispatch wrapper §8):

| Deviation type | Default disposition |
|---|---|
| Eval-set patch that changes `expected_tier` | **Accept** if Cursor's reasoning is sound; flag for low-confidence patches |
| Disclosure-renderer tightening affecting edge cases outside eval set | **Accept** if no regression in pre-existing tests; verify |
| hint_extractor token-budget polish | **Accept** if shipped; else defer to V1.5 |
| Per-query confab-rate gating in addition to aggregate `missing_confab_max` | **Accept** if Cursor shipped; documents the gating spec |
| Eval-patch on q07 (the confabulation case) | **REVERSE** — q07's 0.50 confab rate is a real bug; eval-patching suppresses it. Re-dispatch. |
| Scope creep beyond `app/chat/halt3_*` + `disclosure_render.py` + `entity_catalog_query.py` + `entity_intent.py` + `tier3_handler.py` + `halt3_eval_set.yaml` + `tests/test_phase7_halt3_validation.py` | **Discuss** — if Cursor touched Phase 6.5 / Phase 8a scope by accident, it's a gotcha #18 violation; pull back. |
| New alembic migration | **REVERSE** — Phase 7.5 ships no migration. |

---

## §9 Carries forward

After Phase 7.5 ships:

- **Phase 6.5 dispatch** ready any time (wrapper at `outputs/cursor_dispatch_prompt_phase_6_5.md`; SHA slots `96c915d` + `f6a7b8c9d0e1`). Parallel with Phase 8a still safe (file-scope disjoint).
- **Phase 8a dispatch** ready any time (wrapper at `outputs/cursor_dispatch_prompt_phase_8.md`; SHA slots `0a305e0` + `c9d0e1f2a3b4`). All 3 operator prereqs RESOLVED (AirNow + USGS + Nixle 3726).
- **Phase 8b (cat-13 expansion)** — micro-dispatch after 8a ships. Wrapper authored later.
- **Phase 9** architectural design in place at `outputs/phase_9_architecture_design.md`. Wrapper authored later.
- **hint_extractor token-budget perf carry** — if Cursor 7.5 didn't address (deferred to V1.5), update `outputs/v1_5_carry_inventory_triage.md` to include the entry.
- **`docs/maintainability/dispatch_channels.md` fold of alembic-collision gotcha** — still pending; do at next docs checkpoint.

---

*Authored by Cowork primary at the post-`36405c0` session (2026-05-20). Lives at `outputs/phase_7_5_post_ship_close_out_template.md`. Instantiate as `outputs/phase_7_5_close_out.md` when Cursor returns with its §12 report.*
