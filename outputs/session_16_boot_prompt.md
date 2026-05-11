# Session-16 Boot Prompt

> **For Casey:** paste the content of the fenced block below into a fresh Cowork chat as the first message. The new agent boots into "Phase 1C dispatch ready" mode.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Session-15 closed clean at origin/main `92aa7e2`
with Phase 1A + 1B of the master build plan SHIPPED, all session-15
artifacts durable on origin. Phase 1C (application read pivot) is the
next dispatch.

## Boot sequence (~5 min total)

1. `docs/SESSION_HANDOFF_2026-05-14.md` end-to-end — closes session-15,
   captures the 10 commits + 3 strategic decisions + accepted deviations,
   points at queued artifacts. Read first.
2. `docs/STATE.md` Production block + "Recently shipped" §1 (the
   session-15 entry) — current production state.
3. `docs/maintainability/master_build_plan.md` §0–§4 Phase 1 — the
   13-phase operating doc. Pay attention to the "Shipped (incremental)"
   list under Phase 1 which tracks per-sub-phase status (1A + 1B shipped;
   1C + 1D pending).
4. `outputs/cursor_brief_phase_1_entity_schema.md` §3 + §7 + §8 — the
   heavy-prescriptive operating doc for the whole Phase 1 lane.
   Amendments through 2026-05-14 are folded in (entity_id NOT NULL
   flip deferred from 1B to 1D).
5. `outputs/cursor_dispatch_prompt_phase_1c.md` — the short paste-into-
   Cursor prompt I'll dispatch when ready.
6. `docs/maintainability/dispatch_protocol.md` (12 working-agreement
   rules) + `docs/maintainability/dispatch_channels.md` (channel-pick
   playbook + 12 gotchas). All in force.
7. Run baseline: `git log --oneline -5` (should top at `92aa7e2`),
   `python -m pytest -q --collect-only 2>&1 | tail -3` (should show
   1503 tests), `python -m alembic heads` (should show single head
   `b2c3d4e5f6a7`). Report values back to Casey.

## Your first action

**Wait for Casey's say-so to dispatch Phase 1C.** He may want time
between sub-phases (drop+recreate local SQLite first per session-15
operator note — see `docs/SESSION_HANDOFF_2026-05-14.md` §3). When he
says go, the paste-to-Cursor prompt is in
`outputs/cursor_dispatch_prompt_phase_1c.md`.

After Cursor returns the Phase 1C §13 report:
1. Review against brief §7 acceptance gates (§7.4 specifically — chat-
   route response shape unchanged, Provider profile renders identical,
   tier 2 catalog returns identical rows in identical order).
2. Recommend commit batch by explicit paths (Rule 8 — one substantive
   lane per commit). Phase 1C is expected to touch 6 application/script
   files + 3 new or extended test files.
3. After commit, update master plan §4 Phase 1 "Shipped (incremental)"
   list with the 1C ship-line (same format as 1A + 1B entries).
4. Stand by for Phase 1D — same brief, §8 deliverables (dual-write +
   entity_id NOT NULL flip + close-out).

## Operating principles (firm ground from session-15 carry-over)

- **Anchored Edit on existing files; Write only for new files**
  (Rule 1 + 6).
- **Wait for explicit text reports before `git add`** (Rule 2). Operator
  commits; agents don't.
- **Sequential lanes when files overlap** (Rule 3). Phase 1C touches
  `app/providers/*`, `app/chat/tier2_db_query.py`, `app/contrib/*`,
  `scripts/places_load.py` — nothing else should touch those while
  1C is open.
- **PowerShell single-quote `git commit -m '...'`** when subjects have
  `$`, `§`, `→`, parens, or other sigils (gotcha #8).
- **Local ruff must match `dev-requirements.txt` pin** (gotcha #9 —
  CI is `ruff==0.15.12`).
- **`alembic current (mergepoint)` label is a chain-walk diagnostic,
  not a multi-head alarm** (gotcha #10). Local SQLite may be drifted;
  don't alarm.
- **Don't re-debate locked decisions** in master plan §10. Session-15
  added 3 new locks (category rewrite → Phase 3; pro-services V1.5
  deferral; district paragraphs phased V1/V1.5/V2). All durable.
- **Living-document discipline** — after each sub-phase ships, update
  master plan §4 Phase 1 + §9 calendar slot as appropriate. STATE.md
  was refreshed at session-15 close; refresh again only after a major
  ship.

## What NOT to do

- Don't redo session-15's work. All 10 commits are on origin; STATE.md
  + master plan + brief are current.
- Don't start Phase 1D before Phase 1C ships and commits.
- Don't propose React/SPA migration (tech stack constraint).
- Don't propose national expansion (hyperlocal by design).
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise).
- Don't ship anything violating texture rules (engagement loops,
  popups, fake urgency, native reviews, etc. — Opus design §6).
- Don't run `git commit --amend` while parallel lanes are in flight
  (Rule 12).

## Context that often gets lost

- **Linux bash mount may serve stale `.git` views.** Use Windows-side
  paths via the Read tool when in doubt (Rule 7). Session-15 hit this
  twice with truncated file views — bash sandbox unreliable, Read tool
  authoritative.
- **Phase 1B left `entity_id` NULLABLE on providers/events/programs.**
  NOT NULL flip is Phase 1D work after dual-write helpers populate at
  write time. Pinned in test.
- **`Sponsor.entity_type` defaults to `"commercial"` for legacy rows.**
  Sponsor.business_id has no DB-level FK; app-layer disambiguates.
- **Provider.entity, Event.entity, Program.entity 1:1 relationships
  added in Phase 1B** — Phase 1C reads through these.

## How to know when to escalate

Heuristic from `docs/maintainability/dispatch_channels.md` "When to
escalate to a fresh chat":
- After 4-5 sub-agent dispatches, context is meaningfully fuller
- After 10+ paste-channel round-trips, you've absorbed a lot of state
- A natural escalation point is between phase ships

Session-15 escalated at Phase 1B → 1C boundary (10 commits + 1 sub-agent
+ multiple Cursor round-trips). If you reach similar territory during
Phase 1C dispatch or after, author a session-17 handoff and escalate.

## Begin

1. Read the boot sequence files (steps 1-6 above).
2. Run baseline (step 7) and report values to Casey.
3. Wait for Casey's say-so to dispatch Phase 1C.

Don't ask "where do we start" — start at the boot sequence. The handoff
+ master plan + brief are the source of truth.
```
