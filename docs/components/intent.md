# intent

`app/core/intent.py` (~157 lines post–Slice 71b)

## Purpose

Deterministic helpers left after Backlog #36 Option A removed the legacy `detect_intent` cascade (template-era routing bypassed by LLM Tier 1/2/3). The only production caller is **`detect_out_of_scope_category`** from **`app/chat/intent_classifier.py`** — an early gate before the Tier 1 LLM call.

## Public surface

**`detect_out_of_scope_category(message: str) -> str | None`**

Returns one of `"weather"`, `"lodging"`, `"transportation"`, `"dining"`, or `"commercial_services"` when a category trigger matches and no event-signal rescue applies; otherwise `None`. Guards include `"restaurant week"`, `"… night"` phrases tied to venue nights (`_NIGHT_ACTIVITY_WORDS`), commercial-services rental/booking heuristics (`_commercial_services_query` / `_COMMERCIAL_EVENT_RESCUE_PHRASES`), and `_EVENT_INDICATOR_WORDS` so event-shaped queries (e.g. hotel grand openings) stay in-scope for search.

## Inputs and outputs

The helper normalizes with `message.lower()`. No session dict.

## Conventions

**Substring-first triggers.** Category scans use lowercase substring containment over `_OUT_OF_SCOPE_TRIGGERS`.

**Commercial-services branch precedes category triggers.** `_commercial_services_query` runs before iterating weather/lodging/transport/dining.

## Known limitations

Slice 71b removed **`open_ended_search_message`** after the **`app/core/search.py`** pipeline deletion left it without a live caller — continuing Option A’s spirit rather than keeping orphaned symbols.

## Related

- **`app/chat/intent_classifier.py`** — imports `detect_out_of_scope_category` (`detect_out_of_scope_category(raw) is not None` drives `OUT_OF_SCOPE` Tier 1 routing).
- **`docs/components/intent_classifier.md`** — LLM Tier 1 taxonomy and router wiring.
- **`docs/maintainability/intent_module_disposition_decision.md`** — Option A sign-off and verification posture.
