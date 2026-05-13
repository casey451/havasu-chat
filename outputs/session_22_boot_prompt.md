# Session-22 Boot Prompt

> Paste this into the next Cowork session to boot the primary on havasu-chat. Origin/main HEAD will be `43b5f8f` (session-21 close-out commit, to be SHA-patched here pre-paste mirroring `c4fdc69` precedent). Six commits this session-21: `5dbde39` (Phase 3.2 substantive) → `bd9b00f` (chore: Phase 3.2 dispatch prompt artifact) → `294567b` (Phase 3 SHIPPED on master plan + STATE.md session-21 refresh + district draft top-matter) → `43b5f8f` (this session-21 close-out: handoff + boot prompt + STATE.md Recent commits final prepend) → `59521dd` (chore: pause parks-rec-scrapes cron until production deploy lands). SHA-patch chore landed at session-21 close (NOT session-22 boot as in earlier sessions — explicit choice to close out session-21 with zero pending placeholders); mirrors `c4fdc69` SHA-patch pattern but with both SHAs (close-out + cron-pause) known at patch time.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-21) shipped Phase 3.2 of
the master build plan to origin via a single Cursor dispatch on the
pre-positioned + locked prompt at outputs/cursor_dispatch_prompt_
phase_3_2.md. **Phase 3 of the master build plan is COMPLETE on
origin (3.1 + 3.2).** State is durable on origin/main HEAD = 43b5f8f.
Five-plus commits this session-21.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-12_session21.md — closes out session-21.
   Captures the 5-plus-commit narrative (1 Phase 3.2 substantive ship +
   1 dispatch-prompt chore + 1 docs close-out with Phase 3 SHIPPED
   master plan header + this close-out + 1 cron-pause chore for parks-
   rec-scrapes pending production deploy), Phase 3.2 SHIPPED summary
   (commit chain 5dbde39 -> bd9b00f -> 294567b -> 43b5f8f; pytest delta
   1681 -> 1702 +21; alembic head d0e1f2a3b4c5 -> e1f2a3b4c5d6;
   Phase 3 COMPLETE), queued Phase 4 brief-authoring + production
   deploy work, accepted pragmatic deviations (most notable:
   entities.district String column never existed -- Phase 1A unified
   into locations extension table; brief sec 5.4 drop-column moot;
   Bucket C A.4 + A.5 documented-only locks per mid-session
   clarification; NEW LEGACY_PROVIDER_CATEGORY_LABELS for legacy
   free-text display until Phase 13), six new lessons (sub-agent
   pre-flight verification catches dispatch-prompt gaps; mid-session
   clarification messages work when small + targeted; dispatch prompt
   as-shipped historical artifact is the right framing; Phase 1A
   semantics still surfacing in Phase 3; gotcha #15 + #16 discipline
   held -- three + two session streaks respectively).
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at HEAD 43b5f8f with full Phase 1
   + Phase 2 + Phase 3 chain through alembic head e1f2a3b4c5d6;
   production still at 5132162 with alembic head b2c3d4e5f6a7 (1A + 1B
   live; 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 + 3.1 + 3.2
   queued for next deploy at operator cadence -- **six migrations**
   apply: f8e9d0c1b2a3 -> 92ce4899dc08 -> c8d9e0f1a2b3 -> f9e8d7c6b5a4
   -> d0e1f2a3b4c5 -> e1f2a3b4c5d6). "Recently shipped" section 1 has
   the full session-21 narrative.
3. docs/maintainability/master_build_plan.md section 4 Phase 3
   (SHIPPED 2026-05-12 header + Status line; "Shipped (incremental)"
   subsection has both 3.1 + 3.2 ship-lines) + section 4 Phase 4
   description outlines the next dispatchable major phase
   (background-jobs + layered scrape infrastructure; L estimate
   10-15 days dispatch; parallel-eligible sub-lanes).
4. docs/maintainability/background_job_infrastructure_decision.md +
   docs/maintainability/layered_scrape_strategy.md -- Phase 4 design
   context. If choosing Phase 4 brief-authoring lane, read end-to-end
   before authoring.
5. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (16 gotchas as
   of session-20; gotcha #16 landed session-20 -- embedded double-
   quotes inside -m '...' bodies on PowerShell; carries forward).
6. .github/workflows/parks-rec-scrapes.yml -- cron is paused per
   session-21 chore commit; failures every 6h since session-20 Phase
   3.1 ship caused by ORM-vs-prod-DB schema mismatch (origin includes
   Phase 3.1's 7 new entity columns + 5 new tables + users.preferred_
   mode; production missing these). Re-enable cron AFTER production
   deploy lands. See session-21 handoff sec 2 for full diagnosis.

