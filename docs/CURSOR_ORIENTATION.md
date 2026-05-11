# Cursor orientation — Hava repo

> **2026-05-12 Strategic Pivot Notice**
>
> havasu-chat pivoted from chat-first concierge to a **structured local directory with chat as one of three front doors** (browse + search + ask). Repo info, stack, and operational guidance in this doc remain accurate; the implicit product framing (chat-only) is pre-pivot. **For current strategic direction, read `docs/STRATEGY_PIVOT_2026-05-12.md` first** (plus `docs/SESSION_HANDOFF_2026-05-13.md` for the latest session entry point). Substantive rewrite deferred past Day 90 per pivot §8.7 LOCKED status block.

This file is the entry point for new Cursor sessions working on Hava.
Casey (owner) drives. Cursor executes in the repo.

**Mode A vs B, full doc read order, git reconciliation, session paste templates, ship closeout:** see `docs/CURSOR_NEW_CHAT_PLAN.md`.

## Repo

- Path: `c:\Users\casey\projects\havasu-chat`
- Remote: `https://github.com/casey451/havasu-chat`
- Branch: `main`
- Stack: FastAPI + SQLAlchemy + Postgres (prod) / SQLite (dev)

## How work arrives

Casey pastes a phase prompt drafted by Claude. Each phase prompt is
self-contained — it quotes the spec fragments you need inline. Do NOT
re-read `HAVA_CONCIERGE_HANDOFF.md` or `docs/persona-brief.md` unless
the phase prompt explicitly tells you to. They're long and you don't
need them to execute a well-specified phase.

## Commit + push discipline

- Every code-phase commit holds for explicit push approval. You never
  push without being told to push in chat.
- Stage only files listed in the phase prompt. Do NOT stage untracked
  files that happen to be in the working tree.
- Commit messages follow the format given in the phase prompt.
- "Hold for push approval" at the end of a phase means: commit locally,
  report the hash, stop.

## Process conventions

- Component architecture notes live under `docs/components/<name>.md`.
  When your change affects behavior or public contracts of such a module,
  update its doc in the **same commit** as the code — see
  `docs/WORKING_AGREEMENT.md` (Component doc currency).
- Session transcripts and ad-hoc captures belong in `relay/` (gitignored), not `docs/`. Anything in `docs/` should be a current normative spec, decision, retrospective, or runbook. Slice-complete writeups and one-off transcripts are removed from the working tree once their value is captured in `BACKLOG`/`STATE`/decision retrospectives or git history (recoverable via `git log --all -- <path>`).
- Python isn't runnable in most Cursor environments (Windows Store stub
  only). Flag pytest runs for Casey to execute locally; do not block on
  them yourself.
- If a phase prompt says "read-only audit" or "diagnostic," do NOT
  modify application code. Report findings only.
- If you hit a decision point not covered by the prompt, stop and ask
  in chat rather than guessing.
- If you run out of context mid-phase, commit work-in-progress with a
  `wip(<phase>):` message and flag the state clearly in your reply.

## Authoritative docs (read ONLY when a phase prompt directs you to)

**Canonical state and discipline:**
- `docs/STATE.md` — current production state, deployed commit, recently
  shipped work, queued work
- `docs/WORKING_AGREEMENT.md` — collaboration discipline (commit rules,
  halt-and-report gates, BOM-free verification, component doc currency,
  STATE.md update discipline)
- `docs/BACKLOG.md` — open and recently-closed work items
- `docs/PROJECT.md` — architecture overview, stack, key files
- `docs/components/` — per-component reference docs (purpose, public
  surface, internal structure, conventions, known limitations)
- `docs/POST_SHIP_CHECKLIST.md` — what to update after every ship

**Hava-specific:**
- `HAVA_CONCIERGE_HANDOFF.md` (repo root) — architecture + tier
  routing; voice rules in `docs/persona-brief.md`; what's next in
  `BACKLOG.md` / `STATE.md`
- `docs/persona-brief.md` — persona and voice reference
- `docs/known-issues.md` — open issues, deferred work
- `docs/pre-launch-checklist.md` — living tracker

## Current phase position

Check the latest commit on `main`, `docs/STATE.md`, and
`docs/BACKLOG.md` to determine what's landed and what's next. Do not
assume — priorities advance frequently.
