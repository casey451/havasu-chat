# Session-23 Boot Prompt

> Paste this into the next Cowork session to boot the primary on havasu-chat. Origin/main HEAD will be `81b6f55` (session-22 close-out commit, to be SHA-patched here pre-paste mirroring `d5e9b71` precedent). Six-plus commits this session-22: `18a4100` (cron restore) → `5faa37c` (circular-import fix) → `d506b5a` (docs refresh) → `81b6f55` (this close-out: handoff + boot prompt + STATE.md Recent commits final prepend) → `<TBD-sha-patch>` (SHA-patch follow-up). SHA-patch chore lands at session-22 close (mirrors `d5e9b71` precedent — zero pending placeholders for next primary).

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-22) shipped the production
deploy of Phase 1C + 1D + 2A + 2B + 3 to Railway (6 alembic migrations
walked cleanly on Postgres; alembic head b2c3d4e5f6a7 -> e1f2a3b4c5d6),
restored the parks-rec-scrapes cron, and fixed a latent Phase 1D
circular-import bug at 5faa37c that had been failing the scraper every
6h since session-20 (the session-21 handoff misdiagnosed it as
ORM-vs-prod-DB schema mismatch; real cause was a module-import-time
hook registration cycle in app/db/database.py that worked under uvicorn
but broke any other entry point). Pytest 1702 -> 1703 (+1 net-new
regression test). State is durable on origin/main HEAD = 81b6f55.
Production live at d5e9b71. Six-plus commits this session-22.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-13_session22.md — closes out session-22.
   Captures the six-plus-commit narrative (production deploy via Railway
   auto-deploy + cron restore + circular-import fix + 2 docs commits +
   close-out + SHA-patch), the deploy details (pre-flight pg_trgm + 8
   env vars verified; 6 migrations walked clean at 07:06:34 UTC;
   /api/search?q=marina verified ranked JSON 200; alembic_version table
   queried directly returned e1f2a3b4c5d6), the circular-import fix
   summary (commit 5faa37c; latent regression since session-16's Phase
   1D ship at 3f3628e; fix moves registration from database.py
   module-top to app/db/__init__.py; first-attempted-and-rejected
   end-of-file-in-models.py location documented in __init__.py
   docstring), workflow_dispatch run #26 green at 1m 5s, queued Phase 4
   brief-authoring + UI rebuild + smaller follow-ups, accepted
   pragmatic deviations (most notable: the fix had to land in
   __init__.py not a leaf module; session-21 handoff misdiagnosis
   captured durably; Edit-tool-to-Linux-mount-stale gotcha extension),
   six new lessons (confirm via log/repro before locking a diagnosis;
   module-import-time hook registration creates cycles for alternate
   entry points; gotcha #15 + #16 discipline held -- four + three
   session streaks; Linux mount lag for working-tree files; Railway
   auto-deploys on env-var application).
2. docs/STATE.md — Production block notes Phase 1+2+3 LIVE in production
   as of 2026-05-13 (deployed d5e9b71, alembic e1f2a3b4c5d6); HEAD
   origin/main reaches 81b6f55; pytest 1703; build phase
   updated. Recent commits block has the session-22 chain. Recently
   shipped sec 1 has the full session-22 narrative.
3. docs/maintainability/master_build_plan.md sec 4 Phase 3 (SHIPPED
   2026-05-12 · DEPLOYED 2026-05-13; Status line refreshed) + sec 4
   Phase 4 description outlines the next dispatchable major phase
   (background-jobs + layered scrape infrastructure; L estimate
   10-15 days dispatch; parallel-eligible sub-lanes).
4. docs/maintainability/background_job_infrastructure_decision.md +
   docs/maintainability/layered_scrape_strategy.md -- Phase 4 design
   context. If choosing Phase 4 brief-authoring lane, read end-to-end
   before authoring.
5. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (17 gotchas as
   of session-22; gotcha #17 landed session-22 -- module-import-time
   hook registration creates cycles when alternate entry points hit
   the module before the canonical path; package __init__.py is the
   only cycle-free location for cross-module registration; companion
   lesson: confirm via log/repro before locking a diagnosis).
