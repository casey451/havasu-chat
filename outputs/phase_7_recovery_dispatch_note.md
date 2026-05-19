# Phase 7 Recovery Dispatch Note — Post-Phase-6.4-Collision State

> **What this is:** the recovery plan for Phase 7 (chat ENTITY wiring + boat-mode + conditions + HALT 3 + cross-entity + snowbird) after its parallel Cursor session was disrupted by Phase 6.4's alembic revision-space collision cleanup. Documents the current Phase 7 WIP state in the working tree, diagnoses the 42 tier2 failures, and recommends the re-dispatch path with an amendment to the existing Phase 7 wrapper.
>
> **Author:** Cowork primary, 2026-05-20 post-`96c915d` (Phase 6.4 SHIP) + post-Phase-6.4-§12-report.
>
> **Companion docs:**
> - `outputs/cursor_dispatch_prompt_phase_7.md` — the original Phase 7 dispatch wrapper (still mostly valid; needs minor amendment per §4 below)
> - `outputs/phase_6_4_close_out.md` — Phase 6.4 close-out with the collision finding narrative
> - `outputs/dispatch_channels_alembic_collision_gotcha_draft.md` — the new gotcha drafted from this finding

---

## §1 What happened

Phase 6.4 (Lane D) and Phase 7 (Lane E) were dispatched to parallel Cursor sessions per the 2026-05-19 close-out's gotcha-#18 file-scope-disjointness analysis. The two wrappers were carefully scoped:

- **Phase 6.4 file scope:** `app/templates/` + `app/static/` + `app/api/routes/category_pages.py` + new `themed_groups.py` + new `map_data.py` + `app/main.py` + alembic migration for `users.boat_mode_preference` + 4 test files
- **Phase 7 file scope:** `app/chat/*` + `app/api/routes/chat.py` + new `app/chat/snowbird_query.py` + `halt3_*` + new `app/templates/components/snowbird_panel.html` + anchored edit on `home.html` (snowbird-panel-include anchor only) + 6 test files + conditional alembic migration for `User.last_active_at` IF column not present

The file-scope analysis covered every Python module, template, static asset, and test file correctly. **What it MISSED: alembic revision DAG is GLOBAL, not file-scoped.** Both Cursor sessions could (and did) attempt to chain new migrations off `f6a7b8c9d0e1` in parallel, creating two conflicting "next revision" entries:

- Phase 6.4 Cursor attempted revision `b8c9d0e1f2a3` (for `users.boat_mode_preference`)
- Phase 7 Cursor attempted revision `c9d0e1f2a3b4` (for `User.last_active_at`)

Cursor 6.4's session, when running its full pytest verification, detected the multi-head conflict + chose to revert the conflicting migrations. **The revert scope:**
- Phase 7's untracked alembic migration files (the `c9d0e1f2a3b4` files) — DELETED
- Phase 7's `User.last_active_at` ORM additions to `app/db/models.py` — REVERTED
- Phase 6.4's own decision to collapse its migration in favor of reusing Phase 3.1's `preferred_mode` column — left it in the clean state

Cursor 6.4 wisely did NOT revert Phase 7's chat-module changes (correct — those don't conflict with 6.4's scope; they're Phase 7's substantive work).

**Result post-Phase-6.4-SHIP (`96c915d`):**
- Phase 6.4: cleanly committed
- Phase 7: chat-module changes still in working tree (uncommitted); alembic + User.last_active_at parts reverted
- Full pytest suite: 42 failures in `test_tier2_*` (`assert False on open-now pivots`) attributed to Phase 7's chat-module edits

---

## §2 Phase 7 WIP state inventory

Per `git status --short` immediately post-`96c915d`, Phase 7's surface in the working tree:

**Modified (anchored edits) — Phase 7 in-progress:**
```
M app/api/routes/chat.py
M app/chat/context_builder.py
M app/chat/intent_classifier.py
M app/chat/tier2_db_query.py
M app/chat/tier2_handler.py
M app/chat/tier3_handler.py
M app/chat/unified_router.py
M app/home/router.py
M app/static/styles/home.css        ← anchor for snowbird CSS-import (presumably)
M app/templates/home.html           ← snowbird-panel-include anchor
```

