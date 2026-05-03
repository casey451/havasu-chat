> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context: `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md` (repo root), `docs/maintainability/project_index.md`.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Production URL:** https://havasu-chat-production.up.railway.app
- **Repo `main` @ this STATE update:** tip subject **docs: sync canonical orientation with repo reality** (2026-05-03); authoritative short SHA is the first line under **Recent commits** below. **After `git push`,** confirm Railway’s deployed revision matches `git rev-parse origin/main` (or the Railway dashboard commit).
- **Health:** `GET /health` is expected to return **200** with `db_connected`. Reconcile any `event_count` (or similar) field against a real Postgres client — counts drift with catalog changes.
- **Catalog posture (2026 RS-only cleanup, verified at stream close):** live **`events`** and **`contributions`** rows from **River Scene import** only (71 / 71 at cleanup close); **`providers`**, **`programs`**, **`field_history`**, **`llm_mentioned_entities`** were empty then. **Re-verify** before relying on numbers. Source: `docs/maintainability/non_river_scene_cleanup.md`.

## Tests

- **Test command:** `python -m pytest -q`
- **Note:** Legacy seed / master-file tests were removed with the River Scene–only ingestion cleanup. Expectations and failure modes changed vs older baselines; run the suite after major pulls.

## Recent commits (newest first)

```
364cd5f docs(findings_app_chat): mark H1 parallel-router finding historical
665ff4c docs(STATE): fix recent-commit SHA and stable main pointer
656d54b docs: sync canonical orientation with repo reality
905ce17 docs: prune low-utility historical markdown
5a55347 docs: project index for external-session navigation
e83ccf0 docs: chat behavior followup plan
7cba51e docs: add non_river_scene_cleanup maintainability retrospective
81fe20c chore: add cleanup_non_river_scene.py — purge non-RS data from DB
80f8383 docs: align project-handoff.md with River-Scene-only ingestion
6af8430 docs: align ops copy with River-Scene-only ingestion (pytest + env vars)
d84b9c1 chore: remove Havasu instructions seed lane and related backfills
da8734f chore: remove REAL_SEED lane, admin /reseed, and Railway auto-seed startup
0674467 chore: remove Google bulk ingest/embed and event-provider backfill lane
ac5f92a chore: remove provider seed module, master concierge populate, and tests
```

## Recently shipped (high signal)

- **`364cd5f`** — **`docs/maintainability/findings_app_chat.md`:** H1 “two parallel chat systems” marked historical (`router.py` / **`POST /chat`** removed per H1 ship).

- **Canonical doc sync (`656d54b`)** — Added **`HAVA_CONCIERGE_HANDOFF.md`** content at repo root; rewrote **`docs/STATE.md`** for RS-only posture and current backlog snapshot; fixed **`docs/PROJECT.md`** Tier 1 + catalog lines; refreshed **`START_HERE`**, **`CURSOR_ORIENTATION`**, **`CLAUDE_SESSION_BRIEFING`**, **`persona-brief`** (status + historical sections), **`BACKLOG`** (13/15 resolved, 16 OPEN), **`query-test-battery`**, **`known-issues`**, **`project_index`**, **`findings_app_chat`**, **`havasu-development-plan`** header; small comment updates in **`tier1_templates`**, **`smoke_concurrent_chat`**.

- **Doc hygiene + navigation (`905ce17`..`e83ccf0`)** — Added `docs/maintainability/project_index.md` (repo map, flows, doc index), `docs/maintainability/chat_behavior_followup_plan.md` (deferred chat eval + routing notes), and pruned slice-complete tier/Railway/handoff markdown (substance retained in **git history**). Updated cross-references in orientation docs, `known-issues`, `requirements.txt` comment, RS backfill index/runbook, `h2_consolidation_decision.md`, etc.

- **Non–River-Scene catalog cleanup (`81fe20c` + doc `7cba51e`)** — Script-driven removal of non–River-Scene catalog rows and lanes; production apply per retrospective. Chat and admin paths remain; first-party growth is **River Scene** + **approved contributions**.

- **H2 LLM infrastructure (`h2_consolidation_decision.md` § Status — completed)** — `app/core/llm_messages.py` and migrated Anthropic callers in Tier 2 parser/formatter, `llm_router`, Tier 3. Session-2 kickoff markdown files were later **removed from the tree**; design + commit stack remain in the decision doc and git log.

- **H1 legacy `/chat` removal (`61387e4`..`23a39a5`)** — Sole chat entry is **`POST /api/chat`**. Historical detail in `docs/maintainability/h1_router_decision.md` and git log.

## Queued / open work

See **`docs/BACKLOG.md`**. Snapshot:

- **OPEN** — **2**, **3**, **5**, **7**–**9**, **11**, **12**, **14**, **16** (see `docs/BACKLOG.md` for titles).
- **RESOLVED** this documentation pass — **13** (`STATE.md` drift), **15** (`query-test-battery.md` `venues.py` line).
- **DEFERRED** — **17** (OpenAI helper extraction until a second caller exists).
- **Confabulation / eval** — operator harness: `docs/confabulation-eval-runbook.md`, code under `app/eval/`. Broader “phase 8.8.6” spec markdown was pruned; recover from git history if needed.

## Working tree

Tracked files should be clean at close-out. Optional untracked artifacts under `relay/` (gitignored) are expected per `relay/README.md`.

## How to update this document

At the end of each session that ships work, update:

- **Repo / deploy pointers** — commit hash, production verification notes, catalog counts if materially changed
- **Recent commits** — prepend; keep ~10–12 lines
- **Recently shipped** — what changed for users or architecture
- **Queued** — align with `BACKLOG.md`

Do not update mid-session; update as part of verified close-out.
