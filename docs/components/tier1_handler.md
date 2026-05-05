# tier1_handler

`app/chat/tier1_handler.py` (~311 lines)

## Purpose

Deterministic Tier 1 lookup glue. When a query has an entity match AND one of ten specific sub-intent labels (TIME_LOOKUP, HOURS_LOOKUP, etc.), this module attempts a direct DB lookup and renders the answer via `tier1_templates.render`. Returns `None` to signal "fall through to Tier 2 or Tier 3" — every gate is a first-fit attempt; nothing here calls an LLM. Tier 1 hits are zero-token answers.

## Public surface

**`try_tier1(query: str, intent_result: IntentResult, db: Session) -> str | None`**

Sole exported function. Returns the rendered Tier 1 string on success, `None` on any miss or fallback condition. The unified router treats `None` as "Tier 1 doesn't apply; try Tier 2."

**`_TIER1_SUB_INTENTS` (frozenset, exposed for tests)** — The ten sub-intent labels Tier 1 knows how to answer: `TIME_LOOKUP`, `HOURS_LOOKUP`, `PHONE_LOOKUP`, `LOCATION_LOOKUP`, `WEBSITE_LOOKUP`, `COST_LOOKUP`, `AGE_LOOKUP`, `DATE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW`. Anything else is auto-fall-through.

## Inputs and outputs

**Input.** `IntentResult` from `intent_classifier.classify()` — needs `entity` (canonical Provider name) and `sub_intent` (one of the ten labels). DB session for lookups. The raw `query` arg is mostly used as a fallback when `intent_result.normalized_query` is missing.

