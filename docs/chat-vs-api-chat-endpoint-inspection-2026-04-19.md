# `/chat` vs `/api/chat` — endpoint inspection — 2026-04-19

**Purpose:** Confirm whether the live static UI’s `POST /chat` hits the Phase 2.3+ concierge (unified router / Tier 3) or a separate Track A path. **No** prompt changes; **two** production `curl` checks only.

---

## 1. Route registration (code)

**Both routes exist** on the same FastAPI app. `app/main.py` includes both routers (no prefix on either — paths are exactly as declared on handlers):

```118:121:app/main.py
app.include_router(chat_router)
app.include_router(concierge_chat_router)
app.include_router(admin_router)
app.include_router(programs_router)
```

| Path | Module | Handler | Pipeline |
|------|--------|---------|----------|
| **`POST /chat`** | `app/chat/router.py` | `chat()` → `_chat_inner()` | **Track A** — search, add-event, session state from `app.core.*`. **Does not** import or call `unified_router`. |
| **`POST /api/chat`** | `app/api/routes/chat.py` | `post_concierge_chat()` | **Concierge** — `unified.route(...)` (Tier 1, Tier 3, etc.). |

Concierge module documents the split (Track A UI vs Option B API path):

```1:12:app/api/routes/chat.py
"""Concierge unified-router HTTP API (Phase 2.3).

**Path (Option B, approved):** ``POST /api/chat`` — Track A's static UI still uses
``POST /chat`` with ``message`` + ``session_id``; mounting the concierge here avoids
collisions. **Intent:** keep ``/api/chat`` until Phase 3 is production-ready and the
frontend can migrate safely; then swap to unified ``POST /chat`` in a coordinated
cutover (handoff §5 Phase 2.3).
...
```

Handler wiring:

```28:46:app/api/routes/chat.py
@router.post("/api/chat", response_model=ConciergeChatResponse)
@limiter.limit("120/minute")
def post_concierge_chat(
    request: Request,
    payload: ConciergeChatRequest,
    db: Session = Depends(get_db),
) -> ConciergeChatResponse:
    """Run ``normalize → classify → …`` via :func:`unified_router.route`."""
    result = unified.route(payload.query, payload.session_id, db)
    return ConciergeChatResponse(
        response=result.response,
        mode=result.mode,
        sub_intent=result.sub_intent,
        entity=result.entity,
        tier_used=result.tier_used,
        latency_ms=result.latency_ms,
        llm_tokens_used=result.llm_tokens_used,
    )
```

**Request body shapes** (`app/schemas/chat.py`):

- **Track A** `POST /chat`: `ChatRequest` — `session_id` + **`message`**.
- **Concierge** `POST /api/chat`: `ConciergeChatRequest` — **`query`** + optional `session_id`.

---

## 2. Production comparison (same intent, two endpoints)

**Query intent:** phone number for Altitude.

### `POST https://havasu-chat-production.up.railway.app/chat`

**Body:** `{"session_id":"endpoint-check", "message":"what's the phone number for altitude?"}`

**Full JSON response:**

```json
{
  "response": "No altitude in the system yet. If you hear of one, add it here and help others find it — just tell me the details 👋",
  "intent": "SEARCH_EVENTS",
  "data": {
    "count": 0,
    "search": {
      "slots": {
        "date_range": null,
        "activity_family": null,
        "audience": null,
        "location_hint": null
      },
      "recent_utterances": ["what's the phone number for altitude?"],
      "last_result_set": {
        "ids": [],
        "query_signature": "what's the phone number for altitude?"
      },
      "listing_mode": false,
      "snapshot_stack": []
    }
  }
}
```

### `POST https://havasu-chat-production.up.railway.app/api/chat`

**Body:** `{"session_id":"endpoint-check", "query":"what's the phone number for altitude?"}`

**Full JSON response:**

```json
{
  "response": "Altitude Trampoline Park — Lake Havasu City: (928) 436-8316.",
  "mode": "ask",
  "sub_intent": "PHONE_LOOKUP",
  "entity": "Altitude Trampoline Park — Lake Havasu City",
  "tier_used": "1",
  "latency_ms": 25,
  "llm_tokens_used": null
}
```

**Comparison:** `/chat` routed the utterance as **event search**, returned **count 0**, and a generic “add it” message. `/api/chat` returned the **correct Tier 1** answer with **`tier_used` `"1"`** and concierge metadata.

---

## 3. Live frontend behavior

`app/static/index.html` uses **`fetch("/chat", …)`** with **`message`** (Track A contract). Therefore the **deployed web UI does not** call **`/api/chat`** and does **not** run the **unified concierge / Phase 3.2 Tier 3** pipeline for that UI path.

**Implication:** Markdown or Tier 3 tuning for production **web users** only matters after a **coordinated cutover** (e.g. point the static UI at `/api/chat` with the concierge request shape, or rewire `POST /chat` to `unified.route` as planned in the handoff).

---

## 4. Temp artifacts

Request JSON files used only for the two curls were removed from the working tree after capture.
