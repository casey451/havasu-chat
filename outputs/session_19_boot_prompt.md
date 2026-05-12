# Session-19 Boot Prompt

> Paste this into a fresh Cowork primary chat to boot session-19 on havasu-chat.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-18) shipped Phase 2A.3
(closing out Lane 2A) and Phase 2B.2 (Postgres FTS infrastructure) via
PARALLEL dispatch of two Cursor lanes per dispatch_protocol Rule 3.
State is durable on origin/main HEAD = <TBD-session-18-close-out-SHA>.
Seven commits this session.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-12_session18.md — closes session-18.
   Captures the 7-commit narrative (2 substantive Cursor lanes shipped
   in parallel + 2 docs ship-line commits + 1 dispatch artifact commit
   + 1 gotcha-absorption commit + this close-out), Phase 2 Lane 2A
   COMPLETE summary, Lane 2B 1-of-3 shipped, queued Phase 2B.1 + 2B.3
   work, accepted pragmatic deviations across both lanes, five new
   lessons (gotcha #15 bash mount index.lock + parallel-dispatch
   validation + sub-agents-for-docs + both-lanes-in-one-tree-is-fine
   + pre-author-while-Cursor-works continued).
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at <TBD-session-18-close-out-SHA> with full
   Phase 1 + Phase 2 Lane 2A chain + Phase 2B.2 through alembic head
   c8d9e0f1a2b3; production still at 5132162 with alembic head
   b2c3d4e5f6a7 (1A + 1B live; 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2
   queued for next deploy at operator cadence — three migrations
   apply). "Recently shipped" §1 has the full session-18 narrative.
3. docs/maintainability/master_build_plan.md §4 Phase 2 ("Shipped
   (incremental)" list now has full Lane 2A SHIPPED + 2B.2 ship-line +
   2B.1 / 2B.3 pending stubs) and §4 Phase 3 (next major phase after
   Phase 2 closes — v1.1 schema pass + districts + categories + alerts).
4. outputs/cursor_dispatch_prompt_phase_2b_1.md AND/OR
   outputs/cursor_dispatch_prompt_phase_2b_3.md — both pre-positioned
   in session-18, ready to paste. 2B.1 ships photos + R2 + Pillow
   pipeline + upload route (gated on Cloudflare R2 operator prereq).
   2B.3 ships search bar UI + GET /api/search + Lane 2B close-out
   (gated on 2B.2 which is done; no operator prereq). Per
   dispatch_protocol Rule 3, both can dispatch in PARALLEL Cursor
   chats — they touch file-disjoint domains.
5. outputs/cursor_brief_phase_2b_image_storage_search.md §5 (for
   2B.1 reference; what Cursor will execute) AND/OR §7 (for 2B.3
   reference) — the heavy-prescriptive operating doc.
6. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (15 gotchas as
   of session-18 — new gotcha #15 covers bash mount index.lock
   corruption in mixed-OS sessions, captured in commit 4cb329d).
7. outputs/chatgpt_response_district_paragraphs_v1.md — Phase 3 V1
   deliverable drafted by ChatGPT in session-17. 5 [CASEY: ...]
   placeholders + 5 "Casey to verify" items pending operator polish.
   Not blocking; Phase 3 isn't dispatching until Phase 2 closes out.

## New lessons from session-18 worth folding into Phase 2B.1 + 2B.3 briefs
1. **Gotcha #15 (bash mount index.lock corruption in mixed-OS sessions)
   is now absorbed in dispatch_channels.md.** From session-19 forward,
   DO NOT run any `git ...` from the bash sandbox against the working
   tree — even read-only operations like `git status -s` or
   `git diff --stat HEAD` create a `.git/index.lock` that Linux can't
   unlink and Windows git then refuses to step on. Use Read + Grep +
   Glob tools (Windows-authoritative) for all working-tree inspection.
   Pure object reads via python3 + zlib.decompress on .git/objects/...
   per gotcha #14 parent-walk pattern are the only safe bash-side
   git-adjacent operations. Fix when it happens anyway:
   `Remove-Item .git\index.lock` from PowerShell.
