# schema_chat

`app/schemas/chat.py` (~58 lines)

## Purpose

Pydantic **request/response models** for **`app/api/routes/chat.py`**: unified concierge **`POST /api/chat`**, onboarding hints, and Tier-3 thumb feedback. Keeps the HTTP boundary aligned with **`app.chat.unified_router.route`** return shape and **`chat_logs`** feedback updates.

## Public surface

### `ConciergeChatRequest`

- **`query: str`** — **`Field(min_length=1)`** — non-empty user message.
- **`session_id: str | None`** — optional client-supplied session key for analytics + session memory.

**Consumed by:** **`POST /api/chat`** (`response_model=ConciergeChatResponse`).

### `ConciergeChatResponse`

- **`response: str`** — assistant text.
- **`mode: str`**, **`sub_intent: str | None`**, **`entity: str | None`** — classifier / enrichment snapshot.
- **`tier_used: str`**, **`latency_ms: int`**
- **`llm_tokens_used: int | None`**
- **`chat_log_id: str | None`** — UUID string when **`log_unified_route`** persisted.

**Produced by:** unified-router wrapper in **`chat.py`** (manual construction from **`route()`** result).

### `ChatFeedbackRequest`

- **`chat_log_id: str`** — **`min_length=1`** — targets **`chat_logs.id`**.
- **`signal: Literal["positive", "negative"]`**

**Consumed by:** **`POST /api/chat/feedback`**.

### `ChatFeedbackResponse`

- **`ok: Literal[True]`**, **`chat_log_id: str`**, **`signal: str`**

**Produced by:** feedback route on success.

### `ChatOnboardingRequest`

- **`session_id: str`** — **`min_length=1`**
- **`visitor_status: Literal["local", "visiting"] | None`**
- **`has_kids: bool | None`**

**`@model_validator(mode="after")`** — **`at_least_one_field`**: raises **`ValueError`** if both **`visitor_status`** and **`has_kids`** are **`None`**.

**Consumed by:** **`POST /api/chat/onboarding`**.

### `ChatOnboardingResponse`

- **`ok: Literal[True] = True`** (constant default)
- Echo fields: **`visitor_status`**, **`has_kids`** (optional mirrors)

**Produced by:** onboarding route.

## Inputs and outputs

All models are **JSON-serializable** Pydantic v2 **`BaseModel`** instances suitable for FastAPI **`response_model`** and OpenAPI generation.

**Validation errors** on **`ConciergeChatRequest`** surface through FastAPI’s **`RequestValidationError`** handler (**`app.main`** → **`event_quality.friendly_errors`** for query-field failures).

## Internal structure

Thin file: **no shared base class** across chat models. Only **`ChatOnboardingRequest`** carries a **`model_validator`**; others rely on **`Field`** / **`Literal`** constraints only.

## Conventions

**Literal unions encode closed enums** — adding a new feedback signal requires editing **`ChatFeedbackRequest`** and any clients.

**`ConciergeChatResponse` is hand-built in the route** — not **`model_validate`** from the router dataclass; field names must stay aligned with **`unified_router`** manually.

## Known limitations and design notes

**No server-side max length on `query`.** Only **`min_length=1`**; extremely large payloads are constrained by HTTP limits / infra, not this schema.

**Onboarding session persistence** lives outside this module (**`app.core.session`**); schemas only describe the JSON contract.

## Configuration

None.

## Related

**Direct consumers:**

- **`app/api/routes/chat.py`** — all classes imported and wired to routes.

**Cross-references:**

- **`docs/components/unified_router.md`** — pipeline behind **`ConciergeChatResponse`** fields.
- **`docs/components/event_quality.md`** — validation-error UX for **`ConciergeChatRequest`**.
- **`scripts/run_query_battery.py`** — documents **`ConciergeChatResponse`** field expectations in header comment.
