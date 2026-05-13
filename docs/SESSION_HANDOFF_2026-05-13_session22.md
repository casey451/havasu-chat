# Session-22 Handoff — 2026-05-13

> **Audience:** the next Cowork primary on havasu-chat. **Read time:** ~3 minutes. Then boot per `outputs/session_23_boot_prompt.md`. Most state is durable on origin; this doc captures the deltas since the session-21 close (`d5e9b71`) + what's queued.

---

## §1 — What session-22 accomplished

**Production deploy of Phase 1C + 1D + 2A + 2B + 3 SHIPPED to Railway** (6 alembic migrations walked cleanly on Postgres; alembic head `b2c3d4e5f6a7 → e1f2a3b4c5d6`). **Parks-rec-scrapes cron restored and verified** (workflow_dispatch run #26 green at 1m 5s end-to-end). **Latent Phase 1D circular-import bug fixed** at `5faa37c` with a regression test that locks in the cure. Pytest **1702 → 1703** (+1 net-new).

Session-22 substantive chain on origin/main: `d5e9b71 → 18a4100 → 5faa37c → d506b5a → 81b6f55 → <SHA-patch>`.

| Commit | Summary |
|---|---|
| (carry-over) `d5e9b71` | session-21 SHA-patch chore (closed out session-21; was top of main at boot) |
| `18a4100` | **chore(ci): re-enable parks-rec-scrapes cron after production deploy lands.** One-line patch to `.github/workflows/parks-rec-scrapes.yml` uncommenting the `schedule:` block (`cron: "15 */6 * * *"`); PAUSED comment block replaced with RESTORED block citing deployed SHA `d5e9b71` + alembic head `e1f2a3b4c5d6`. `workflow_dispatch: {}` retained for operator manual runs. Reverses session-21's `59521dd` pause. |
| `5faa37c` | **fix(db): break Phase 1D dual-write hook registration cycle — centralize in app/db/__init__.py.** Resolves the parks-rec-scrapes workflow failure that session-21 handoff §2 misdiagnosed as ORM-vs-prod-DB schema mismatch. Real cause: `app/db/database.py` module-top `_register_orm_listeners()` worked under uvicorn (canonical entry-point loads models first) but broke any entry point that reached `contribution_store → models → database` before models finished initializing — `entity_dual_write` tried to import `ContactPoint` from a partially-initialized `app.db.models` → `ImportError`. Latent regression since session-16's Phase 1D ship at `3f3628e`. Fix moves registration to `app/db/__init__.py` (was empty); the package init runs once when any `app.db.*` module is first imported, BEFORE any submodule attribute lookup, so it serializes the load order. Both leaf modules (database.py + entity_dual_write.py) are now free of cycle-creating imports. **First attempted fix** put registration at end-of-file in `models.py` (mirror of `_register_provider_slug_listeners()`); that shifted the cycle to `entity_dual_write → models → entity_dual_write` and was reverted before push. Three files: `app/db/__init__.py` NEW (37 lines: registration + docstring history of two attempted-and-rejected leaf-module locations); `app/db/database.py` MODIFIED (-11/+11: function + call removed, replaced with explanatory comment); `tests/test_phase1d_dual_write.py` MODIFIED (+57: new `test_scraper_entry_point_import_chain_does_not_cycle` runs the failing import in a subprocess to bypass sys.modules cache masking, asserts chain succeeds + `_CATALOG_DUAL_WRITE_HOOKS_REGISTERED` flag True). Pytest 1702 → 1703. Zero regressions. Application-code-only — no migration impact. |
| `d506b5a` | **docs: Phase 3 DEPLOYED 2026-05-13 + dispatch_channels gotcha #17 + STATE.md session-22 production block refresh.** Three docs touched: master plan §4 Phase 3 status line gets `DEPLOYED 2026-05-13` annotation + production-deploy sentence; dispatch_channels.md adds gotcha #17 (module-import-time hook registration cycle + the session-21 misdiagnosis companion lesson "confirm via log/repro before locking a diagnosis"); STATE.md Production block refreshed across 5 paragraphs (HEAD origin `5faa37c`, deployed `d5e9b71`, alembic prod head `e1f2a3b4c5d6`, six-migration deploy narrative with pre-flight verifications + post-deploy smokes, build phase notes Phase 1+2+3 LIVE in production, pytest 1702 → 1703). STATE.md Recent commits prepended with session-22 commits. STATE.md Recently shipped §1 prepended with comprehensive session-22 entry covering deploy + cron restore + fix + 4 session-22 lessons. |
| `81b6f55` | Session-22 close-out commit — this handoff doc + `outputs/session_23_boot_prompt.md` + STATE.md Recent commits final prepend with the docs commit SHA `d506b5a` (this close-out itself gets SHA-patched in the follow-up chore per session-21 precedent at `d5e9b71`). |
| `<SHA-patch>` | **chore: SHA-patch follow-up — patch session-22 docs commit + close-out SHAs into session-23 boot prompt + this handoff doc + STATE.md Recent commits.** Mirrors session-21 close `d5e9b71` precedent (land SHA-patches at session close, not session-23 boot — zero pending placeholders for next primary). |

### Production deploy details (operator-run)

Pre-flight verifications:

- `pg_trgm` extension availability on Railway Postgres: `SELECT * FROM pg_available_extensions WHERE name='pg_trgm'` returned `default_version 1.6 / installed_version 1.6` — extension was already installed, so the Phase 2B.2 migration's `CREATE EXTENSION IF NOT EXISTS pg_trgm` was a no-op. Highest-risk first-deploy DDL had zero risk.
- All 8 required env vars confirmed present in Railway Variables tab: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL_BASE`, `RESEND_API_KEY`, `RESEND_FROM_ADDRESS`, `AUTH_MAGIC_LINK_BASE_URL`. 6 were in the staged "Apply 9 changes" set; applying the changes triggered the auto-deploy.

Deploy execution:

- Railway auto-deployed when operator applied 9 staged env-var changes (Railway config rule: env-var application triggers redeploy). Deploy timestamp 07:06:34 UTC.
- Migration runner walked all six migrations cleanly: `f8e9d0c1b2a3 → 92ce4899dc08 → c8d9e0f1a2b3 → f9e8d7c6b5a4 → d0e1f2a3b4c5 → e1f2a3b4c5d6`.
- Deploy logs showed alembic init lines (`Context impl PostgresqlImpl. Will assume transactional DDL.`) and the deploy marked "successful" — Railway only marks deploys successful after build + release + start phases all complete cleanly.

Post-deploy smoke:

- Direct Postgres query: `SELECT version_num FROM alembic_version` returned `e1f2a3b4c5d6`. All six migrations applied.
- `/home` rendered cleanly with events visible + search box active (UI is mid-rebuild per operator note — rendered home page categories show mixed canonical 12 + legacy free-text labels; that's browser/CDN-cached vintage of the home page, not a data correctness issue).
- `/api/search?q=marina` returned JSON 200 with multi-result match — River Scene marina entities (`Marina Fuel Station`, `Havasu Riviera Marina`, `Lake Havasu Marina Fuel Dock`, etc.) surfaced with non-trivial ranking scores. Confirms FTS index built + queryable + ranking pipeline works on Postgres.
- Magic-link login + photo upload smokes deferred (functional surface, not migration correctness).

### Workflow_dispatch verification

After `5faa37c` landed on main, Casey manually triggered `parks-rec-scrapes` workflow_dispatch run #26 on GitHub Actions. Run completed in 1m 5s with green ✓ status; `pull-and-load` step ran 4s vs the previous 48s+exit-code-1 ImportError failure. Cron is durably restored for the next scheduled fire (15 minutes past every 6h boundary).

---

## §2 — What's in flight or queued

- **Phase 4 — pending brief authoring + dispatch.** Phase 4 brief does NOT exist yet; that's the gating artifact for Phase 4 dispatch. Per master plan §4 Phase 4: background-jobs + layered scrape infrastructure (Option A from `docs/maintainability/background_job_infrastructure_decision.md` — Railway scheduled jobs + FastAPI BackgroundTasks + optional Outbox + layered scrape strategy from `docs/maintainability/layered_scrape_strategy.md`). Estimated L (10-15 days dispatch); parallel-eligible sub-lanes (OSM client + LHC open data clients separable). Carries over from session-21 (lane (a) of the session-22 lane pick was Phase 4 brief authoring; operator chose lane (b) production deploy instead).

- **UI rebuild (in flight, separate workstream).** Casey noted mid-session that the UI is being rebuilt. The post-deploy `/home` render showed mixed-vintage category labels which the operator attributed to "the UI is old…we are changing the ui anyway so i dont know if this is right or not." Whoever picks up session-23 should ask about UI rebuild progress + whether that's the higher-priority lane than Phase 4 backend.

- **Functional smokes deferred from session-22 deploy** — magic-link login + photo upload routes are wired and depend on env vars that we verified are present, but no live end-to-end test has been run. If a user reports either fails post-deploy, that's the first thing to debug.

- **`docs/BACKLOG.md` unstaged modification** — carry-over from session-21 §3. Stray modification in working tree from before session-21; not in any session-22 commit. Either commit as its own lane or revert if stray.

---

## §3 — Open operator-decision items

| Item | When | Notes |
|---|---|---|
| Author Phase 4 brief | Session-23 or later | Phase 4 brief authoring is the gating artifact for Phase 4 dispatch. Read `docs/maintainability/background_job_infrastructure_decision.md` + `docs/maintainability/layered_scrape_strategy.md` end-to-end first. |
| UI rebuild workstream | In flight per operator | Higher priority than Phase 4 if active. Whoever picks up session-23 should ask Casey for context on where the UI rebuild stands. |
| Resolve `docs/BACKLOG.md` unstaged modification | Session-23 or later | Carry-over from session-21. |
| AirNow API key registration | Pre-Phase-8 (months out) | ~20 min; signup + Railway env var drop. |

---

## §4 — Pragmatic deviations to remember (session-22 ships)

Phase 1D circular-import fix (commit `5faa37c`):

- **The fix had to land in `app/db/__init__.py`, not in either leaf module.** First attempt put `register_catalog_dual_write_hooks()` at end-of-file in `models.py` (mirror of `_register_provider_slug_listeners()`). That works for the original failure path (parks-rec scraper) but breaks any test that imports `entity_dual_write` directly — the cycle is `entity_dual_write → models → entity_dual_write` (entity_dual_write hasn't defined `register_catalog_dual_write_hooks` yet when models tries to import it at end-of-file). Only `app/db/__init__.py` is structurally cycle-free for all entry points because Python runs `__init__.py` once at package-first-import time, before any submodule attribute lookup, so it can drive the load order without itself being part of any cycle.
- **The session-21 handoff §2 diagnosis was wrong.** "ORM-vs-prod-DB schema mismatch since Phase 3.1 ship" was inferred from workflow exit code 1 + known origin-vs-prod schema gap without inspecting the GitHub Actions stack trace. The actual error was always a Python ImportError, not a Postgres column-does-not-exist error. The fix for the production deploy was correct and necessary anyway (production was 5 months behind origin), but it didn't address the actual scraper bug. Session-22 lesson: confirm via log/repro before locking a diagnosis. Captured durably in dispatch_channels.md gotcha #17.
- **Latent regression since Phase 1D shipped at `3f3628e` (session-16, ~5 months earlier).** The bug existed in the code from the moment Phase 1D shipped; it never surfaced because no entry point exercised the broken import path until the parks-rec scraper started running on its 6h cadence. Reminder: latency between "code shipped" and "bug surfaced" can be months when no consumer exercises the broken path.

Session-22 process deviations:

- **Edit tool wrote to Windows; Linux bash mount served stale view.** Mid-session the Edit tool modified `app/db/models.py` (verified via Read at line 1491 showing the new dual-write block) but the Linux bash mount continued to serve the pre-edit 1475-line version even after `sync` + O_DIRECT + dd. Practical impact: in-sandbox pytest runs against the mount would have tested stale code; verification was deferred to Casey's Windows-side venv (which sees the current file content). Cure: trust Windows-side Read for file content; defer pytest verification to Windows-side when Linux mount lag is observed. Extension of gotcha #7 (Linux bash mount staleness) from `.git` views to working-tree files.

---

## §5 — New lessons absorbed in session-22

1. **Confirm via log/repro before locking a diagnosis.** Session-21's "ORM-vs-prod-DB schema mismatch" diagnosis was made from workflow exit code 1 + the known origin-vs-prod schema gap, without ever reading the actual stack trace. Both context pieces were true; neither was the actual cause. The first-failure surface in the trace (the ImportError) told us exactly what was broken in ~5 seconds of log inspection. Decision-rule for future agents: when diagnosing a workflow failure, always read the actual stack trace from the GitHub Actions log before locking a root-cause story — even when the "obvious" diagnosis matches the timeline + known state-of-the-world. Captured durably as the companion lesson in dispatch_channels.md gotcha #17.

2. **Module-import-time hook registration creates cycles when alternate entry points hit the module before the canonical path.** Phase 1D's `_register_orm_listeners()` at `app/db/database.py` module-top worked under uvicorn (loads `app.main → models` first) but cycled under any other entry point. Cure: cross-module registration belongs in the package `__init__.py`, not a leaf module. First-attempted-and-rejected location was end-of-file in models.py; that shifted the cycle rather than breaking it. The `__init__.py` location is documented in the file's docstring with both rejected alternatives, deterring future regressions.

3. **Gotcha #15 discipline held throughout** (continuation; four-session streak now session-19 + 20 + 21 + 22) — zero bash `git` operations against the working tree all session; HEAD verification via Read on `.git/refs/heads/main` + parent-walk decompression via `python3 + zlib.decompress` on `.git/objects/` per gotcha #14 cure pattern.

4. **Gotcha #16 discipline held throughout** (continuation; three-session streak now session-20 + 21 + 22) — all session-22 commit recipes used PowerShell-safe single-quoted `-m` bodies with em-dashes / `->` / plain text for emphasis; no embedded double-quote pairs.

5. **Linux mount view of the working tree can lag Windows edits** — extension of gotcha #7 from `.git` views to working-tree files. Surfaced session-22 when Edit tool modified `app/db/models.py` but bash mount continued serving the pre-edit version even after `sync` + O_DIRECT. Windows-side Read is authoritative for file content too; defer in-sandbox pytest to Windows-side venv when mount lag is observed.

6. **Railway auto-deploys on env-var application.** Discovered session-22: applying staged env-var changes in Railway UI auto-triggers a redeploy. Useful for "deploy without pushing new code" scenarios (the same git HEAD redeploys with new env). Was the trigger that initiated the session-22 production deploy.

---

## §6 — Pointers for the next agent

Boot order:

1. `outputs/session_23_boot_prompt.md` (the boot prompt Casey pastes; see that file)
2. `docs/STATE.md` (refreshed 2026-05-13 at session-22 close — start with the Production block + `5faa37c` HEAD reference + Phase 1+2+3 LIVE annotation + alembic prod head `e1f2a3b4c5d6`)
3. `docs/maintainability/master_build_plan.md` §4 Phase 3 (SHIPPED 2026-05-12 · DEPLOYED 2026-05-13) + §4 Phase 4 (next dispatchable; brief not yet authored)
4. `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules) + `docs/maintainability/dispatch_channels.md` (17 gotchas as of session-22; gotcha #17 landed session-22 — module-import-time hook registration cycle + the session-21 misdiagnosis companion lesson)
5. `docs/maintainability/background_job_infrastructure_decision.md` + `docs/maintainability/layered_scrape_strategy.md` (Phase 4 design context for the brief authoring task, IF that's the chosen lane)

Session-22 absorbed six new lessons (above) worth carrying into future dispatches. The narrative in `docs/STATE.md` "Recently shipped" §1 captures every session-22 commit + decision + deviation with enough detail that the next agent shouldn't need to re-read this handoff except for §3 above + the UI rebuild question.

**Carry-over urgency for session-23:** the production deploy + cron + bug fix all landed clean, so there's no operational gating issue forcing a particular lane. Likely lane priority based on session-22 signals: (i) UI rebuild workstream (Casey actively rebuilding; ask for status), (ii) Phase 4 brief authoring (gated artifact for next major backend phase), (iii) hold + smaller follow-ups (BACKLOG.md cleanup, AirNow registration). Casey decides.

---

*Authored at session-22 close, 2026-05-13. Production is live + healthy at `d5e9b71` / alembic `e1f2a3b4c5d6`. Origin is at `5faa37c` (the circular-import fix). Next agent boots from a state where there's no urgent fire — pick the lane that fits Casey's current focus.*