2. **Parallel-dispatch validated at production scale.** Rule 3
   file-disjoint pattern worked: two Cursor chats ran 2A.3 + 2B.2
   simultaneously, returned coordinated §13 reports, combined working
   tree passed 1607 (= 1563 baseline + 23 (2A.3) + 21 (2B.2)). Casey
   committed each lane as a separate substantive commit per Rule 8 —
   `git add` per-file-list kept the commits clean. Pattern is
   production-ready; use it for 2B.1 + 2B.3 if you dispatch both.
3. **Sub-agents are great for docs-only dispatch-prompt authoring
   during Cursor in-flight time.** Two general-purpose sub-agents in
   parallel pre-positioned 2B.1 + 2B.3 prompts to disjoint outputs/
   paths while the Cursor lanes were still running. Each sub-agent
   read the brief + closest template prompt + wrote one new file.
   Worth the ~10-17 tool calls per sub-agent for next-dispatch
   latency drop from ~30 min to ~0 min.
4. **Both parallel lanes' code in one working tree at commit time is
   fine.** When two Cursor lanes operate on the same on-disk repo,
   both see each other's uncommitted changes during their work +
   final pytest. Final pytest count converges to total of both
   deltas. Commits stay file-disjoint per Rule 8 — stage per-file-list,
   not `git add .`, to split lanes into separate substantive commits.
5. **Pre-author-while-Cursor-works pattern is durable.** Bake into
   primary's working rhythm: whenever scope for the next-after-current
   sub-phase is locked, author the next dispatch prompt during current
   Cursor in-flight time. Sub-agents work if the next prompt is
   docs-only + file-disjoint from the in-flight work; primary-authored
   if you have spare cycles + the prompt is more complex than a
   sub-agent would handle cleanly.

## Your first actions, in order
1. Run baseline: git log --oneline -5 (top should be
   <TBD-session-18-close-out-SHA> → 4cb329d → 740223a → bc9cebc →
   d631c77 — the five most recent session-18 commits), pytest
   --collect-only | tail -3 (should show 1607 + 1 skipped = 1608
   total), python -m alembic heads (should show c8d9e0f1a2b3). Report
   values to Casey. **DO NOT** use bash `git status` or `git diff`
   per gotcha #15; use Read + Grep + Glob for any working-tree
   inspection.
2. Ask Casey which lane(s) to dispatch: 2B.1 alone (photos; gated on
   R2 operator prereq — if R2 isn't locked, this dispatches once R2
   is locked), 2B.3 alone (the search bar UI lane, dependency-free),
   BOTH IN PARALLEL (max throughput; two Cursor chats; file-disjoint
   per Rule 3), or hold. Recommend BOTH if R2 is locked AND Casey has
   bandwidth — file-disjoint so cognitive load is the only
   constraint. If R2 isn't locked yet, recommend 2B.3 ALONE (the
   independent lane) and offer to walk Casey through R2 setup in
   parallel (~30-45 min, outputs/operator_prereqs_phase_2.md §2) so
   2B.1 can dispatch in the same session.
3. If 2B.1 dispatches: paste outputs/cursor_dispatch_prompt_phase_2b_1.md
   contents to a fresh Cursor chat. Patch any <TBD-FILL-AFTER-2A.3-LANDS>
   placeholders to 5fea2ce (the 2A.3 ship SHA) and pytest count to
   1607 before paste, per the session-18 prompt-patch pattern.
4. If 2B.3 dispatches in parallel: paste outputs/cursor_dispatch_prompt_phase_2b_3.md
   contents to a SECOND fresh Cursor chat. Patch placeholders for
   2A.3 ship SHA (5fea2ce), 2B.2 ship SHA (d631c77), FTS migration rev
   (c8d9e0f1a2b3), and pytest count (1607).