6. .github/workflows/parks-rec-scrapes.yml -- cron is RESTORED per
   session-22's 18a4100 chore commit. Cron fires every 6h, 15 minutes
   past the hour. workflow_dispatch verified green at run #26 (1m 5s).

## New lessons from session-22 worth folding into Phase 4 brief
1. **Confirm via log/repro before locking a diagnosis.** Session-21's
   "ORM-vs-prod-DB schema mismatch" diagnosis was wrong; the real cause
   was a Python ImportError visible in the GitHub Actions stack trace
   the whole time. Cure: read the actual stack trace before locking a
   root-cause story, even when the obvious diagnosis matches the
   timeline. Pattern is durably captured in dispatch_channels.md
   gotcha #17 as the companion lesson.

2. **Module-import-time hook registration creates cycles when alternate
   entry points exist.** Phase 1D's database.py module-top register
   call worked under uvicorn but broke the parks-rec scraper entry
   point. Latent regression since session-16. Cure: cross-module
   registration belongs in the package __init__.py, not a leaf module
   — __init__.py runs before any submodule attribute lookup so it can
   drive load order. First-attempted-and-rejected location was
   end-of-file in models.py (mirror of _register_provider_slug_
   listeners); that shifted the cycle. Only the third-party location
   (__init__.py) is structurally cycle-free for ALL entry points.
   Captured in dispatch_channels.md gotcha #17.

3. **Gotcha #15 discipline held throughout (four-session streak).**
   Zero bash git operations against working tree all session; HEAD
   verification via Read on .git/refs/heads/main + parent-walk
   decompression via python3+zlib on .git/objects/ per gotcha #14
   cure pattern; alembic head via Glob on alembic/versions/; file-
   presence via Glob/Grep.

4. **Gotcha #16 discipline held throughout (three-session streak).**
   All session-22 commit recipes used PowerShell-safe single-quoted
   -m bodies with em-dashes / -> / plain text for emphasis; no
   embedded double-quote pairs; all commits landed clean.

5. **Linux mount view of working tree can lag Windows edits.**
   Extension of gotcha #7 from .git views to working-tree files.
   Surfaced session-22 when Edit tool modified app/db/models.py but
   bash mount continued serving the pre-edit version even after sync
   + O_DIRECT. Windows-side Read is authoritative for file content;
   defer in-sandbox pytest to Windows-side venv when mount lag is
   observed.

6. **Railway auto-deploys on env-var application.** Applying staged
   env-var changes in Railway UI auto-triggers a redeploy. Useful
   for "deploy without pushing new code" scenarios. Was the trigger
   that initiated the session-22 production deploy.

## Your first actions, in order
1. Run baseline: read top of .git/refs/heads/main via Read tool
   (top should be 81b6f55 + the SHA-patch chore commit if it
   landed per session-22 close-out followups, else 81b6f55
   directly), cross-check docs/STATE.md Recent commits block for the
   81b6f55 -> d506b5a -> 5faa37c -> 18a4100 -> d5e9b71
   chain, confirm alembic head e1f2a3b4c5d6 via Glob on alembic/
   versions/. Run python -m pytest -q --collect-only | tail -3 if
   Windows-side venv is available (should show 1703 + 1 skipped).
   Report values to Casey. DO NOT use bash git ... per gotcha #15.

2. Ask Casey which lane to pursue: (a) Phase 4 brief authoring
   (background-jobs + layered scrape infrastructure; L 10-15 days
   dispatch estimate; parallel-eligible sub-lanes); (b) UI rebuild
   workstream (Casey mentioned mid-session-22 that the UI is being
   rebuilt; check status before deciding scope); (c) smaller follow-
   ups (BACKLOG.md unstaged-mod cleanup, AirNow API key registration,
   functional smokes Casey wanted to defer like magic-link + photo
   upload); (d) hold. Recommend (b) if Casey is actively rebuilding
   UI; recommend (a) if Casey wants forward progress on master plan
   backend; recommend (c) if Casey wants smaller wins.

