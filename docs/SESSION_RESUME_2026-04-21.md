# Havasu Chat — Session Resume (2026-04-21)

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

## 2. Current state (top of session)

- **Last commit on main:** `a1a0a6d1f20ec1e0b94b3d974445a9b786a4d16f` docs: add phase 6.2.3 post-ship delivery reports
- **Tests:** 679 passing
- **Working tree:** clean, main in sync with origin/main
- **Production:** healthy

### Phase status

**Shipped:**
- Phase 1 — Data model, seed data ✅
- Phase 2 — Chat API, classifier, Tier 3, ChatLog, rate limiter ✅
- Phase 3.1–3.8 — Tier 1 templates, routing, gap handling ✅
- Phase 4.1–4.7 — Tier 2 retrieval-then-generate (shipped before Contribute per re-plan) ✅
- Phase 5.1–5.6 — Contribute mode (data model, URL/Places, admin review, user form, mentions, categories/hours) ✅
- Phase 6.2 — Feedback loop end-to-end ✅
  - 6.2.1 backend: POST /api/chat/feedback
  - 6.2.2 frontend: 👍/👎 on Tier 3 responses
  - 6.2.3 admin view: /admin/feedback with window filter, summary, recent negatives

**Remaining in Phase 6:**
- 6.1 Voice audit (small, self-contained — recommended next)
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

## 4. Known Cursor quirks

- Cursor has skipped ordered tasks in multi-task prompts. Mitigation: number tasks, require explicit `proceed` tokens between them.
- Cursor's agent environment doesn't have Python on PATH — always specify `.\.venv\Scripts\python.exe`.
- PowerShell mangles `curl -d` JSON bodies; use `--data-binary "@file.json"`.

## 5. Known issues

See `docs/known-issues.md` for current live issues. Tier 3 thumbs render bug was resolved 2026-04-21.

## 6. Deferred decisions (not blocking)

- Soft launch timing, monetization strategy, community seeding — owner hasn't decided.
- Admin nav consistency (Feedback link only in core nav, not in sibling `_nav_shell` helpers) — low priority cleanup.
- Generic 422 error message from global validation handler says "Some event details are not valid" on every endpoint including feedback — minor UX papercut, Phase 8 hardening candidate.

## 7. Where to find authoritative specs

- **HAVA_CONCIERGE_HANDOFF.md** (repo root) — full architectural spec, voice decisions, phase scopes, risks. Source of truth for anything this resume doc doesn't cover.
- **docs/known-issues.md** — live bug tracker.
- **docs/phase-*-report.md** — per-sub-phase delivery reports.

## 8. Suggested opening moves

- "Plan Phase 6.1 voice audit" — smallest next piece.
- "Plan Phase 6.3 onboarding" — UX work.
- "Discuss soft launch / monetization strategy" — no build, just thinking.
- "Continue wherever makes sense" — Claude will recommend.