5. While Cursor lanes work, consider parallel work:
   - Author Phase 3 dispatch prompt (only if Phase 2 is closing out
     this session — both 2B.1 AND 2B.3 expected to ship; otherwise
     premature)
   - Audit any docs that may show wear (master plan section 4 Phase
     3 should be refreshed if Phase 3 dispatches next session)
   - Help Casey polish the district paragraph [CASEY: ...]
     placeholders in outputs/chatgpt_response_district_paragraphs_v1.md
     (~15-20 min)
   - Help Casey with R2 setup walkthrough if not already locked
     (~30-45 min, outputs/operator_prereqs_phase_2.md §2) if he wants
     to unblock 2B.1 dispatch concurrently
6. When Cursor returns §13 reports, run the verify-commit-push rhythm
   (session-18 pattern: spot-check files via Read + Grep ONLY, NOT
   bash git; propose commit recipe with PowerShell-safe single-quoted
   -m bodies; Casey commits + pushes; then docs commit + dispatch
   artifact commit if next sub-phase scope is locked).

## Firm ground (carry-over from sessions 15 + 16 + 17 + 18)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint
  (Rule 3) — 2B.1 + 2B.3 are file-disjoint so parallelizable
- PowerShell single-quote git commit -m '...' when subjects have $, §,
  →, parens, or other sigils (gotcha #8). PowerShell 5.1 uses ; not
  && for command chaining (gotcha #13).
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current "(mergepoint)" label is a chain-walk diagnostic NOT
  a multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views — use Windows-side Read
  tool as authoritative (Rule 7). When bash mount git is broken, walk
  parent links via python3 + zlib.decompress on .git/objects
  (gotcha #14). **DO NOT run bash git status/diff/log/anything against
  the working tree — even read-only ops leave a stuck .git/index.lock
  that Windows git refuses to step on (gotcha #15, NEW this session).
  Use Read + Grep + Glob (Windows-authoritative) for everything.**
- Don't run git commit --amend while parallel lanes in flight (Rule 12)
- Postgres-vs-SQLite portability: sa.true()/sa.false() for booleans;
  sa.func.now() for timestamps; verify raw SQL inside op.execute()
  works on Postgres not just SQLite. For Phase 2B.1 specifically:
  Photo migration adds FK to entities.id with ondelete CASCADE,
  CHECK constraints on variant_set, UniqueConstraint on
  (entity_id, sha256) — Postgres-portable shapes only.

## What NOT to do
- Don't redo session-18's work; 7 commits including Phase 2A.3 + 2B.2
  ship, Lane 2A SHIPPED header on master plan, 2B.1 + 2B.3 dispatch
  prompts pre-positioned, gotcha #15 absorbed in dispatch_channels.md
  are all on origin
- Don't author Phase 2B.1 / 2B.3 briefs from scratch — both are
  pre-positioned + ready to paste; just patch the TBD-... placeholders
  to known SHAs before pasting
- Don't dispatch Phase 2B.1 without R2 prereq locked (Cloudflare R2
  bucket + API token + Railway env vars per
  outputs/operator_prereqs_phase_2.md §2)
- Don't dispatch Phase 2B.3 without verifying 2B.2 is on origin (it
  is, as of session-18 close)
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan §10
- Don't dispatch sub-agents while Cursor is mid-flight unless work is
  in a disjoint file domain (context burn for primary)
- **Don't run any bash git operations against the working tree
  (gotcha #15).** Pure object reads via python3 + zlib.decompress on
  .git/objects/... are the ONLY safe bash-side git-adjacent
  operation per gotcha #14 parent-walk pattern. Everything else:
  Read + Grep + Glob.

## Begin
1. Boot sequence reads (steps 1-7 above)
2. Baseline check (via Read + Grep, NOT bash git per gotcha #15)
   + report values to Casey
3. Ask Casey which lane(s) to dispatch (2B.1 / 2B.3 / both / hold;
   recommend based on R2 prereq state)
4. Patch the TBD-... placeholders in the relevant dispatch prompt(s)
   to the known session-18 ship SHAs (5fea2ce, d631c77,
   c8d9e0f1a2b3, 1607) before pasting
5. Paste the relevant dispatch prompt(s) into fresh Cursor chat(s)
6. Wait + verify rhythm per session-18 pattern (NO bash git)
Don't ask "where do we start" — the boot sequence is the source of
truth.
```
