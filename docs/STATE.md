> **Fresh Claude or Cursor session?** Read this file first, then `docs/WORKING_AGREEMENT.md`, then `docs/BACKLOG.md`. Architecture context: `docs/PROJECT.md`, `HAVA_CONCIERGE_HANDOFF.md` (repo root), `docs/maintainability/project_index.md`.

# Current state

This document is updated at the end of each session that ships work. It is the canonical answer to "where is the project right now."

## Production

- **Production URL:** https://havasu-chat-production.up.railway.app
- **Repo `main` @ this STATE update:** tip subject **docs(BACKLOG): open #21-#23 (bonus findings from Slices 8, 10)** · short SHA **`5412695`** (2026-05-04); authoritative short SHA is the first line under **Recent commits** below. **After `git push`,** confirm Railway’s deployed revision matches `git rev-parse origin/main` (or the Railway dashboard commit).
- **Health:** `GET /health` is expected to return **200** with `db_connected`. Reconcile any `event_count` (or similar) field against a real Postgres client — counts drift with catalog changes.
- **Catalog posture (2026 RS-only cleanup, verified at stream close):** live **`events`** and **`contributions`** rows from **River Scene import** only (71 / 71 at cleanup close); **`providers`**, **`programs`**, **`field_history`**, **`llm_mentioned_entities`** were empty then. **Re-verify** before relying on numbers. Source: `docs/maintainability/non_river_scene_cleanup.md`.

## Tests

- **Test command:** `python -m pytest -q`
- **Note:** Legacy seed / master-file tests were removed with the River Scene–only ingestion cleanup. Expectations and failure modes changed vs older baselines; run the suite after major pulls.

## Recent commits (newest first)

```
5412695 docs(BACKLOG): open #21-#23 (bonus findings from Slices 8, 10)
894dc28 docs(BACKLOG): close #20 (legacy tracked-output disposition)
15f7248 chore(scripts): remove 5 legacy tracked outputs (Backlog #20)
ddb8569 docs(BACKLOG): close #19 (tool default-path migration)
d429fe7 chore(scripts): migrate tool default output paths to scripts/output/
61f73b4 docs(BACKLOG): tick #18 Phase C end-to-end creation sub-bullet
c1cd8b0 docs(maintainability): add end_to_end_creation.md (Phase C)
f179e84 docs(BACKLOG): tick #18 Phase C HTTP API sub-bullet
5f14f36 docs(maintainability): add http_api.md (Phase C HTTP API sketch)
06b62c7 docs(BACKLOG): restructure #18 Phase C into sub-bullets; tick Railway
765ee61 docs(maintainability): add railway_layout.md (Phase C kickoff)
a4d8449 docs(BACKLOG): tick #18 Phase B root sub-bullet (Phase B complete)
```

## Recently shipped (high signal)

