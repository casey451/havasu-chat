# Claude Code Dispatch Briefs — 2026-05-20

> **What this is:** two paste-ready Claude Code (CC) dispatch briefs for the small commit-shipping work that's pre-positioned but hasn't been applied yet. CC runs in a separate terminal session; this artifact gives you copy-paste prompts. Both briefs are fully independent + can run in any order or parallel.
>
> **Author:** Cowork primary, 2026-05-20 post-`6422df4`. Authored during Cursor 7.5's HALT 3 polish-lane grind window.
>
> **Disjoint from Cursor 7.5:** Cursor 7.5 touches `app/chat/halt3_*` + `disclosure_render.py` + `entity_catalog_query.py` + `entity_intent.py` + `tier3_handler.py` + `halt3_eval_set.yaml`. Brief A touches `app/contrib/google_types_mapping.py` + a new test file. Brief B touches `docs/maintainability/master_build_plan.md` + `docs/maintainability/dispatch_channels.md`. Both disjoint per gotcha #18; safe to run during Cursor 7.5's flight window.

---

## Brief A — Apply sustainability extensions (closes triage §8 #1)

**What:** apply the pre-positioned artifact at `outputs/sustainability_extensions_apply.md` to ship the 14 deferred sustainability-layer mapping carries from Phase 5.7 + 5.9 + 5.10 + 5.11.

**Where to run:** open a fresh Claude Code terminal session in `C:\Users\casey\projects\havasu-chat`.

**Paste-ready prompt:**

```
Apply the sustainability-layer extensions per outputs/sustainability_extensions_apply.md.

The artifact has the exact patch in §2 (4 blocks) + the new test file content
in §3 + the apply recipe in §4. Execute the full recipe end-to-end:

1. Verify Cursor 7.5 is NOT touching app/contrib/google_types_mapping.py
   per git status (it shouldn't be; Cursor 7.5 file scope is app/chat/halt3_*
   + disclosure_render.py + entity_catalog_query.py + entity_intent.py +
   tier3_handler.py + halt3_eval_set.yaml).

2. Verify alembic heads returns SINGLE head (c9d0e1f2a3b4) before starting:
   python -m alembic heads

3. Apply the 4 patch blocks from §2 to app/contrib/google_types_mapping.py
   at the specified line anchors (after lines 146, 286, 208, 254
   respectively). Use anchored edits; do NOT rewrite the existing file.

4. Create tests/test_sustainability_extensions.py with the content from §3
   (parametrized test for 14 mappings + 1 omission guard for `church`;
   15 tests total).

5. Run the test guard alone:
   python -m pytest tests/test_sustainability_extensions.py -v
   Expected: 15 passed.

6. Run ruff:
   ruff check app/contrib/google_types_mapping.py tests/test_sustainability_extensions.py
   Expected: 0 issues.

7. (Optional) Run a focused regression check:
   python -m pytest tests/test_phase5_*.py tests/test_places_load*.py -q
   Expected: all green (no regressions on Phase 5 tests; sustainability
   layer extensions are additive).

8. Stage + commit using PowerShell-safe multi-line `-m` flags (NO bash
   heredocs). Recipe at §4 of the artifact has the exact commit message
   text — copy verbatim.

9. Push: git push origin main

Report back: SHA + files touched + pytest delta + ruff status + any
deviations encountered. Do NOT run the full pytest suite (would conflict
with Cursor 7.5's mid-flight pytest runs in its parallel session). The
test guard run + focused regression check are sufficient.
```

**Expected outcome:** single `chore(data): sustainability layer direct mappings -- 5.7+5.9+5.10+5.11 V1.5 carries` commit, ~44 lines net in `app/contrib/google_types_mapping.py` + new test file with 15 tests. Alembic head unchanged.

---

## Brief B — Apply Phase 13 V1.5 backlog patch (Option A) + fold alembic-collision gotcha (closes triage §8 #4 + gotcha durability)

