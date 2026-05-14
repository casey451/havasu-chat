# New-Chat Kickoff — Phase 5 (restructured: 5.0 + 5.1–5.6)

> **Operator:** paste the fenced block below into a fresh Cowork chat. It starts a clean Phase 5 Cowork primary at the 5.0 boundary, post-restructure. This supersedes the older `outputs/new_chat_kickoff_phase_5.md` (which predates the 5.0/5.1–5.6 restructure).
>
> **Why a fresh chat:** the prior Phase 5 chat ran long and hit an `AskUserQuestion` tool-infrastructure freeze. A fresh chat picks up clean with the restructured framing.

---

```
You are Cowork primary for the havasu-chat project, running a fresh chat dedicated to PHASE 5 (Tier 1 data gathering), restructured 2026-05-14 into Phase 5.0 (shared lead-up + tooling) + Phase 5.1–5.6 (one sub-phase per Tier 1 category).

A separate Cowork agent is running PHASE 6 (Tier 1 UI build) IN PARALLEL. Coordinate via origin commits — both chats pull origin/main at session start; both edit only files in their declared scope (gotcha #18). Phase 5 chat scope: app/contrib/* + scripts/* + app/db/* + outputs/*. Phase 6 chat scope: app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + new app/api/routes/* + new tests/test_phase6_*.py. Shared docs (docs/STATE.md, docs/maintainability/*) are NOT in either declared scope — coordinate explicitly before touching them.

## State of origin (verify with `git log --oneline -12`)

Phase 4 SHIPPED. Phase 5.0 is largely SHIPPED on origin already:
- ac94b6c feat(phase4.4): Phase 4 close-out — SHIPPED
- 08bca69 / 62ab3b7 / b755b03 — Phase 5 prep + lead-up content + §3.1.a-c + §3.4.k locks
- acf5e2b — §3 11-decision lock-batch sealed (brief §2 + prereq §3.5)
- 54ca07d — heat_exposure priority-30 scaffold
- 4ba29e4 — Lane B §4 verification briefing
- 0331102 — busted-quote filename cleanup
- 23a6a1c — Phase 5 lead-up tooling Cursor dispatch prompt
- (possibly more — the parallel Phase 6 agent may have pushed; pull origin/main first and read any unfamiliar commits)

Alembic head on origin: 0a1b2c3d4e5f. Production deploy: still pre-Phase-4 (Railway redeploy is a Phase 5.0 operator action, pending). Pytest baseline: ~1803 collected (verify — Phase 6 agent may have added tests).

## Reading list (first session, in order)

1. docs/STATE.md — production state + recently shipped + session lessons (gotcha #15 sandbox-bash-git staleness, gotcha #16 no embedded double-quotes in -m bodies, gotcha #18 parallel-chat file-scope lock)
2. outputs/phase5_restructure_master_plan_patch.md — the 5.0 + 5.1–5.6 restructure; ALREADY APPLIED to master_build_plan.md §4 on 2026-05-14 (this artifact is now the historical record of the change, not a pending task)
3. outputs/phase5_prereq_checklist.md — 11 operator decisions (all locked, §3.5) + 10 §4 external verifications + workload audit
4. outputs/cursor_brief_phase_5_tier_1_data.md — §2 locked decisions + §3.1–§3.6 per-category playbooks (these become Phase 5.1–5.6)
5. outputs/cursor_dispatch_prompt_phase5_leadup_tooling.md — the Cursor dispatch for Lane B verifications + the 3 tooling-touchup scripts (SHIPPED 23a6a1c; awaiting operator to dispatch into Cursor)
6. outputs/phase5_lane_b_verification_briefing.md — the spec the above Cursor dispatch executes
7. outputs/heat_exposure_priority_30_list.md — scaffold; needs operator amendment (22 LHC-venue placeholders)
8. docs/operations/boat_access_rubric.md + docs/maintainability/manual_recovery_checklist.md — Phase 5.2 + Layer-5 references
9. outputs/phase7_handoff_note.md — Phase 7 (Tier 2 UI + chat integration) is the next major lane after Phase 5; reuses the Phase 5 playbook + tooling at smaller scale (75-175 entries across 3 Tier 2 categories)

## First action

The Phase 5 restructure (5.0 + 5.1–5.6) is **already applied** to docs/maintainability/master_build_plan.md §4 — landed 2026-05-14 in the new-chat post-`2f4676a` session, after the Phase 6 chat confirmed via coordination sync that it had not touched the `### Phase 5` block. The master plan ledger already reflects the 5.0/5.1–5.6 structure with per-sub-phase SHIPPED lines. No action needed on the restructure. Your first action is just: confirm state with `git log --oneline -12`, read the docs above, then surface the Phase 5.0 remaining-work punch list to the operator.

