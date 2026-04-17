# Havasu Chat — Development Plan and Working Agreement

**Audience:** Claude Code, executing sessions against the Havasu Chat codebase.
**Author:** Senior reviewer, working with Casey (solo dev).
**Last updated:** April 17, 2026.
**Status:** Active working document. Update after each session completes.

---

## 1. Read This First

Before executing any session, read:

1. This document in full.
2. `docs/project-handoff.md` — system of record for state and history.
3. `docs/havasu-knowledge-base.md` — product/query taxonomy.
4. `docs/query-test-battery.md` — 120-query regression contract.
5. `havasu-state-snapshot.md` on the user's desktop — most recent external audit.

If any of those are missing or out of date, flag it and stop before proceeding.

---

## 2. Project Context (Non-Negotiable)

**Havasu Chat is a conversational hyperlocal assistant for Lake Havasu City, Arizona.** Today's scope is dated events. The longer-term vision is a trusted "friend in town who knows everything" — events, ongoing programs, venues, service recommendations, and everyday local knowledge.

**Primary user:** Local parents with kids, with a secondary audience of visiting families. The app should feel like asking a knowledgeable friend, not querying a database.

**Current production URL:** `https://web-production-bbe17.up.railway.app`
**Deployment:** Railway auto-deploys every push to `main`.
**Stack:** FastAPI, SQLAlchemy, Alembic, SQLite locally / PostgreSQL on Railway, OpenAI for embeddings and extraction, vanilla HTML/CSS/JS frontend.

---

## 3. Working Principles (Apply These Every Session)

These are non-negotiable. They are the reason the project has shipped 20+ sessions cleanly with minimal regressions.

### 3.1 One session, one change
Every session targets exactly one thing. No scope creep. If you find related work that needs doing, log it as a future session and stay focused on the current task. The only exception is a regression you cause — fix that in the same session, document it, and move on.

### 3.2 Tests must pass before commit
Run the full pytest suite before every commit. If a test fails, either fix it or explain why the change legitimately requires updating the test. Never push a failing suite.

### 3.3 The 120-query battery is the quality contract
After any change to search, intent, venues, slots, seed data, or conversation copy, re-run `scripts/run_query_battery.py` against production. If pass rate drops below 95%, investigate before merging the next session. The current baseline is 96.67%.

### 3.4 Quality over speed
Casey's stated standard is "right, not fast." Take the time to diagnose before fixing. When in doubt, propose the change and wait for approval rather than guessing. A careful fix is worth more than three rushed ones.

### 3.5 Diagnose before fixing
When behavior is wrong, trace the code path. Identify the root cause with file and line numbers. Show the evidence before proposing a fix. Never assume — verify.

### 3.6 Ask when ambiguous
If a prompt is garbled, contradictory, or references something that doesn't exist in the repo, stop and ask. Do not guess. Do not invent behavior.

### 3.7 Honor the product decisions already made
Certain behaviors are intentional, not bugs:
- Venue precedence: queries naming venues that have seeded events return those events rather than a venue redirect. Battery rows 22, 44, 46, 49 reflect this.
- Embeddings use `text-embedding-3-small` for both query and event. Do not change this without explicit approval.
- Synonyms expand the embedding query string only, not the SQL keyword filter. Do not widen this without explicit approval.
- Admin review is required before submitted events go live. Do not bypass.

### 3.8 Pay once per event, never per search
Embeddings and tags are generated once at event creation or admin backfill. Search queries run free keyword and synonym matching plus one embedding call per query. No per-search LLM calls.

### 3.9 Update docs as part of the session
Every session that changes behavior must update the handoff doc and any relevant knowledge base section in the same commit. Doc drift is a bug.

---

## 4. Current State Summary

**As of April 17, 2026 (after Session AD):**

- 91 passing tests across 10 test files
- 96.67% pass rate on the 120-query production battery; canonical baseline file is `scripts/battery_results.json` (kept in sync with `scripts/battery_session_t_final.json`; see `scripts/README.md`)
- 29 seed events spanning May through July 2026
- AI-generated tags live on all seeded events
- Admin panel with tag pills, embedding status badges, preview links, sort controls, and analytics dashboard at `/admin/analytics`
- Permalink route `/events/{id}` with Open Graph meta tags and share button
- Out-of-scope intent detection for weather, lodging, transportation, dining
- Venue recognition layer with longest-alias-wins matching
- Session state hardened against stale date carryover
- Welcome chip self-heal for transient render failures
- Pending review deadline in code: **72 hours** (`timedelta(hours=72)` in `_store_pending_review`); handoff and tests aligned to that window in Session AD
- `search_debug.log` ignored at repo root; Playwright removed from `requirements.txt` (unused)

---

## 5. The Forward Plan

Execution happens in four phases. Each phase has a purpose. Do not skip ahead.

### Phase 1 — Housekeeping (1 session)

**Session AD** ✅ *(completed April 17, 2026)* — Reconciled documentation, resolved the stale battery baseline, aligned pending-review TTL **copy and tests** with the existing 72-hour code, verified `.gitignore` for `search_debug.log`, and removed unused Playwright. No functional product changes.

Why this comes first: the next several sessions will build on the current state, and the docs lying about that state causes confusion and wasted work.

### Phase 2 — Track B Cleanup (4 sessions)

**Session I** — Returning-user onboarding via localStorage. First-time visitors keep current onboarding. Returning visitors get a shorter "welcome back" with two time-appropriate chips.

