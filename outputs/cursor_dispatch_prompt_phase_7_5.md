# Cursor Dispatch Prompt — Phase 7.5 (HALT 3 validator triage + flag-flip closure)

> Paste-into-Cursor prompt for Phase 7.5 — the focused polish lane that closes the 10 HALT 3 validator failures from Phase 7's initial run (commit `0a305e0`, validator output `cited_coverage=42% missing_confab_max=0.50 all_passed=False`). Triages each failure (real-bug-fix vs eval-set-patch), fixes the real bugs (q07 confabulation is P0), refines the eval set where expectations were wrong, and re-runs the validator to acceptance (`cited_coverage=100% missing_confab_max=0.00 all_passed=True 22/22 PASS`). Closes the gate so the operator can flip `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band post-ship. Companion brief: `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`; raw run report: `outputs/phase_7_halt3_initial_run_report.md`.
>
> **Gating dependencies:** Phase 7 SHIPPED on origin at `0a305e0` (chat ENTITY wiring + boat-mode + conditions awareness + HALT 3 close-out infra + cross-entity + snowbird-return view). Alembic head `c9d0e1f2a3b4` (Phase 7's `users.last_active_at` migration; chains from `f6a7b8c9d0e1`). Phase 6.4 + Phase 6.3 + Phase 6.2 + Phase 6.1 + Phase 5 multi-phase data-population all SHIPPED. **Phase 7.5 consumes** Phase 7's HALT 3 infrastructure (`app/chat/halt3_eval_set.yaml` + `app/chat/halt3_validator.py`) + the chat module surfaces Phase 7 wired (`tier2_db_query.py`, `tier2_handler.py`, `tier3_handler.py`, `disclosure_render.py`, `entity_catalog_query.py`, `entity_intent.py`). No new alembic migration expected.
>
> **Parallel-with-Phase-6.5 / Phase-8a caveat:** Phase 7.5 file scope is `app/chat/halt3_*` + `app/chat/disclosure_render.py` + `app/chat/entity_catalog_query.py` + `app/chat/entity_intent.py` + `app/chat/tier3_handler.py` + `app/chat/halt3_eval_set.yaml` + `tests/test_phase7_halt3_validation.py`. **Disjoint from Phase 6.5** (templates / static / routes / `app/api/routes/home.py`) and **disjoint from Phase 8a** (`app/conditions/` + `app/alerts/` + `app/api/routes/conditions.py` + `app/api/routes/alerts.py`). Triple-parallel dispatch (6.5 + 7.5 + 8a) is safe per gotcha #18 file-scope disjointness. **No alembic-collision risk** because Phase 7.5 ships no migration (Phase 8a is the only migration-shipping lane).
>
> **No operator prereq for Phase 7.5.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure code-tightening + eval-set-refinement work on top of Phase 7's HALT 3 infrastructure.
>
> **Operator decision-lock status:** the 3 Phase 7.5-relevant decisions are locked per `outputs/phase_7_close_out.md` + `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md`:
>
> 1. **Scope is closure, not new features.** Phase 7.5 triages + fixes + re-runs validator. NO new chat features. NO new categories. NO new alembic migration. NO new test files unless a fix introduces a behavior worth guarding.
> 2. **q07 confabulation is P0.** The chat fabricated entity citations on a missing-data query (0.50 confabulation rate). This is the exact failure mode HALT 3 was built to prevent. Investigate `entity_intent.detect_multi_domain_category_slugs()` + `tier3_handler.py` LLM prompt + `disclosure_render.py` cited-vs-uncited path. Tighten until missing-data queries return `i_dont_know` with 0 confab.
> 3. **`FEATURE_FLAG_DISCLOSURE_RENDERER` flip stays OUT-OF-BAND.** Cursor 7.5 does NOT flip the env var. After Cursor returns with 22/22 PASS, operator flips on Railway production manually + STATE.md "Recently shipped" entry notes both Phase 7.5 ship AND flag-flip date.
>
> **Author note:** authored 2026-05-20 by Cowork primary post-`36405c0` (Phase 7 close-out + HALT 3 report + Phase 7.5 polish-lane dispatch note pushed). Wrapper extracts and refines the §2 paste-into-Cursor template from `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` into the canonical dispatch-wrapper shape with clipboard pipeline.
>
> **Clipboard pipeline** (PowerShell 5.1 truncates large payloads; uses Notepad as synchronous router per session-2026-05-19 lesson #3):
> ```powershell
> Get-Content outputs\cursor_dispatch_prompt_phase_7_5.md | Select-Object -Skip 34 | Select-Object -SkipLast 43 | Out-File -FilePath $env:TEMP\phase_7_5_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_7_5_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-2026-05-19 lesson #2):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~6000–8000 bytes (Phase 7.5 is a smaller wrapper than feature lanes). <500 bytes = truncation; redo Notepad.

---

````
PHASE 7.5 — HALT 3 VALIDATOR TRIAGE + FLAG-FLIP CLOSURE

You are a focused polish-lane Cursor session. Phase 7 SHIPPED at 0a305e0
(chat ENTITY wiring + boat-mode + conditions + HALT 3 close-out + cross-
entity + snowbird-return view). The HALT 3 close-out's INFRASTRUCTURE is
shipped (app/chat/halt3_eval_set.yaml with 22 queries + app/chat/halt3_
validator.py + tests/test_phase7_halt3_validation.py). But the initial
validator run failed 10/22 (cited_coverage=42% missing_confab_max=0.50
all_passed=False). Your job is to close the gap to 22/22 PASS.

Read these first (in order):

1. outputs/phase_7_halt3_initial_run_report.md (per-query categorization +
   5 hypotheses to test -- this is your PRIMARY input)
2. outputs/phase_7_5_halt3_polish_lane_dispatch_note.md (sec1 scope + sec2
   approach + sec4 acceptance gate; companion brief to this wrapper)
3. outputs/phase_7_close_out.md (Phase 7 close-out; sec3 Finding #1
   documents the HALT 3 outcome + deferral decision)
4. app/chat/halt3_eval_set.yaml (the 22 queries with expected
   tier/disclosure/confabulation/notes)
5. app/chat/halt3_validator.py (validator runner + per-query check shape)
6. docs/maintainability/disclosure_renderer_spec.md (canonical spec)
7. app/chat/disclosure_render.py + entity_catalog_query.py + entity_intent.py
   + tier3_handler.py (likely fix surface)

Verify baseline at session start:

- python -m pytest --collect-only -q | tail -3  (expected: 2135 collected)
- python -m alembic current  (expected: c9d0e1f2a3b4 head)
- python -m alembic heads  (expected: c9d0e1f2a3b4 SINGLE head; no multi-head)
- python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml
  (expected initial: cited_coverage=42% missing_confab_max=0.50
  all_passed=False; 12 PASS / 10 FAIL)

REPORT THE OBSERVED VALUES (do NOT copy dispatch-body-claimed values --
session-2026-05-19 lesson #6).

Order of work:

1. TRIAGE every FAIL. For each of q02, q03, q06, q07, q10, q14, q16,
   q17, q21, q22:
   - Read the eval-set entry for that query (the query text + expected
     tier/disclosure/notes)
   - Run the query through the chat module manually (single-query
     filter via halt3_validator.py if supported, else manual chat
     invocation via app/chat/unified_router.py)
   - Examine: did the chat actually behave correctly + the eval is wrong?
     OR did the chat behave wrong + the eval is right?
   - Decide unambiguously per query: FIX CODE or PATCH EVAL SET
   - Document the decision in a per-query comment in halt3_eval_set.yaml
     OR in your sec12 commit-batch narrative

2. FIX THE P0 CASES FIRST:
   - q07 (confabulation; chat fabricated citations; 0.50 confab rate) --
     investigate entity_intent + tier3_handler + disclosure_render.
     Tighten until missing-data queries return i_dont_know with 0 confab.
     This is the smoking gun for the exact failure mode HALT 3 was built
     to prevent.
   - q06 + q22 (i_dont_know expected, got uncited; missing-data leakage)
     -- investigate disclosure_render path. Tighten until missing-data
     queries always route to i_dont_know, never produce uncited responses
     without explicit cite sources.

3. THEN THE P1 CASES (q03, q10, q14, q16, q17, q21; expected cited, got
   i_dont_know). Each may be:
   - Real bug: entity_catalog_query.py missing the entity --> fix matching
   - Eval-too-strict: entity not in catalog --> patch eval yaml
   - Tier-routing: entity reachable at different tier than expected -->
     adjust expected_tier in yaml OR re-classify the tier-routing
   Both code-fix and eval-patch are valid; document disposition per query.

4. THEN q02 (tier mismatch; expected tier=2 cited, got tier=3 i_dont_know).
   Lowest priority. Either:
   - Fix tier classifier
   - Patch eval set (eval may have expected wrong tier)

5. RE-RUN VALIDATOR after each significant change set. Iterate until
   22/22 PASS:
     python -m app.chat.halt3_validator app/chat/halt3_eval_set.yaml
   Goal output:
     cited_coverage=100% missing_confab_max=0.00 all_passed=True
     22 PASS / 0 FAIL

6. (OPTIONAL secondary cleanup) hint_extractor token-budget polish. The
   initial run logged 22 warnings of "hint_extractor: token usage exceeds
   soft budget (inp=~378 out=8)" -- one per query. Either tighten the
   hint_extractor prompt OR raise the soft-budget constant. Skip if
   non-trivial; document as remaining V1.5 carry if so.

7. PYTEST STAY GREEN. After your fixes:
   - tests/test_phase7_halt3_validation.py may need updates if eval set
     expectations changed
   - other tests/test_phase7_*.py should remain green
   - full suite should remain at >=2133 passed (baseline)
   - ruff clean

CONSTRAINTS:

- No new alembic migration. Phase 7.5 is code-side polish only.
- No FEATURE_FLAG_DISCLOSURE_RENDERER flip (operator does out-of-band
  post-validator-green).
- No new chat features. Tighten + fix existing surface only.
- No new test files unless a fix introduces a behavior worth guarding.
- File scope: app/chat/halt3_* + app/chat/disclosure_render.py +
  app/chat/entity_catalog_query.py + app/chat/entity_intent.py +
  app/chat/tier3_handler.py + tests/test_phase7_halt3_validation.py
  (the latter only if eval-set patches change test expectations).
  DO NOT touch app/templates/ or app/api/routes/ (Phase 6.5 scope) or
  app/conditions/ or app/alerts/ (Phase 8a scope) -- gotcha #18
  file-scope disjointness.
- Don't bash heredoc commit messages. PowerShell-safe.
- Re-verify python -m alembic current AND python -m alembic heads at end
  of session -- should return c9d0e1f2a3b4 (single head; unchanged).
  Report observed values.

DELIVER sec12 final report when complete (mirroring Phase 4 sec12 format
adapted for Phase 7.5):

- Baseline observed at start (pytest collect + alembic current + alembic
  heads + initial validator output)
- Final observed state (pytest collect + alembic current + alembic heads
  + FINAL validator output -- the goal is 22/22 PASS with cited_coverage
  100% + missing_confab_max 0.0 + all_passed True)
- Per-query disposition table for the 10 originally-FAILing queries
  (CODE-FIX or EVAL-PATCH per query + brief reason)
- Files touched (likely 4-7 files; modest scope)
- Pytest delta (likely 0 net-new tests OR small +1-3 for new guards;
  must stay >=2133 passed)
- Ruff status (must be clean)
- sec13 deviations (any departures from this wrapper's guidance)
- (If addressed) hint_extractor token-budget polish narrative
- HALT at the sec3 boundary; do NOT proceed to Phase 6.5 / Phase 8 /
  Phase 8b / other lanes
- DO NOT git add / commit / push / amend (operator commits the batch)
````

---

## After Cursor returns with the §12 report

Same rhythm as prior dispatch close-outs: paste back to Cowork primary chat, primary reviews against the Phase 7.5 acceptance gate (22/22 PASS + `cited_coverage=100%` + `missing_confab_max=0.00`), recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 0 new files (Phase 7.5 is closure work; no new features)
- 1 modified `app/chat/halt3_eval_set.yaml` (eval-set patches for queries where eval expectation was wrong)
- 1-4 modified `app/chat/disclosure_render.py` + `entity_catalog_query.py` + `entity_intent.py` + `tier3_handler.py` (code fixes)
- 0-1 modified `tests/test_phase7_halt3_validation.py` (only if eval-set patches change test expectations)
- 0 alembic migrations
- Potentially 1 modified `app/chat/halt3_validator.py` (only if validator logic itself has a bug; unlikely)

Expected pytest delta: 0 net-new (or +1-3 if fixes introduce new behavior worth guarding). Pre-existing tests must remain green.

Expected effort: 3-5 days dispatch per `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` §3. Could compress to 1-2 days if a single root cause explains many of the FAILs. Could stretch to 5-7 days if the eval set turns out to have wider semantic issues.

Expected pragmatic deviations:

1. Eval-set patches that change `expected_tier` (low-confidence eval-set adjustments may need cross-check)
2. Disclosure-renderer tightening that affects edge-case responses outside the eval set
3. hint_extractor token-budget polish vs defer to V1.5
4. Whether to gate the validator on per-query confab-rate as well (currently aggregate `missing_confab_max`)

## After Phase 7.5 ships

Update master plan §4 Phase 7 — append a Phase 7.5 ship-line under the existing Phase 7 SHIPPED entry. Update STATE.md "Recently shipped" with Phase 7.5 entry.

**Operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true` out-of-band on Railway production** post-Phase-7.5-ship. STATE.md entry should note both:
- Phase 7.5 ship SHA + commit chain
- Flag-flip date + Railway env-var change

The flag-flip is the substantive operator gate that closes the HALT 3 narrative arc. Without it, Phase 7.5's validator-going-green doesn't materialize as user-facing behavior change.

After Phase 7.5 + flag flip, the V1 chat surface honors the disclosure renderer's full contract — Phase 7's deliverable (d) is fully complete.

---

*Authored by Cowork primary at the post-`36405c0` session (2026-05-20). Lives at `outputs/cursor_dispatch_prompt_phase_7_5.md`. Companion docs: `outputs/phase_7_5_halt3_polish_lane_dispatch_note.md` (the brief), `outputs/phase_7_halt3_initial_run_report.md` (raw validator output + categorization), `outputs/phase_7_close_out.md` (Phase 7 close-out + Phase 7.5 deferral decision). No SHA-patch slots; dispatch-ready at authoring time. Parallel-eligible with Phase 6.5 + Phase 8a per gotcha #18 file-scope disjointness.*
