# Phase 3.1 — Tier 1 template wiring (implementation summary)

## Files touched

| Action | Path |
|--------|------|
| **Created** | `app/chat/tier1_handler.py` |
| **Created** | `tests/test_tier1_handler.py` |
| **Modified** | `app/chat/unified_router.py` (`_handle_ask` calls `try_tier1`, returns `(text, tier_used)`; ask branch unpacks tuple; Tier 3 placeholder copy updated) |
| **Modified** | `tests/test_unified_router.py` (placeholder path uses `OPEN_ENDED`; added `test_ask_tier1_when_provider_row_present`) |
| **Modified** | `tests/test_phase2_integration.py` (`test_placeholder_tier_for_non_chat_modes` — ask query switched to open-ended so a shared pytest DB with seeded providers does not accidentally hit Tier 1) |
| **Modified** | `tests/test_api_chat.py` (omitted-`session_id` test uses open-ended ask for the same stability) |

**Not modified (per scope):** `app/chat/tier1_templates.py`, `intent_classifier.py`, `entity_matcher.py`, `normalizer.py`.

---

## Handoff vs implementation note

- **§3.3** lists eight Tier 1 sub-intents and does **not** name `NEXT_OCCURRENCE` or `OPEN_NOW`.
- **§3.4** places **next occurrence**-style flows and **`OPEN_NOW`** under **Tier 2**.

Phase 3.1 product spec for this build still asked for **`NEXT_OCCURRENCE`** and **`OPEN_NOW`** in Tier 1; they are implemented that way, using `tier1_templates.render` for date-style copy and small custom strings for `OPEN_NOW`.

---

## Tier 1 behavior (`try_tier1`)

Returns a **non-`None`** string → unified router sets **`tier_used == "1"`** when:

1. `intent_result.entity` is set, and  
2. A **`Provider`** row exists for that canonical `provider_name`, and  
3. `sub_intent` is in the Tier 1 coverage set, and  
4. Required fields are present (otherwise returns **`None`** → Tier 3 placeholder).

### Coverage (sub-intents)

| Sub-intent | Behavior |
|------------|----------|
| **`TIME_LOOKUP`** | If `provider.hours` is set → answer via **`HOURS_LOOKUP`** templates. If hours empty → best **`Program`** by title match / first active → **`TIME_LOOKUP`** template with start/end schedule. |
| **`HOURS_LOOKUP`** | `provider.hours` + `render("HOURS_LOOKUP", ...)`. |
| **`PHONE_LOOKUP`** | `provider.phone`, else program `contact_phone` when program title appears in normalized query, else any program phone. |
| **`LOCATION_LOOKUP`** | `provider.address`. |
| **`WEBSITE_LOOKUP`** | `provider.website`. |
| **`COST_LOOKUP`** | Program with literal `cost`, or `show_pricing_cta` + **`CONTACT_FOR_PRICING`** path via `render` (phone from program or provider). |
| **`AGE_LOOKUP`** | First active program with `age_min` / `age_max`. |
| **`DATE_LOOKUP`** / **`NEXT_OCCURRENCE`** | Next **live** `Event` for `provider_id` with `date >= today` (UTC), using **`DATE_LOOKUP`** template. |
| **`OPEN_NOW`** | 24/7-style keywords → “open”; else a **single** `H:MM am/pm – H:MM am/pm` span vs **`_utcnow()`**; unparseable hours → **`None`**. |

### Voice / provenance

- **`provider.verified == True`**: append **` (confirmed)`** after the rendered line.

### Tier 3 placeholder (fall-through)

When `try_tier1` returns **`None`**:

```text
Ask mode: intent=<sub>, entity=<entity or 'none'>. Tier 3 retrieval will be implemented in Phase 3.2.
```

**`tier_used`:** `placeholder`.

---

## Tests

- Full suite: **`pytest tests`** → **369 passed**, **0 failed** (at time of this write).
- **`tests/test_tier1_handler.py`:** **18** cases (entity/sub-intent null paths, field lookups, cost CTA, age, next event, `OPEN_NOW` in/out of window + unparseable, verified suffix, length, no trailing `?`).

---

## Flags for Phase 3.2+

1. **`field_history` contested state** (handoff §3.3 criterion 4): **not** read; answers always use current DB columns.
2. **`OPEN_NOW`**: only **simple** one-line AM/PM span + **24/7**-style keywords; free-form hours → fall through to Tier 3.
3. **Program disambiguation**: light heuristic (title tokens in normalized query, else first active program).
4. **Events**: “next upcoming” by `provider_id` only; no title-based event pick yet.

---

## Related code

- `app/chat/tier1_handler.py` — `try_tier1(query, intent_result, db) -> str | None`
- `app/chat/unified_router.py` — `_handle_ask` → `(text, tier_used)`
- `app/chat/tier1_templates.py` — **`render`** / **`CONTACT_FOR_PRICING`** (unchanged in this phase)
