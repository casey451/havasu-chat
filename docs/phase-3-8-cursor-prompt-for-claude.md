# Phase 3.8 — Classifier patch + catalog-gap template

**Date context:** 2026-04-20  
**Read first (no edits in this task unless the prompt says so):** Post-Phase 3 re-plan draft — HOURS_LOOKUP miss on phrasings like "is altitude open late on friday"; catalog-gap Tier 3 bypass for DATE_LOOKUP / LOCATION_LOOKUP / HOURS_LOOKUP when `entity_matched` is null.

---

## Git operations scope fence

You may run `git add`, `git commit`, and `git push` **once** at the end of this task **only if** the prompt explicitly tells you to commit and push.

You may **NOT**: amend commits, rewrite history, force-push, rebase, modify `.git/config`, install git hooks or hook-bypassing workarounds, or alter commit messages or trailers after the fact. If a commit was created with an undesired trailer, message, or author, **STOP and ask**. Cosmetic cleanups of shared history are **never** permitted without explicit instruction.

---

## STOP-and-ask (handoff §9)

When any STOP trigger fires, **stop and ask**. Do not ship an alternative and disclose afterward.

---

## Goal

1. **Classifier / template:** Extend Tier 1 **HOURS_LOOKUP** (and related routing) so variants like **"open late on [day]"**, **"close at what time on [day]"**, **"open early on [day]"** match Tier 1 instead of Tier 3. Confirmed miss: **"is altitude open late on friday"** must hit Tier 1 after fix.
2. **Catalog-gap layer:** If sub-intent is **DATE_LOOKUP**, **LOCATION_LOOKUP**, or **HOURS_LOOKUP** and **no entity matched**, return a **templated gap response** and **do not** call Tier 3 for that path.
3. **Tech debt:** Add **rate-limiter test-mode env var** called for in the re-plan (carry from Phase 3.4 context — implement minimal, documented behavior tests rely on).

---

## In scope

- HOURS_LOOKUP (and any existing shared helpers) — **template/pattern additions only** for the phrasings above; align with existing Tier 1 patterns.
- **One new test fixture per new variant** (or minimal set that clearly covers each new phrasing class).
- Lightweight **pre–Tier 3** branch: DATE_LOOKUP / LOCATION_LOOKUP / HOURS_LOOKUP + **no `entity_matched`** → templated gap response (no Tier 3).
- Rate-limiter test-mode env var (name and behavior documented in code or existing docs pattern the repo uses).
- **No** new sub-intents unless unavoidable — prefer extending existing intents/templates.

## Out of scope

- Tier 2 retrieval path, Contribute mode, voice copy beyond what gap templates require, new sub-intents for their own sake, schema migrations beyond what is strictly required for 3.8 (if migration is not needed, do not add one).

---

## Constraints

- Do **not** weaken Track A or existing ask-mode tests.
- Match existing code style, routing, and logging patterns (`unified_router`, Tier 1 handlers, tests layout).
- Do **not** add dependencies unless already justified elsewhere in repo (prefer none).
- Do **not** print or log raw production user queries in new code paths.

---

## Acceptance criteria

- All **three** reruns of **"is altitude open late on friday"** (or equivalent fixture coverage proving the same routing) would route to **Tier 1** / HOURS_LOOKUP path — demonstrate via tests.
- Known-gap style behavior: for DATE_LOOKUP / LOCATION_LOOKUP / HOURS_LOOKUP with **no entity**, response is **template-only**, **no Tier 3** invocation (assert in tests or handler contract as appropriate).
- **Full ask-mode test suite** + **Track A regression** pass locally (`pytest` or project-standard command).

---

## Verification (you run)

1. Full test suite green.
2. Brief summary in your reply: files touched, how gap-template is triggered (conditions), env var name + purpose.

---

## Commit (only if you completed all acceptance criteria)

One commit. Message **exactly** (or adjust only if the owner changed it in review):

`Phase 3.8: HOURS_LOOKUP variants + catalog-gap template + rate-limit test mode`

Then `git push` to `main` **once**.

If commit message or scope is unclear, **STOP and ask** before committing.

---

## Owner notes (optional context for Claude)

- Commit message at end is a placeholder until the owner locks the exact string.
- Gap template wording is left to the implementer to match existing voice/tone in the codebase unless the owner adds a specific UX line.
- "Three reruns" in acceptance criteria matches production diagnostic narrative; tests may use one deterministic case unless the owner requests triple parametrization.
