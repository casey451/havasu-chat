# New Cowork Chat — Phase 6 Kickoff Prompt

> Paste the block below into a fresh Cowork chat **separate from the Phase 5 chat**. Phase 6 (UI build) runs in parallel with Phase 5 (data gathering) per master plan §4 Phase 5 + §4 Phase 6. Two distinct Cowork chats so operator decisions + Cursor dispatches stay scope-disjoint. Pre-positioned at session-23-extension-3 (2026-05-13).

---

```
You are Cowork primary continuing the havasu-chat build plan in a fresh chat dedicated to PHASE 6 (Tier 1 UI build). Phase 5 (Tier 1 data gathering) is running in PARALLEL in a separate Cowork chat. Coordinate via origin commits — both chats pull origin/main at session start; both chats only edit files in their declared scope (gotcha #18 reminder).

## State of origin (verify with `git log --oneline -10`)

Phase 4 SHIPPED on origin (all 4 sub-phases — 2026-05-13): 91cd37b feat(phase4.1) + f5b3953 ruff + a75cfe8 docs + aaac4db chore + 86eeaf8 feat(phase4.2) + 2ab5f07 chore + 997cdc3 docs + 2f87211 feat(phase4.3) + 2eb2759 docs + ac94b6c feat(phase4.4 SHIPPED).

Phase 5 forward-positioning + first tooling-touchup on origin: 08bca69 chore(outputs) Phase 5 prereq checklist + Tier 1 brief; 62ab3b7 feat(phase5-prep) google_types_mapping Tier 1 expansion. Phase 5 lead-up docs (boat_access_rubric + manual_recovery_checklist back-fill + Phase 6 surface artifacts) may or may not be committed pre-paste — check git log.

Phase 6 forward-positioning on origin (this chat dispatches against these):
- outputs/phase6_prereq_checklist.md (~280 lines) — 10 operator decisions + 6 technical verifications + workload audit + 12 risks + Phase 1-5 dependency check
- outputs/cursor_brief_phase_6_tier_1_ui.md (~700 lines) — per-sub-phase playbooks for 5 sub-phases (6.1 unified card → 6.5 close-out)
- outputs/cursor_dispatch_prompt_phase_6_1.md (~280 lines) — paste-ready first Cursor dispatch for the unified Hava card grammar

Pytest baseline: 1803 collected (1801 passed + 2 skipped + 30 subtests). Alembic head on origin: 0a1b2c3d4e5f. Phase 6 ships no schema migrations across all 5 sub-phases.

## File-scope discipline (gotcha #18)

Phase 5 chat and Phase 6 chat must stay scope-disjoint at the Cursor level — whichever Cursor session commits second can revert the other's uncommitted-but-in-working-tree edits if scopes overlap. The locked split:

- **Phase 5 Cursor sessions touch:** app/contrib/* + scripts/* + app/db/* (+ existing tests for those surfaces)
- **Phase 6 Cursor sessions touch:** app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + new app/api/routes/* for category pages + new tests/test_phase6_*.py

Strict-disjoint at the file level. If a Phase 6 sub-phase surfaces a real need to touch app/contrib/* (e.g., a helper that doesn't belong in app/providers/), Cowork primary in this chat pauses + coordinates with the Phase 5 chat operator before dispatching.

## Reading list for first session

1. docs/STATE.md end-to-end — production state + recently shipped (Phase 4 SHIPPED + Phase 5 prep) + 3 session-23 lessons absorbed (especially gotcha #18 about parallel work)
2. outputs/phase6_prereq_checklist.md (~280 lines) — 10 operator decisions to lock + 6 technical verifications + 12 risk-register entries + 10 explicit non-goals
3. outputs/cursor_brief_phase_6_tier_1_ui.md (~700 lines) — per-sub-phase playbooks (§3.1-§3.5) + 14 locked decisions in §2 + 10 non-goals in §4 + 12 risks in §5 + close-out criteria in §6
4. outputs/cursor_dispatch_prompt_phase_6_1.md (~280 lines) — first sub-phase Cursor dispatch shape (will dispatch in fresh Cursor session when lead-up closes)
5. docs/maintainability/master_build_plan.md §4 Phase 6 + §4 Phase 7 (briefly — §4 Phase 7 informs the snowbird-return panel deferral + chat integration hooks Phase 6 leaves behind)
6. outputs/cursor_brief_phase_5_tier_1_data.md (briefly — Phase 5 brief; this chat reads it to understand what data Phase 5 is producing so empty-state copy + per-category sort defaults match)

## Phase 6 lead-up tasks remaining (operator + Cowork primary in this chat)

Per prereq checklist §9 timeline:

**Days 1-2 (operator + Cowork primary in this chat):**
- [§3 prereq decisions] Lock the 10 decisions (~1-2h with AskUserQuestion in this chat or written response from operator). Most are pre-locked at recommendation in prereq §3; operator confirms or revises.
- [Brief §2] Fill Phase 6 brief §2 placeholder with the locked answers.

**Days 3-7 (operator-driven; mostly browser work):**
- [§4 technical verifications] OSM tile rate posture (~15 min); CDN cache headers verify (~15 min); mobile testing matrix lock (~15 min); Cloudflare Pages decision (~5 min); Jinja2 vs framework lock (~5 min); Opus design 8-questions defer-or-resolve (~variable).
- Operator schedules Phase 6 design-review cadence (1x/week recommended).

**Days 7-14 (Cowork primary in this chat):**
- [Phase 6.1 dispatch] When prereq §3 decisions are locked + §4 verifications done, paste outputs/cursor_dispatch_prompt_phase_6_1.md into a fresh CURSOR session (not Cowork) for the unified Hava card grammar sub-phase
- Cursor's §13 returns to this Cowork chat for review

## Phase 6 sub-phase execution

After lead-up closes, 5 sub-phases dispatch sequentially (NOT in parallel — each one's HALT at §3 boundary is a real boundary):

- **Phase 6.1** — Unified Hava card grammar (4-7 days)
- **Phase 6.2** — First category page template + Eat & Drink proof (4-6 days)
- **Phase 6.3** — Remaining 5 Tier 1 category pages + district + ranking + seasonal hours (5-8 days)
- **Phase 6.4** — Map view + boat-access mode + themed group landing pages (5-7 days)
- **Phase 6.5** — Homepage + Provider profile extension + mobile polish + close-out (4-6 days)

Each sub-phase dispatch prompt is authored by Cowork primary in this chat after the prior sub-phase closes out + operator design-review happens. Phase 6.1 is the only pre-authored prompt; 6.2-6.5 are authored on-demand.

## What today's first session should do

Pick one of these as the opening task (or propose alternative):

**A. Commit the Phase 5 + Phase 6 lead-up docs that landed in the prior chat** (boat_access_rubric.md + manual_recovery_checklist.md back-fill + Phase 5 new-chat kickoff + Phase 6 prereq + brief + 6.1 dispatch prompt + Phase 6 new-chat kickoff). Single chore-docs commit + push. ~15 min. Verifies the parallel-positioning state is on origin before either chat starts substantive work.

**B. Lock the 10 prereq §3 operator decisions** by Cowork primary surfacing each as an AskUserQuestion + updating Phase 6 brief §2 with locked answers. ~30-60 min. After this, brief §2 placeholder is filled and Phase 6.1 dispatch is unblocked.

**C. Run the 6 prereq §4 technical verifications** (operator browser work; ~1h spread). Cowork stays quiet during operator verification; surface back with what was found.

**D. Dispatch Phase 6.1 immediately** — assuming §3 decisions accepted at recommendation (no need to lock individually) and §4 verifications can run in parallel with Cursor's 6.1 work. Paste outputs/cursor_dispatch_prompt_phase_6_1.md into fresh Cursor session. Cursor's §13 returns to this chat for review.

**E. Coordinate with Phase 5 chat** — confirm the Phase 5 chat operator picked a starting lane (per Phase 5 kickoff outputs/new_chat_kickoff_phase_5.md options A-E); if Phase 5 is still in lead-up, Phase 6 can run ahead since Phase 6 builds against schema not data.

## Constraints + reminders

- Phase 6 is engineering-driven (unlike Phase 5 which is operator-driven). Cowork primary stays active per sub-phase; operator reviews at boundaries.
- HALT etiquette: 5 sub-phase boundaries (§3.1 close → §3.2 dispatch → §3.2 close → §3.3 dispatch → etc.). Phase 6 SHIPS at §3.5 close.
- Gotcha #18: this chat ONLY edits files in the Phase 6 scope (app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + new app/api/routes/* + new tests/test_phase6_*.py). Phase 5 chat handles app/contrib/* + scripts/* + app/db/*.
- Gotcha #16: no embedded double-quotes inside `-m '...'` PowerShell commit bodies.
- Pytest must stay green throughout. ~1803 floor; sub-phases add ~10-25 each.
- Ruff must stay clean.
- No git add / commit / push / amend by Cowork primary. Operator commits per Rule 2 + 12.

## First operator action when you paste this

After confirming state above with `git log --oneline -10` + `python -m pytest -q --collect-only | tail -3` + `python -m alembic heads`, pick a lane (A-E above) or propose alternative. I will execute the chosen lane in this chat.

Phase 6 begins.
```