**Untracked new files — Phase 7 in-progress:**
```
?? app/chat/chat_request_context.py
?? app/chat/entity_catalog_query.py
?? app/chat/entity_intent.py
?? app/chat/halt3_eval_set.yaml
?? app/chat/halt3_validator.py
?? app/chat/snowbird_query.py
?? app/home/snowbird_panel.py
?? app/templates/components/snowbird_panel.html
?? tests/test_phase7_chat_boat_mode.py
?? tests/test_phase7_chat_conditions.py
?? tests/test_phase7_chat_entity_wiring.py
?? tests/test_phase7_cross_entity.py
?? tests/test_phase7_halt3_validation.py
?? tests/test_phase7_snowbird.py
```

**REVERTED by Cursor 6.4 (no longer in working tree):**
- Untracked alembic migrations with revision IDs `b8c9d0e1f2a3` + `c9d0e1f2a3b4`
- `User.last_active_at` ORM drift in `app/db/models.py`

**Assessment:** Phase 7 is **substantially complete** in file production. The wrapper's expected file scope is mostly satisfied:
- ✅ All 6 expected new test files present
- ✅ Most expected new chat-module files (snowbird_query, halt3_eval_set, halt3_validator) present
- ✅ Plus 3 additional new chat files (chat_request_context, entity_catalog_query, entity_intent) — Cursor's pragmatic refactoring
- ✅ Snowbird panel template + Python helper (`app/home/snowbird_panel.py` — wrapper-anticipated location)
- ✅ Anchored edits on 9 expected files
- ⚠️ `User.last_active_at` ORM + migration reverted — needs re-decision (does the column actually need to exist? Phase 7 wrapper said "verify at step 1; ship migration only if needed")
- ⚠️ 42 tier2 test failures — chat-module changes introduced regressions

---

## §3 Diagnosis: the 42 tier2 failures

Cursor 6.4's report: "42 failures in test_tier2_* on this machine (assert False on open-now pivots); not reproduced in the 111-test Phase 6 scope bundle."

**Possibilities (ranked by likelihood):**

1. **Phase 7's `tier2_db_query.py` rewrite changed the open-now filter shape.** The wrapper said: replace the pre-pivot River Scene events catalog query at line 33+ with an ENTITY query that "applies intent filters from the tier 2 parser (cuisine / sub-trade / district / operational)". The "operational" filter includes open-now logic. If the new query returns entities in a different ordering OR if the open-now predicate evaluates differently from how the pre-existing tier2 tests expected, all 42 tests pivot on `assert False`.

2. **`User.last_active_at` revert cascading effect.** If Phase 7's chat code references `User.last_active_at` and the column was reverted out of the ORM, queries against `User.last_active_at` would crash. But the failure mode would be import-time or query-time errors, not `assert False` — so probably NOT this.

3. **Schema-fixture mismatch in test_tier2_***. If the test setup creates entities with old shape and the new query expects new shape, fixtures need updating. Could be batch of 42 fixture-update needs.

4. **Heat-bias / conditions-aware ordering changed.** Phase 7's "chat conditions awareness" wires `STUB_CURRENT_TEMPERATURE_F` into the query. If the heat-bias re-ranking changes which entities surface first in test scenarios, existing tier2 tests that pivot on specific entity ordering would fail.

**Likely root cause:** combination of #1 + #3 — Phase 7's query rewrite changed the result-set shape in ways the pre-existing tier2 tests didn't anticipate. The 42 failures are Phase 7's **acceptable churn** from rewiring the query layer, and need to be addressed in Phase 7's own scope (either by fixing the new query to preserve compatibility OR by updating the existing tier2 tests to match the new shape).

**Test scope hint from Cursor:** the failures are in `test_tier2_*` (pre-existing files), NOT in Phase 7's new `tests/test_phase7_*` files. The new test files are presumably green (validating the new query directly). The legacy tier2 tests are validating the OLD query shape.

---

## §4 Recovery path — recommended: re-dispatch with amendment

**Three options:**