**Output.** Either a rendered string (already voice-shaped per `_append_voice` — appends `(confirmed)` when the provider's `verified` flag is set) or `None`.

## Internal structure

`try_tier1()` is a guard-and-dispatch function:

1. **Entity gate.** `intent_result.entity is None` → return `None`. No entity means no provider lookup.
2. **Sub-intent gate.** Sub-intent not in `_TIER1_SUB_INTENTS` → return `None`. Tier 1 only handles the ten listed labels.
3. **Provider lookup.** `_get_provider(db, canonical_name)` does an exact-match `Provider.provider_name == entity`. Missing → return `None`.
4. **Sub-intent dispatch.** A flat if-chain on `sub`, one branch per label. Each branch:
   - Performs whatever DB lookups the label requires (provider fields, programs, events).
   - Returns `None` if required data is missing (e.g., `OPEN_NOW` needs `provider.hours`; missing → fall through).
   - Calls `tier1_templates.render(label, provider_or_program, data, variant=0)` to produce the user-facing string.
   - Returns the result through `_append_voice` (the `(confirmed)` suffix).

The ten dispatch branches in order:

| Sub-intent | DB lookups | Required data | Notes |
|------------|-----------|---------------|-------|
| `OPEN_NOW` | provider.hours | parseable hours window | Custom regex parser `_open_now_from_hours`; supports "24/7" / "all day" / "open 24" / "Hh-Hh am/pm" formats. Falls through on unparseable hours. |
| `DATE_LOOKUP`, `NEXT_OCCURRENCE` | next live event for provider | event with `end_date >= today` | Returns the soonest live event by `(date, start_time)`. |
| `PHONE_LOOKUP` | program-matching phone, then provider.phone, then any program phone | first non-empty | Three-priority cascade. |
| `LOCATION_LOOKUP` | provider.address | non-empty | Direct field. |
| `WEBSITE_LOOKUP` | provider.website | non-empty | Direct field. |
| `HOURS_LOOKUP` | provider.hours | non-empty | Direct field; `normalized_query` passed to the template for day-of-week awareness. |
| `TIME_LOOKUP` | provider.hours OR primary program's schedule | non-empty | Falls back from hours → program time window if hours absent. |
| `COST_LOOKUP` | program with `cost` set OR with `show_pricing_cta` | priced program OR pricing-CTA program | Returns `CONTACT_FOR_PRICING` constant when only `show_pricing_cta` is true. |
| `AGE_LOOKUP` | program with age range | `age_min` or `age_max` set | Format: `"5–12"` / `"5+"` / `"up to 12"` depending on which sides are set. |

## Conventions

**Returns `None` for "this gate doesn't apply"; never raises.** Same fallback discipline as `tier2_handler` — the unified router sees `None` and tries the next tier.

**`_append_voice` runs on every success path.** Centralizes the `(confirmed)` suffix logic. Call it on the rendered string before returning, never on substrings.

**Strip-and-empty-as-falsy.** `(field or "").strip()` is the consistent pattern. Empty string → falsy → fall through.

**Hours parser is a custom regex, not `dateutil`.** `_open_now_from_hours` handles formats common in operator-entered hours strings (`"9am-5pm"`, `"10:00 AM – 2:00 PM"`, `"24/7"`). Not robust to all natural phrasings; falls through on miss.

**Variant always `0`.** `render(..., variant=variant)` passes `variant=0`. The templates support multiple variants for response-style randomization, but Tier 1 always uses the first. Tunable later if response variety becomes worthwhile.

**Programs are queried `is_active=True`.** Inactive programs are filtered at the DB layer (`_programs_for`). Tier 1 will never return data from an inactive program.

**Time math is naive UTC.** `_utcnow()` returns tz-aware UTC; `_open_now_from_hours` strips tz to compare against operator-entered local times. **Implicit assumption: provider hours are in Lake Havasu local time.** Comparing UTC-now against local-hours produces wrong results. This is a real bug-shaped corner — see Known limitations.

## Known limitations and design notes

**OPEN_NOW timezone bug (Backlog #27).** `_utcnow()` is in UTC; provider `hours` strings are operator-entered local Lake Havasu time. The current code compares UTC-now against local-hours-of-day, which is off by 7 hours (MST/UTC-7). At MST midnight the comparison is against 5pm UTC. Operator-visible effect: OPEN_NOW answers will be wrong outside a narrow midday window. Fix: `_utcnow()` should call `now_lake_havasu()` from `app.core.timezone` and compare against same-locale times. Filed as Backlog #27 by Slice 35.

**Hours parser is brittle.** Regex covers common formats but not edge cases like multi-window days ("9am-12pm, 2pm-5pm"), day-specific hours ("Mon-Fri 9-5; Sat 10-2"), or seasonal hours. Falls through cleanly on parse failure; user gets Tier 2/Tier 3 fallback.

**Provider lookup is exact-match on `provider_name`.** If the entity matcher returns a canonical name that doesn't perfectly match a `Provider.provider_name`, Tier 1 falls through. The entity matcher uses fuzzy matching, so matched canonical names should always exist as exact provider names — but a stale `_ENTITY_NAMES` list could break this assumption.

**No multi-program disambiguation in `COST_LOOKUP`.** Provider with multiple priced programs returns the first program with a non-empty `cost`. Order is whatever SQL returns (typically `id` ascending). Not deterministic if two programs are roughly equivalent.

**Variant=0 always.** Tier 1 has no response-style variety. Probably fine since these are factual lookups; voice consistency matters more than variation. But if Hava ever wants Tier 1 answers to feel less templated, add variant rotation.

**`COST_LOOKUP` returns `CONTACT_FOR_PRICING` placeholder.** When a program has `show_pricing_cta=True` but no `cost` field, the response says "contact for pricing" via the constant. This is intentional but feels awkward — better long-term would be a cost-template that explicitly does the CTA framing.

## Configuration

No environment configuration. Behavior is driven entirely by DB state (provider/program rows) and `IntentResult` shape.

## Related

**Direct callers:** `app/chat/unified_router.py` `_handle_ask` — calls `try_tier1(query, intent_result, db)` first; falls through to optional LLM router → Tier 2 → Tier 3 on `None`.

**Direct dependencies:**
- `app/chat/intent_classifier.IntentResult` — input shape.
- `app/chat/normalizer.normalize` — fallback normalizer when `IntentResult.normalized_query` is absent.
- `app/chat/tier1_templates.render` + `CONTACT_FOR_PRICING` — output rendering.
- `app/db/models.{Event, Program, Provider}` — DB models.

**Adjacent docs:**
- `docs/components/tier2_handler.md` — next tier in the fallback chain.
- `docs/components/intent_classifier.md` — produces the `IntentResult` Tier 1 reads.
- `docs/components/unified_router.md` — orchestrates the Tier 1 → 2 → 3 fallback.
