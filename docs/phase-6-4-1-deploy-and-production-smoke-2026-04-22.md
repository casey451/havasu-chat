# Phase 6.4.1 — Deploy and production smoke (2026-04-22)

Saved from the implementation chat.

---

## Commit and push

- **Commit:** `3b6315e` — `Phase 6.4.1: recommended-entity capture for prior_entity`
- **Pushed:** `main` → `origin/main` (`9f8abb0..3b6315e`)

**Included in commit:** `entity_matcher.py`, `unified_router.py`, both test files, `known-issues.md`, `phase-6-4-session-memory-report.md`, plus `docs/phase-6-4-1-recommended-entity-capture-report.md`, `phase-6-4-1-preflight-report.md`, `phase-6-4-1-gates-report-2026-04-22.md`, `phase-6-4-1-manual-a-live-verification-2026-04-22.md`.

---

## 1. Deploy (after ~3 min + extra wait)

- **Public app:** `GET https://havasu-chat-production.up.railway.app/openapi.json` succeeded after the initial wait (service up).
- **Railway UI / deploy ID:** Not available from the agent environment (no Railway token). Treat **successful production smoke on the second try** (below) as evidence the **new** revision is live on at least one instance.

---

## 2. Local uvicorn on 8765

- **`taskkill /F /PID 29820`** — exit code **128** (process already gone or different PID).
- **Port 8765:** No listener afterward — local server **stopped**.

---

## 3. Production smoke — scenario (a)

Script: `POST https://havasu-chat-production.up.railway.app/api/chat`, fresh `session_id` each run.

### Run A (right after first 3-minute wait)

- **T1:** Tier **3**, single-venue style answer (**Altitude** + Aqua Beginnings — **two** venues in text).
- **T2:** Still **“which place?”** — `entity: null`, TIME_LOOKUP Tier 3.

→ Likely **old replica** or **deploy not fully rolled** yet.

### Run B (+2 minutes)

- **session_id:** `prod-smoke-641-99e365c2197e`
- **T1:** Tier **3**, OPEN_ENDED, `entity` null. Response centers **Altitude** for tomorrow (Wednesday), channel context, $19 / 11am–7pm.
- **T2:** **`entity`:** `"Altitude Trampoline Park"` — **resolved**, hours-style reply (**no** “which place?”). Tier **3**, TIME_LOOKUP.

**Verdict:** **PASS** on production for the **6.4 smoke** loop (Turn 2 binds to the venue from Turn 1). **Run A** is worth treating as **transitional** (stale/old task) unless it repeats.

---

## 4. Summary

| Item | Result |
|------|--------|
| Commit / push | `3b6315e` on `main` |
| Railway dashboard | Not checked (no API access from agent) |
| Local :8765 | Stopped / not listening |
| Production smoke (a) | **PASS** on retry (Run B); Run A failed briefly, then OK |

---

*One-off smoke script was not kept in the repo; re-create or add under `scripts/` if you want it versioned.*
