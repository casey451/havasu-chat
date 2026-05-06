# chat_route

`app/api/routes/chat.py` (~119 lines)

## Purpose

Sole HTTP entry point for the unified concierge: `POST /api/chat` plus two adjacent endpoints (`/api/chat/onboarding`, `/api/chat/feedback`). The handler is intentionally thin — request validation via Pydantic, rate-limit decoration, dispatch to `app.chat.unified_router.route`, and a background-task hook that schedules Tier 3 mention scanning. All the chat logic lives downstream; this file is the FastAPI seam between the static-UI POST and the tier 1/2/3 pipeline.

The Phase 2.3 mount path is `/api/chat` (not `/chat`) — Track A's static UI still uses `POST /chat` with a different request shape, so the concierge mounts at `/api/chat` to avoid collision. The intent (per the module docstring) is to swap to `POST /chat` in a coordinated cutover once Phase 3 is production-ready.

## Public surface

**`router: APIRouter`** — Sole export. Tagged `concierge`. No prefix; the route paths in this file include `/api/...` literally. Mounted from `app/main.py` via `app.include_router(concierge_chat_router)`.

There is no Python callable API beyond the HTTP handlers.

## Route inventory

| Route | Method | Rate limit | Schema | Purpose |
|---|---|---|---|---|
| `/api/chat` | POST | **120/minute** | `ConciergeChatRequest` → `ConciergeChatResponse` | Unified concierge entry. Calls `unified_router.route(query, session_id, db)`. |
| `/api/chat/onboarding` | POST | **120/minute** | `ChatOnboardingRequest` → `ChatOnboardingResponse` | Stores Phase 6.3 onboarding hints (`visitor_status`, `has_kids`) on the in-memory session. |
| `/api/chat/feedback` | POST | (none) | `ChatFeedbackRequest` → `ChatFeedbackResponse` | Sets `chat_logs.feedback_signal` on a prior turn (Phase 6.2.1 thumb signal). |

The 120/min limit is shared with Track A's `POST /chat`. The module docstring calls out the deliberate divergence from the Phase 2.3 prompt (which referenced `POST /events`'s 5/min): the concierge owner kept 120/min for conversational bursts. The inline comment at the decorator records the rationale.

## Inputs and outputs

**`POST /api/chat` request — `ConciergeChatRequest`** (see `docs/components/schema_chat.md`): `query: str`, `session_id: str`. The request goes through FastAPI's standard validation; failures are formatted by `app/core/event_quality.friendly_errors` (installed in `app/main.py`).

**`POST /api/chat` response — `ConciergeChatResponse`**: `response`, `mode`, `sub_intent`, `entity`, `tier_used`, `latency_ms`, `llm_tokens_used`, `chat_log_id`. Fields are populated from `unified_router.route`'s named-tuple-shaped result.

**`POST /api/chat/onboarding`** — Body has optional `visitor_status` and `has_kids`; only set keys are written into `get_session(session_id)["onboarding_hints"]`. Returns the merged hint state for the session. The session store is in-memory (`app/core/session.py`).

**`POST /api/chat/feedback`** — Body has `chat_log_id` and `signal`. Sets `ChatLog.feedback_signal` and commits. Returns 404 JSON when the chat log row is missing (returns a `JSONResponse` rather than raising `HTTPException`, so the response shape stays JSON for the JS client).

## Internal structure

**`post_concierge_chat`** is a single linear function:

1. `unified.route(payload.query, payload.session_id, db)` — does all the work. The returned `result` carries every field the response needs plus a `chat_log_id` and a `tier_used` label.
2. **Background task hook (Tier 3 only).** When `result.tier_used == "3"` and the chat-log row was successfully written, schedule `scan_and_save_mentions(chat_log_id, response_text, SessionLocal)` via `BackgroundTasks`. The mention scan reads the assistant's reply (Tier 3 text) and seeds rows in `llm_mentioned_entities` for admin review. Lower tiers (1, 2) skip this — the deterministic / parsed-search paths don't generate the kind of free-text that needs scanning.
3. **Build the response model** field-for-field from `result`.