## New lessons from session-21 worth folding into Phase 4 brief
1. **Sub-agent pre-flight verification catches dispatch-prompt gaps
   before Cursor halts.** Use Explore sub-agent for pre-flight
   dispatch-prompt verification during long Cursor sessions when
   there's audit/memo cross-referencing to do. The cost is one
   sub-agent context burn (~350 words report); the savings is one
   or more Cursor round-trips. Pattern is production-ready.
2. **Mid-session clarification messages work** when the message is
   small + targeted (one section of the prompt). Don't always wait
   for sec 13 HALT and re-dispatch -- a focused mid-flight
   clarification can save a Cursor round-trip.
3. **Dispatch prompt as-shipped historical artifact is the right
   framing.** Preserves pre-clarification context as a record;
   post-clarification reframe lives in commit message + STATE.md
   narrative + tests. Mirrors session-20 brief sec 4.1 narration
   precedent (didn't patch the brief; narrated in commit).
4. **Phase 1A semantics still surfacing in Phase 3.** Cursor caught
   that entities.district String column never existed (Phase 1A
   unified district into locations extension); brief sec 5.4's drop-
   column instruction was authored assuming entities.district
   existed. Future Cursor inheritance: when a brief instruction
   touches a column, always verify the column exists in models.py
   before authoring SQL.
5. **Gotcha #15 discipline held throughout (three-session streak).**
   Zero bash git operations against working tree all session;
   HEAD verification via Read on .git/refs/heads/main + parent-walk
   decompression via python3+zlib on .git/objects/ per gotcha #14
   cure pattern; alembic head via Glob on alembic/versions/; file-
   presence via Glob/Grep.
6. **Gotcha #16 discipline held throughout (two-session streak).**
   All session-21 commit recipes used PowerShell-safe single-quoted
   -m bodies with em-dashes / -> / plain text for emphasis; no
   embedded double-quote pairs; all commits landed clean. Hyphens
   (-) work fine as emphasis brackets when used in pairs as a
   quote-like-affordance.

## Your first actions, in order
1. Run baseline: read top of .git/refs/heads/main via Read tool
   (top should be 43b5f8f + the cron-pause chore commit if it landed
   per session-21 close-out followups, else 43b5f8f directly),
   cross-check docs/STATE.md Recent commits block for the
   43b5f8f -> 294567b -> bd9b00f -> 5dbde39 -> c4fdc69 chain,
   confirm alembic head e1f2a3b4c5d6 via Glob on alembic/versions/.
   Run python -m pytest -q --collect-only | tail -3 if Windows-side
   venv is available (should show 1702 + 1 skipped). Report values
   to Casey. DO NOT use bash git ... per gotcha #15.
2. Ask Casey which lane to pursue: (a) Phase 4 brief authoring
   (background-jobs + layered scrape infrastructure; L 10-15 days
   dispatch estimate; parallel-eligible sub-lanes); (b) Production
   deploy of Phase 1C+1D+2A+2B+3 (six migrations apply on first push
   including 2B.2 first-ever Postgres FTS DDL + 2B.1 photos + 3.1
   schema + 3.2 data pass; non-trivial smoke; unblocks parks-rec-
   scrapes); (c) Hold. Recommend (b) if Casey wants to unblock the
   parks-rec-scrapes cron; recommend (a) if Casey wants forward
   progress on master plan.
3. If (a) Phase 4 brief authoring:
   - Read background_job_infrastructure_decision.md + layered_scrape_
     strategy.md end-to-end first.
   - Author outputs/cursor_brief_phase_4_background_jobs_scrape.md
     (heavy-prescriptive operating doc with sec 0 baseline + sec 1
     why + sec 2 locked + sec 3 boundaries + sec 4 deliverables in
     dispatch order + sec 5 acceptable deviations + sec 6 risk
     register + sec 7 what NOT to do + sec 8 final report format).
     Estimated effort to author: ~half-day primary-side; brief
     should be sufficient to dispatch Phase 4.1 (sub-phase
     decomposition recommended -- 4.1 background-jobs scaffold,
     4.2 layered-scrape clients, 4.3 OSM + LHC open data, 4.4
     close-out -- exact decomposition is brief-authoring decision).
   - Then: author Phase 4.1 dispatch prompt at outputs/cursor_
     dispatch_prompt_phase_4_1.md. Chains off whatever the latest
     deployed-or-pending alembic head is.
   - Then: surface the dispatch prompt body for Casey to paste
     into a fresh Cursor chat.
4. If (b) production deploy:
   - Walk Casey through the 6-migration sequence (f8e9d0c1b2a3 ->
     92ce4899dc08 -> c8d9e0f1a2b3 -> f9e8d7c6b5a4 -> d0e1f2a3b4c5 ->
     e1f2a3b4c5d6).
   - Confirm R2 env vars live in Railway (locked session-19); confirm
     Resend env vars (locked session-17); verify Railway has pg_trgm
     available pre-push (highest-risk first-deploy DDL).
   - Outline smoke-check checklist: EXPLAIN on Tier 2 query for GIN
     usage; downgrade-1/upgrade-head cycle on staging Postgres for
     2B.2 FTS + 2B.1 photos + 3.1 schema + 3.2 data pass; /home
     anonymous chat shape regression; /api/search returns results;
     photo upload route auth flow; magic-link login.
   - Post-deploy: re-enable parks-rec-scrapes cron (revert the
     cron-pause chore via a new chore commit) + manually trigger
     the workflow once to confirm scraper recovers.

## Firm ground (carry-over from sessions 15 + 16 + 17 + 18 + 19 + 20 + 21)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint (Rule 3)
- PowerShell single-quote git commit -m '...' when subjects have $,
  sec, ->, parens, or other sigils (gotcha #8). PowerShell 5.1 uses ;
  not && for command chaining (gotcha #13). NEW: avoid embedded
  double-quotes inside -m '...' bodies entirely on PowerShell (gotcha
  #16 landed session-20). Use plain text or em-dashes or Unicode
  curly quotes for emphasis.
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current mergepoint label is a chain-walk diagnostic NOT a
  multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views -- use Windows-side Read
  tool as authoritative (Rule 7). When bash mount git is broken,
  walk parent links via python3 + zlib.decompress on .git/objects
  (gotcha #14). Don't run bash git status/diff/log/ls-tree/ANYTHING
  against the working tree (gotcha #15, three-session streak now).
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

## What NOT to do
- Don't redo session-21's work; 5+ commits including Phase 3.2
  substantive ship + dispatch prompt artifact chore + Phase 3
  SHIPPED docs close-out + session-21 close-out + cron-pause chore
  -- all on origin
- Don't author Phase 4 brief without first reading background_job_
  infrastructure_decision.md + layered_scrape_strategy.md end-to-end.
  Those memos are the locked design context.
- Don't dispatch Phase 4.1 without an authored brief. Phase 4 is
  larger scope than Phase 3 (10-15 days dispatch estimate) and
  needs a heavy-prescriptive operating doc.
- Don't re-enable the parks-rec-scrapes cron until production
  deploy lands. The cron is currently paused (workflow_dispatch
  still available) per session-21 chore commit. Re-enable via
  reverting that chore after deploy lands.
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan section 10 or
  Phase 3 brief sections 2 + 6.
- Don't dispatch sub-agents while Cursor is mid-flight unless work
  is in a disjoint file domain (context burn for primary).
  Exception: sub-agent pre-flight verification of dispatch prompts
  per session-21 lesson 1 -- those are read-only research and
  always disjoint from Cursor's writes.
- Don't run any bash git operations against the working tree
  (gotcha #15, three-session streak now). Pure object reads via
  python3 + zlib.decompress on .git/objects/... per gotcha #14's
  parent-walk pattern are the ONLY safe bash-side git-adjacent
  operation. Everything else: Read + Grep + Glob.
- Don't include embedded double-quote pairs in -m '...' commit
  bodies on PowerShell (gotcha #16, two-session streak now). Use
  plain text or em-dashes or Unicode curly quotes for emphasis;
  hyphens (-) work fine as emphasis brackets when used in pairs.

## Begin
1. Boot sequence reads (steps 1-6 above)
2. Baseline check (via Read + Grep + Glob, NOT bash git per gotcha
   #15) + report values to Casey
3. Ask Casey which lane to pursue (a Phase 4 brief authoring / b
   production deploy / c hold; recommendation depends on whether
   Casey wants to unblock parks-rec-scrapes (b) or progress master
   plan (a))
4. If (a): read decision memo + scrape strategy end-to-end, then
   author Phase 4 brief, then author Phase 4.1 dispatch prompt,
   then surface dispatch prompt body inline for Casey to paste
   into a fresh Cursor chat
5. If (b): walk 6-migration sequence + env-var + pg_trgm check +
   smoke checklist + post-deploy re-enable parks-rec-scrapes cron
6. Wait + verify rhythm per session-19 + 20 + 21 pattern (NO bash
   git; NO embedded double-quotes in -m '...' bodies; cross-check
   Cursor's claimed file list against actual git status Windows-
   side before staging)
Don't ask "where do we start" — the boot sequence is the source of
truth.
```
