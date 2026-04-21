# Havasu Chat — Session Resume (2026-04-22)

**Purpose:** Start-of-new-chat handoff. Read this file first, then HAVASU_CHAT_CONCIERGE_HANDOFF.md for full architectural spec.

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

- **Last commit on main:** `cf867b8` docs: session resume doc for 2026-04-22
- **Tests:** 681 passing
- **Working tree:** clean, main in sync with origin/main
- **Production:** healthy

**Phase 6.1 — recent `main` history** (newest first; omits transient revert/duplicate commits around the clean 6.1.3 artifact land):

```text
cf867b8 docs: session resume doc for 2026-04-22
4c5d4b3 docs: log Phase 6.1 deferred items
10b251b Phase 6.1.4: voice fixes for HOURS, Tier 3 §8.2, Tier 2 explicit-rec
c899bfb Phase 6.1.3: voice audit execution + report
b5f6be1 docs: archive Phase 6.1.1–6.1.2 process artifacts
a7be089 Phase 6.1.2: voice audit runner + dry-run proof
b1eb5b4 Phase 6.1.1: establish voice_audit.txt prompt file
```

### Phase status

**Shipped:**
- Phase 1 — Data model, seed data ✅
- Phase 2 — Chat API, classifier, Tier 3, ChatLog, rate limiter ✅
- Phase 3.1–3.8 — Tier 1 templates, routing, gap handling ✅
- Phase 4.1–4.7 — Tier 2 retrieval-then-generate ✅
- Phase 5.1–5.6 — Contribute mode ✅
- Phase 6.2 — Feedback loop end-to-end ✅
- **Phase 6.1 — Voice audit (NEW: closed 2026-04-21)** ✅
  - 6.1.1 prompts/voice_audit.txt established
  - 6.1.2 scripts/run_voice_audit.py runner built with 55-sample fixture
  - 6.1.3 paid audit executed: 51 PASS / 1 MINOR / 3 FAIL / 0 ERROR (~$0.17 spend)
  - 6.1.4 voice fixes shipped: t1-HOURS-03 cleared; t3-01 + t3-24 deferred at root; t3-25 rejected as auditor over-score

**Remaining in Phase 6:**
- 6.3 Onboarding first-turn (visiting/local + kids quick-tap)
- 6.4 Session memory (age/location hints, prior entity recall, 30-min idle)
- 6.5 Local-voice content (OWNER TASK: 20–30 editorial blurbs)

**Post-Phase 6:**
- Phase 8 Pre-launch hardening: seed verification, load testing, admin runbook, ToS, privacy review
- Deferred: correction flow (reads field_history baseline)
- Deferred: cost optimization pass (after 2–4 weeks real traffic)

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

- **HAVASU_CHAT_CONCIERGE_HANDOFF.md** (repo root) — full architectural spec, voice decisions, phase scopes, risks. Source of truth.
- **docs/known-issues.md** — live bug tracker.
- **docs/phase-*-report.md** — per-sub-phase delivery reports.
- **scripts/run_voice_audit.py** — reusable voice audit runner (uses prompts/voice_audit.txt).

## 8. Suggested opening moves

- "Plan Phase 6.3 onboarding" — UX work, moderate scope, self-contained.
- "Plan Phase 6.4 session memory" — more involved; could combine with context_builder date-injection fix (resolves t3-01 known-issue).
- "Discuss 6.5 local-voice content" — owner writing task, no code.
- "Discuss soft launch / monetization strategy" — no build.
- "Continue wherever makes sense" — Claude will recommend.
