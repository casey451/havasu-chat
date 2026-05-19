# Phase 7.5 Polish Lane — HALT 3 Validator Triage + Flag-Flip Closure (Dispatch Note)

> **What this is:** the dispatch note for a Phase 7.5 polish-lane Cursor session that triages the 10 HALT 3 validator failures, fixes the real bugs (especially q07 confabulation), refines the eval set where expectations were wrong, and re-runs the validator to acceptance (100% cited coverage + 0.0 confabulation max). Closes the flag-flip gate so the operator can flip `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band post-ship.
>
> **Author:** Cowork primary, 2026-05-20 post-`0a305e0`.
>
> **Why a "polish lane" rather than a full Phase 7 re-dispatch:** Phase 7's 6 deliverables are SHIPPED at `0a305e0`. The HALT 3 close-out's INFRASTRUCTURE is shipped (eval set + validator + tests). What's left is investigation + fix + re-run. That's polish, not new feature work. Lighter weight than a full wrapper authoring.
>
> **Companion docs:**
> - `outputs/phase_7_close_out.md` — Phase 7 close-out documenting the deferral decision
> - `outputs/phase_7_halt3_initial_run_report.md` — raw validator output + per-query interpretation + 5 hypotheses to test (this is your primary input)
> - `outputs/cursor_dispatch_prompt_phase_7.md` — original Phase 7 wrapper (canonical scope of what was built)
> - `app/chat/halt3_eval_set.yaml` — the 22-query eval set
> - `app/chat/halt3_validator.py` — the validator
> - `docs/maintainability/disclosure_renderer_spec.md` — the canonical disclosure renderer spec

---

## §1 Scope (what Phase 7.5 ships)

### Goal

`python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml` returns:
```
cited_coverage=100% missing_confab_max=0.00 all_passed=True
22/22 PASS
```

### Deliverables

1. **Per-failure triage** of the 10 FAILs documented in `outputs/phase_7_halt3_initial_run_report.md` §3. Per query: real-bug-needs-fix vs eval-set-too-strict. Update the eval set OR fix the code as appropriate.

2. **Fix q07's confabulation** (P0). The chat is fabricating citations on a missing-data query. Diagnosis: investigate why tier 3 is reached + cites entities not in catalog. Possible fixes:
   - Tighten `entity_intent.detect_multi_domain_category_slugs()` to prevent over-broad category surfacing
   - Tighten the tier-3 LLM prompt to refuse citations when the ENTITY catalog returns no matches
   - Tighten the cited-vs-uncited disclosure renderer logic when LLM output mentions entity names not in the recent query results

3. **Fix the 2 missing-data leakage cases** (P0; q06 + q22). The chat is producing `uncited` responses on missing-data cases that should return `i_dont_know`. Diagnosis: investigate the chat / disclosure renderer path for these specific queries. Possible fixes:
   - Tighten the disclosure renderer to require explicit cite-source on every chat-tier response
   - Add a guard in the tier-classifier to route missing-data queries to a gap_template path

4. **Resolve the 6 "expected cited, got i_dont_know" cases** (P1; q03, q10, q14, q16, q17, q21). Per Hypothesis A + D from the initial-run report: investigate each query in the eval set. For each:
   - **Real-bug path:** entity exists in catalog but matching/query missed it → fix in `app/chat/entity_catalog_query.py` OR `app/chat/entity_matcher.py` OR `intent_classifier.py`
   - **Eval-too-strict path:** eval expected an entity that's DRAFT'd, soft-deleted, or doesn't exist → patch the eval set with corrected expectation (or remove the query)
   - **Tier-routing path:** entity is reachable but a different tier than the eval expects → adjust the eval's `expected_tier` (low confidence) OR re-classify the tier-routing (high confidence)

5. **Resolve the tier mismatch in q02** (P2). Decide: eval expected tier=2 + cited; observed tier=3 + i_dont_know. Either the tier classifier is wrong (fix code) or the eval expectation is wrong (patch yaml).

6. **Re-run validator** + verify 22/22 PASS. If new failures emerge from fixes (regression), iterate.

7. **No code changes outside the HALT 3 closure surface.** Phase 7.5 file scope:
   - `app/chat/halt3_eval_set.yaml` (eval set patches)
   - `app/chat/halt3_validator.py` (only if validator logic itself has a bug)
   - `app/chat/disclosure_render.py` (likely fix surface for q06/q22 + q07)
   - `app/chat/entity_catalog_query.py` (likely fix surface for q03 / q10 / q14 / q16 / q17 / q21 cited-misses)
   - `app/chat/entity_intent.py` (likely fix surface for q07 confabulation)
   - `app/chat/tier3_handler.py` (likely fix surface for q07 confabulation in tier 3 LLM)
   - `tests/test_phase7_halt3_validation.py` (if eval-set patches change expectations, may need test guard updates)
   - **NO new alembic migration** (HALT 3 polish is code-side; no schema change)

8. **Optional secondary cleanup:** the 22 `hint_extractor: token usage exceeds soft budget (inp=~378 out=8)` warnings flagged in the initial run. Either tighten the hint_extractor prompt OR raise the soft-budget constant. V1.5 candidate but defer unless trivial to address in Phase 7.5.

### What Phase 7.5 does NOT ship

- No new chat features (Phase 7 + Phase 8 cover the feature surface)
- No new categories / migrations
- No `FEATURE_FLAG_DISCLOSURE_RENDERER` flip (that's operator out-of-band after validator goes green)
- No master-plan / STATE.md narrative changes (those are Cowork-primary post-ship)

---

## §2 Recommended Cursor approach (paste-into-Cursor template)

```
PHASE 7.5 — HALT 3 VALIDATOR TRIAGE + FLAG-FLIP CLOSURE

