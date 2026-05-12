# Session-20 Boot Prompt

> Paste the body below into a fresh Cowork conversation to boot the next Cowork primary on havasu-chat.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-19) shipped Phase 2 of
the master build plan TO COMPLETION via PARALLEL dispatch of two
Cursor lanes per dispatch_protocol Rule 3 (Phase 2B.3 search bar UI
+ public /api/search; Phase 2B.1 photos schema + R2 + Pillow + upload
routes + sweep + three-tier hero/gallery + Lane 2B close-out + Phase
2 SHIPPED). State is durable on origin/main HEAD = <TBD-this-close-
out-commit-SHA>. Seven commits this session.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-12_session19.md — closes out session-19.
   Captures the 7-commit narrative (3 substantive ships + 3 docs/chore
   commits + this close-out), Phase 2 COMPLETE summary (Lane 2A chain
   6000138 -> 714ca52 -> 5fea2ce; Lane 2B chain d631c77 -> 8338505 ->
   1c57c73; total Phase 2 pytest delta 1518 -> 1663 +145; final Phase
   2 alembic head f9e8d7c6b5a4), queued Phase 3.1 + 3.2 work,
   accepted pragmatic deviations across both lanes, six new lessons
   (gotcha #16 candidate embedded "..." in -m '...' PowerShell,
   gotcha #15 discipline scales, per-step operator walkthrough scales
   for one-shot consequences, three-track parallelism validated,
   primary-side strategic brief authoring during Cursor in-flight,
   dispatch prompt SHA-patch pattern durable).
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at <TBD-this-close-out-commit-SHA> with full
   Phase 1 + Phase 2 chain through alembic head f9e8d7c6b5a4;
   production still at 5132162 with alembic head b2c3d4e5f6a7 (1A +
   1B live; 1C + 1D + 2A.1 + 2A.2 + 2A.3 + 2B.2 + 2B.3 + 2B.1 queued
   for next deploy at operator cadence — four migrations apply).
   "Recently shipped" §1 has the full session-19 narrative.
3. docs/maintainability/master_build_plan.md §4 Phase 2 (now reads
   "SHIPPED 2026-05-12" with full Lane 2A + 2B SHIPPED + Phase 2
   SHIPPED close-out paragraph) and §4 Phase 3 (next major phase
   after Phase 2 closes — v1.1 schema pass + districts + categories
   + alerts).
4. outputs/cursor_dispatch_prompt_phase_3_1.md — pre-positioned in
   session-19 and patched in c9ab794 with known SHAs (1c57c73 +
   f9e8d7c6b5a4 + 1663). Ready to paste. Phase 3.1 ships 7 new entity
   columns + 5 new tables + users.preferred_mode + ORM models +
   ~15-20 new tests. Additive-only; no operator prereq.
5. outputs/cursor_brief_phase_3_v11_schema_pass.md §0 + §3 + §4 + §6
   + §7 + §10 + §11 + §12 — the heavy-prescriptive operating doc
   (~580 lines, two-sub-phase decomposition; 3.2 dispatch gated on
   5 Bucket C operator decision-locks + district paragraphs polish).
6. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (15 gotchas as
   of session-18; gotcha #16 candidate — embedded "..." in -m '...'
   PowerShell — needs landing this session per session-19 handoff §5
   lesson 2).
7. outputs/chatgpt_response_district_paragraphs_v1.md — Phase 3 V1
   deliverable drafted by ChatGPT in session-17. 5 [CASEY: ...]
   placeholders + 5 "Casey to verify" items pending operator polish.
   NOW BLOCKING Phase 3.2 dispatch (bumped from "no rush" in
   session-18 + 19 handoffs).

## New lessons from session-19 worth folding into Phase 3.1 brief
1. **Gotcha #16 candidate — embedded `"..."` inside `-m '...'`
   PowerShell.** Even inside `-m 'plain single-quoted body'`,
   PowerShell's native-command argument re-tokenizer treats embedded
   `"..."` as token boundaries and breaks the argument. Symptom:
   `error: pathspec '<rest-of-body>' did not match any file(s) known
   to git`. Fix: avoid embedded double-quotes entirely in `-m '...'`
   bodies; use plain text (no quotes needed for emphasis) or Unicode
   curly quotes. Session-19 first surfaced this at the docs commit
   attempt; the bundled-commit-as-consequence was the impact. Author
   gotcha #16 to dispatch_channels.md in this session as a docs lane
   so future sessions inherit the rule.
2. **Three-track parallelism validated at production scale.** Session
   -18 first ran two Cursor lanes (2A.3 + 2B.2) simultaneously per
   Rule 3; session-19 ran TWO Cursor lanes (2B.3 + 2B.1) + an
   operator-side R2 walkthrough simultaneously. Working tree
   converges; commits stay file-disjoint per Rule 8 via per-file
   `git add` staging. Pattern is production-ready for 2-3-track
   work.