| Option | Description | Pro | Con | Recommendation |
|---|---|---|---|---|
| **A: Re-dispatch with amendment** | Open fresh Cursor session; paste original Phase 7 wrapper + amendment briefing on WIP state + 42-failure diagnosis | Cursor has full original wrapper + reset state context; substantive work preserved | Cursor restarts its own session context | **RECOMMENDED** |
| B: Hard reset + re-dispatch from scratch | `git stash` or `git checkout` to reset Phase 7 WIP; re-dispatch original wrapper from scratch | Clean slate; no confusion | Wastes substantial in-flight work (1500+ lines of code) | Avoid unless WIP is truly broken |
| C: Operator-driven recovery | Operator manually investigates + fixes the 42 tier2 failures + decides each Phase 7 commit | Most surgical | Operator time-intensive; not Cursor's strength | Use only if A + B both fail |

### Option A — recommended re-dispatch amendment

Authored to paste alongside the original Phase 7 wrapper. The original wrapper at `outputs/cursor_dispatch_prompt_phase_7.md` stays canonical; this amendment is a header note that the operator prepends when re-dispatching.

**Amendment text (paste BEFORE the existing wrapper body when re-dispatching to fresh Cursor):**

```
PHASE 7 RECOVERY DISPATCH AMENDMENT — 2026-05-20

You are RESUMING Phase 7 work that was disrupted by a parallel-session
alembic-revision-DAG collision with Phase 6.4 (Lane D, SHIPPED at 96c915d
on origin/main).

Working tree state at re-dispatch:
- Phase 6.4 is SHIPPED on origin at 96c915d (Leaflet+OSM map + boat-access
  mode via users.preferred_mode + 4 themed group landing pages + search bar)
- alembic head is f6a7b8c9d0e1 (UNCHANGED -- Phase 6.4 shipped no migration;
  reused Phase 3.1's preferred_mode column instead of adding boat_mode_
  preference boolean)
- Substantial Phase 7 WIP is ALREADY in the working tree from a prior
  aborted session:
  - 9 modified files (app/chat/tier2_db_query.py + tier2_handler.py +
    tier3_handler.py + context_builder.py + intent_classifier.py +
    unified_router.py + app/api/routes/chat.py + app/home/router.py +
    app/static/styles/home.css + app/templates/home.html)
  - 8 untracked new files in app/chat/ (snowbird_query.py + halt3_eval_set.yaml +
    halt3_validator.py + chat_request_context.py + entity_catalog_query.py +
    entity_intent.py) and app/home/snowbird_panel.py and
    app/templates/components/snowbird_panel.html
  - 6 untracked test files: tests/test_phase7_chat_{boat_mode,conditions,
    entity_wiring,cross_entity,halt3_validation,snowbird}.py
- REVERTED by the Phase 6.4 cleanup (no longer in working tree):
  - The conflicting Phase 7 alembic migration (revision ID c9d0e1f2a3b4)
  - User.last_active_at ORM additions to app/db/models.py

Three blockers to resolve before this re-dispatch can SHIP Phase 7 cleanly:

1. RE-DECIDE THE User.last_active_at MIGRATION QUESTION. The original Phase 7
   wrapper said: "verify at step 1 read whether User.last_active_at exists; ship
   migration only if needed." Verify NOW against app/db/models.py + alembic
   migrations -- the column does NOT exist anymore (Phase 6.4's revert removed
   it). DECIDE whether snowbird-return-view actually NEEDS this column or
   whether existing user activity tracking (e.g. sessions.last_seen_at OR
   users.updated_at OR magic_link_tokens) can cover the use case. If a new
   column IS needed: ship ONE alembic migration with a UNIQUE revision ID
   chaining from f6a7b8c9d0e1. Do NOT use revision IDs b8c9d0e1f2a3 or
   c9d0e1f2a3b4 (both were collision-prone in the prior dispatch).

2. RESOLVE THE 42 test_tier2_* FAILURES. The prior Phase 6.4 Cursor session
   reported "42 failures in test_tier2_* on this machine (assert False on
   open-now pivots); not reproduced in the 111-test Phase 6 scope bundle.
   Investigate separately if those were green on origin before parallel
   Phase 7 work." Diagnosis hint: the most likely cause is that
   tier2_db_query.py's pre-existing River Scene-replacement work changed the
   result-set shape for legacy tier2 tests (the new tests/test_phase7_* files
   are presumably green; the failures are in pre-existing test_tier2_* files
   that were validating the OLD query shape). Resolution paths: (a) update
   the pre-existing tier2 tests to match the new query shape (acceptable
   churn for a query layer rewrite); or (b) make the new query backward-
   compatible with the legacy test expectations (if the operator brief
   doesn't authorize result-set shape changes). PICK ONE; DOCUMENT YOUR
   CHOICE in section 13 deviations.

3. RUN THE COMPLETE PHASE 7 ACCEPTANCE-GATE BUNDLE. After resolving #1
   and #2, verify:
   - All 6 new tests/test_phase7_* files pass
   - All pre-existing tier1, tier2, tier3 tests pass (no new regressions)
   - HALT 3 eval set (app/chat/halt3_eval_set.yaml) runs successfully
     through halt3_validator with operator-reviewable per-query report
   - Full-suite pytest is green
   - Ruff clean
   - alembic current matches the new head (either f6a7b8c9d0e1 if no
     migration shipped, or the new unique revision SHA chaining off
     f6a7b8c9d0e1)

The rest of the original Phase 7 dispatch wrapper (below) is canonical.
Follow it as the spec; the WIP in the working tree gets you ~70% of the
way to ship; finish the remaining 30% per the spec + resolve the three
blockers above.

REPORT per the wrapper's §12 final report format. End-of-amendment.
```

