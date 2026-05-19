# Dispatch Channels Gotcha Draft — Alembic Revision DAG Is Global

> **What this is:** a draft gotcha for `docs/maintainability/dispatch_channels.md` capturing the lesson from the Phase 6.4 + Phase 7 parallel-dispatch collision (2026-05-20). The pattern: file-scope disjointness (gotcha #18) was NECESSARY but not SUFFICIENT for safe parallel Cursor dispatches. The alembic migration revision DAG is global and creates collision risk that file-scope analysis misses.
>
> **Author:** Cowork primary, 2026-05-20 post-`96c915d`.
>
> **Fold into:** `docs/maintainability/dispatch_channels.md` at next docs checkpoint. Probable gotcha number: next after the existing chain (~#19 or #20 depending on what's already landed via the `session_23_extension_3_gotchas_draft.md` predecessor draft). Operator confirms the number at fold time.
>
> **Pairs with:** existing gotcha #18 (file-scope disjointness). This is the COMPLEMENT — adds the global-resource-disjointness corollary.

---

## Proposed gotcha text (paste-ready for dispatch_channels.md)

### Gotcha #N — Alembic revision DAG is global; parallel sessions must coordinate migrations explicitly

**Discovered:** 2026-05-20 during Phase 6.4 + Phase 7 parallel Cursor dispatch.

**Symptom:** Two parallel Cursor sessions both authored alembic migration files chaining off the same head SHA. Their independently-chosen revision IDs (`b8c9d0e1f2a3` from Phase 6.4 for `users.boat_mode_preference`; `c9d0e1f2a3b4` from Phase 7 for `User.last_active_at`) BOTH wanted to be the next revision after `f6a7b8c9d0e1`. Result: a multi-head DAG state when both sessions tried to commit, with neither head able to ship cleanly. The session that ran its full pytest verification first (Phase 6.4) detected the conflict and reverted the OTHER session's migration + ORM-drift to land cleanly.

**Root cause:** Gotcha #18 (file-scope disjointness) covers Python modules + templates + static assets + test files — every file each session writes to was disjoint. But alembic's revision space is GLOBAL across the repo: any new migration writes to `alembic/versions/<revision_id>_<slug>.py` AND modifies the parent revision's `down_revision` reference. Two parallel sessions chaining off the same head create two would-be heads, which is a DAG inconsistency that alembic detects only at upgrade-cycle test time or at deploy time.

**Why file-scope analysis missed it:** the file-scope analysis correctly flagged `alembic/versions/` as a directory NEITHER wrapper explicitly added to its expected file list. But BOTH wrappers conditionally said "ship a migration if needed" — and both decided "yes, ship one". The conditional migration shapes weren't explicit in the gotcha-#18 disjointness check.

**Cure pattern (pick one):**

- **(a) Serial dispatch when both contemplate migrations.** If both parallel lanes' wrappers say "ship a migration if needed", default to sequential dispatch instead of parallel. One ships first (`alembic head` advances); the second rebases its migration against the new head before dispatch.
- **(b) Schema-reuse collapse.** Review whether one lane's migration is actually NECESSARY vs. reusing an existing column. Phase 6.4 ultimately took this path — reused Phase 3.1's `users.preferred_mode` instead of adding `users.boat_mode_preference`. If reuse is possible, collapse the migration in the wrapper before dispatch. The wrapper says: "verify column doesn't exist before authoring migration" — that's the right reuse-check gate.
- **(c) Pre-coordinate revision IDs in the wrapper.** If both lanes MUST ship migrations + serialization isn't feasible, assign revision IDs explicitly in each wrapper (rather than letting Cursor pick). Wrap the migration shape with explicit `down_revision = "<head>"` + a manually-chosen `revision = "<unique>"`. Future ships rebase manually if heads shift.

**Cure pattern preference:** **(a) serial > (b) reuse > (c) pre-coordinate.** Sequential dispatch is the lowest-cognitive-load fix; schema reuse is the second-best when one of the migrations turns out to be unnecessary; pre-coordination is brittle and should only be used when both migrations are required + serialization is impossible.

**Companion lesson — multi-head detection at acceptance-gate time:** Cursor 6.4's session caught the collision by running `python -m pytest -q` against the full suite, which exercised both heads. Lesson: dispatch wrappers should explicitly instruct Cursor to run `python -m alembic heads` (note: PLURAL) and verify a SINGLE head is returned before declaring `§12` complete. If multiple heads are returned, HALT and report.

**Future dispatch wrapper amendment (recommended):** add to the §"What NOT to do" section of any wrapper that contemplates an alembic migration:

> - Don't author a new alembic migration without first checking the parallel-lane wrapper(s) for migration intent. If the parallel lane also contemplates a migration off the same head, HALT and ask the operator to serialize the dispatches OR coordinate revision IDs explicitly.

And add to the §"Pre-dispatch checklist":

> - `python -m alembic heads` returns a SINGLE head (the one expected by this dispatch's chain). If multiple heads exist, fix the multi-head state before paste.

**Real-world reference:** Phase 6.4 + Phase 7 collision 2026-05-20. Recovery handled in `outputs/phase_7_recovery_dispatch_note.md`. Phase 6.4 SHIPPED at `96c915d`; Phase 7 needs re-dispatch with unique revision ID if a migration is still needed (the recovery note proposes operator re-decide whether the migration is actually necessary).

---

## §1 How to fold this in

When the next docs checkpoint touches `docs/maintainability/dispatch_channels.md`:

1. Open `docs/maintainability/dispatch_channels.md`.
2. Find the current last gotcha number (probably gotcha #18 or #19 depending on whether `session_23_extension_3_gotchas_draft.md` was folded in yet). Sequence the alembic-collision gotcha as #N (next available number).
3. Paste the gotcha text from above into the file at the correct sequence position.
4. Optionally add a one-line cross-reference under gotcha #18:
   > See also: gotcha #N — alembic revision DAG is global; file-scope disjointness doesn't cover it.
5. Update the Phase 8 + Phase 9 dispatch wrappers (if/when authored) to apply the wrapper-amendment guidance (the "What NOT to do" + "Pre-dispatch checklist" additions described above).

**Commit shape (typical):**
```powershell
git add docs/maintainability/dispatch_channels.md
git commit `
  -m "docs(maintainability): gotcha #N -- alembic revision DAG is global; parallel sessions must coordinate migrations explicitly" `
  -m "Captures the Phase 6.4 + Phase 7 parallel-dispatch collision finding 2026-05-20 (commit 96c915d). File-scope disjointness (gotcha #18) is NECESSARY but not SUFFICIENT for safe parallel Cursor dispatches -- the alembic migration revision DAG is global and creates collision risk that file-scope analysis misses. Cure patterns: (a) serial dispatch when both contemplate migrations; (b) schema-reuse collapse; (c) pre-coordinate revision IDs. Companion lesson: dispatch wrappers should explicitly check 'alembic heads' (plural) for multi-head state at acceptance-gate time. Draft at outputs/dispatch_channels_alembic_collision_gotcha_draft.md."
```

---

## §2 Why this matters for future dispatches

The Phase 6.4 + Phase 7 collision was caught + recovered cleanly because:
1. Cursor 6.4's session ran its full pytest verification proactively (which exercises the multi-head state)
2. Cursor 6.4 made a sensible decision to revert the conflicting WIP rather than fail the verification
3. The operator brief had `outputs/phase_7_recovery_dispatch_note.md` authored quickly post-collision

But the recovery cost ~1-2 days of calendar lag (the Phase 7 re-dispatch + verify + ship cycle). For a project with 6-9 month total budget, that's not a major hit. **For future parallel dispatches contemplating migrations, this gotcha gives operators the framework to avoid the lag entirely** — either by serializing (most common cure) or by pre-checking + collapsing (when reuse is feasible).

Pre-Phase-7 + Phase 8 parallel dispatch (the next likely parallel-lane opportunity): both lanes might want migrations. Phase 7 (User.last_active_at if column doesn't exist). Phase 8 (external_conditions_cache table is mandatory). If both dispatch in parallel, the gotcha pattern recurs. **Recommended posture: serialize Phase 7 then Phase 8** — Phase 7's migration question may collapse to "no migration needed" (reuse `sessions.last_seen_at` or similar), in which case Phase 8 is the only migration-shipping lane + can dispatch normally.

---

*Authored by Cowork primary at the post-`96c915d` Phase 6.4 close-out session (2026-05-20). Lives at `outputs/dispatch_channels_alembic_collision_gotcha_draft.md`. Fold into `docs/maintainability/dispatch_channels.md` at next docs checkpoint per §1.*
