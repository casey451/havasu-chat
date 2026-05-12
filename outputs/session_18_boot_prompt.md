# Session-18 Boot Prompt

> Paste this into a fresh Cowork primary chat to boot session-18 on havasu-chat.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-17) shipped Phase 2A.1 +
Phase 2A.2 of Phase 2 Lane 2A (account-lite v0.1) and pre-positioned
dispatch prompts for both Phase 2A.3 and Phase 2B.2. State is durable
on origin/main HEAD = 7f5b1f7. Eleven commits this session.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-11_session17.md — closes session-17.
   Captures the 11-commit narrative (3 substantive Cursor lanes +
   8 docs/dispatch-artifact commits), Phase 2 Lane 2A 2A.1+2A.2 ship
   summary, queued Phase 2A.3 + 2B.2 + 2B.1 + 2B.3 work, accepted
   pragmatic deviations, five new lessons worth folding into Phase
   2A.3 + 2B.2 dispatches.
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at 7f5b1f7 with full Phase 1 + Phase 2A.1 +
   2A.2 chain through alembic head 92ce4899dc08; production still
   at 5132162 with alembic head b2c3d4e5f6a7 (1A + 1B live; 1C + 1D
   + 2A.1 + 2A.2 queued for next deploy at operator cadence). "Recently
   shipped" §1 has the full session-17 narrative.
3. docs/maintainability/master_build_plan.md §4 Phase 2 ("Shipped
   (incremental)" list now has 2A.1 + 2A.2 ship-lines + the 2A.3
   pending stub + Lane 2B pending) and §4 Phase 3 (next major phase
   after Phase 2 closes).
4. outputs/cursor_dispatch_prompt_phase_2a_3.md AND/OR
   outputs/cursor_dispatch_prompt_phase_2b_2.md — both pre-positioned
   in session-17, ready to paste. 2A.3 closes out Lane 2A (claim flow
   + favorites + admin role + viewer_is_owner). 2B.2 is the FTS lane
   (dependency-free of 2A.3, no operator prereq needed). Per
   dispatch_protocol Rule 3, both can dispatch in PARALLEL Cursor
   chats — they touch file-disjoint domains.
5. outputs/cursor_brief_phase_2a_account_lite.md §7 (for 2A.3
   reference; what Cursor will execute) AND/OR
   outputs/cursor_brief_phase_2b_image_storage_search.md §6 (for
   2B.2 reference). Read whichever you're dispatching first.
6. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (channel-pick
   playbook + 14 gotchas as of session-17 — new gotcha #14 covers
   reflog-vs-ancestry forensics when bash mount git is broken per
   Rule 7).
7. outputs/chatgpt_response_district_paragraphs_v1.md — Phase 3 V1
   deliverable drafted by ChatGPT in session-17. 5 [CASEY: ...]
   placeholders + 5 "Casey to verify" items pending operator polish.
   Not blocking; Phase 3 isn't dispatching soon.

