# Orientation — new Claude session for Hava pre-launch work

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

Conversational concierge for Lake Havasu City, Arizona. One
chat box routes every question through four tiers — quick
template lookups for direct facts, structured retrieval for
filtered queries, and an LLM synthesis layer for open-ended
recommendations — all speaking in one consistent firsthand
local voice. The database grows from community contributions:
users submit businesses and events with a Google Business URL,
which auto-enriches and lands in an operator review queue
before going live.

## Authoritative docs (READ THESE BEFORE ANY WORK)

- `HAVA_CONCIERGE_HANDOFF.md` — architectural spec, locked
  voice rules (§3, §8), phase scopes, the seven locked
  decisions (§2). Renamed from
  `HAVASU_CHAT_CONCIERGE_HANDOFF.md` in Phase 8.8.1a.
- `docs/persona-brief.md` — persona and identity reference for
  Hava (Phase 8.8.0 output). Authoritative for voice specifics
  per the revised §2.1. §6.7 (voice-for-bulk, locked
  2026-04-23) is an authoritative addition.
- `docs/START_HERE.md` — onboarding entry point. Read first
  for fastest orientation.
- `docs/components/` — per-component reference docs (purpose,
  public surface, internal structure, conventions, known
  limitations). Start here when working on a specific subsystem.
- `docs/pre-launch-scope-revision-2026-04-22.md` — **LOCKED**
  decision record revising pre-launch scope. Reverses prior
  post-launch sequencing of bulk catalog expansion. Launch
  moves from ~2–4 weeks to ~6–10 weeks. Locked 2026-04-23.
- `docs/runbook.md` — operational guide (Phase 8.4)
- `docs/privacy.md` + `docs/tos.md` — user-facing legal pages
- `docs/pre-launch-checklist.md` — living tracker; 16 items
  as of Phase 8.8.1a-supplement