**What:** two small docs commits applying pre-positioned artifacts:
1. `outputs/master_plan_phase_13_carry_forward_patch.md` Option A → master plan §4 Phase 13 (closes triage §8 #4)
2. `outputs/dispatch_channels_alembic_collision_gotcha_draft.md` → fold into `docs/maintainability/dispatch_channels.md` as next sequential gotcha number

**Where to run:** open a fresh Claude Code terminal session in `C:\Users\casey\projects\havasu-chat`.

**Paste-ready prompt:**

```
Two small docs commits per the pre-positioned artifacts. Run them in
sequence:

=== COMMIT 1: Phase 13 V1.5 backlog patch (Option A) ===

Apply outputs/master_plan_phase_13_carry_forward_patch.md sec2 (Option A)
to docs/maintainability/master_build_plan.md §4 Phase 13. The patch
appends a 'Phase 5 carry-forward' sub-section after the existing 11-item
bullet list (end of line ~526 'Native review system'), before the `---`
separator at line ~528. Exact content block is in §2 of the artifact.

Use anchored edit; do NOT rewrite the master plan. Verify the diff is
~15 lines added under §4 Phase 13.

Stage + commit using PowerShell-safe multi-line `-m` flags. Recipe at
§3 of the artifact has the exact commit message — copy verbatim. The
commit message should reference 'triage sec8 #4 Option A' as the closure.

=== COMMIT 2: Fold alembic-collision gotcha into dispatch_channels.md ===

Apply outputs/dispatch_channels_alembic_collision_gotcha_draft.md to
docs/maintainability/dispatch_channels.md. The draft has paste-ready
content in its top section. The fold steps in §1 of the draft:

1. Read docs/maintainability/dispatch_channels.md and find the current
   last gotcha number (probably #18 or #19; verify).
2. Sequence the new alembic-collision gotcha as #N (next available
   number).
3. Paste the gotcha content from the draft into dispatch_channels.md at
   the correct sequence position.
4. (Optional) Add a one-line cross-reference under gotcha #18 (file-scope
   disjointness): "See also: gotcha #N -- alembic revision DAG is global;
   file-scope disjointness doesn't cover it."

Stage + commit using PowerShell-safe `-m` flags. Commit shape in §1 of
the draft. Subject suggestion: 'docs(maintainability): gotcha #N -- alembic
revision DAG is global; parallel sessions must coordinate migrations
explicitly'.

=== AFTER BOTH COMMITS ===

Push: git push origin main

Verify the 2 new commits appear in git log:
git log --oneline -3

Report back: 2 SHAs + files touched + commit subjects + the gotcha number
used (so we can update STATE.md / future references accordingly).

Do NOT run pytest (no code changes; pytest would conflict with Cursor 7.5).
Do NOT touch app/ files (master_build_plan.md + dispatch_channels.md only).
```

**Expected outcome:** two small docs commits (`docs(master_plan): ...` + `docs(maintainability): gotcha #N ...`). Master plan §4 Phase 13 now cross-references the 39 V1.5-defer items. dispatch_channels.md has the alembic-collision gotcha durable.

---

## §3 Coordination notes

**Both briefs are disjoint from each other.** Brief A touches `app/contrib/` + new test file. Brief B touches `docs/maintainability/` only. They could even run in parallel CC sessions (no race risk).

**Both disjoint from Cursor 7.5.** Cursor 7.5 is on `app/chat/` + chat-module-specific test file. No file overlap.

**Sequencing recommendation:** run Brief A first (more substantive; the test guard validates the mappings). Brief B is pure docs; runs in <10 min CC time.

**Don't push between briefs if running them both close-together.** Single push at the end suffices (or push after each — either works; both pushes will fast-forward cleanly).

**After both briefs land:**
- 2-3 new commits on origin (1 for Brief A + 1-2 for Brief B depending on how CC sequences the gotcha fold)
- Triage §8 #1 + §8 #4 both CLOSED
- Alembic-collision gotcha durable in `dispatch_channels.md`
- The pre-positioned artifacts at `outputs/sustainability_extensions_apply.md` + `outputs/master_plan_phase_13_carry_forward_patch.md` + `outputs/dispatch_channels_alembic_collision_gotcha_draft.md` become historical (applied; could remain in `outputs/` as ledger or be removed at operator discretion)

---

## §4 What this artifact does NOT do

- Does NOT dispatch CC for you (CC is operator-initiated; you paste the brief into a separate terminal)
- Does NOT touch any files (just provides the paste-ready prompts)
- Does NOT block on Cursor 7.5 — both briefs run independently
- Does NOT include manual smoke checks beyond what each brief explicitly states

---

*Authored by Cowork primary at the post-`6422df4` session (2026-05-20). Lives at `outputs/cc_dispatch_briefs_2026_05_20.md`. Two paste-ready CC dispatch prompts for the small commit-shipping work that's pre-positioned. Both disjoint from Cursor 7.5's HALT 3 polish lane per gotcha #18. Operator fires CC at convenience; this artifact stays as the brief.*