## New lessons from session-17 worth folding into Phase 2A.3 + 2B.2 briefs
1. Reflog (.git/logs/HEAD) is NOT the commit ancestry — walk parent
   links via python3 + zlib.decompress on .git/objects when bash
   mount git is broken (gotcha #14). Already absorbed.
2. Parallel-dispatch posture for Phase 2 — 2A and 2B are file-disjoint
   per Rule 3. The brief §0 baseline checks halt gracefully if a
   prereq isn't locked, so dispatching 2A.3 + 2B.2 in parallel is
   safe + Casey doesn't need to babysit.
3. Pre-author-dispatch-prompt-while-Cursor-works pattern — reduces
   next-dispatch latency from ~30 min to ~0 min. Worth doing whenever
   next-sub-phase scope is already locked.
4. ChatGPT-as-Phase-3-prep channel — district paragraphs draft pattern
   generalizes to any prose-shaped + voice-anchorable + has-clear-
   failure-mode-flagging deliverable.
5. Auth deviation patterns worth carrying forward when 2A.3 dispatches:
   (a) detached-ORM-via-expunge for cross-request survival (2A.2's
       `db.refresh + db.expunge` pattern in SessionMiddleware);
   (b) module-level `_LAST_SEEN_MONO`-style debounce dict;
   (c) `_safe_next` whitelist with unquote + leading / + reject //,
       ://, .. (open-redirect guard);
   (d) parallel-path auth (admin-cookie OR role==admin) — 2A.3 implements
       this for the admin role bridge;
   (e) test conftest `setdefault` for AUTH_DEV_MODE=1.

## Your first actions, in order
1. Run baseline: git log --oneline -5 (top should be 7f5b1f7 →
   95d9f79 → 9e672b5 → 714ca52 → 0e8e9e3 — the five most recent
   session-17 commits), pytest --collect-only | tail -3 (should
   show 1563), python -m alembic heads (should show 92ce4899dc08).
   Report values to Casey.
2. Ask Casey which lane(s) to dispatch first: 2A.3 alone (sequential,
   closes Lane 2A), 2B.2 alone (the FTS lane, dependency-free, no
   prereq needed), BOTH IN PARALLEL (max throughput; two Cursor chats),
   or hold. Recommend BOTH if Casey has energy + bandwidth — they're
   file-disjoint so cognitive load is the only constraint.
3. If 2A.3 dispatches: paste outputs/cursor_dispatch_prompt_phase_2a_3.md
   contents to a fresh Cursor chat.
4. If 2B.2 dispatches in parallel: paste outputs/cursor_dispatch_prompt_phase_2b_2.md
   contents to a SECOND fresh Cursor chat.
5. While Cursor lanes work, consider parallel work:
   - Author 2B.1 dispatch prompt (gated on 2A.3 ship; pre-position
     now reduces future latency)
   - Author 2B.3 dispatch prompt (gated on 2B.2 ship; same logic)
   - Audit + refresh any docs that have been showing wear
   - Help Casey with R2 setup walkthrough (~30-45 min,
     outputs/operator_prereqs_phase_2.md §2) if he wants to unblock
     2B.1 dispatch
   - Help Casey polish the district paragraph [CASEY: ...] placeholders
     in outputs/chatgpt_response_district_paragraphs_v1.md (15-20 min)
6. When Cursor returns §13 reports, run the verify-commit-push rhythm
   (session-17 pattern: spot-check files, propose commit recipe with
   PowerShell-safe single-quoted -m bodies, Casey commits + pushes,
   then docs commit + dispatch artifact commits).

## Firm ground (carry-over from sessions 15 + 16 + 17)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint
  (Rule 3) — Phase 2A.3 + 2B.2 are file-disjoint so parallelizable
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
  (gotcha #14, NEW this session) — DO NOT grep .git/logs/HEAD
  (the reflog includes abandoned-branch commits).
- Don't run git commit --amend while parallel lanes in flight (Rule 12)
- Postgres-vs-SQLite portability: sa.true()/sa.false() for booleans;
  sa.func.now() for timestamps; verify raw SQL inside op.execute()
  works on Postgres not just SQLite. For Phase 2B.2 specifically:
  FTS DDL (tsvector + GIN + pg_trgm) is Postgres-only and must be
  dialect-gated; SQLite LIKE fallback path stays alive permanently
  for tests.

## What NOT to do
- Don't redo session-17's work; 11 commits including Phase 2A.1 +
  2A.2 ship, Lane 2B brief, 2A.3 + 2B.2 dispatch prompts, district
  paragraphs draft, gotcha #14 are all on origin
- Don't author Phase 2A.3 / 2B.2 briefs from scratch — both are
  pre-positioned + ready to paste
- Don't dispatch Phase 2B.1 without R2 prereq locked (Cloudflare R2
  bucket + API token + Railway env vars per
  outputs/operator_prereqs_phase_2.md §2)
- Don't dispatch Phase 2B.1 before Phase 2A.3 ships — 2B.1's
  upload-auth depends on 2A.3's claim flow + viewer_is_owner
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan §10
- Don't dispatch sub-agents while Cursor is mid-flight unless work is
  in a disjoint file domain (context burn for primary)

## Begin
1. Boot sequence reads (steps 1-7 above)
2. Baseline check + report values to Casey
3. Ask Casey which lane(s) to dispatch (2A.3 / 2B.2 / both / hold)
4. Paste the relevant dispatch prompt(s) into fresh Cursor chat(s)
5. Wait + verify rhythm per session-17 pattern

Don't ask "where do we start" — the boot sequence is the source of
truth.
```
