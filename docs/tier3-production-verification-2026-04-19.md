# Tier 3 production verification — 2026-04-19

Summary of push, deploy wait, and **one** controlled `POST /api/chat` to Railway production after Phase 3.2.

---

## Step 1 — Push to Railway

| Item | Detail |
|------|--------|
| Command | `git push origin main` |
| Result | Success (exit code 0) |
| Commit range pushed | `48e6fd6..8819059` |
| Commits in range | `1066540` — Phase 3.1 (Tier 1 template in unified router); `8819059` — Phase 3.2 (Tier 3 LLM + prompt caching) |
| Remote | `https://github.com/casey451/havasu-chat.git` → `main` |

---

## Step 2 — Deploy wait / health

| Item | Detail |
|------|--------|
| Railway dashboard | Not checked (no dashboard access from agent environment). |
| Method | Polled `GET https://havasu-chat-production.up.railway.app/health` immediately after push, then every **60 seconds** for **3 × 60s** (three additional polls). |
| Deploy flicker | None observed in this window (all requests succeeded). |
| HTTP | **200** on every poll. |
| Health JSON note | Production `/health` returns **`event_count`**, not `response_count` (see `app/main.py`). |
| `event_count` | **43** on every poll (stable). |
| Gate for Step 3 | ≥3 minutes of timed waits **and** 200 **and** count 43 — satisfied using `event_count`. |

---

## Step 3 — One Tier 3 production call

**Request** (`Content-Type: application/json`):

```json
{
  "query": "what's a good place for my 6-year-old to burn off some energy?",
  "session_id": "tier3-first-real-call"
}
```

**Endpoint:** `POST https://havasu-chat-production.up.railway.app/api/chat`

**Full response body (JSON):**

```json
{
  "response": "Altitude Trampoline Park is perfect for that—it's got open jump sessions throughout the week, and a 90-minute session runs $19. Flips for Fun Gymnastics is another great option if they're into that kind of activity, open 3–8pm weekdays.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": null,
  "tier_used": "3",
  "latency_ms": 1695,
  "llm_tokens_used": 1719
}
```

| Field | Value | Notes |
|-------|-------|--------|
| `tier_used` | `"3"` | **Not** `"placeholder"` — Phase 3.2 behavior confirmed for this call. |
| `llm_tokens_used` | `1719` | Non-null integer. |
| HTTP | 200 | |
| Wall-clock (curl `time_total`) | ~**1.93 s** | `TIME_TOTAL_SEC: 1.928307` |

### Response copy — qualitative checks

| Criterion | Assessment |
|-----------|------------|
| Leads with the answer, not setup | **Yes** — opens with Altitude as the primary recommendation. |
| Under 4 sentences | **Yes** — two sentences. |
| Names specific providers (seeded-style) | **Yes** — Altitude Trampoline Park; Flips for Fun Gymnastics. |
| Ends without a follow-up question | **Yes** — ends on “weekdays.” with no trailing question. |

### Cleanup

- Request file `tier3_test.json` and capture `tier3_response.json` were **deleted** after reporting (no extra production queries).

---

## Stop condition (not triggered)

If `tier_used` had still been `"placeholder"`, the instruction was to **stop**, not retry, and diagnose deploy/code pickup. **`tier_used` was `"3"`** — no stop.

---

## Optional follow-up for future runs

Consider exposing **`git_sha`** (or build id) on `/health` or `/version` so deploy verification does not rely on timing or absence of errors alone.
