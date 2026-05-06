# intent

`app/core/intent.py` (~170 lines post–Slice 71)

## Purpose

Deterministic helpers left after Backlog #36 Option A removed the legacy `detect_intent` cascade (template-era routing bypassed by LLM Tier 1/2/3). Production callers only use **`detect_out_of_scope_category`** from **`app/chat/intent_classifier.py`** as an early gate before the Tier 1 LLM call.

**`open_ended_search_message`** remains exported per the §7 disposition; there is no remaining `app/` importer after the dormant `app/core/search.py` pipeline was deleted at Slice 71.

## Public surface

**`detect_out_of_scope_category(message: str) -> str | None`**

Returns one of `"weather"`, `"lodging"`, `"transportation"`, `"dining"`, or `"commercial_services"` when a category trigger matches and no event-signal rescue applies; otherwise `None`. Guards include `"restaurant week"`, `"… night"` phrases tied to venue nights (`_NIGHT_ACTIVITY_WORDS`), commercial-services rental/booking heuristics (`_commercial_services_query` / `_COMMERCIAL_EVENT_RESCUE_PHRASES`), and `_EVENT_INDICATOR_WORDS` so event-shaped queries (e.g. hotel grand openings) stay in-scope for search.

**`open_ended_search_message(message: str) -> bool`**

True on a small curated set (`"what's good?"`, `"surprise me"`, `"anything fun?"`, etc.). Retained for disposition parity; no live `app/` caller today.

## Inputs and outputs

Both helpers normalize with `message.lower()` (and `.strip()` where noted in source). No session dict.

## Conventions

**Substring-first triggers.** Category scans use lowercase substring containment over `_OUT_OF_SCOPE_TRIGGERS`.

**Commercial-services branch precedes category triggers.** `_commercial_services_query` runs before iterating weather/lodging/transport/dining.

## Related

- **`app/chat/intent_classifier.py`** — imports `detect_out_of_scope_category` (`detect_out_of_scope_category(raw) is not None` drives `OUT_OF_SCOPE` Tier 1 routing).
- **`docs/components/intent_classifier.md`** — LLM Tier 1 taxonomy and router wiring.
- **`docs/maintainability/intent_module_disposition_decision.md`** — Option A sign-off and verification posture.
