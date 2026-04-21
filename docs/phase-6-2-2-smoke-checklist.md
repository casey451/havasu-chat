# Phase 6.2.2 — Manual smoke checklist (feedback thumbs)

Run against **production** after deploy, or **local** (`uvicorn` + `index.html`). Use a query that reliably hits **Tier 3** (open-ended; e.g. “What’s fun to do this weekend?” with mocks off, or any prompt your environment routes to `tier_used: "3"`).

---

## 1. Thumbs only on Tier 3

1. Send a **Tier 1**-style query (e.g. short greeting “Hi”) — assistant row should have **no** thumb row below the bubble.
2. Send a query that returns **Tier 2** if you can identify one in your environment — **no** thumbs.
3. Send a **Tier 3** query — confirm **two** 44×44 controls (👍 👎) appear **below** the grey bubble, **left-aligned** with the bubble.

---

## 2. DOM / metadata

1. Inspect the assistant **`.row.bot`** for the Tier 3 turn.
2. Confirm **`data-tier-used="3"`** and **`data-chat-log-id="<uuid>"`** on the **row** (not only on inner nodes).

---

## 3. POST payload (DevTools → Network)

1. Tap **👍**.
2. Find **`POST /api/chat/feedback`** — body must be `{"chat_log_id":"<same id>","signal":"positive"}`.
3. Response **200** — JSON `{"ok":true,"chat_log_id":"...","signal":"positive"}`.

---

## 4. UI lock after success

1. After a successful 👍, the up button should show **filled / primary** selected state; 👎 should look **dimmed**.
2. Tap **👍** again quickly — **no** second request (same selection ignored).
3. Tap **👎** — a **new** `POST` with `"signal":"negative"`; after **200**, 👎 is selected and 👍 dimmed.

---

## 5. Error path (no production data mutation)

1. In DevTools console, run a fetch with a **fake** id (or use curl):

   ```bash
   curl -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat/feedback" \
     -H "Content-Type: application/json" \
     --data-binary "{\"chat_log_id\":\"00000000-0000-0000-0000-000000000001\",\"signal\":\"positive\"}"
   ```

2. Expect **404** if that id does not exist — not required for UI test.

**UI error string:** Temporarily break the client (e.g. offline) or block the request — after a failed save, inline text **“Couldn't save that — try again”** (or server `error` / `message`) should appear under the thumbs and both buttons usable again for retry.

---

## 6. Validation (optional curl-only)

- Invalid body → **422** (same as Phase 6.2.1 smoke).

---

## 7. Regression

- **Welcome** chips and **calendar** still work.
- **User** bubbles still **right-aligned**; layout unchanged for **`.row.user`**.
