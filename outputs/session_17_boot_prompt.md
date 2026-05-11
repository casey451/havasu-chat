# Session-17 Boot Prompt

> Paste this into a fresh Cowork primary chat to boot session-17 on havasu-chat.

---

```
You're the new Cowork primary on havasu-chat — Lake Havasu City local
directory + AI chat. Previous agent (session-16) closed out Phase 1 of
the master build plan + signed off cleanly. State is durable on
origin/main HEAD = dcf2f7a.

## Boot sequence (~5-7 min)
1. docs/SESSION_HANDOFF_2026-05-14_session16.md — closes session-16.
   Captures the 11-commit narrative (8 substantive + 3 close-out
   hygiene: gotcha #13 + prereq guide + boot prompt update), Phase 1
   close-out summary, queued Phase 2 work, accepted pragmatic
   deviations, two new lessons worth folding into Phase 2 briefs.
2. docs/STATE.md — Production block notes the origin-vs-deployed
   divergence: origin at dcf2f7a (the latest at session-16 close;
   STATE.md itself last updated at 1c98365 so it doesn't reflect the
   final 3 close-out commits — those landed on top and are pure
   docs hygiene, no code changes) with full Phase 1 chain through
   alembic head f8e9d0c1b2a3; production at 5132162 with alembic head
   b2c3d4e5f6a7 (1A + 1B live; 1C + 1D queued for next deploy at
   operator cadence). "Recently shipped" §1 has the full session-16
   narrative through 1c98365.
3. docs/maintainability/master_build_plan.md §4 Phase 1 ("Shipped" list
   now has all four sub-phase ship-lines + the Phase 1 SHIPPED header)
   and §4 Phase 2 (next dispatchable lane: 2A account-lite + 2B image
   storage / search index — file-disjoint per Rule 3, parallelizable).
4. outputs/operator_prereqs_phase_2.md — operator-side setup guide
   for Resend (Lane 2A) + Cloudflare R2 (Lane 2B), authored at
   session-16 close in response to Casey not knowing R2 was needed.
   Read this BEFORE step 5 — it's what you'll point Casey at when
   asking about prereq status in your first-actions step #2.
5. docs/maintainability/account_lite_v01_design.md if dispatching
   Lane 2A; docs/maintainability/image_storage_design.md +
   docs/maintainability/search_index_decision.md if dispatching
   Lane 2B. (Read whichever lane Casey wants to dispatch first.)
6. outputs/cursor_brief_phase_1_entity_schema.md — preserved as the
   reference for the brief-authoring pattern. Sections 0/3/10/11/12/13
   are the canonical shape to mirror when authoring Phase 2 briefs.
7. docs/maintainability/dispatch_protocol.md (12 working-agreement
   rules) + docs/maintainability/dispatch_channels.md (channel-pick
   playbook + 13 gotchas as of session-16 — new gotcha #13 covers
   PowerShell ; vs && command chaining).

## New lessons from session-16 worth folding into Phase 2 briefs
1. Postgres-vs-SQLite portability is a real and recurring risk. The
   bash sandbox runs SQLite; production runs Postgres; constructs that
   work in one don't necessarily work in the other. Already folded into
   Phase 1 brief §10 — Phase 2 briefs should carry the same checklist:
   use sa.true()/sa.false() not sa.text("1")/sa.text("0") for boolean
   defaults; use sa.func.now() not sa.text("CURRENT_TIMESTAMP") for
   timestamp defaults; verify raw SQL inside op.execute() works on
   Postgres not just SQLite. The Phase 1A migration crashloop'd
   production at session-15 close because of exactly this; the lesson
   is durable.
2. The before_flush Session listener safety-net pattern generalizes
   well across write-path lanes. Cursor reached for it independently in
   Phase 1D (`register_catalog_dual_write_hooks` in app/db/database.py)
   after the slug-listener precedent in session-13's d967568. When
   Phase 2 briefs touch write paths (Lane 2A's user creation +
   magic-link issuance + claim creation; Lane 2B's photo upload), the
   §11 acceptable-deviations section should explicitly invite the
   safety-net pattern so Cursor doesn't have to rediscover it.

## Your first actions, in order
1. Run baseline: git log --oneline -3 (top should be dcf2f7a → 4bb74bc
   → 03f7160 — the three close-out hygiene commits at the end of
   session-16), pytest --collect-only | tail -3 (should show 1518),
   python -m alembic heads (should show f8e9d0c1b2a3). Report values
   to Casey.
2. Check operator-prereq status. Phase 2 brief authoring is gated
   usefully on two operator actions: (a) Resend API key registration
   for Lane 2A account-lite; (b) Cloudflare R2 bucket + CDN domain for
   Lane 2B image storage. ASK CASEY which (if either) is done before
   authoring the corresponding brief — locking in the prereq before
   brief authoring avoids baking-in assumptions that need rework.
3. Confirm production deploy status of 1c98365. The Phase 1C + 1D
   code chain is on origin but may not yet be deployed (was operator's
   cadence call at session-16 close). If still un-deployed, no urgency
   — but worth confirming so the STATE.md Production block is accurate
   for any subsequent session-16-style deploy hotfix.
4. Wait for operator say-so on which Phase 2 lane to author + dispatch
   first. Lane 2A is smaller (5-7 day brief estimate per master plan);
   Lane 2B is bigger (7-10 day). Per master plan §4 Phase 2 they're
   parallelizable but operator may prefer sequential.

After authoring a Phase 2 brief: save to
outputs/cursor_brief_phase_2a_account_lite.md (or
outputs/cursor_brief_phase_2b_image_storage_search.md) per
dispatch_channels.md gotcha #12 (durable workspace artifacts).
Mirror the Phase 1 brief structure: §0 baseline + reads, §1 why this
lane exists, §2 locked decisions, §3 sub-phase boundaries, §4+
deliverables in detail, §10 what NOT to do (carry the Postgres
portability rules forward), §11 pragmatic deviations are allowed
(invite the safety-net pattern), §12 risk register, §13 final report
format. Then author a short paste-into-Cursor dispatch prompt at
outputs/cursor_dispatch_prompt_phase_2a.md (or 2b) mirroring the
Phase 1C/1D dispatch prompts.

## Firm ground (carry-over from sessions 15 + 16)
- Anchored Edit on existing files; Write only for new files (Rule 1+6)
- Wait for explicit text reports before git add (Rule 2)
- Sequential lanes when files overlap (Rule 3) — Phase 2 lanes 2A + 2B
  are file-disjoint so parallelizable
- PowerShell single-quote git commit -m '...' when subjects have $, §,
  →, parens, or other sigils (gotcha #8). PowerShell uses ; not && for
  command chaining (5.1 doesn't support &&; pwsh 7+ does but ; works
  everywhere; this lesson surfaced session-16 close).
- Local ruff must match dev-requirements.txt pin ruff==0.15.12
  (gotcha #9)
- alembic current "(mergepoint)" label is a chain-walk diagnostic NOT
  a multi-head alarm (gotcha #10)
- Linux bash mount serves stale .git views — use Windows-side Read
  tool as authoritative (Rule 7); session-16 hit this AGAIN at boot.
  When the bash mount git is broken, .git/refs/heads/main can be read
  directly to confirm HEAD SHA without git commands.
- Don't run git commit --amend while parallel lanes in flight (Rule 12)
- Postgres-vs-SQLite portability checklist (new in session-16 §10):
  use sa.true()/sa.false() for booleans; sa.func.now() for timestamps;
  verify raw SQL works on Postgres not just SQLite

## What NOT to do
- Don't redo session-16's work; 11 commits including Phase 1
  close-out + close-out hygiene (handoff doc, boot prompt, gotcha
  #13, operator-prereq guide) are on origin
- Don't author Phase 2 briefs before checking with Casey on operator
  prereqs (Resend / R2) — premature briefs bake in unverified
  assumptions
- Don't dispatch Phase 2 lanes before their briefs are authored AND
  the corresponding operator prereq is locked
- Don't propose React/SPA migration (tech stack constraint)
- Don't propose native user reviews (deferred unless review-war
  dynamics in Havasu prove otherwise)
- Don't ship anything violating texture rules (no engagement loops,
  popups, fake urgency)
- Don't re-debate locked decisions in master plan §10
- Don't dispatch sub-agents while Cursor is mid-flight unless work is
  in a disjoint file domain (context burn for primary)
- Don't re-tighten the Phase 1C orphan-fallback hybrid pattern as a
  side quest — Cursor explicitly chose Option X at the Phase 1D
  decision point; if/when it's worth doing it lives in Phase 13
  cleanup

## Begin
1. Boot sequence reads (steps 1-7 above)
2. Baseline check + report values to Casey
3. Ask Casey which Phase 2 lane to author + whether the corresponding
   operator prereq is locked
4. Wait for Casey's say-so before authoring or dispatching anything
Don't ask "where do we start" — the boot sequence is the source of
truth.
```

---

*Authored at session-16 close, 2026-05-14. Mirrors the session-16 boot prompt shape (which mirrored session-15's). When session-17 closes, drop a corresponding `outputs/session_18_boot_prompt.md` here using this same pattern.*