- `docs/known-issues.md` — open issues, deferred work,
  resolved items (don't edit outside its own sub-phase)

## Current repo state

**Intended tip:** commit `3a860c4` (docs: known-issues entry
for t3-02 Tier 1 day-specific hour gap). **First thing to do:
run `git log origin/main -1 --oneline` and
`git log main -1 --oneline` and report back.** If the two
don't match, owner may need to push. Do not proceed to work
until this is verified.

**Untracked (not in any commit):**
- `docs/phase-8-x-documentation-refresh-completion-report.md`
- `docs/phase-9-scoping-notes-2026-04-22.md`

**Completed work history (summary):**

- Phases 1–6: shipped (baseline app, feedback, onboarding,
  session memory, local voice)
- Phase 8 pre-launch hardening: shipped (`0d01d40`)
- Phase 8.8.0: persona design + `docs/persona-brief.md`
  (`3d4680b`)
- Phase 8.8.1a: handoff rewrite — renamed to
  `HAVA_CONCIERGE_HANDOFF.md`, §2.1 revised to firsthand
  voice (`3d4680b`)
- Phase 8.X: onboarding doc + handoff §1d/§5/§6 catch-up
  (`1314d31`)
- Phase 8.8.1a-supplement-pre: added
  `docs/pre-launch-scope-revision-2026-04-22.md` as
  PROVISIONAL (`17e4a0a`)
- Phase 8.8.1a-supplement: docs cluster — PROVISIONAL→LOCKED,
  checklist 7→16 items, handoff §5 phases 8.10–8.13,
  persona-brief §11 (`0b6a854`)
- Phase 8.8.1a-supplement-fixup: stale checklist reference
  in handoff §5 Phase 8.9 (`3b958dd`)
- Phase 8.8.1a-supplement-voice-for-bulk: persona-brief §6.7
  — voice-for-bulk option 3b locked (`2a58e00`)
- Phase 8.8.1b + fixup: voice spec implementation across
  system_prompt.txt, tier2_formatter.txt, tier2_parser.txt,
  unified_router.py; carryover cleanups (`2db768e`, `7b9bbad`)
- Phase 8.8.2a: test assertion drift fixes, suite 794/0
  (`404826e`)
- Phase 8.8.2b: voice audit design + execute + remediate +
  close; 54 PASS / 0 MINOR / 1 FAIL-waived / 0 ERROR; waivers
  at `scripts/voice_audit_waivers_2026-04-23.md`
  (`f982941`, `50cf425`, `4fcd5bc`, `3a860c4`)

## Revised pre-launch sequence (LOCKED 2026-04-23)

```
8.8.1a [done]
  → [docs cluster — done]
  → §2.3 voice-for-bulk conversation [done — option 3b, §6.7]
  → 8.8.1b [done]
  → 8.8.2  [done — voice regression v1, curated catalog]
  → 8.9    [← NEXT — event ranking]
  → 8.10   (River Scene event pull)
  → 8.11   (Google bulk import — havasu-enrichment full run,
            all 4,574 businesses, no stage gate)
       ├── 8.11.0 — Day 1 setup
       ├── 8.11.1 — Batch 1 execution + quality report
       ├── 8.11.2 — Batches 2–N execution
       ├── 8.11.3 — Operator review drain
       └── 8.11.4 — Ingestion into Postgres catalog
  → 8.12   (voice regression v2 — expanded catalog, revised bar)
  → 8.13   (Tier 3 retrieval tuning for expanded surface area)
  → dogfood
  → launch
```

## Voice spec constraints (NOT to be contradicted)

From `HAVA_CONCIERGE_HANDOFF.md` §3 and §8 plus
`docs/persona-brief.md`. These are LOCKED:

- Hava speaks from firsthand local voice (§2.1 of handoff,
  revised 2026-04-22). No community-credit phrasing
  ("a local told me...", "the community says..."). These are
  superseded Option B patterns.
- §6.7 Voice across curated and bulk-imported providers
  (persona-brief §6.7, locked 2026-04-23): firsthand voice
  at landscape level; factual-descriptive at per-provider
  level for bulk-imported providers; framing beat precedes
  specifics on single-provider lookups; no provenance flag
  in data model.
- §3.1 Tone & diction: conversational, direct, confident
- §3.3 Length: concise, no filler
- §3.4 Option patterns (1–3): picks one, names what to skip
- §3.5 Voice across tiers: consistent regardless of which
  tier answered
- §3.9 No follow-up questions outside intake/correction flows
  (with §8.7 out-of-scope carve-out as intentional exception)
- §8.7 Out-of-scope template: *"That's outside what I cover
  right now — I stick to things-to-do, local businesses, and
  events. Want me to point you to anything else?"*
- Regional language: place-name fluency only, no Southwest
  climate/season texture (persona brief §4.1)
- Humor: playful — light contrast beats and mild bits
  (persona brief §4.2)
- Pronouns: she/her (persona brief §2)
- Backstory: vague only, "been around Havasu for a while"
  (persona brief §3)

## Role split (unchanged)

- **Owner (Casey):** Decisions, adjudications, approvals.
  Works mostly from mobile.
- **Claude (you):** Drafts Cursor prompts, provides
  architectural guidance. Does NOT write code directly.
- **Cursor:** Executes in the repo. Reports outcomes. Holds
  commits for explicit push approval.

## Process conventions (reaffirmed)

- "Push" = push commits already reviewed in chat. Nothing
  else.
- "Proceed to X.Y" = owner drafts the next prompt. Not
  implicit permission to implement.
- "Implement X.Y" = explicit code phase after read-first pass
  and owner approval of fix shape.
- Every code-phase commit holds for explicit push approval.
- `docs/known-issues.md` edits are their own sub-phase work.
- `docs/pre-launch-checklist.md` is a living tracker; later
  sub-phases can append launch-blocker items.
- Owner uses the `ask_user_input_v0` tool format for decisions
  — respect one-decision-at-a-time pacing. Do NOT delegate
  decisions back to owner with "whatever you think is best"
  framing; owner may use that phrasing but it usually means
  a real decision is needed and the tradeoffs need surfacing.

## Carryover items from previous sessions

- **t3-02 Tier 1 day-specific hour gap** — known-issues entry
  filed (`3a860c4`). Fix is in `tier1_templates.py`, scoped
  to a Tier 1 templates phase. Waiver at
  `scripts/voice_audit_waivers_2026-04-23.md`.
- **"Havasu Chat" product-name migration** — still present in
  `app/main.py`, `app/static/index.html`, contribute/program
  HTML, `README.md`, `HAVASU_CHAT_MASTER.md`. Deferred to a
  dedicated product-name migration phase.
- **`tests/test_phase87_privacy.py:167`** — asserts "Terms of
  Service for Havasu Chat" in page title. UI/legal copy, not
  assistant voice. Flagged in 8.8.2a, still outstanding.
- **`docs/phase-8-x-documentation-refresh-completion-report.md`**
  and **`docs/phase-9-scoping-notes-2026-04-22.md`** — still
  untracked, housekeeping TBD.

## First move

Acknowledge this orientation. Verify push status on `3a860c4`
by running `git log origin/main -1 --oneline` and
`git log main -1 --oneline`. Once confirmed, draft the Phase
8.9-read prompt.

**Phase 8.9-read scope (read-only, no code changes):**
Read `app/core/search.py` event retrieval and ranking logic;
any event-quality modules (grep for event ranking, quality
scoring, recurrence classification); `docs/persona-brief.md`
§9.6; `HAVA_CONCIERGE_HANDOFF.md` Phase 8.9 entry in §5.
Report current state and proposed fix shape for owner approval
before any implementation.
