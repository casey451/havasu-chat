You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-20) shipped Phase 3.1 of
the master build plan to origin via a single Cursor dispatch on the
pre-positioned + SHA-patched prompt at outputs/cursor_dispatch_prompt_
phase_3_1.md. State is durable on origin/main HEAD = <TBD-session-20-
close-out-SHA>. Six commits this session.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-12_session20.md — closes out session-20.
   Captures the 6-commit narrative (1 gotcha #16 docs + 1 Phase 3.2
   district UX operator-reality-check docs + 1 Phase 3.1 substantive
   ship + 1 chore for the session-19 dispatch-prompt patches + 1
   Phase 3.1 docs close-out + this close-out), Phase 3.1 SHIPPED
   summary (commit chain 3bf9f66 -> 540efbd -> 7925a14 -> 38abbcb ->
   81a83a1; pytest delta 1664 -> 1681 +17; alembic head
   f9e8d7c6b5a4 -> d0e1f2a3b4c5), queued Phase 3.2 dispatch authoring
   work, accepted pragmatic deviations (most notable: seasonal_hours
   JSON column + Phase 1A extension table coexist via brief sec 9
   intentional-column path, brief sec 4.1 explicit-HALT bypassed
   then operator-confirmed during commit), six new lessons (gotcha
   #16 landed durably; operator reality-check feedback loop matters;
   Cursor sec 11 prose may be descriptive not change-revealing;
   dispatch prompt SHA-patch pattern continues durable; primary-side
   parallel-work cadence during Cursor in-flight time scales; gotcha
   #15 discipline held throughout).
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at <TBD-session-20-close-out> with full Phase 1
   + Phase 2 + Phase 3.1 chain through alembic head d0e1f2a3b4c5;
   production still at 5132162 with alembic head b2c3d4e5f6a7 (1A + 1B
   live; 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 + 3.1
   queued for next deploy at operator cadence — five migrations
   apply). "Recently shipped" section 1 has the full session-20
   narrative.
3. docs/maintainability/master_build_plan.md section 4 Phase 3 (now
   has "Shipped (incremental)" sub-section with the Phase 3.1 ship
   line) and the rest of Phase 3 description outlines the next
   dispatchable sub-phase (3.2 — category taxonomy rewrite + audited
   backfill + district seed + Phase 3 close-out).
4. outputs/cursor_brief_phase_3_v11_schema_pass.md sections 5 + 7 +
   10 + 11 — the heavy-prescriptive operating doc covering Phase 3.2.
   Section 5 has the Phase 3.2 deliverable list; section 7 captures
   the 5 Bucket C operator decisions now LOCKED at recommendation
   (session-20 -- beauty_personal_care NULL/V1.5 defer; tourism NULL
   queue; barbershop fixture NULL; K-12/charter schools classes-
   sports-recreation; bowling/arcades/mini golf classes-sports-
   recreation) PLUS the session-20 operator reality check on district
   paragraph UX direction (OPEN with three candidate paths); section
   10 is risk register; section 11 is don't-do.
5. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (16 gotchas as
   of session-20; gotcha #16 -- embedded double-quotes inside -m
   bodies on PowerShell -- landed this session at 3bf9f66).
6. outputs/chatgpt_response_district_paragraphs_v1.md — Phase 3 V1
   district paragraphs draft. **Now flagged as illustrative not
   canonical** at the top per session-20 operator reality check.
   Do NOT polish the 5 placeholders + 5 verify items until the
   Phase 3.2 district UX direction resolves (the polish-the-
   paragraphs version of this work has been superseded by a
   strategic-direction question).

## New lessons from session-20 worth folding into Phase 3.2 brief
1. **Gotcha #16 (embedded double-quotes in -m bodies on PowerShell)
   landed durably.** Future commit recipes use plain text or
   em-dashes for emphasis; never embedded double-quote pairs in
   -m '...' bodies. Session-20's gotcha #16 docs commit used its own
   medicine and parsed clean; same for all 5 other session-20 commits.
2. **Operator reality-check feedback loop matters.** Casey surfaced
   the Havasu-too-small-for-10-districts reality check mid-session-20
   on Cursor 3.1. The strategic-direction reframe (from "polish 5
   paragraph placeholders" to "decide if 10-district paragraph plan
   is the right primitive") matters more than the polish task. Bake
   "ask the operator what's actually true about their geography/
   users" into early-phase brief authoring, especially when the brief
   was authored from research not local knowledge.
3. **Cursor sec 11 prose may be descriptive not change-revealing.**
   Cursor's sec 13 sec 11 mentioned alembic/env.py modification but
   the sec 4 file list only showed app/db/models.py modified. git
   status Windows-side was the truth (env.py NOT modified; sec 11
   described existing state). Rule from session-20 forward: always
   cross-check Cursor's claimed file list against actual git status
   Windows-side before staging; never trust sec 11 prose alone to
   determine commit scope.
4. **Dispatch prompt SHA-patch pattern continues durable.** Session-19
   patched 2B.1 + 2B.3 dispatch prompts in-place; session-19 close-
   out missed them; session-20's chore commit at 38abbcb mirrored
   the c9ab794 pattern to preserve as durable historical state.
   Future agents: when a dispatch prompt gets SHA-patched in-place
   pre-paste, land it as a chore commit at session close-out -- don't
   let patched prompts sit in working tree across session boundaries.
5. **Primary-side parallel-work cadence during Cursor in-flight time
   scales.** Session-20 walked 5 Bucket C decisions + surfaced the
   district UX reality check + authored gotcha #16 docs + queued
   the dispatch-prompt chore all during Cursor 3.1's ~hour of in-
   flight time. AskUserQuestion calls with recommendations attached
   were efficient for the 5 decision-locks. Pattern is production-
   ready for any session where Cursor has substantial in-flight time.
6. **Gotcha #15 discipline held throughout (continuation).** Zero
   bash git operations against the working tree across the entire
   session; HEAD verification via Read on .git/refs/heads/main,
   recent commits via STATE.md cross-reference, alembic head via
   Glob on alembic/versions/, file-presence via Glob/Grep. Session-
   19's rule extension (no read-only git ls-tree either) held.

## Your first actions, in order
1. Run baseline: read top of .git/refs/heads/main via Read tool
   (top should be <TBD-session-20-close-out> — this close-out commit),
   cross-check docs/STATE.md Recent commits block for the 81a83a1 ->
   38abbcb -> 7925a14 -> 540efbd -> 3bf9f66 -> 26e6eb4 chain, confirm
   alembic head d0e1f2a3b4c5 via Glob on alembic/versions/. Run
   python -m pytest -q --collect-only | tail -3 if Windows-side venv
   is available (should show 1681 + 1 skipped). Report values to
   Casey. DO NOT use bash git ... per gotcha #15.
2. Ask Casey which lane to pursue: (a) Phase 3.2 dispatch prompt
   authoring (requires resolving district UX direction first; chains
   off d0e1f2a3b4c5; embeds 5 locked Bucket C decisions); (b) Phase
   1C+1D+2A+2B+3.1 production deploy to Railway (5 migrations apply
   on first push including 2B.2 first-ever Postgres FTS DDL; non-
   trivial smoke); (c) Hold. Recommend (a) -- Phase 3.2 is the next
   dispatchable lane and the dispatch prompt is the gating artifact.
3. If (a) Phase 3.2 dispatch prompt authoring:
   - First: walk Casey through the district UX direction resolution
     (3 candidate paths in brief sec 7: pare to 2-3 real districts +
     default, defer paragraphs to V1.5, re-think to streets/landmarks).
     This is a 5-10 min operator decision.
   - Then: author the Phase 3.2 dispatch prompt at outputs/cursor_
     dispatch_prompt_phase_3_2.md. Chains off d0e1f2a3b4c5. Embeds:
     (i) 5 Bucket C decision-locks (all at recommendation per session-
     20); (ii) operator-decided district UX direction; (iii) brief
     sec 5 + sec 11 scope discipline; (iv) Postgres portability rules;
     (v) HALT at brief sec 3 boundary (Phase 3 close-out is part of
     3.2).
   - Then: surface the dispatch prompt body for Casey to paste into
     a fresh Cursor chat. ~3-4 day Cursor walltime estimate.
4. If (b) production deploy: walk Casey through the 5-migration
   sequence (f8e9d0c1b2a3 -> 92ce4899dc08 -> c8d9e0f1a2b3 ->
   f9e8d7c6b5a4 -> d0e1f2a3b4c5); confirm R2 env vars live in Railway
   (locked session-19); confirm Resend env vars (locked session-17);
   verify Railway has pg_trgm available; outline smoke-check checklist
   (EXPLAIN on Tier 2 query for GIN usage, downgrade-1/upgrade-head
   cycle on staging Postgres for 2B.2 FTS + 2B.1 photos + 3.1 schema
   additions, /home anonymous chat shape regression, /api/search
   returns results, photo upload route auth flow, magic-link login).
5. When Cursor 3.2 ships its section 13 report (if (a)): run the
   verify-commit-push rhythm (session-19 + 20 pattern: spot-check
   files via Read + Grep ONLY, NOT bash git; cross-check Cursor's
   claimed file list against actual git status Windows-side per
   session-20 lesson 3; propose commit recipe with PowerShell-safe
   single-quoted -m bodies; NO embedded double-quotes per gotcha #16;
   Casey commits + pushes; then Phase 3.2 docs close-out commit;
   then Phase 3 SHIPPED master plan header; then session-21 close-out).

## Firm ground (carry-over from sessions 15 + 16 + 17 + 18 + 19 + 20)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint (Rule 3)
  -- Phase 3.2 is single-lane (no parallel sub-phase since 3.2 closes
  out Phase 3)
- PowerShell single-quote git commit -m '...' when subjects have $,
  sec, ->, parens, or other sigils (gotcha #8). PowerShell 5.1 uses ;
  not && for command chaining (gotcha #13). NEW: avoid embedded
  double-quotes inside -m '...' bodies entirely on PowerShell (gotcha
  #16 landed at 3bf9f66 this session). Use plain text or em-dashes
  or Unicode curly quotes for emphasis.
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current mergepoint label is a chain-walk diagnostic NOT a
  multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views -- use Windows-side Read
  tool as authoritative (Rule 7). When bash mount git is broken,
  walk parent links via python3 + zlib.decompress on .git/objects
  (gotcha #14). Don't run bash git status/diff/log/ls-tree/ANYTHING
  against the working tree (gotcha #15, extended session-19 + 20).
- Don't run git commit --amend while parallel lanes in flight
  (Rule 12). Session-20 close-out commits also avoided amends.
- Postgres-vs-SQLite portability: sa.true()/sa.false() for booleans;
  sa.func.now() for timestamps; verify raw SQL inside op.execute()
  works on Postgres not just SQLite. For Phase 3.2 specifically: the
  migration is a data-only migration (no schema changes) -- backfills
  use op.execute() with portable SQL, mirroring Phase 1B's pattern.
  Most of 3.2 is INSERT INTO + UPDATE statements driven by the
  audited mapping in docs/maintainability/category_backfill_mapping_
  audit_2026-05-14.md sec 2.
- Cross-check Cursor's claimed file list against actual git status
  Windows-side before staging (session-20 lesson 3). Cursor sec 11
  prose is sometimes descriptive of existing state, not a change
  Cursor made.

## What NOT to do
- Don't redo session-20's work; 6 commits including Phase 3.1
  substantive ship + 5 Bucket C decision locks + district UX
  reality check captured + gotcha #16 landed + session-19 dispatch
  prompt patches preserved as chore -- all on origin
- Don't author Phase 3.2 dispatch prompt without first resolving the
  district paragraph UX direction (3 candidate paths in brief sec 7).
  This is the gating operator decision before dispatch prompt
  authoring can complete.
- Don't polish the 5 [CASEY: ...] placeholders in the district
  paragraphs draft. The strategic question (is the 10-district
  paragraph plan even the right primitive?) supersedes the polish
  task. Resolve the UX direction first; the paragraph polish work
  may be entirely superseded.
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan section 10 or
  brief sections 2 + 6 -- including the 12-slug new-taxonomy lock
  + the 5 professional-services strings V1.5 deferral + the
  entities.district_id FK targeting districts.id. The 5 Bucket C
  decisions are LOCKED as of session-20; embed them into the 3.2
  dispatch prompt at authoring time, don't re-walk.
- Don't dispatch Phase 3.2 with the 10-district paragraph plan
  unless the operator explicitly re-confirms after the reality check.
- Don't dispatch sub-agents while Cursor is mid-flight unless work
  is in a disjoint file domain (context burn for primary)
- Don't run any bash git operations against the working tree
  (gotcha #15, extended session-19 + 20). Pure object reads via
  python3 + zlib.decompress on .git/objects/... per gotcha #14's
  parent-walk pattern are the ONLY safe bash-side git-adjacent
  operation. Everything else: Read + Grep + Glob.
- Don't include embedded double-quote pairs in -m '...' commit
  bodies on PowerShell (gotcha #16, landed session-20). Use plain
  text or em-dashes or Unicode curly quotes for emphasis. Session-
  20 wrote 5 substantive commits with this rule and all landed
  clean; pattern is durable.
- Don't trust Cursor sec 13 sec 11 prose alone to determine commit
  scope. Cross-check claimed file list against actual git status
  Windows-side before staging (session-20 lesson 3).

## Begin
1. Boot sequence reads (steps 1-6 above)
2. Baseline check (via Read + Grep + Glob, NOT bash git per gotcha
   #15) + report values to Casey
3. Ask Casey which lane to pursue (a Phase 3.2 dispatch prompt
   authoring / b production deploy / c hold; recommend (a))
4. If (a): walk district UX direction resolution first, then author
   Phase 3.2 dispatch prompt embedding 5 Bucket C locks + UX
   direction + Postgres portability rules + HALT at brief sec 3
   boundary
5. Surface the dispatch prompt body inline for Casey to paste into a
   fresh Cursor chat (session-19 lesson 6: SHA-patch-and-inline-
   present rhythm)
6. Wait + verify rhythm per session-19 + 20 pattern (NO bash git;
   NO embedded double-quotes in -m '...' bodies; cross-check Cursor's
   claimed file list against actual git status Windows-side before
   staging)
Don't ask "where do we start" — the boot sequence is the source of
truth.
