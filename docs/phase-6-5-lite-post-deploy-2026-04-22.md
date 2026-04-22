# Phase 6.5-lite — post-push / deploy / production smoke (2026-04-22)

## Commit and push

| Field | Value |
|--------|--------|
| **Commit** | `35194af` — `Phase 6.5-lite: local voice plumbing (empty, ready to grow)` |
| **Remote** | `main` pushed to `origin` (`a9dca4d..35194af`) |

Only Phase 6.5-lite–related paths were included in the commit; other untracked docs in the repo remained unstaged.

---

## After ~3 minutes (Railway wait)

### 1) Railway deployment status (CLI)

`railway deployment list` showed the latest **SUCCESS** as:

- **`cb1bd50f-a08c-4a99-946d-40fb02ed285a`** — **SUCCESS** — **2026-04-21 18:46:53 -07:00**

No newer deployment row appeared in the CLI after the push and wait (possible webhook delay, dashboard-only visibility, or deploy not yet listed). **Confirm in the Railway UI** that a deploy for **`35194af`** completed (or was triggered).

### 2) Local uvicorn on port 8765

`netstat` on **`:8765`**: **no listener** (nothing to stop).

### 3) Production smoke

**Request:** `POST https://havasu-chat-production.up.railway.app/api/chat`  

**Body:**

```json
{"query": "what should I do Saturday night", "session_id": "prod-smoke-65lite"}
```

**Results:**

| Check | Result |
|--------|--------|
| HTTP / JSON | OK, body parsed |
| `tier_used` | `"2"` |
| `response` | Normal concierge copy (e.g. Rock & Bowl / Saturday night) |
| Errors | None |
| `Local voice:` in API response | Not expected in the **public** JSON; that label lives only in Tier 3 internal `user_text`, and **`LOCAL_VOICE` is empty** in production |

---

## Summary

| Item | Result |
|------|--------|
| **Push** | Done — `35194af` on `main`. |
| **Railway (CLI)** | Latest listed SUCCESS unchanged; **verify new deploy in dashboard**. |
| **Port 8765** | Clear. |
| **Production smoke** | **PASS** — healthy JSON, tier 2, no regression symptoms. |