---

## Coordinating with Phase 5 chat

Both Cowork chats reference origin/main; both pull before substantive work; both stay file-scope-disjoint. Suggested coordination cadence:

- **Daily:** operator opens both chats in the morning, runs `git pull` in each, briefly notes "Phase 5 is on category X / Phase 6 is in sub-phase 6.Y" to each chat's context
- **Weekly:** operator does a design-review with the Phase 6 chat at sub-phase boundaries (~30-60 min)
- **Phase 5 schedule-day vs Phase 6 schedule-day:** alternate. Don't try to drive both phases hard on the same day; that path leads to operator burnout per Phase 6 prereq §6 risk row 1.

## After Phase 6 ships

Phase 6 SHIPS at §3.5 close (when all 5 sub-phases land + master plan SHIPPED header + STATE.md refresh). Phase 5 continues if not yet closed (Phase 5 takes 4-8 weeks; Phase 6 takes 4-6 weeks; Phase 5 likely finishes 1-3 weeks after Phase 6).

After both Phase 5 + Phase 6 ship:
- master plan §4 Phase 5 + §4 Phase 6 both have SHIPPED headers
- Phase 7 (Tier 2 UI + chat integration) becomes the next dispatchable major lane — runs ~3-4 weeks
- Phase 8 (trust layer + conditions + alerts) follows
- Phase 9 (events + classes/sports/rec)
- Phase 10 (polish + pre-launch hardening)
- Phase 11 (monetization wiring)
- Phase 12 (launch)
- Phase 13 (V1.5 post-launch features)

Approximate elapsed time from Phase 5 + 6 start to launch: ~4-6 months of real-calendar time given the multi-phase chain after.
