# Phase 3 prep — concierge data inference (archive)

Two assistant responses consolidated into one file.

---

## Report 1 — Full read-only inference pass (re-run)

**Production:** `https://web-production-bbe17.up.railway.app`  
**Scope:** read-only HTTP + git only — no seeds, no Railway DB/CLI, no writes.

### 1. Git — `origin/main` last 5 (after `git fetch origin main`)

1. `48e6fd6a82ad4ea78fe2d2d55bd242ba70ca4f21` — tests: Phase 2.4 — end-to-end integration tests for the concierge stack  
2. `f22b901752bfb806da347d13c135f0ce92804791` — chat: Phase 2.3 — POST /api/chat endpoint wiring unified router  
3. `a41d01f870570c7deda70b846d4f0063bfb57355` — docs: add Phase 2.2 implementation review note for handoff  
4. `c55d3ac99104fab54e12f9202ca8baffd57b2847` — chat: Phase 2.2 — unified router with two-stage classifier routing  
5. `05287cf592691ecf88ebfb2788ea00bc09ed5eae` — chat: Phase 2.1 — two-stage intent classifier (ask/contribute/correct/chat + sub-intents)

- **`48e6fd6`:** tip of `origin/main` (commit 1 above).  
- **`d03b6b2`:** `d03b6b20c5eb60eff0c8ce833e1dbe6c091ab116` — db: Phase 1.1 Alembic migrations (providers, field_history, programs, events). On `origin/main` as an **ancestor** of tip (`merge-base --is-ancestor d03b6b2 origin/main` succeeds) but **not** one of the five commits above (older).

### 2. `GET /events` (production)

**27** rows.

### 3. `POST /api/chat` — `entity` per nickname (production)

| Query | `entity` |
|--------|----------|
| a. `altitude` | `Altitude Trampoline Park — Lake Havasu City` |
| b. `sonics` | `Universal Gymnastics and All Star Cheer — Sonics` |
| c. `bmx` | `Lake Havasu City BMX` |
| d. `bowling alley` | `Havasu Lanes` |
| e. `iron wolf` | `Iron Wolf Golf & Country Club` |

All five non-null; strong signal that Phase 1.3 provider seeding is present and enrichment is working. HTTP cannot prove exactly 25 provider rows.

### 4. `POST /api/chat` — `"gymnastics for kids havasu"` (production)

- **`response`:** `Ask mode: intent=OPEN_ENDED, entity=none. Retrieval will be implemented in Phase 3.`  
- **`entity`:** `null`  
- **`tier_used`:** `placeholder`  

Nothing beyond the usual ask-mode + Phase 3 retrieval line.

### 5–6. Local DB (`python -c …`)

**Not run.** Only `WindowsApps\python.exe` (store stub) on PATH; no `py`, `uv`, `poetry`, or `conda` on PATH in that environment.

### Phase 3 data picture (inference only)

Production exposes **27** events; **five** canonical provider nicknames all enrich. Open-ended gymnastics query stays placeholder with **`entity: null`**. Programs, `field_history` “established” baselines, and event→provider linkage were **not** verified (no DB access; public API may not expose all DB fields).

---

## Report 2 — Markdown summary (“md please”)

# Phase 3 prep — read-only inference (Railway concierge data)

**Production:** `https://web-production-bbe17.up.railway.app`  
**Scope:** read-only HTTP + git only — no seeds, no Railway DB/CLI, no writes.

---

### 1. Git — `origin/main` (last 5, after `git fetch origin main`)

| # | SHA | Subject |
|---|-----|---------|
| 1 | `48e6fd6a82ad4ea78fe2d2d55bd242ba70ca4f21` | tests: Phase 2.4 — end-to-end integration tests for the concierge stack |
| 2 | `f22b901752bfb806da347d13c135f0ce92804791` | chat: Phase 2.3 — POST /api/chat endpoint wiring unified router |
| 3 | `a41d01f870570c7deda70b846d4f0063bfb57355` | docs: add Phase 2.2 implementation review note for handoff |
| 4 | `c55d3ac99104fab54e12f9202ca8baffd57b2847` | chat: Phase 2.2 — unified router with two-stage classifier routing |
| 5 | `05287cf592691ecf88ebfb2788ea00bc09ed5eae` | chat: Phase 2.1 — two-stage intent classifier (ask/contribute/correct/chat + sub-intents) |

- **`48e6fd6`:** tip of `origin/main` (row 1).
- **`d03b6b2`:** `d03b6b20c5eb60eff0c8ce833e1dbe6c091ab116` — *db: Phase 1.1 Alembic migrations (providers, field_history, programs, events)*. Present on `origin/main` as an **ancestor** of tip, **not** among the five commits above.

---

### 2. `GET /events` (production)

- **Count:** **27** events (JSON array length).

---

### 3. `POST /api/chat` — nickname → `entity` (production)

| Query | `entity` |
|-------|----------|
| `altitude` | `Altitude Trampoline Park — Lake Havasu City` |
| `sonics` | `Universal Gymnastics and All Star Cheer — Sonics` |
| `bmx` | `Lake Havasu City BMX` |
| `bowling alley` | `Havasu Lanes` |
| `iron wolf` | `Iron Wolf Golf & Country Club` |

**Inference:** 5/5 non-null entities; consistent with Phase 1.3 provider data + enrichment on production. HTTP cannot prove exactly 25 provider rows.

---

### 4. `POST /api/chat` — `"gymnastics for kids havasu"` (production)

| Field | Value |
|-------|--------|
| `response` | `Ask mode: intent=OPEN_ENDED, entity=none. Retrieval will be implemented in Phase 3.` |
| `entity` | `null` |
| `tier_used` | `placeholder` |

No extra wording beyond the standard ask-mode + Phase 3 retrieval line.

---

### 5–6. Local DB counts (`Program`, `Provider`, `FieldHistory`)

**Not run** in that Cursor environment: only the Windows Store `python` stub on PATH; no working `py` / `uv` / `poetry` / `conda` detected.

Run the two `python -c "..."` snippets from the repo root with a real venv and `DATABASE_URL` for local reference numbers.

---

### Phase 3 checklist (what this pass did / did not show)

| Need | This pass |
|------|-----------|
| Providers (via enrichment) | Strong positive (5 nicknames) |
| Programs / concierge fields | Not verified (no local DB there; no prod DB) |
| Events | 27 via API; provider linkage not inferred from API shape alone |
| `field_history` baselines | Not verified (no DB) |