You are a focused polish-lane Cursor session. Phase 7 SHIPPED at 0a305e0
(chat ENTITY wiring + boat-mode + conditions + HALT 3 close-out + cross-
entity + snowbird-return view). The HALT 3 close-out's INFRASTRUCTURE is
shipped (app/chat/halt3_eval_set.yaml with 22 queries + app/chat/halt3_
validator.py + tests/test_phase7_halt3_validation.py). But the initial
validator run failed 10/22 (cited_coverage=42% missing_confab_max=0.50
all_passed=False). Your job is to close the gap.

Read these first:
1. outputs/phase_7_halt3_initial_run_report.md (per-query categorization +
   5 hypotheses to test — this is your primary input)
2. outputs/phase_7_5_halt3_polish_lane_dispatch_note.md (this brief; sec1
   scope + sec2 approach + sec4 acceptance gate)
3. app/chat/halt3_eval_set.yaml (the 22 queries with expected
   tier/disclosure/confabulation)
4. app/chat/halt3_validator.py (validator runner + per-query check shape)
5. docs/maintainability/disclosure_renderer_spec.md (canonical spec)
6. app/chat/entity_catalog_query.py + entity_intent.py + disclosure_
   render.py + tier3_handler.py (likely fix surface)

Order of work:

1. **Triage every FAIL.** For each of q02, q03, q06, q07, q10, q14, q16,
   q17, q21, q22:
   - Read the eval-set entry for that query (the query text + expected
     tier/disclosure/notes)
   - Run the query through the chat module manually (or via
     halt3_validator.py with a single-query filter if it supports one)
   - Examine: did the chat actually behave correctly + the eval is wrong?
     OR did the chat behave wrong + the eval is right?
   - Decide: FIX CODE or PATCH EVAL SET (must be unambiguous)
   - Document the decision in a per-query comment in halt3_eval_set.yaml
     OR in your sec12 commit message

2. **Fix the P0 cases first:**
   - q07 (confabulation; chat fabricated citations) — investigate
     entity_intent + tier3_handler + disclosure_render. Tighten until
     missing-data queries return i_dont_know with 0 confab.
   - q06 + q22 (i_dont_know expected, got uncited) — investigate
     disclosure_render path. Tighten until missing-data queries always
     route to i_dont_know.

3. **Then the P1 cases (q03, q10, q14, q16, q17, q21).** Each may be:
   - Real bug: entity_catalog_query.py missing the entity → fix matching
   - Eval-too-strict: entity not in catalog → patch eval yaml
   - Both possible; document per-query disposition

4. **Then q02 (tier mismatch).** Lowest priority; may be eval-set adjust.

5. **Re-run validator.** Iterate until 22/22 PASS:
   python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml
   Goal output:
     cited_coverage=100% missing_confab_max=0.00 all_passed=True
     22 PASS / 0 FAIL

6. **(Optional) hint_extractor token-budget polish.** 22 warnings of
   "token usage exceeds soft budget" per validator run. Either tighten
   the prompt OR raise the budget constant. Skip if non-trivial.

7. **Pytest stay green throughout.** After your fixes:
   - tests/test_phase7_halt3_validation.py — may need updates if eval set
     expectations changed
   - other tests/test_phase7_*.py — should remain green unaffected
   - full suite — should remain at 2133+ passed
   - ruff clean

