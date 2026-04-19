# Phase 2.3 — implementation review (for Claude)

Summary of the **POST /chat API** work (Phase 2.3 — concierge HTTP entrypoint). Full suite at time of implementation: **336 tests passed** (+5 from `tests/test_api_chat.py`).

---

## Phase 2.3 done

### Path: `POST /api/chat` (not `POST /chat`)

Track A’s `app/static/index.html` still calls **`POST /chat`** with `{ session_id, message }`. Registering a second `POST /chat` would collide or break the UI. The concierge endpoint is therefore **`POST /api/chat`** with `{ query, session_id? }`. This is documented in `app/api/routes/chat.py`.

If the product later needs the public URL to be exactly **`/chat`**, that requires a coordinated move (e.g. Track A under `/legacy/chat` or a versioned path) without breaking the static client.

---

## Added / updated

| Item | Role |
|------|------|
| `app/api/__init__.py`, `app/api/routes/__init__.py` | Package layout |
| `app/api/routes/chat.py` | `post_concierge_chat` → `unified_router.route`, **`@limiter.limit("120/minute")`**, `Depends(get_db)` |
| `app/main.py` | `include_router(concierge_chat_router)` after `chat_router` |
| `app/schemas/chat.py` | **`ConciergeChatRequest`** (`query`, optional `session_id`), **`ConciergeChatResponse`** (matches unified router fields). **Track A `ChatRequest` / `ChatResponse` unchanged** (extend-only, no replacement). |

---

## Tests (`tests/test_api_chat.py`, 5)

- 200 + expected body keys for concierge responses
- `session_id: null` and omitted `session_id`
- Ask-style query → `mode == "ask"`
- Empty `query` → 422
- **`POST /chat`** (Track A) still returns shape `response`, `intent`, `data`

---

## Handoff alignment notes

- **§3.10 / logging:** `unified_router.route()` already writes `chat_logs` via `log_unified_route`; the HTTP layer does not duplicate logging.
- **§3.11 / failures:** Graceful copy and logging remain inside `route()`; the API returns the same JSON body the router produced.
- **§5 Phase 2.3** describes request/response as `query` + optional `session_id` and structured response fields — implemented on **`/api/chat`** due to path collision with Track A.
- **§7:** Reused existing `limiter`, `get_db`, and unified router; did not modify Track A `app/chat/router.py`.

---

## Suite

**336 passed** (previously 331 + unified router tests), **no regressions** reported at implementation time.

---

*Generated from the assistant Phase 2.3 checkpoint message.*
