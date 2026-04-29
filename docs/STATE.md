> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context lives in `docs/PROJECT.md` if you need it.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Deployed commit:** `23a39a5` — H1 deletion ship tip (legacy `POST /chat` removed; unified `POST /api/chat` unchanged). Range: `61387e4..23a39a5` (9 commits: 1 plan doc + 7 ship + commit 3.5 amend for orphan imports).
- **Production URL:** https://havasu-chat-production.up.railway.app
- **Health:** `/health` returns 200, db_connected, event_count 114

## Tests

- **Pytest baseline:** 942 passing (8 failures: seed/backfill tests requiring `HAVASU_CHAT_MASTER.md` locally — pre-existing, unchanged by H1)
- **Test command:** `python -m pytest -q`

## Recent commits (newest first)

```
23a39a5  feat(schemas): remove legacy ChatRequest/ChatResponse (H1 commit 7)
f3da1df  feat(db): remove log_chat_turn + TRACK_A_TIER_USED (H1 commit 6)
6e528ed  feat(core): delete venues module (H1 commit 5 — orphan after /chat removal)
f70be20  feat(chat): delete legacy /chat router (H1 commit 4)
ef1e6a6  test: remove remaining /chat tests + invert Sentry scrub assertion (H1 commit 3.5)
cbe087e  feat(main): unwire legacy /chat router (H1 commit 3)
f76d5e2  test: remove /chat tests from mixed files (H1 commit 2)
dcc5454  test: remove test_phase4 (H1 commit 1 — legacy /chat duplicate tests)
61387e4  docs: file H1 deletion-ship plan
9aa5904  STATE.md: record session-launch-briefing ship
```

## Recently shipped (last work cycle)

- **H1 — Delete legacy `/chat` router** (`61387e4`..`23a39a5`) — Removed the Track A `POST /chat` stack: `app/chat/router.py` deleted; `app/main.py` unwired (`concierge_chat_router` only). Deleted orphan modules **`app/core/venues.py`**; deleted **`tests/test_phase4.py`** and **`tests/test_search_relevance.py`**. Trimmed **`app/db/chat_logging.py`** (`log_chat_turn`, `TRACK_A_TIER_USED`). Trimmed **`app/schemas/chat.py`** (legacy `ChatRequest` / `ChatResponse`); concierge schemas unchanged. Mixed test files no longer exercise legacy `/chat` (`test_api_chat`, `test_calendar_intent`, `test_phase2`, `test_phase3`, `test_phase6`, `test_phase8`, `test_phase8_5`, `test_phase87_privacy` — Sentry scrub assertion inverted so legacy `/chat` URLs are not scrubbed). **Production verification:** `GET /health` 200; `POST /chat` 404; `POST /api/chat` 200 with concierge response shape. **Deploy:** `6c416456-d1aa-4945-922a-cd6d7466c133`. **Suite:** 942 passing post-ship vs 987 pre-ship (**45 tests removed**, all legacy `/chat` integration coverage); **8** seed/backfill failures unchanged (not caused by H1). Follow-ups: **`docs/BACKLOG.md`** Backlog **7**–**11**.

- **Session-launch briefing artifact** (`e0e995f`) — `docs/CLAUDE_SESSION_BRIEFING.md` introduced as a version-controlled copy of the external session-launch briefing. Primary use is external paste at the start of fresh Claude sessions; in-repo copy is durable storage. The briefing carries project identity, role split, voice constraints, process discipline, and embedded doc-update rhythm inline; points at canonical state docs for everything that drifts. Stable orientation doc — not in the per-ship update set.

- **Session onboarding refresh + post-ship discipline** (`ea3f606` + `155cbac`) — `docs/POST_SHIP_CHECKLIST.md` introduced as the canonical post-ship runbook (what to update, what does not need updating, edge cases). `docs/START_HERE.md` trimmed to point at canonical state docs rather than carrying ship state inline (removes per-ship drift). `docs/CURSOR_ORIENTATION.md` refreshed in parallel with the same authoritative-docs structure. No application code changes; production verification was `/health` 200 with stable `event_count`.

- **Component reference docs introduced** (`f7d58f2` + `9848a51`) — `docs/components/` directory established as the per-component navigation layer for AI sessions; first entry is `unified_router.md` describing the `POST /api/chat` orchestrator (pipeline phases, public surface, tier_used taxonomy, conventions, known limitations). Companion working-agreement update (`9848a51`) codifies "component doc currency" — when code in component X changes, `docs/components/X.md` updates in the same commit, with explicit no-update reasoning required when no change is needed. No application code changes; production verification was `/health` 200 with stable `event_count`.

- **Docs tree cleanup** (`caab6f5`) — Removed 278 Markdown paths from the working tree (153 tracked deletions in commit; 125 were untracked/ignored filesystem-only). Scope: session and phase reports, relay artifacts, generated outputs, historical handoffs. `.gitignore` now uses `relay/` + `!relay/README.md` (replaces the prior three-line relay pattern). Rationale: ongoing maintenance is AI-assisted; files not instinctively opened for normal product work are not kept in-tree—git history retains removed content. No application code changes.

- **Canonical session docs** (`98b8545`) — `PROJECT.md`, `STATE.md`, `WORKING_AGREEMENT.md`, and `BACKLOG.md` under `docs/`; session-start pointer at top of `STATE.md`. No application code changes.

- **Past-date retrieval fix** (`6934d1d`) — `_query_events` no longer clamps explicit past date bounds to today. Production verification deferred until catalog has past-dated events.
- **Tier 2 ranking improvement** (`1c262ad`, SQL ordering portion only) — events whose start_date matches the query date rank above overlap-only events for `date_exact` queries. The prompt-rule portion of this commit was deployed but had no observable effect on the LLM and was superseded by `d279165`.
- **Clickable URLs** (`7d89a03` + `cdc4ac7` + emergent in `d279165`) — `event_url` flows through the row payload, frontend renders markdown link syntax as clickable anchors, deterministic renderer emits `[title](url)` for events with non-empty URLs.
- **Formatter completeness fix** (`d279165`) — Tier 2 event responses now render via deterministic Python instead of LLM. Row count, order, and verbatim titles structurally guaranteed. Programs and providers still use the LLM path with the existing prompt.

## Queued / open work

See `docs/BACKLOG.md` for the canonical list. Items not yet addressed:

- **H1 follow-ups** — Backlog **7**–**11** (post-H1 cleanup and infra carryovers).
- Programs and providers: scope-limited out of the deterministic renderer. Whether they have the same dropping/count-fabrication bug as events did is unverified.
- Phase 8.8.6 eval harness: automated LLM-behavior testing wiring is incomplete. Several deferred-verification notes in `BACKLOG.md` would close once this lands.

## Working tree

Tracked files clean after the H1 close-out (STATE/BACKLOG). Optional untracked Markdown under `docs/` (e.g. local design drafts) may still appear—stage intentionally if they should join `main`.

## How to update this document

At the end of each session that ships work, update:

- **Deployed commit** — new top commit hash and subject
- **Recent commits** — prepend the new commit(s); keep the list at roughly 10 entries
- **Recently shipped** — describe what changed in user-facing or architectural terms; reference the commit hash
- **Queued / open work** — adjust based on what's now closed vs. still pending

Do not update this file mid-session. Update it as part of close-out, after verification has confirmed ship.