3. If (a) Phase 4 brief authoring:
   - Read background_job_infrastructure_decision.md + layered_scrape_
     strategy.md end-to-end first.
   - Author outputs/cursor_brief_phase_4_background_jobs_scrape.md
     (heavy-prescriptive operating doc with sec 0 baseline + sec 1
     why + sec 2 locked + sec 3 boundaries + sec 4 deliverables in
     dispatch order + sec 5 acceptable deviations + sec 6 risk
     register + sec 7 what NOT to do + sec 8 final report format).
     Estimated effort to author: ~half-day primary-side; brief should
     be sufficient to dispatch Phase 4.1 (sub-phase decomposition
     recommended -- 4.1 background-jobs scaffold, 4.2 layered-scrape
     clients, 4.3 OSM + LHC open data, 4.4 close-out -- exact
     decomposition is brief-authoring decision).
   - Then: author Phase 4.1 dispatch prompt at outputs/cursor_
     dispatch_prompt_phase_4_1.md. Chains off e1f2a3b4c5d6.
   - Then: surface the dispatch prompt body for Casey to paste into
     a fresh Cursor chat.

4. If (b) UI rebuild:
   - Ask Casey for status + scope. Where is the rebuild? New design
     system? Component-by-component refresh? Full rewrite? What's
     the target end-state look like?
   - Identify what the next session should produce: design doc?
     component spec? code commit? Decision depends on rebuild scope.
   - Watch for any data-shape regressions during smoke. The post-
     deploy /home render in session-22 showed mixed canonical 12 +
     legacy free-text category labels (Casey attributed to "the UI
     is old…we are changing the ui anyway"); confirm whether that's
     CDN/browser cache or a real rendering gap as part of any UI
     work.

5. If (c) smaller follow-ups:
   - BACKLOG.md unstaged-mod: read the working-tree diff vs origin;
     decide commit-or-revert.
   - Magic-link login smoke: log in with a real email; confirm Resend
     delivers + the magic-link round-trip works. Tests RESEND_API_KEY
     + RESEND_FROM_ADDRESS + AUTH_MAGIC_LINK_BASE_URL.
   - Photo upload smoke: claim a provider (or use an existing one)
     and upload a photo; confirm R2 storage + URL generation works.
     Tests R2_* env vars.
   - AirNow API key registration: 20-min operator task; signup +
     Railway env var drop. Pre-Phase-8.

## Firm ground (carry-over from sessions 15 + 16 + 17 + 18 + 19 + 20 +
## 21 + 22)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint (Rule 3)
- PowerShell single-quote git commit -m '...' when subjects have $,
  sec, ->, parens, or other sigils (gotcha #8). PowerShell 5.1 uses ;
  not && for command chaining (gotcha #13). AVOID embedded double-
  quotes inside -m '...' bodies entirely on PowerShell (gotcha #16
  landed session-20; three-session streak now). Use plain text or
  em-dashes or Unicode curly quotes for emphasis.
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current mergepoint label is a chain-walk diagnostic NOT a
  multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views AND stale working-tree
  files -- use Windows-side Read tool as authoritative for both
  (Rule 7 + gotcha #7 extension from session-22). When bash mount
  git is broken, walk parent links via python3 + zlib.decompress on
  .git/objects/ (gotcha #14). Don't run bash git status/diff/log/
  ls-tree/ANYTHING against the working tree (gotcha #15, four-
  session streak now).
- Don't run git commit --amend while parallel lanes in flight
  (Rule 12).
- Postgres-vs-SQLite portability: sa.true()/sa.false() for booleans;
  sa.func.now() for timestamps; verify raw SQL inside op.execute()
  works on Postgres not just SQLite. For Phase 4 specifically:
  background-jobs use Railway scheduled jobs (Option A from the
  decision memo) which is a Railway runtime concern, not a migration
  portability concern; the layered-scrape clients write to entities
  table via dual-write helpers (Phase 1D code on origin/main).
- Cross-check Cursor's claimed file list against actual git status
  Windows-side before staging (session-20 lesson 3). Cursor sec 11
  prose is sometimes descriptive of existing state, not a change
  Cursor made.
- Sub-agent pre-flight verification catches dispatch-prompt gaps
  before Cursor halts (session-21 lesson 1). Pattern is production-
  ready.
- Confirm via log/repro before locking a diagnosis (session-22
  lesson 1; gotcha #17 companion). Don't infer root cause from
  status code + known state-of-world without reading the actual
  trace.
- Cross-module hook registration belongs in __init__.py, not leaf
  modules (session-22 lesson 2; gotcha #17). Module-top registration
  in a leaf module creates cycles when alternate entry points exist.

## What NOT to do
- Don't redo session-22's work; six-plus commits including production
  deploy verification + cron restore + circular-import fix + 2 docs
  commits + close-out + SHA-patch -- all on origin
- Don't re-pause the parks-rec-scrapes cron unless there's a fresh
  failure surface. Workflow is GREEN as of run #26.
- Don't author Phase 4 brief without first reading background_job_
  infrastructure_decision.md + layered_scrape_strategy.md end-to-end.
  Those memos are the locked design context.
- Don't dispatch Phase 4.1 without an authored brief. Phase 4 is
  larger scope than Phase 3 (10-15 days dispatch estimate) and
  needs a heavy-prescriptive operating doc.
- Don't propose React/SPA migration unless the UI rebuild scope
  already implies it (ask Casey first; default tech stack constraint
  is server-rendered).
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan section 10 or
  Phase 3 SHIPPED + DEPLOYED state.
- Don't dispatch sub-agents while Cursor is mid-flight unless work
  is in a disjoint file domain (context burn for primary).
  Exception: sub-agent pre-flight verification of dispatch prompts
  per session-21 lesson 1 -- those are read-only research and
  always disjoint from Cursor's writes.
- Don't run any bash git operations against the working tree
  (gotcha #15, four-session streak now). Pure object reads via
  python3 + zlib.decompress on .git/objects/... per gotcha #14's
  parent-walk pattern are the ONLY safe bash-side git-adjacent
  operation. Everything else: Read + Grep + Glob.
- Don't include embedded double-quote pairs in -m '...' commit
  bodies on PowerShell (gotcha #16, three-session streak now). Use
  plain text or em-dashes or Unicode curly quotes for emphasis;
  hyphens (-) work fine as emphasis brackets when used in pairs.
- Don't trust the Linux bash mount for working-tree file content
  if you've just edited via the Edit tool (session-22 lesson 5;
  gotcha #7 extension). Use Windows-side Read for verification;
  defer pytest to Windows-side venv if you observe mount lag.

## Begin
1. Boot sequence reads (steps 1-6 above)
2. Baseline check (via Read + Grep + Glob, NOT bash git per gotcha
   #15) + report values to Casey
3. Ask Casey which lane to pursue (a Phase 4 brief authoring / b UI
   rebuild status / c smaller follow-ups / d hold; recommendation
   depends on whether Casey is actively rebuilding UI (b), wants
   forward backend progress (a), or wants smaller wins (c))
4. If (a): read decision memo + scrape strategy end-to-end, then
   author Phase 4 brief, then author Phase 4.1 dispatch prompt,
   then surface dispatch prompt body inline for Casey to paste
   into a fresh Cursor chat
5. If (b): ask Casey for UI rebuild status + scope; identify what
   the next session should produce
6. If (c): pick a follow-up; do it
7. Wait + verify rhythm per session-19 + 20 + 21 + 22 pattern (NO
   bash git; NO embedded double-quotes in -m '...' bodies; cross-
   check Cursor's claimed file list against actual git status
   Windows-side before staging; trust Windows-side Read for working-
   tree file content if Linux mount lag observed)
Don't ask "where do we start" — the boot sequence is the source of
truth.
```