3. **Primary-side strategic brief authoring during Cursor in-flight
   scales.** Sub-agent pattern is right for narrow tightly-scoped
   dispatch prompts (session-18 pre-positioned 2B.1 + 2B.3 prompts
   via parallel sub-agents); primary-side is right for heavy
   synthesis work (session-19 authored Phase 3 brief primary-side
   during 2B.1 in-flight time, ~580 lines + locked decisions + risk
   register). Rule of thumb: primary-author when you have context
   cached + parallel Cursor lane is active; sub-agent when scope
   is small + structured.
4. **Per-step operator walkthrough scales for one-shot consequences.**
   Bulk-mode dumps work as first-pass material; operator opts into
   per-step mode for actual execution when irrecoverable consequences
   are involved (token creation, one-time secret displays, payment
   method on file). Cloudflare R2 setup had three such steps in
   session-19; per-step walkthrough kept Casey from missing the
   one-shot secret display.
5. **Bash mount `git` is unsafe even for `git ls-tree` in mixed-OS
   sessions.** Gotcha #15 (originally about `git status -s` /
   `git diff --stat HEAD`) extends to ANY git invocation that touches
   the index, even read-only plumbing commands like `git ls-tree`.
   The Linux mount creates `.git/index.lock`, which CAN'T be unlinked
   from Linux sandbox in some race conditions. Session-19 had one
   slip + no consequence (Windows-side checked the lock and found
   none — apparently the lock was confined to the bash mount's view
   of the filesystem and didn't propagate). Still: from session-20
   forward, the rule is **zero `git ...` from the bash sandbox**.
   Use `python3 + zlib.decompress` on `.git/objects/...` per gotcha
   #14's parent-walk pattern for any commit-content verification
   needs. Read + Grep + Glob remain the working-tree-inspection
   tools.

## Your first actions, in order
1. Run baseline: read top of `.git/refs/heads/main` via Read tool
   (top should be <TBD-this-close-out-commit-SHA> — the session-19
   close-out commit), cross-check `docs/STATE.md` Recent commits
   block for the c9ab794 → 3d89e58 → 1c57c73 → c464007 → 8338505 →
   aed79ac chain, confirm alembic head f9e8d7c6b5a4 via Glob on
   alembic/versions/. Run `python -m pytest -q --collect-only |
   tail -3` if Windows-side venv is available (should show 1663 + 1
   skipped). Report values to Casey. **DO NOT** use bash `git ...`
   per gotcha #15 — even `git ls-tree` is unsafe.
2. Ask Casey which lane to dispatch: (a) Phase 3.1 (schema additions;
   no operator prereq; ~3-4 day Cursor estimate); (b) Walk through
   the 5 Bucket C decision-locks + district paragraph polish FIRST
   so Phase 3.2 unblocks ASAP after 3.1 ships; (c) Production deploy
   of Phase 1C+1D+2A+2B to Railway first (carries 4 migrations
   including first-deploy Postgres FTS DDL — non-trivial smoke); (d)
   author gotcha #16 docs commit to dispatch_channels.md first (small
   docs lane; durable artifact); (e) hold. Recommend (a) + (b) IN
   PARALLEL — paste 3.1 prompt to Cursor, then walk Bucket C decisions
   + district paragraph polish operator-side during Cursor in-flight
   time. Operator decision time is ~20-25 min total; Phase 3.1 ships
   in ~3-4 days of Cursor walltime.
3. If Phase 3.1 dispatches: paste outputs/cursor_dispatch_prompt_
   phase_3_1.md contents to a fresh Cursor chat. Prompt is already
   patched with known SHAs (1c57c73 + f9e8d7c6b5a4 + 1663); no
   placeholder patching needed pre-paste.
4. While Cursor 3.1 works, consider parallel work:
   - Bucket C decision-locks + district paragraph polish (Phase 3.2
     prereq; ~20-25 min combined)
   - Author Phase 3.2 dispatch prompt (only authorable after 3.1
     ships since chains off 3.1 alembic revision)
   - Author gotcha #16 docs commit for dispatch_channels.md
   - Help Casey plan the Phase 2 production deploy (Railway-side
     migration sequencing, smoke-check checklist)
5. When Cursor returns §13 reports, run the verify-commit-push rhythm
   (session-19 pattern: spot-check files via Read + Grep ONLY, NOT
   bash git; propose commit recipe with PowerShell-safe single-quoted
   -m bodies; **NO embedded double-quotes per gotcha #16 candidate**;
   Casey commits + pushes; then docs commit if next sub-phase scope
   is locked).

