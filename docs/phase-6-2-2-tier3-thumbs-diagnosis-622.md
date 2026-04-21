# Phase 6.2.2 — Tier 3 thumbs not rendering (diagnosis)

**Date:** 2026-04-20  
**Scope:** Read-only investigation (Task 1). No code changes in this phase.

## Summary

Production `POST /api/chat` was exercised with an open-ended Tier 3 style query. The JSON body returned **`tier_used` as the string `"3"`** and a **non-empty `chat_log_id` (UUID string)**. The static UI gates thumb attachment on **`data.tier_used === "3"`** and a truthy **`data.chat_log_id`**. For that sample response, **the wire format matches the frontend expectation**; missing thumbs are **not** explained by a response-shape mismatch in that reproduction.

## 1. Production curl (verbatim response body)

Request (PowerShell-friendly):

```powershell
Set-Location <repo>
'{"session_id":"diagnose-622-001","query":"whats fun for kids this weekend"}' |
  Out-File -Encoding utf8 -NoNewline .\diag.json
curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
  -H "Content-Type: application/json" `
  --data-binary "@diag.json"
```

**Full JSON response (verbatim, single line as returned):**

```json
{"response":"Altitude Trampoline Park's open this weekend — 90-minute jump sessions are $19 and they're open 9am–9pm Saturday, 11am–7pm Sunday. If your kids need something more structured, Flips for Fun Gymnastics opens at 3pm weekdays, or check out the dance studios (Arizona Coast Performing Arts, Ballet Havasu, Footlite) for classes.","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"3","latency_ms":3124,"llm_tokens_used":2962,"chat_log_id":"2fb91062-5283-4473-be29-e3087488ace7"}
```

## 2. Field notes (from that response)

| Field | Notes |
|--------|--------|
| **`tier_used`** | Present. JSON **string** `"3"` (not a bare numeric `3`). |
| **`chat_log_id`** | Present, non-empty, truthy in JavaScript. Format: UUID string (e.g. `2fb91062-5283-4473-be29-e3087488ace7`). |
| **Tier 3 signaling** | `mode` / `sub_intent` / response prose are consistent with Tier 3; nothing in the payload contradicts the UI’s Tier 3 thumb gate beyond the gate itself. |

## 3. Frontend references (`app/static/index.html`)

| Concern | Location (line numbers) |
|----------|-------------------------|
| `tier_used === "3"` (strict string check) | **748** |
| `chat_log_id` read / `data-chat-log-id` | **738–741** |
| `data-tier-used` set / removed | **743–746** |
| `attachFeedbackThumbs` **called** | **749** |
| `attachFeedbackThumbs` **defined**; early return if no id or existing `.msg-feedback` | **439–440** |

Relevant snippet:

```javascript
if (data.chat_log_id != null && data.chat_log_id !== "") {
  pendingRow.setAttribute("data-chat-log-id", String(data.chat_log_id));
} else {
  pendingRow.removeAttribute("data-chat-log-id");
}
if (data.tier_used != null && data.tier_used !== "") {
  pendingRow.setAttribute("data-tier-used", String(data.tier_used));
} else {
  pendingRow.removeAttribute("data-tier-used");
}
if (data.tier_used === "3" && data.chat_log_id) {
  attachFeedbackThumbs(pendingRow, String(data.chat_log_id));
}
```

## 4. Cross-reference: API vs UI

- **`tier_used`:** API returned string `"3"` → `data.tier_used === "3"` is **true**.
- **`chat_log_id`:** API returned a non-empty string → **`data.chat_log_id` is truthy** and `String(data.chat_log_id)` is valid for feedback.

**No mismatch** for this reproduction.

**Fragility (not observed in this sample):** If `tier_used` were ever JSON **number** `3`, then `String(data.tier_used)` would still yield `"3"` on the `data-tier-used` attribute, but **`data.tier_used === "3"` would be false**, so thumbs would not attach. Current `ConciergeChatResponse` uses `tier_used: str` in `app/schemas/chat.py`; the live sample matched that.

## 5. Hypothesis

- **Gate line:** Thumbs are only attached when **line 748** passes (`data.tier_used === "3" && data.chat_log_id`).
- **For the captured production response, line 748 should pass** and **line 749** should run; the response body alone does not explain missing thumbs.
- **If the owner still saw no thumbs with an equivalent payload**, likely causes include: **stale/cached `index.html`**, a **JavaScript error** before the success handler completes, a **different build/tab**, or a **different historical response** (e.g. missing `chat_log_id` or non-string `tier_used`).

## 6. Stop / next steps

- **STOP (diagnosis only):** Response shape for this curl is correct; treat render/cache/runtime as the next investigation axis, not API field naming for this sample.
- **Next (after owner confirmation):** Verify served `index.html` in production matches repo; capture owner HAR/console; optionally harden line 748 to accept numeric `3` if that ever appears on the wire.
