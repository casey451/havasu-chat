> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context: `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md` (repo root), `docs/maintainability/project_index.md`.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Production URL:** https://havasu-chat-production.up.railway.app
- **Repo `main` @ this STATE update:** tip subject **docs(BACKLOG): tick #18 Phase B docs/ sub-bullet** · short SHA **`0fad8ee`** (2026-05-03); authoritative short SHA is the first line under **Recent commits** below. **After `git push`,** confirm Railway’s deployed revision matches `git rev-parse origin/main` (or the Railway dashboard commit).
- **Health:** `GET /health` is expected to return **200** with `db_connected`. Reconcile any `event_count` (or similar) field against a real Postgres client — counts drift with catalog changes.
- **Catalog posture (2026 RS-only cleanup, verified at stream close):** live **`events`** and **`contributions`** rows from **River Scene import** only (71 / 71 at cleanup close); **`providers`**, **`programs`**, **`field_history`**, **`llm_mentioned_entities`** were empty then. **Re-verify** before relying on numbers. Source: `docs/maintainability/non_river_scene_cleanup.md`.

## Tests

- **Test command:** `python -m pytest -q`
- **Note:** Legacy seed / master-file tests were removed with the River Scene–only ingestion cleanup. Expectations and failure modes changed vs older baselines; run the suite after major pulls.

## Recent commits (newest first)

```
0fad8ee docs(BACKLOG): tick #18 Phase B docs/ sub-bullet
f8da738 docs: prune phase-6-1 transcripts; formalize docs/ archive convention
97b642d docs(BACKLOG): tick #18 Phase B scripts sub-bullet; open #19, #20
28cd5c6 docs(scripts): document tools, fixtures, outputs, baselines convention
2627693 docs(BACKLOG, unified_router): resolve #8, note sandbox artifact in #18
857c7fc docs(project_index): add CURSOR_NEW_CHAT_PLAN row and .gitattributes mention
dc917f4 docs(BACKLOG): tick #18 Phase B; log truncation incident
23b2054 chore: add .gitattributes and normalize line endings to LF
67740de docs(BACKLOG): open #18 — repo hygiene & documentation hierarchy
ed76435 docs: add PM organization brief and Cursor new-chat playbook
364cd5f docs(findings_app_chat): mark H1 parallel-router finding historical
665ff4c docs(STATE): fix recent-commit SHA and stable main pointer
```

## Recently shipped (high signal)

- **`f8da738`..`0fad8ee`** — **Phase B `docs/` archive convention (Slice 5)** — Two misfiled session transcripts (`docs/phase-6-1-2-dry-run-transcript-2026-04-21.txt`, `docs/phase-6-1-3-execution-transcript-2026-04-21.txt`, ~13KB total) removed from the tree (recoverable via git log). Convention formalized in `docs/CURSOR_ORIENTATION.md` (Process conventions bullet) and `docs/maintainability/project_index.md` (post-doc-list paragraph): session transcripts and slice-complete writeups go to git history; live-session captures go to `relay/` (gitignored). Backlog #18 Phase B `docs/` sub-bullet ticked; remaining Phase B work is the root-convention sub-bullet.

- **`28cd5c6`..`97b642d`** — **Phase B `scripts/` convention (Slice 4)** — `scripts/README.md` rewritten from 13 to ~50 lines: directory convention table (committed tools, fixtures, baselines, output, gitignored ephemeral results) plus alphabetical inventory of all 16 tracked CLI tools with one-line purpose, output-path notes, and references to known-issue Backlog items where applicable. Backlog #18 Phase B `scripts/` sub-bullet ticked; tool default-path migration filed as Backlog #19, and the disposition of 5 legacy tracked outputs in `scripts/` (~410KB) filed as Backlog #20. No code change; no file moves in this slice.

- **`857c7fc`..`2627693`** — **Phase A drift sweep (Slice 3)** — `docs/maintainability/project_index.md` picks up the missing `CURSOR_NEW_CHAT_PLAN.md` row and a `.gitattributes` mention in the root tooling files line. Backlog #8 resolved by tightening the `tier_used` comment in `app/chat/unified_router.py:96` to match the precise wording already documented in `docs/components/unified_router.md`'s taxonomy table. Backlog #18 truncation paragraph annotated with a sandbox-unreliability follow-up: bash mount produces NUL-append and mid-content-truncation artifacts that don't reflect Casey's real filesystem; the original incident was never independently verified via PowerShell and may have been spurious.

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

- **OPEN** — **2**, **3**, **5**, **7**, **9**, **11**, **12**, **14**, **16**, **18**–**20** (see `docs/BACKLOG.md` for titles).
- **Recently resolved** — **8** (Slice 3, `2627693`); historical: **13**, **15** (`656d54b`).
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