**Session W** — Error monitoring setup with Sentry. Casey must sign up for Sentry and provide a DSN before this session runs.

**Session P** — Extend `extract_date_range` in `slots.py` to consistently parse "this week," "next week," "this month," "next month." Some of this is handled at the router level today but not in the canonical slot extractor.

**Session X** — Copy polish pass over `conversation_copy.py` and the welcome message in `index.html`. Casey provides notes on tone and flagged strings before this session runs.

**Session Y** — Rate limit review and mobile audit. Check tap target sizes, text sizing on small screens, safe area handling. Tune rate limits to sensible values.

Why this phase: quick wins that clear polish work off the plate, protect the app with monitoring, and confirm the foundation is solid before significant new features land.

### Phase 3 — Major Features (9-12 sessions)

**Session Z** — Programs and classes (multi-session).

Sub-sessions:
- Z-1: Add `Program` model with fields for activity category, age range (min/max), recurring schedule (days of week, time range), location, cost, contact, provider info, source type, active status. Migration.
- Z-2: Search routing. Detect program-style queries ("lessons," "classes," "learn," "where can my kid") and query the programs table. Responses show "Every Saturday, 9:00 AM–12:00 PM" instead of a specific date.
- Z-3: Admin UI for creating, editing, deactivating programs. Mirror the existing event moderation flow.
- Z-4: Seed 15-25 real Havasu programs across core categories (golf, swim, martial arts, dance, music, art, sports, tutoring, summer camp). Curation work, mostly manual.

**Session AA** — Community data contribution loop with two-tier source model.

Sub-sessions:
- AA-1: Add `source` field to events and programs (provider, parent, admin, scraped). Admin UI surfaces this as a badge.
- AA-2: Parent submission flow — any authenticated-by-cookie user can submit program info or venue corrections. Goes to moderation queue.
- AA-3: Provider claim flow — email-based verification so providers can claim and edit their listings. Provider-submitted and provider-verified entries show differently to end users.

**Session AB** — Unified moderation queue.

One admin view that handles events, programs, and venue info submissions. Red-flag detection (duplicates, suspicious URLs, all caps, empty fields). Keyboard shortcuts: A to approve, D to deny, E to edit-then-approve. Must work on mobile — Casey does moderation on his phone.

**Session AC** — Calendar view (multi-session).

Sub-sessions:
- AC-1: Calendar UI as a full-screen overlay over chat. Month grid, tap a day to see events. Navigate months forward and backward. Small calendar icon in the top corner of the chat as the entry point.
- AC-2: Chat integration. When the user types "show me the calendar" or "what's this month look like," open the calendar programmatically. Tapping an event in the calendar opens it as a chat response.

**Conversation style upgrades** (1-2 sessions)

Implement the behavior patterns surfaced during product design roleplay:
- When a query is broad and involves personal context ("my family," "my kids," "us"), the app asks ONE short clarifying question before recommending. One sentence, not a form.
- Response length scales with query complexity. Simple factual questions get short answers. Complex or personal queries get warmer, more structured responses.
- Knowledge-gap redirects: when the app can't answer a factual question (hours, prices, menus), it acknowledges the limit, points to the venue's website or Facebook page, and invites the user to contribute the info back. Turns gaps into community-building moments.
- One-answer-or-refine rule: 1-2 strong matches get a confident answer, 3-5 matches show results with a refining question, 6+ matches prompt the app to ask for more specificity before dumping a list.

### Phase 4 — Pre-Launch

- Real data seeding: expand to 75-100 events, 15-25 programs, venue info for the 20 most-named Havasu venues. Curation work.
- Final battery run targeting 96%+ pass rate with the new feature surface included.
- Contributor onboarding document: a short note Casey sends to trusted early users explaining what the app is, how to submit events and programs, and how to give feedback.
- Stealth launch: URL goes live, Casey shares it privately with trusted contributors. No advertising. Organic discovery is fine.

---

## 6. The Next Task (Session AD)

**Session AD is complete.** Do not re-execute from this section; see Section 4 for current state and Section 5 Phase 1 for the checkbox.

---

## 7. Communication Protocol

When reporting back at the end of a session, produce:

1. **Summary** — what changed, in one paragraph.
2. **Files touched** — list with one-line description each.
3. **Test results** — count passing, any failures and why.
4. **Battery results** — if the session touched search or intent, include old and new pass rates.
5. **Regressions introduced** — must be zero, or explicitly called out with remediation plan.
6. **Commit hash** — from `git log -1 --format=%H`.
7. **Follow-ups surfaced** — anything you noticed that should become a future session but isn't in scope for this one.

Keep it factual. No filler. Casey and the reviewer read these reports closely.

---

## 8. Escalation

Stop and ask if any of the following happens:

- A prompt references a file that doesn't exist.
- A prompt contradicts a working principle in Section 3.
- A proposed change would touch more than the scoped files.
- A test fails and the fix is not obvious.
- Production behavior differs from local behavior after a deploy.
- A session would introduce a new external dependency (npm package, Python library, external API).

Do not guess. Ask.

---

## 9. Versioning of This Document

This file is the single source of truth for the plan forward. When a session completes, update Section 4 (Current State Summary) and Section 5 (cross off completed sessions or mark them done). Do not delete completed sessions — they are the historical record.

When the plan materially changes (new phase added, feature scope reduced, vision shifts), update the affected sections and note the date at the top.

---

**End of document.**