## Firm ground (carry-over from sessions 15 + 16 + 17 + 18 + 19)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap; parallel when disjoint
  (Rule 3) — Phase 3.1 + Phase 3.2 are sequential (3.2 chains off
  3.1's alembic revision), so dispatch sequentially not in parallel.
  Phase 3.1 + Phase 3.2-prereq-operator-work (Bucket C + district
  polish) ARE parallel because they touch disjoint domains.
- PowerShell single-quote git commit -m '...' when subjects have $,
  §, →, parens, or other sigils (gotcha #8). PowerShell 5.1 uses ;
  not && for command chaining (gotcha #13). **NEW: avoid embedded
  "..." double-quotes inside -m '...' bodies entirely (gotcha #16
  candidate from session-19; needs landing this session).**
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current "(mergepoint)" label is a chain-walk diagnostic
  NOT a multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views — use Windows-side Read
  tool as authoritative (Rule 7). When bash mount git is broken,
  walk parent links via python3 + zlib.decompress on .git/objects
  (gotcha #14). **Don't run bash git status/diff/log/ls-tree/
  ANYTHING against the working tree — even read-only ops leave a
  stuck .git/index.lock that Windows git refuses to step on (gotcha
  #15, extended in session-19 to include `git ls-tree`).** Use Read
  + Grep + Glob (Windows-authoritative) for everything.
- Don't run git commit --amend while parallel lanes in flight (Rule 12)
- Postgres-vs-SQLite portability: sa.true()/sa.false() for booleans;
  sa.func.now() for timestamps; verify raw SQL inside op.execute()
  works on Postgres not just SQLite. For Phase 3.1 specifically: the
  migration adds 5 new tables + 8 new columns; mirrors Phase 2A.1 +
  2B.2 + 2B.1 portable shapes. Beware potential conflict on
  entities.seasonal_hours JSON column vs Phase 1A's seasonal_hours
  extension table — brief §4.1 + §9 instructs Cursor to HALT + flag
  before authoring if both exist.

## What NOT to do
- Don't redo session-19's work; 7 commits including Phase 2B.3 +
  2B.1 substantive ships, Phase 2 SHIPPED header on master plan,
  Phase 3 brief + 3.1 dispatch prompt pre-positioned + patched,
  R2 operator prereq locked + 5 R2_* env vars in Railway are all
  on origin
- Don't author Phase 3.1 brief from scratch — it's pre-positioned at
  outputs/cursor_brief_phase_3_v11_schema_pass.md (~580 lines)
- Don't author Phase 3.1 dispatch prompt from scratch — it's pre-
  positioned + already patched with known SHAs at
  outputs/cursor_dispatch_prompt_phase_3_1.md
- Don't dispatch Phase 3.2 without operator locking the 5 Bucket C
  decisions + polishing the district paragraphs draft (both
  enumerated in brief §7)
- Don't dispatch Phase 3.1 and Phase 3.2 in parallel — 3.2 chains
  off 3.1's alembic revision (Rule 3 sequential-when-files-overlap;
  alembic chain IS a file overlap)
- Don't author Phase 3.2 dispatch prompt before 3.1 ships (chains
  off 3.1's alembic revision; can't fill until shipped)
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan §10 or brief §2 +
  §6 — including the 12-slug new-taxonomy lock; the 5 professional-
  services strings V1.5 deferral; the entities.district_id FK
  targeting entities.id (not polymorphic)
- Don't dispatch sub-agents while Cursor is mid-flight unless work
  is in a disjoint file domain (context burn for primary)
- **Don't run any bash git operations against the working tree
  (gotcha #15 — extended in session-19 to ALL git invocations
  including read-only plumbing).** Pure object reads via python3 +
  zlib.decompress on .git/objects/... per gotcha #14's parent-walk
  pattern are the ONLY safe bash-side git-adjacent operation.
  Everything else: Read + Grep + Glob.
- **Don't include embedded "..." double-quotes in -m '...' commit
  bodies on PowerShell (gotcha #16 candidate).** Use plain text or
  Unicode curly quotes for emphasis. Session-19 lost the docs commit
  to this; the docs files landed inside a chore commit instead.

## Begin
1. Boot sequence reads (steps 1-7 above)
2. Baseline check (via Read + Grep, NOT bash git per gotcha #15)
   + report values to Casey
3. Ask Casey which lane to dispatch (3.1 / Bucket C + district
   polish / deploy / gotcha #16 docs / hold; recommend 3.1 +
   prereq-work IN PARALLEL)
4. Phase 3.1 prompt is already patched + ready; no pre-paste
   placeholder work needed
5. Paste the relevant dispatch prompt(s) into fresh Cursor chat(s)
6. Wait + verify rhythm per session-19 pattern (NO bash git; NO
   embedded "..." in -m '...' bodies)
Don't ask "where do we start" — the boot sequence is the source of
truth.
```