- **`5412695`** — **Bonus findings filed (Slice 12)** — Three observations from earlier slices filed as trackable Backlog items rather than buried in doc/commit narrative: **#21** (`POST /events` posture review, surfaced in Slice 8 http_api.md), **#22** (`/admin/debug-pw` posture review, surfaced in Slice 8), **#23** (`diagnose_search.py` cleanup — stale `BASE_URL` and docstring, surfaced in Slice 10 #19 closure). All three are LOW severity. Pure backlog bookkeeping; no code or doc change beyond BACKLOG.md additions.
- **`15f7248`..`894dc28`** — **#20 close: legacy tracked-output disposition (Slice 11)** — Removed 5 legacy tracked outputs from `scripts/` (`battery_results.json` 68KB + 4 dated `voice_audit_results_2026-04-*.json` totaling ~340KB; ~410KB freed). All recoverable via `git log -- <path>`. `scripts/README.md` legacy paragraph removed in same commit. Three other narrative/historical references in `havasu-development-plan.md`, `runbook.md`, `known-issues.md` left as-is per project_index convention. Pytest count unchanged pre/post. Phase B follow-up family fully closed (#19 in Slice 10, #20 here).
- **`d429fe7`..`ddb8569`** — **#19 close: tool default-path migration (Slice 10)** — `scripts/run_voice_audit.py:1097` and `scripts/diagnose_search.py:19` updated to write under `scripts/output/` (the gitignored convention established in Slice 4's `scripts/README.md` rewrite). `parent.mkdir(parents=True, exist_ok=True)` added before each `write_text` to handle fresh-clone directory absence; matches the pattern already used by the other scripts/output writers. Three other CLI tools surveyed (`extract_tier3_queries.py`, `run_voice_spotcheck.py`, `confabulation_eval.py`) already used a correct convention; no edits needed. Pytest count unchanged pre/post (behavior-neutral). Bonus finding noted in #19 resolution: `diagnose_search.py:18 BASE_URL` is stale and would fail if the script were run as-is.
- **`c1cd8b0`..`61f73b4`** — **Phase C: End-to-end creation doc (Slice 9)** — New `docs/maintainability/end_to_end_creation.md` (~140 lines) documents the four paths that produce catalog rows: public submission via `/contribute` → admin review → `approval_service.approve_contribution_as_*`; River Scene auto-import (CLI script → contribution-shaped row → same admin review); Tier 3 mention scan via `mention_scanner.scan_and_save_mentions` → `LlmMentionedEntity` queue → admin promotion creates Provider; admin direct create (Programs only via `/admin/programs/new`). Plus Contribution status state machine (pending/approved/rejected/needs_info), per-entity-type fields touched at creation, and explicit non-coverage list. Indexed in project_index Maintainability table; §5 gap bullet for "no end-to-end provider/program creation doc" removed. Backlog #18 Phase C now 3/6 ticked (Railway + HTTP API + end-to-end).
- **`5f14f36`..`f179e84`** — **Phase C: HTTP API sketch (Slice 8)** — New `docs/maintainability/http_api.md` (~140 lines) consolidates all 58 routes: mount layout (7 routers/prefixes), public routes by group (chat, UI/legal, health, events, contribute, programs), admin HTML routes (`/admin/*`, cookie-gated via `verify_admin`), admin JSON API routes (`/admin/api/*`, `Depends(require_admin)`), auth posture summary, rate limits (5 slowapi + 1 custom contribute limiter), schema pointers to `app/schemas/`. Indexed in project_index Maintainability table; §5 gap bullet for "no API reference doc" removed. Backlog #18 Phase C now 2/6 ticked (Railway + HTTP API). Doc notes but doesn't gate on two observations: `POST /events` is a public rate-limited endpoint (Phase 1 leftover?) and `/admin/debug-pw` is an unauthenticated admin debug helper (verify production posture); both queued for future review.

- **`765ee61`..`06b62c7`** — **Phase C kickoff: Railway service layout doc (Slice 7)** — New `docs/maintainability/railway_layout.md` consolidates Hava's Railway deployment surface (process types, build, DB URL resolution, env var matrix, .env semantics, health checks, deploy flow, explicit non-coverage list). Indexed in project_index Maintainability table; §5 gap bullet for Railway service layout removed. Backlog #18 Phase C restructured into sub-bullets (1 ongoing component-docs growth + 5 §5 gaps); Railway sub-bullet ticked. 4 §5 gaps remain (HTTP API sketch, CI query-battery story, provider ingestion lane, end-to-end provider/program creation).

- **`ea4fcfb`..`a4d8449`** — **Phase B `repo root` convention (Slice 6) — Phase B complete** — Repo root reserved for project spine (top-level packages, build/deploy config, tooling config, architecture spine doc); operational clutter (local SQLite DBs, script logs, env overrides, bytecode) gitignored at root or under packages; live-session captures go to `relay/`. Convention documented in `README.md` along with a current-Hava rewrite (replacing the stale 16-line Phase 1 stub that referenced removed `POST /events` endpoints) and a navigation table pointing at STATE/BACKLOG/WORKING_AGREEMENT/HAVA_CONCIERGE_HANDOFF/project_index/persona-brief/CURSOR docs. Misfiled `admin-dashboard-pending.png` (~30KB, no references) removed; recoverable via git log. `project_index.md` §5 gap bullet ("README does not mention relay/") removed since closed by this rewrite. **Backlog #18 Phase B is now complete (4/4 sub-bullets ticked: EOL, scripts, docs, root). Remaining #18 work: Phases A (ongoing), C, D.**

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

- **OPEN** — **2**, **3**, **5**, **7**, **9**, **11**, **12**, **14**, **16**, **18**, **21**–**23** (see `docs/BACKLOG.md` for titles).
- **Recently resolved** — **8** (Slice 3, `2627693`); **19** (Slice 10, `d429fe7`); **20** (Slice 11, `15f7248`); historical: **13**, **15** (`656d54b`).
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
