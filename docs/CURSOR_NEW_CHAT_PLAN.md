# New Cursor chat — playbook

> **2026-05-12 Strategic Pivot Notice**
>
> havasu-chat pivoted from chat-first concierge to a **structured local directory with chat as one of three front doors** (browse + search + ask). The Mode A/B playbook, doc-read-order guidance, and ship-closeout templates in this doc remain useful; the implicit product framing (chat-only) is pre-pivot. **For current strategic direction, read `docs/STRATEGY_PIVOT_2026-05-12.md` first** (plus `docs/SESSION_HANDOFF_2026-05-13.md` for the latest session entry point). Substantive rewrite deferred past Day 90 per pivot §8.7 LOCKED status block.

How a new Cursor session should start, what to read, and how to close a ship. Complements `docs/CURSOR_ORIENTATION.md` (entry point) with mode split, full doc order, templates, and practical notes.

## Modes

| Mode | When to use it | Doc depth |
|------|----------------|-----------|
| **A — Phase execution** | Casey pastes a self-contained phase prompt from Claude (quotes spec inline). | Thin: orientation + gates only; do not reread long specs unless the prompt says so (`docs/CURSOR_ORIENTATION.md` lines 15–19). |
| **B — Full alignment** | New feature, refactor, audit, “get on the same page,” or no phase prompt. | Full stack below, in order, so STATE / BACKLOG / architecture / voice do not contradict each other. |

If you do not say which mode, default to **B** for anything ambiguous.

## Plan for a new Cursor chat (steps)

1. **Declare mode** in the first message: “Mode A: execute attached phase” vs “Mode B: align then implement X.”
2. **Read the doc stack** for that mode (sections below).
3. **Reconcile with git:** `git status`, `git log origin/main -5 --oneline` (and after a push, that Railway matches `origin/main`, per `docs/STATE.md`).
4. **Restate alignment** in one short reply: production URL, branch, what is OPEN in backlog that might collide with the task, and any doc/git mismatch (flag as a finding before coding — per `docs/START_HERE.md` / `docs/CLAUDE_SESSION_BRIEFING.md`).
5. **Execute** with `docs/WORKING_AGREEMENT.md`: halt-and-report between steps, no push until Casey explicitly approves push, stage only what the prompt lists (Mode A), update `docs/components/<name>.md` in the same commit as code when behavior/contracts change.
6. **Close** with `docs/POST_SHIP_CHECKLIST.md` when something ships: STATE / BACKLOG / component docs as applicable; remember WORKING_AGREEMENT “STATE update discipline” (trailing STATE commit rules).

## What to read, in order, and when

### Always first (Mode A and B)

1. **`docs/CURSOR_ORIENTATION.md`**  
   - **When:** First file for Cursor specifically (`docs/START_HERE.md` line 3 points here instead of the longer Claude-oriented file).  
   - **Why:** Repo path, branch, stack, how work arrives, commit/push rules, when not to read long docs (Mode A).

2. **`docs/STATE.md`**  
   - **When:** Immediately after orientation. Repo banner at line 1 also says read this first among canonicals.  
   - **Why:** “Where the project is right now”: production URL, health expectations, catalog posture notes, recent commits, recently shipped, queued snapshot.

3. **`docs/WORKING_AGREEMENT.md`**  
   - **When:** Before any commit or multi-step work.  
   - **Why:** Halt-and-report, no commit/push without approval, UTF-8 commit messages without BOM, component-doc currency, STATE update discipline, Cursor permissions (including no prod DB writes).

4. **`docs/BACKLOG.md`**  
   - **When:** Before designing or implementing anything non-trivial.  
   - **Why:** OPEN / DEFERRED / RESOLVED items and ship log — avoids duplicating known issues or fighting existing decisions.

### Mode B only (or Mode A only if the phase prompt says “read architecture”)

5. **`docs/PROJECT.md`**  
   - **When:** Any change that touches routing, tiers, API surface, or “where does this live in the repo?”  
   - **Why:** High-level architecture, stack, key files.