`post_chat_onboarding` is two writes plus a structured log line; `post_chat_feedback` is a `db.get` + assignment + commit + structured log line. No helpers; nothing complex enough to factor out.

## Conventions

**Single dispatch site.** Every concierge call goes through `unified.route`. Tier-specific handlers live in `app/chat/tier{1,2,3}_*.py`; this route doesn't know about them directly. Adding a "skip Tier 2 in some cases" knob belongs in the unified router, not here.

**Background mention scan uses `SessionLocal`, not request `db`.** The request-scoped session closes when the response returns; the background task needs its own session factory. Same pattern as the admin promote/enrich handlers.

**`120/minute` is intentional, not a port.** The decorator carries an inline comment explaining why it diverges from Phase 2.3's stated 5/minute. If a reviewer flags the number, the comment + module docstring are the authoritative answer.

**Onboarding writes only set keys.** A request that omits `has_kids` does not clear it. The form on the client posts each step independently, so partial writes are the correct semantics.

**Feedback returns `JSONResponse(404)` not `HTTPException`.** The chat client expects a JSON envelope on every response; `HTTPException` would still work via FastAPI's exception handler, but the route handles the not-found case explicitly to keep the body shape predictable.

## Known limitations and design notes

**No streaming.** Responses are full assistant turns; there is no SSE or WebSocket path. If streaming is added, this file is the natural seam — but `unified_router.route` would need to yield rather than return, which is a larger refactor.

**No request-id / trace propagation.** The route doesn't read incoming `X-Request-ID` or similar; structured-log lines rely on Python `logging` and the chat-log row's `id` for correlation.

**Mention scan is best-effort.** `BackgroundTasks` runs after the response returns. If the worker process restarts mid-task, the scan is lost; no retry. Acceptable: the operator queue surfaces unreviewed mentions, and future Tier 3 turns will re-seed.

**Chat-log persistence is the unified router's responsibility, not this route's.** `result.chat_log_id` is populated by `unified_router.route` calling `app/db/chat_logging.log_unified_route`. The route only reads the id for the response and the mention-scan dispatch.

**Onboarding hint store is in-memory (single-worker).** Multi-worker uvicorn would partition the hints; not currently a deployment shape used in production. See `docs/components/session.md`.

**Path is `/api/chat` until Phase 3 cutover.** The intent recorded in the module docstring is to migrate to unified `POST /chat` once the Track A static UI is retired or migrated. This route would change paths at that point.

## Configuration

No environment configuration of its own. The slowapi limiter inherits `RATE_LIMIT_DISABLED` from `app/core/rate_limit.py` (test isolation).

## Related

**Direct callers:** `app/main.py` mounts the router. The static UI (`app/static/js/chat.js`) calls `POST /api/chat`, `POST /api/chat/onboarding`, and `POST /api/chat/feedback` from the browser.

**Direct dependencies:**

- `app/chat/unified_router.py` — `unified.route` (the work).
- `app/contrib/mention_scanner.py` — `scan_and_save_mentions` (Tier 3 background task).
- `app/core/rate_limit.py` — shared `limiter` instance.
- `app/core/session.py` — in-memory `get_session` for onboarding hints.
- `app/db/database.py` — `SessionLocal` (background-task factory) and `get_db` (request-scoped session).
- `app/db/models.py` — `ChatLog` (feedback writes).
- `app/schemas/chat.py` — request/response Pydantic models.

**Cross-references:**

- `docs/components/unified_router.md` — the dispatch target; the actual chat work.
- `docs/components/schema_chat.md` — the request/response field shapes.
- `docs/components/rate_limit.md` — the shared limiter and its disable flag.
- `docs/components/mention_scanner.md` — the Tier 3 background task.
- `docs/components/chat_logging.md` — `log_unified_route`, where `chat_log_id` is born.
- `docs/maintainability/http_api.md` — full HTTP API surface (this route alongside the others).