## Phase 5.0 status + what's left

Phase 5.0 (lead-up & shared tooling) is ~70% shipped. What remains:
- DISPATCH: operator pastes outputs/cursor_dispatch_prompt_phase5_leadup_tooling.md into a fresh Cursor session → Cursor runs Lane B's 10 verifications (HALT, operator commits findings) → Cursor authors scripts/az_roc_verify.py + scripts/npi_verify.py + scripts/osm_overpass_load.py (HALT, operator commits). This is the live-web-dependent work the Cowork chat structurally cannot do.
- OPERATOR ACTION 1: Google Places API billing check + spend cap (Cloud Console).
- OPERATOR ACTION 2: Phase 4 Railway redeploy → walks prod alembic to 0a1b2c3d4e5f.
- OPERATOR ACTION 3: amend outputs/heat_exposure_priority_30_list.md — fill 22 LHC-venue placeholders + validate 4 medium-confidence rows.

Phase 5.0 is DONE when all four close. Then Phase 5.1 (Eat & Drink) can dispatch.

## Parallelization map

- TRACK A: Phase 6 agent — already running, independent. Continues.
- TRACK B: Phase 5.0 — these run IN PARALLEL with each other:
  - B1: the Cursor dispatch (Lane B + 3 tooling scripts) — operator dispatches into Cursor
  - B2: operator actions 1+2+3 (billing / redeploy / priority-30 amendment) — none depend on B1
  - B3: the master_build_plan.md restructure application — needs a clean window on the shared doc
- TRACK C: Phase 5.1–5.6 — gated on 5.0. Technically independent of each other (not a dependency chain), but realistically sequential because one operator does the field entry. The SCRAPE portion (discovery/enrich/load) of 5.2–5.6 COULD be batched ahead of field entry once 5.1 proves the pipeline — but brief §3.2.d locked "per-category" sequencing for blast-radius reasons on early runs; revisit batching after 5.1 closes.

## Constraints carry-forward

- No git add/commit/push/amend by Cowork primary. Operator commits per Rule 2 + 12.
- Gotcha #15: in mixed-OS sessions the sandbox bash git view goes stale — use `git log --oneline -N` for state, never `git status` from bash (it leaves a stale index.lock + can serve phantom diffs). Trust the Windows-side Read tool for file content.
- Gotcha #16: no embedded double-quotes inside `-m '...'` PowerShell commit bodies — use hyphens / em-dashes / rephrase.
- Gotcha #18: edit only files in this chat's declared scope. New files in outputs/ are always safe.
- Pytest must stay green; ruff must stay clean. The Cowork sandbox cannot run pytest (no module) — defer canonical test runs to the operator's Windows venv or the Cursor session.
- Each per-category sub-phase + each tooling-touchup is its own natural HALT boundary. No sub-phase chain.

## Deferred maintainability debt (not blocking; fold into a clean-window commit)

- docs/STATE.md "Recent commits" refresh with: acf5e2b, 54ca07d, 4ba29e4, 0331102, 23a6a1c (+ whatever this restructure lands as).
- docs/maintainability/dispatch_channels.md gotcha #15 reinforcement (the sandbox-bash-git staleness pattern observed across the prior Phase 5 session).
Both are shared-surface docs — coordinate with the Phase 6 agent OR let it fold them into one of its doc commits since it's already touching STATE.md + dispatch_channels.md.

## What to do first

