> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context: `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md` (repo root), `docs/maintainability/project_index.md`.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Production URL:** https://havasu-chat-production.up.railway.app
- **Repo `main` @ this STATE update:** tip subject **docs(BACKLOG): tick #18 Phase B; log truncation incident** · short SHA **`dc917f4`** (2026-05-03); authoritative short SHA is the first line under **Recent commits** below. **After `git push`,** confirm Railway’s deployed revision matches `git rev-parse origin/main` (or the Railway dashboard commit).
- **Health:** `GET /health` is expected to return **200** with `db_connected`. Reconcile any `event_count` (or similar) field against a real Postgres client — counts drift with catalog changes.
- **Catalog posture (2026 RS-only cleanup, verified at stream close):** live **`events`** and **`contributions`** rows from **River Scene import** only (71 / 71 at cleanup close); **`providers`**, **`programs`**, **`field_history`**, **`llm_mentioned_entities`** were empty then. **Re-verify** before relying on numbers. Source: `docs/maintainability/non_river_scene_cleanup.md`.

## Tests

- **Test command:** `python -m pytest -q`
- **Note:** Legacy seed / master-file tests were removed with the River Scene–only ingestion cleanup. Expectations and failure modes changed vs older baselines; run the suite after major pulls.

## Recent commits (newest first)

```
dc917f4 docs(BACKLOG): tick #18 Phase B; log truncation incident
23b2054 chore: add .gitattributes and normalize line endings to LF
67740de docs(BACKLOG): open #18 — repo hygiene & documentation hierarchy
ed76435 docs: add PM organization brief and Cursor new-chat playbook
364cd5f docs(findings_app_chat): mark H1 parallel-router finding historical
665ff4c docs(STATE): fix recent-commit SHA and stable main pointer
656d54b docs: sync canonical orientation with repo reality
905ce17 docs: prune low-utility historical markdown
5a55347 docs: project index for external-session navigation
e83ccf0 docs: chat behavior followup plan
7cba51e docs: add non_river_scene_cleanup maintainability retrospective
81fe20c chore: add cleanup_non_river_scene.py — purge non-RS data from DB
```

## Recently shipped (high signal)

- **#18 Phase B — EOL normalization (`23b2054`..`dc917f4`)** — Added repo `.gitattributes` (`text=auto eol=lf` default + binary markers). HEAD was already LF; ship primarily fixes Windows-side CRLF drift on checkout via working-tree refresh. Pre/post `pytest -q` matched exactly (verification of behavior-neutrality). Truncation incident on `docs/BACKLOG.md` and `docs/STATE.md` discovered in pre-step survey; HEAD-restore performed before any normalization touched the index; forensic `stat` data and finding logged under Backlog #18.

- **`ed76435`..`67740de`** — **PM organization program kickoff (Slice 1 + Backlog #18 open)** — Added `docs/maintainability/project_manager_organization_brief.md` (zero-context PM onboarding, phases A–D, anti-patterns, success criteria) and `docs/CURSOR_NEW_CHAT_PLAN.md` (Mode A/B playbook, doc read order, paste templates, ship close-out). Indexed in `docs/maintainability/project_index.md`; `docs/CURSOR_ORIENTATION.md` now points to the playbook. Backlog #18 opened to track phased execution; the ~79-file CRLF↔LF working-tree drift surfaced during this session is queued as a Phase B sub-bullet, not bundled into this ship.

- **`364cd5f`** — **`docs/maintainability/findings_app_chat.md`:** H1 “two parallel chat systems” marked historical (`router.py` / **`POST /chat`** removed per H1 ship).

- **Canonical doc sync (`656d54b`)** — Added **`HAVA_CONCIERGE_HANDOFF.md`** content at repo root; rewrote **`docs/STATE.md`** for RS-only posture and current backlog snapshot; fixed **`docs/PROJECT.md`** Tier 1 + catalog lines; refreshed **`START_HERE`**, **`CURSOR_ORIENTATION`**, **`CLAUDE_SESSION_BRIEFING`**, **`persona-brief`** (status + historical sections), **`BACKLOG`** (13/15 resolved, 16 OPEN), **`query-test-battery`**, **`known-issues`**, **`project_index`**, **`findings_app_chat`**, **`havasu-development-plan`** header; small comment updates in **`tier1_templates`**, **`smoke_concurrent_chat`**.

- **Doc hygiene + navigation (`905ce17`..`e83ccf0`)** — Added `docs/maintainability/project_index.md` (repo map, flows, doc index), `docs/maintainability/chat_behavior_followup_plan.md` (deferred chat eval + routing notes), and pruned slice-complete tier/Railway/handoff markdown (substance retained in **git history**). Updated cross-references in orientation docs, `known-issues`, `requirements.txt` comment, RS backfill index/runbook, `h2_consolidation_decision.md`, etc.

- **Non–River-Scene catalog cleanup (`81fe20c` + doc `7cba51e`)** — Script-driven removal of non–River-Scene catalog rows and lanes; production apply per retrospective. Chat and admin paths remain; first-party growth is **River Scene** + **approved contributions**.

- **H2 LLM infrastructure (`h2_consolidation_decision.md` § Status — completed)** — `app/core/llm_messages.py` and migrated Anthropic callers in Tier 2 parser/formatter, `llm_router`, Tier 3. Session-2 kickoff markdown files were later **removed from the tree**; design + commit stack remain in the decision doc and git log.

- **H1 legacy `/chat` removal (`61387e4`..`23a39a5`)** — Sole chat entry is **`POST /api/chat`**. Historical detail in `docs/maintainability/h1_router_decision.md` and git log.

## Queued / open work

See **`docs/BACKLOG.md`**. Snapshot:

- **OPEN** — **2**, **3**, **5**, **7**–**9**, **11**, **12**, **14**, **16**, **18** (see `docs/BACKLOG.md` for titles).
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
