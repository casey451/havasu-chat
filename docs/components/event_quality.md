# event_quality

`app/core/event_quality.py` (~38 lines)

## Purpose

Pretty-prints FastAPI `RequestValidationError` payloads for end-user display. The unified chat endpoint (`POST /api/chat`) uses `ConciergeChatRequest`; if a request body fails Pydantic validation, FastAPI's default handler emits a verbose machine-shaped error (loc/type/ctx/msg). `event_quality.friendly_errors` translates that into a single human sentence — typically "That request didn't parse — the 'query' field is required and can't be empty." for missing-query cases, and the underlying `ValueError` message for content-validation failures.

The module shrunk dramatically in Slice 21 (Backlog #7 close, `9020b2d`). Pre-Slice-21 it had ~265 lines covering legacy `/chat` route handling, contribution-shaped form normalization, and various helpers. Post-Slice-21 it's a focused 38-line helper with three exported names.

## Public surface

**`CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE: str`** — The canonical user-facing message when a chat request body fails the `query` field validation. Hard-coded as a module constant so tests can assert against it without duplicating the literal.

**`friendly_errors(errors: list[dict[str, Any]]) -> str`** — Translates a FastAPI validation error list into a single message. Three branches:

1. If any error's `loc` targets the `query` field (either as `('query',)` or as `('body', 'query')`): return the canonical chat-validation message.
2. Else, scan errors for an inner `ValueError` (e.g., a Pydantic `field_validator` raising) — return its message.
3. Else, scan for a string error message starting with `"Value error, "` (alternate form) — return the trimmed message.
4. Fallback: `"Some event details are not valid. Please check and try again."`

**`_errors_touch_concierge_query_field(errors: list[dict[str, Any]]) -> bool`** — Internal helper but exported (no underscore-prefix removal in Slice 21 because tests reference it). Returns `True` iff any error's `loc` points at the `query` field at the body root.

## Inputs and outputs

**Input.** A FastAPI/Pydantic-shaped error list — each entry is a dict with `loc` (path tuple), `msg` (string), `type` (string), and sometimes `ctx` (dict containing the original `error` object).

**Output.** A single string suitable for direct user display. Never empty; always has a fallback.

## Internal structure

`friendly_errors` is a four-step linear scan with early returns:

1. **Concierge-query branch.** `_errors_touch_concierge_query_field(errors)` — if any error targets `query` field, return the canonical chat message. This is checked first because chat is the highest-volume request type.
2. **Inner-ValueError branch.** Iterate; for each error, check `ctx['error']` if present. If it's a `ValueError`, return `str(error)`. This is the path for custom `field_validator` raises in Pydantic v2.
3. **String-prefix branch.** Iterate; for each error, check `msg`. If it starts with `"Value error, "`, return the message with the prefix stripped. This is the path for older Pydantic error shapes.
4. **Fallback.** Return the canonical fallback string.

`_errors_touch_concierge_query_field` iterates errors, checks `loc[-1] == "query"`, and accepts either a one-element loc (`('query',)`) or a body-shaped loc (`('body', 'query')`). The second form is what FastAPI produces; the first is what `model_validate` produces in tests that bypass FastAPI's body parsing.

## Conventions

**Loc-shape duality.** `_errors_touch_concierge_query_field` deliberately accepts both `('query',)` and `('body', 'query')` shapes because tests sometimes call validation directly on the model and sometimes through FastAPI's request-body machinery. Both shapes are the same logical "query field at root."

**Hard-coded canonical message.** The `CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE` constant exists so tests can compare without duplicating the literal. If the message changes, both the constant and any tests asserting against it need updating in the same commit.

**Fallback is generic.** When neither the chat-query path nor a `ValueError` path matches, the user gets a generic "details are not valid" message. Acceptable because this fallback is rare in practice (most validation errors are query-field or `ValueError`-typed).

**No logging.** `friendly_errors` is pure — no IO, no side effects. The validation-error handler in `app/main.py` is responsible for any logging if observability of error rates is desired. Currently no logging is wired.

## Configuration

No environment configuration. Pure Python helpers.

## Known limitations and design notes

**Single canonical chat message.** Every chat-request validation failure produces the same message regardless of WHY the field failed (missing, empty string, wrong type). Acceptable because the field is a free-text query — distinguishing "missing" from "empty" doesn't help the user act differently.

**Fallback is generic.** If a non-query, non-ValueError validation error reaches `friendly_errors`, the user sees a generic message that's not particularly informative. Acceptable rarity makes this not worth specializing.

**`_errors_touch_concierge_query_field` is exported despite the underscore.** Tests reference it directly. The convention "leading underscore = private" is violated here, but renaming would break tests. Documented exception.

**Slice 21 pruning rationale.** Pre-Slice-21 the module had 14 symbols including form-handling helpers (`apply_user_reply_to_field`, `build_pending_review_create`, etc.) inherited from the legacy `/chat` router. Post-H1 those were dead; Slice 21 (`9020b2d`) trimmed them, leaving only the live request-validation surface. See `docs/BACKLOG.md` Backlog #7 closure paragraph for the per-symbol audit.

**No internationalization.** Messages are English-only and not parameterized. If Hava ever adds a non-English chat surface, this helper would need to be extended.

## Related

**Direct callers:**

- `app/main.py` — the `RequestValidationError` exception handler at line 518 calls `friendly_errors` to produce the user-visible response body. Sole live caller.

**Direct dependencies:**

- None (pure Python, only stdlib `typing`).

**Cross-references:**

- `app/schemas/chat.py` `ConciergeChatRequest` — the schema whose validation produces these errors. Defines the `query` field that the canonical message references.
- `docs/BACKLOG.md` Backlog #7 — Slice 21 closure documents what was pruned and why.
- `tests/test_api_chat.py` — references `CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE` for assertion shape.