CONSTRAINTS:
- No new alembic migration. HALT 3 polish is code-side.
- No FEATURE_FLAG_DISCLOSURE_RENDERER flip (operator does out-of-band post-
  validator-green).
- No new chat features. Tighten + fix existing surface only.
- No new test files unless a fix introduces a behavior worth guarding.
- Don't bash heredoc commit messages. PowerShell-safe.
- Re-verify python -m alembic current AND python -m alembic heads at end
  of session — should return c9d0e1f2a3b4 (single head; unchanged).

PARALLEL-DISPATCH SAFETY: Phase 7.5 can run in parallel with Phase 6.5
(templates / static / routes) and Phase 8a (app/conditions/ + app/alerts/)
per gotcha #18 file-scope disjointness. Phase 7.5 touches: app/chat/halt3_
* + disclosure_render.py + entity_catalog_query.py + entity_intent.py +
tier3_handler.py + halt3_eval_set.yaml + maybe test_phase7_halt3_
validation.py. None of those are in Phase 6.5's or Phase 8's file scope.
No alembic migration so no alembic-collision risk.

DELIVER §12 report when complete:
- Pre-work + post-work pytest collect + alembic state
- Final validator output (target 22/22 PASS + cited_coverage=100% +
  missing_confab_max=0.00 + all_passed=True)
- Per-query disposition (10 entries; CODE-FIX or EVAL-PATCH per query)
- Files touched (likely 4-7 files; modest scope)
- Pytest delta (likely 0 net-new tests OR small +1-3 for new guards)
- Ruff status
- §13 deviations
- HALT at the sec3 boundary; do NOT proceed to other lanes.
```

---

## §3 Expected effort

**3–5 days** Cursor session. Estimate breakdown:
- Day 1: triage all 10 FAILs (read eval set + run each query through chat + decide CODE-FIX vs EVAL-PATCH per query)
- Day 2–3: fix the P0 cases (q07 confabulation; q06 + q22 missing-data leakage); validator iteration loop
- Day 3–4: fix the P1 cases (q03 / q10 / q14 / q16 / q17 / q21); validator iteration loop
- Day 4–5: resolve q02; final validator green; pytest + ruff cleanup; §12 report

Could compress to **1–2 days** if a single root cause explains many of the FAILs (e.g., one bug in `entity_catalog_query.py` causes q03 + q10 + q14 + q16 + q17 + q21 all at once).

Could stretch to **5–7 days** if the eval set turns out to have wider semantic issues + needs substantial re-authoring.

---

## §4 Acceptance gate (Phase 7.5 SHIP criteria)

Cursor's §12 report must include:
1. `cited_coverage=100% missing_confab_max=0.00 all_passed=True 22/22 PASS` — the actual validator output
2. Per-query disposition table for the 10 originally-FAILing queries (code-fix vs eval-patch)
3. Pytest still green at ≥2133 passed
4. Ruff clean
5. Alembic head unchanged at `c9d0e1f2a3b4` (single head; no Phase 7.5 migration)

When Cursor returns with this, Cowork primary reviews + recommends commit batch (typically single `feat(phase7.5):` commit for substantive fixes, plus `docs(phase7.5):` close-out + master plan + STATE.md ledger updates).

After Phase 7.5 ships, operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band on Railway production. STATE.md "Recently shipped" entry should note both Phase 7.5 ship AND the flag-flip date.

---

## §5 Why not just defer everything to V1.5?

The operator chose "defer iteration to Phase 7.5 polish lane" (not "defer to V1.5") because:
1. **q07's confabulation is a real bug, not a polish item.** The chat fabricating citations is exactly what HALT 3 was built to prevent. Shipping V1 with this exposed weakens the trust contract.
2. **The validator infra works.** Building it was the substantive lift. Fixing the failures it surfaced is incremental.
3. **3–5 day Phase 7.5 dispatch is well-bounded.** No new architecture; just tightening existing surfaces against a known-good test set.
4. **The flag-flip unlocks downstream value.** Phase 8 conditions panel + Phase 6.5 homepage + the overall V1 trust surface all benefit from a green HALT 3 contract.

V1.5 deferral was still an option (master plan §8 OQ #11 pattern) but the operator weighed q07's severity + the bounded effort + the unlock value and chose the polish-lane route.

---

*Authored by Cowork primary at the post-`0a305e0` Phase 7 close-out session (2026-05-20). Lives at `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`. Companion artifacts: `outputs/phase_7_close_out.md`, `outputs/phase_7_halt3_initial_run_report.md`. Operator dispatches Phase 7.5 at convenience; parallel-eligible with Phase 6.5 + Phase 8a per gotcha #18.*
