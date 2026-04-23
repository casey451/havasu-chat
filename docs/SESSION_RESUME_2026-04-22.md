# Havasu Chat — Session Resume (2026-04-22)

**Purpose:** Start-of-new-chat handoff. Read this file first, then HAVA_CONCIERGE_HANDOFF.md for full architectural spec.

## 0. Role split

- **Owner:** Casey. Solo developer, Lake Havasu City, AZ. ~20 hrs/week. Working mostly from mobile.
- **Claude (this chat):** Drafts Cursor delegation prompts. Provides architectural guidance. Does NOT write code directly.
- **Cursor:** Executes in the repo. Reports outcomes back to owner, who relays to Claude.

## 1. Repo and environment

- **Canonical URL:** https://havasu-chat-production.up.railway.app
- **Repo:** https://github.com/casey451/havasu-chat
- **Stack:** FastAPI + SQLAlchemy + Postgres (Railway prod) / SQLite (local dev)
- **Python interpreter:** `.\.venv\Scripts\python.exe` (Windows Store stub intercepts plain `python`)
- **Test command:** `.\.venv\Scripts\python.exe -m pytest -q`
- **PowerShell JSON POST:** use `curl.exe --data-binary "@file.json"`, NOT `-d`
- **Anthropic:** `claude-haiku-4-5-20251001`, max_tokens=150, temp=0.3, ephemeral prompt cache
- **Local .env:** Contains ANTHROPIC_API_KEY, OPENAI_API_KEY, ADMIN_PASSWORD. Gitignored.

## 2. Current state (top of session)

- **Last commit on `main`:** `35194af` — Phase 6.5-lite: local voice plumbing (empty `LOCAL_VOICE`, matcher, Tier 3 injection, tests, reports). **`Phase 6 is fully shipped`**, including 6.5-lite plumbing per the deferral plan in `docs/PHASE_6_5_LOCAL_VOICE_HANDOFF.md` (correct-and-grow; editorial blurbs post-launch).
- **Tests:** **742** passed (`.\.venv\Scripts\python.exe -m pytest -q`, 2026-04-22)
- **Working tree:** clean; `main` in sync with `origin/main`
- **Production:** healthy

**Recent `main` history** (newest first; anchor commits for Phase 6 close):

```text
35194af Phase 6.5-lite: local voice plumbing (empty, ready to grow)
a9dca4d docs: Phase 6.5 deferral plan and correct-and-grow workflow
3b6315e Phase 6.4.1: recommended-entity capture for prior_entity
9f8abb0 test: fix environment-dependent assertions in embedding and router latency tests
68c65cf docs: refresh session resume doc for 6.3/6.4 close + 6.4.1 planned
34ad30d docs: add Phase 6.4.1 implementation prompt (recommended-entity capture)
ce64b92 docs: document Phase 6.4 known gap (recommended-entity capture → 6.4.1)
4c5c7cb Phase 6.4: session memory (hints, prior-entity, date injection)
f6d423f Phase 6.3: onboarding first-turn (visitor status + kids quick-tap)
cf867b8 docs: session resume doc for 2026-04-22
```

### Phase status

**Shipped (Phases 1–5):**
- Phase 1 — Data model, seed data ✅
- Phase 2 — Chat API, classifier, Tier 3, ChatLog, rate limiter ✅
- Phase 3.1–3.8 — Tier 1 templates, routing, gap handling ✅
- Phase 4.1–4.7 — Tier 2 retrieval-then-generate ✅
- Phase 5.1–5.6 — Contribute mode ✅

**Phase 6 — closed (all sub-phases shipped):**
- **6.1** ✅ — Voice audit (6.1.1–6.1.4): `prompts/voice_audit.txt`, `scripts/run_voice_audit.py`, paid audit (~51 PASS / 1 MINOR / 3 FAIL / 0 ERROR), voice fixes `10b251b` lineage; t3-01 / t3-24 deferred at root per prior notes.
- **6.2** ✅ — Feedback loop end-to-end.
- **6.3** ✅ — Onboarding first-turn (visitor status + kids quick-tap), shipped this session — **`f6d423f`**.
- **6.4** ✅ — Session memory (hints, prior-entity, date injection), shipped this session — **`4c5c7cb`** + **`ce64b92`** (gap documented → 6.4.1).
- **6.4.1** ✅ — Recommended-entity capture for `prior_entity`, shipped this session — **`3b6315e`** (prompt doc **`34ad30d`**).
- **6.5** ✅ — Local-voice **plumbing** live: empty `LOCAL_VOICE`, matcher, Tier 3 `user_text` injection, system prompt note; correct-and-grow workflow per **`docs/PHASE_6_5_LOCAL_VOICE_HANDOFF.md`** — **`a9dca4d`** (plan) + **`35194af`** (implementation). Editorial blurbs are owner/operator content, not a scheduled dev phase.