After confirming state with `git log --oneline -12`: (1) surface to the operator the Phase 5.0 remaining-work punch list (the Cursor dispatch + 3 operator actions) and the parallelization map; (2) the operator drives 5.0 to done, then Phase 5.1 Eat & Drink dispatches as the first per-category sub-phase. Do NOT start Phase 5.1 work until 5.0's four items all close.

## After Phase 5 — Phase 7 is next

When Phase 5 (Tier 1 data gathering) completes, **Phase 7 (Tier 2 UI + chat integration)** is the next major lane — not a Phase 5 sub-phase, its own master-plan phase. Phase 7 carries forward both the Phase 6 unified card grammar (UI strand) and the Phase 5 operator-driven data-gathering playbook (Tier 2 data strand: ~75-175 entries across Outdoors/Parks/Trails, Lodging & VR, Pets — same workflow as Phase 5 at ~1/4 the volume). Full handoff in `outputs/phase7_handoff_note.md`. When you author the Phase 5 close-out narrative, end it with the Phase 7 pointer so the sequence isn't lost.
```

---

## Operator instructions

1. **Commit these two new artifacts** (this kickoff prompt + the restructure patch):
   ```powershell
   git add outputs/phase5_restructure_master_plan_patch.md outputs/new_chat_kickoff_phase_5_0.md
   git commit -m 'chore(outputs): Phase 5 restructure patch + fresh Phase 5.0 agent kickoff prompt' -m 'Two brand-new outputs artifacts. phase5_restructure_master_plan_patch.md holds the exact old-to-new block for master_build_plan.md section-4 -- restructures Phase 5 into 5.0 shared lead-up plus 5.1-5.6 per-category sub-phases, each with its own SHIPPED ledger line and acceptance gate, partial close-out explicit. Authored as a patch artifact not a direct edit because master_build_plan.md is a shared-surface doc the parallel Phase 6 agent is touching -- applying it directly from the Phase 5 chat would collide per gotcha 18. new_chat_kickoff_phase_5_0.md is the paste-ready kickoff for a fresh Phase 5 Cowork primary at the 5.0 boundary post-restructure, superseding the older new_chat_kickoff_phase_5.md. Includes the parallelization map: Phase 6 agent runs independent; within 5.0 the Cursor dispatch plus the 3 operator actions plus the restructure application all run in parallel; 5.1-5.6 gate on 5.0. No code change. No migration.'
   git push
   ```

2. **Apply the restructure to `master_build_plan.md`** — pick the cleanest path:
   - **Fastest:** you apply it directly. Open `master_build_plan.md`, find the §4 Phase 5 block (~line 244), replace with the NEW BLOCK from `outputs/phase5_restructure_master_plan_patch.md` §3. ~2 min. Commit with the body suggested in that artifact's §1.
   - **Or:** hand it to the Phase 6 agent — it's already touching `master_build_plan.md`, so it has a natural clean window.
   - **Or:** let the fresh Phase 5 agent (step 3) do it as its first action.

3. **Open a fresh Cowork chat**, paste the fenced block from this file. That's your new Phase 5 primary — it picks up at the 5.0 boundary, gets the restructure landed, and drives 5.0 → 5.1.

## Parallelization summary

Three things can move at once right now:

| Track | Work | Owner | Depends on |
|---|---|---|---|
| A | Phase 6 UI build | Phase 6 agent | nothing — already running |
| B1 | Lane B verifications + 3 tooling scripts | Cursor session (via `23a6a1c` dispatch) | clean working tree |
| B2 | Google Places billing + Railway redeploy + priority-30 amendment | operator | nothing |
| B3 | `master_build_plan.md` restructure | operator / Phase 6 agent / fresh Phase 5 agent | clean window on the shared doc |

B1, B2, B3 are all Phase 5.0 and all independent of each other — do them concurrently. Phase 5.1–5.6 gate on all of 5.0 being done.

---

*Authored by Cowork primary at the new-chat post-`23a6a1c` session (2026-05-14). Lives at `outputs/new_chat_kickoff_phase_5_0.md` — brand-new outputs/ file, safe under the parallel-chat lock.*
