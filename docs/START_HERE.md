# Orientation — new Claude session for Hava

> **New Cursor session?** Read `docs/CURSOR_ORIENTATION.md` instead. It's shorter and tailored to Cursor's role. This file is for new Claude chat sessions.

## Project

- **Repo:** https://github.com/casey451/havasu-chat (local at
  `c:\Users\casey\projects\havasu-chat`)
- **Stack:** FastAPI + SQLAlchemy + Postgres (Railway prod) /
  SQLite (local dev)
- **Branch:** `main`
- **Product + assistant name:** Hava (fused naming — product and
  assistant share the name as of Phase 8.8)
- **Tagline:** "The AI local of Lake Havasu"

## What Hava is

Conversational concierge for Lake Havasu City, Arizona. One chat box
routes every question through tiered handlers — quick template lookups
for direct facts, structured retrieval for filtered queries, and an
LLM synthesis layer for open-ended recommendations — all speaking in
one consistent firsthand local voice. The database grows from
community contributions: users submit businesses and events with a
Google Business URL, which auto-enriches and lands in an operator
review queue before going live.

## Authoritative docs

Read these before any work. The canonical state docs are the source
of truth for "where the project is right now." The Hava-specific
docs are the source of truth for product spec and voice rules.

**Canonical state and discipline (read first):**

- `docs/STATE.md` — current production state, deployed commit,
  recently shipped work, queued work. Updated every ship.
- `docs/WORKING_AGREEMENT.md` — collaboration discipline (commit
  rules, halt-and-report gates, BOM-free verification, component
  doc currency, STATE.md update discipline).
- `docs/BACKLOG.md` — open and recently-closed work items with
  attribution to commits.
- `docs/PROJECT.md` — architecture overview, stack, key files.
- `docs/components/` — per-component reference docs (purpose,
  public surface, internal structure, conventions, known
  limitations). Start here when working on a specific subsystem.
- `docs/POST_SHIP_CHECKLIST.md` — the closing-discipline runbook
  for every ship.

**Hava-specific spec:**

- `HAVA_CONCIERGE_HANDOFF.md` — architectural spec, locked voice
  rules (§3, §8), phase scopes, the seven locked decisions (§2).
  §5 is the current phase list — that's the live source for
  "what's next," not any snapshot in this file.
- `docs/persona-brief.md` — persona and identity reference for
  Hava. Authoritative for voice specifics. §6.7 (voice-for-bulk,
  locked 2026-04-23) is an authoritative addition.
- `docs/pre-launch-scope-revision-2026-04-22.md` — **LOCKED**
  decision record revising pre-launch scope to include bulk
  catalog expansion before launch.
- `docs/runbook.md` — operational guide.
- `docs/privacy.md` + `docs/tos.md` — user-facing legal pages.
- `docs/pre-launch-checklist.md` — living tracker of pre-launch
  items.
- `docs/known-issues.md` — open issues, deferred work, resolved
  items. Don't edit outside its own sub-phase.

## Current state

Don't reconstruct project state from this file. The current state
lives in the canonical state docs:

- For **deployed commit, recent ships, queued work**: read
  `docs/STATE.md`. Verify the deployed-commit field matches origin
  by running `git log origin/main -1 --oneline`.
- For **what's next**: read `HAVA_CONCIERGE_HANDOFF.md` §5. Phases
  advance frequently; don't trust any inline phase reference here
  or anywhere else as the source of truth.
- For **open backlog and recently-closed items**: read
  `docs/BACKLOG.md`.
- For **known-issues and deferred work**: read
  `docs/known-issues.md`.

If those four agree with each other and with what `git log` shows,
you have an accurate picture. If they disagree, that's a finding —
flag it before doing work.

## Voice spec constraints (NOT to be contradicted)

From `HAVA_CONCIERGE_HANDOFF.md` §3 and §8 plus
`docs/persona-brief.md`. These are LOCKED:

- Hava speaks from firsthand local voice (§2.1 of handoff,
  revised 2026-04-22). No community-credit phrasing
  ("a local told me...", "the community says..."). These are
  superseded Option B patterns.
- §6.7 Voice across curated and bulk-imported providers
  (persona-brief §6.7, locked 2026-04-23): firsthand voice at
  landscape level; factual-descriptive at per-provider level for
  bulk-imported providers; framing beat precedes specifics on
  single-provider lookups; no provenance flag in data model.
- §3.1 Tone & diction: conversational, direct, confident.
- §3.3 Length: concise, no filler.
- §3.4 Option patterns (1–3): picks one, names what to skip.
- §3.5 Voice across tiers: consistent regardless of which tier
  answered.
- §3.9 No follow-up questions outside intake/correction flows
  (with §8.7 out-of-scope carve-out as intentional exception).
- §8.7 Out-of-scope template: *"That's outside what I cover right
  now — I stick to things-to-do, local businesses, and events.
  Want me to point you to anything else?"*
- Regional language: place-name fluency only, no Southwest
  climate/season texture (persona brief §4.1).
- Humor: playful — light contrast beats and mild bits (persona
  brief §4.2).
- Pronouns: she/her (persona brief §2).
- Backstory: vague only, "been around Havasu for a while"
  (persona brief §3).

## Role split

- **Owner (Casey):** Decisions, adjudications, approvals. Works
  mostly from mobile.
- **Claude (you):** Drafts Cursor prompts, provides architectural
  guidance. Does NOT write code directly.
- **Cursor:** Executes in the repo. Reports outcomes. Holds
  commits for explicit push approval.

## Process conventions

- "Push" = push commits already reviewed in chat. Nothing else.
- "Proceed to X.Y" = owner drafts the next prompt. Not implicit
  permission to implement.
- "Implement X.Y" = explicit code phase after read-first pass and
  owner approval of fix shape.
- Every code-phase commit holds for explicit push approval.
- `docs/known-issues.md` edits are their own sub-phase work.
- `docs/pre-launch-checklist.md` is a living tracker; later
  sub-phases can append launch-blocker items.
- Owner uses the `ask_user_input_v0` tool format for decisions —
  respect one-decision-at-a-time pacing. Do NOT delegate decisions
  back to owner with "whatever you think is best" framing; owner
  may use that phrasing but it usually means a real decision is
  needed and the tradeoffs need surfacing.
- After every ship, walk through `docs/POST_SHIP_CHECKLIST.md`.
  STATE.md and BACKLOG.md updates are part of the ship discipline,
  not optional follow-ups.

## First move

When this orientation is read at the start of a fresh session:

1. Read `docs/STATE.md` — get current deployed commit, recent ships,
   queued work.
2. Verify `git log origin/main -1 --oneline` matches STATE.md's
   deployed-commit field (or is one ahead, if the trailing
   commit is a STATE.md self-update).
3. Read `docs/WORKING_AGREEMENT.md` and `docs/BACKLOG.md` for
   discipline and open items.
4. For the specific phase you're picking up, read
   `HAVA_CONCIERGE_HANDOFF.md` §5 to find the current phase entry,
   then any phase-specific pointer docs from there.
5. Acknowledge orientation back to owner before drafting anything.

If any of the canonical state docs disagree with each other or with
git, surface that as a finding before proceeding.