**Phase 6 closed.**

**Post-Phase 6:**

- **Phase 8 — pre-launch hardening is next** (see **§5 Phase 8** in `HAVA_CONCIERGE_HANDOFF.md`): seed verification, load testing, admin runbook, ToS, privacy review.
- **Phase 6.5 content** continues to accumulate **organically post-launch** (not a scheduled phase); the repo wiring is done.
- **Deferred (unchanged from prior session resume):** correction flow (reads `field_history` baseline); cost optimization pass (after 2–4 weeks real traffic). Other deferred decisions and follow-ups — unchanged from **§6** below.

## 3. Process conventions (reinforced across sessions)

- **One prompt at a time.** Long prompts as markdown when multi-step.
- **Read-first then owner-confirm.** Cursor inspects/reports, pauses, owner types `proceed` before implementation.
- **Scope fences + STOP triggers** in every Cursor prompt.
- **Delivery reports saved under** `docs/phase-<n>-<sub>-<short-title>-report.md`.
- **Single consolidated commit per sub-phase.** Message format: `Phase <n>.<sub>: <short description>`.
- **Honest pushback.** No sycophancy. Owner prefers direct feedback.
- **Auditor/classifier outputs require human judgment.** Phase 6.1 surfaced systematic auditor over-scoring on §8.4 Option 3 samples. Treat model verdicts as signal, not truth.

## 4. Known Cursor quirks

- Cursor has skipped ordered tasks in multi-task prompts. Mitigation: number tasks, require explicit `proceed` tokens between them.
- Cursor's agent environment doesn't have Python on PATH — always specify `.\.venv\Scripts\python.exe`.
- PowerShell mangles `curl -d` JSON bodies; use `--data-binary "@file.json"`.
- Cursor's agent shell may not inherit ANTHROPIC_API_KEY from user env. `.env` at repo root is the reliable source (loaded via app/bootstrap_env.py with override=False).

## 5. Known issues

See `docs/known-issues.md` for current live issues. Newly logged 2026-04-21:
- Mountain-bike retrieval miss (Havasu Mountain Bike Association not surfacing)
- Tier 3 date hedging on temporal queries (context_builder date-injection gap)
- Tier 2 explicit-rec routing (should skip to Tier 3 for opinionated queries)

## 6. Deferred decisions (not blocking)

- Soft launch timing, monetization strategy, community seeding — owner hasn't decided.
- Router-level explicit-rec handling (skip Tier 2 → Tier 3) — architectural follow-up.
- context_builder date-awareness — ties to 6.4 session memory work or standalone later.
- Auditor variance in voice audits — dual-run on borderline samples is a future runner improvement.
- Admin nav consistency, generic 422 error message — Phase 8 candidates.

## 7. Where to find authoritative specs

- **HAVA_CONCIERGE_HANDOFF.md** (repo root) — full architectural spec, voice decisions, phase scopes, risks. Source of truth.
- **docs/known-issues.md** — live bug tracker.
- **docs/phase-*-report.md** — per-sub-phase delivery reports.
- **scripts/run_voice_audit.py** — reusable voice audit runner (uses prompts/voice_audit.txt).

## 8. Suggested opening moves (Phase 8 kickoff)

Phase 6 is closed; orient the next session around **Phase 8 pre-launch hardening** or housekeeping:

- **Plan a Phase 8 design conversation** — walk `HAVA_CONCIERGE_HANDOFF.md` §5 Phase 8 (seed verification, load testing, admin runbook, ToS, privacy review) and sequence work vs. soft launch.
- **Discuss soft launch strategy** — timing, surface area, and what “good enough” means before wider promotion (no code required).
- **Housekeeping** — archive or dedupe process artifacts (`docs/phase-*`, one-off prompts) so the repo stays navigable before Phase 8 execution work ramps up.
- **Continue wherever makes sense** — Claude will recommend from the above.