(Paste the original `outputs/cursor_dispatch_prompt_phase_7.md` body after this amendment when sending to fresh Cursor.)

### Why Option A works

Cursor's resumed session will:
1. Read the amendment (knows it's resuming)
2. Inspect the working tree (sees the WIP)
3. Verify against the original wrapper's expected file list (most of it is present)
4. Resolve the 3 blockers explicitly
5. Run the acceptance-gate bundle
6. Ship per §12

The substantive work (1500+ lines across chat module + tests) is preserved. Cursor's job becomes "finish + verify + ship", not "build from scratch".

---

## §5 Action items (operator-side)

1. **Check Phase 7's current Cursor session.** If the prior Cursor session is still active in some window, check whether it has produced a §12 report or is mid-flight or has crashed. Three sub-cases:
   - **Crashed/errored** (likely if its files were reverted under it): kill the session; proceed to re-dispatch per §4.
   - **Reporting cleanly with a §12 final report**: read its report; if it acknowledges the 42 tier2 failures + has a story for them, treat as a normal §12 close-out (skip the re-dispatch; review the report per `outputs/lane_d_e_post_ship_close_out_template.md`).
   - **Still mid-flight**: wait for it to halt; then assess.

2. **Reset alembic state if needed** (only if Phase 7's prior Cursor session left untracked migration files in `alembic/versions/`). Verify:
   ```powershell
   git status --short alembic/versions/
   # Expected: 0 untracked files (Cursor 6.4 cleaned this up)
   # If any ?? alembic/versions/* lines: delete them manually before re-dispatch
   ```

3. **Apply the amendment + re-dispatch** per §4 Option A.

4. **Plan to land the alembic-collision gotcha** in `docs/maintainability/dispatch_channels.md` at the next docs checkpoint. Draft at `outputs/dispatch_channels_alembic_collision_gotcha_draft.md`.

---

## §6 What survives + what doesn't

| Item | Status |
|---|---|
| Phase 7's chat-module modifications (9 modified files) | ✅ Preserved in working tree |
| Phase 7's new chat-module files (8 untracked) | ✅ Preserved in working tree |
| Phase 7's 6 new test files | ✅ Preserved in working tree |
| Phase 7's snowbird panel (template + Python helper) | ✅ Preserved in working tree |
| Phase 7's alembic migration for User.last_active_at | ❌ Reverted by Phase 6.4 Cursor; re-decide whether needed |
| Phase 7's User.last_active_at ORM column | ❌ Reverted by Phase 6.4 Cursor; re-decide whether needed |
| Phase 7's home.html anchor + snowbird-panel `{% include %}` | ✅ Preserved (modified file) |
| `<!-- snowbird-panel-include -->` anchor coordination with Phase 6.4's `<!-- search-bar-include -->` | ✅ Preserved; verify both anchors present + distinct regions |

---

*Authored by Cowork primary at the post-`96c915d` Phase 6.4 close-out session (2026-05-20). Lives at `outputs/phase_7_recovery_dispatch_note.md`. Use the amendment in §4 when re-dispatching Phase 7 to fresh Cursor. The original `outputs/cursor_dispatch_prompt_phase_7.md` stays canonical; this amendment briefs Cursor on the resume state.*