6. **`HAVA_CONCIERGE_HANDOFF.md`** (repo root)  
   - **When:** Tier routing, data model, “where is Tier 1 vs chat greetings,” cross-refs to decisions.  
   - **Why:** Normative §3 tier pipeline; §5 explicitly defers “what’s next” to BACKLOG / STATE (not a duplicate phase table).

7. **`docs/maintainability/project_index.md`**  
   - **When:** Unfamiliar area of the tree, cross-cutting change, or “where is the doc for X?”  
   - **Why:** Repo map and doc index.

### When the task touches a specific subsystem

- **`docs/components/<component>.md`** (as relevant)  
  - **When:** Work on that module’s behavior or public contract.  
  - **Why:** WORKING_AGREEMENT requires updating the component doc in the same commit as the code change.

### When the task touches copy, prompts, or “how Hava sounds”

- **`docs/persona-brief.md`**  
  - **When:** Prompts under `prompts/`, Tier 2/3 wording, blocklist, intake/correct, out-of-scope templates.  
  - **Why:** Canonical voice; `HAVA_CONCIERGE_HANDOFF.md` §8 points here instead of duplicating.

### When the task touches ops, legal, or “known broken / deferred”

- **`docs/runbook.md`** — deploy, env, operational checks.  
- **`docs/known-issues.md`** — deferred behavior, spec vs code notes (do not casually edit outside its own process — file says so).  
- **`docs/privacy.md` / `docs/tos.md`** — only if the change affects user-facing legal or data handling.  
- **`docs/pre-launch-checklist.md`** — if work relates to launch readiness.

### When closing a ship (after push + verification)

- **`docs/POST_SHIP_CHECKLIST.md`**  
  - **When:** After substantive work lands on main and prod checks out.  
  - **Why:** STATE / BACKLOG / component doc updates; aligns with WORKING_AGREEMENT.

### Optional reference (not “read every time”)

- **`docs/CLAUDE_SESSION_BRIEFING.md`** — mirrors Claude’s first moves; useful if Cursor is doing planning-like work or you want the same “first moves” list as Claude sessions (§ first moves ≈ STATE → WORKING_AGREEMENT → BACKLOG → components → deeper spec).  
- **`docs/START_HERE.md`** — longer Claude-oriented orientation; Cursor is already steered to `CURSOR_ORIENTATION.md` first.

## First message you can paste into Cursor (template)

**Session: Mode B (full alignment) — [one-line goal].**

Read in order:

1. `docs/CURSOR_ORIENTATION.md`  
2. `docs/STATE.md`  
3. `docs/WORKING_AGREEMENT.md`  
4. `docs/BACKLOG.md`  
5. `docs/PROJECT.md`  
6. `HAVA_CONCIERGE_HANDOFF.md`  
7. `docs/maintainability/project_index.md`  

Then: `docs/components/…` as needed for [subsystem].

After reading: reply with (a) `origin/main` tip + working tree clean?, (b) any OPEN backlog items relevant to this goal, (c) contradictions between docs and git — then propose a short implementation plan and wait for approval before commits/pushes per WORKING_AGREEMENT.

**For Mode A**, replace the middle with: “Read 1–4 only; implement phase prompt below; do not read persona-brief / HAVA unless the prompt says so.”

## Practical notes from the repo itself

- `docs/CURSOR_ORIENTATION.md` still says Python/pytest may not be runnable in some Cursor Windows setups — flag pytest for Casey if the agent cannot run it; do not pretend it ran.

- `docs/POST_SHIP_CHECKLIST.md` describes a “Deployed commit:” style STATE update; your current `docs/STATE.md` uses a slightly different “Production” pattern (tip subject + recent commits). When closing a ship, follow WORKING_AGREEMENT “STATE.md update discipline” and whatever `STATE.md`’s current sections actually ask for — if checklist and STATE diverge, treat that as a small doc-consistency finding.
