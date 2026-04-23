# Cursor orientation — Hava repo

This file is the entry point for new Cursor sessions working on Hava.
Casey (owner) drives. Cursor executes in the repo.

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

- `HAVA_CONCIERGE_HANDOFF.md` — architectural spec, phase history,
  voice rules
- `docs/persona-brief.md` — persona and voice reference
- `docs/pre-launch-scope-revision-2026-04-22.md` — locked sequence
- `docs/known-issues.md` — open issues, deferred work
- `docs/pre-launch-checklist.md` — living tracker

## Current phase position (as of 2026-04-23)

Check the latest commit on `main` and the `HAVA_CONCIERGE_HANDOFF.md`
§5 phase list to determine what's landed and what's next. Do not
assume — phases advance frequently.
