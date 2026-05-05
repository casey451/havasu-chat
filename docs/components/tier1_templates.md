# tier1_templates

`app/chat/tier1_templates.py` (~322 lines)

## Purpose

Tier 1 deterministic-template engine. Combines a regex-based intent classifier (`INTENT_PATTERNS`, ordered first-match-wins) with per-intent response variants (`TEMPLATES`, voice-shaped per `docs/persona-brief.md`). The `tier1_handler` calls `render()` to produce a final Tier 1 string from a matched intent + a Provider/Program entity + a slot-filled `data` dict, or gets `None` when required slots are missing — which signals "fall through to Tier 2."

## Public surface

**`INTENT_PATTERNS: list[tuple[str, re.Pattern]]`** — Ordered list of `(intent_label, compiled_regex)` pairs. The classifier matches in order; more-specific intents come first (WEBSITE before PHONE before HOURS before DATE). Adding new intents appends to this list and adds a corresponding entry to `TEMPLATES`.

**`TEMPLATES: dict[str, list[str]]`** — Per-intent response variants. Each variant is a string with `.format(**slots)` placeholders. Multiple variants per intent allow response-style randomization (the handler currently always picks `variant=0`; future variant rotation is a separate decision).

**`render(intent: str, entity: Provider | Program, data: dict[str, Any], variant: int) -> str | None`** — Produces a Tier 1 response string. Returns `None` when any required slot is missing — caller treats `None` as "fall through to Tier 2." Variant index is clamped to `[0, len(variants)-1]`.

**`CONTACT_FOR_PRICING`** — Sentinel string returned in COST_LOOKUP `data` when a program has `show_pricing_cta=True` but no concrete `cost`. Triggers the call-for-pricing variant of the cost template.

## Internal structure

`render()` is a guard-and-format flow:

1. **Intent lookup.** `TEMPLATES.get(intent)`. Missing → return `None`.
2. **Variant selection.** Clamp `variant` to range; pick the variant string.
3. **Special-case routing.** Some intents have multi-variant logic (e.g., COST_LOOKUP picks the pricing-CTA variant when `data['cost'] == CONTACT_FOR_PRICING`; HOURS_LOOKUP picks closed-state variant when `data['closed_today'] is True`).
4. **Slot fill.** `template.format(**data)`. KeyError on missing slot → return `None`.
5. **Voice suffix appended by caller.** `tier1_handler._append_voice` adds the `(confirmed)` suffix; `render()` doesn't do voice-shaping itself.

## Conventions

**First-match-wins ordering matters.** `INTENT_PATTERNS` order is load-bearing. WEBSITE patterns precede PHONE precede HOURS, etc. Reordering to fix one intent often breaks another; test extensively.

**Voice shape per persona-brief.** Each variant: 1-2 sentences, contractions, no filler, no follow-up questions, direct answer then stop. Variant authoring goes through the §7 voice audit.

**`None` for missing slot.** The `template.format(**data)` raises `KeyError` for missing keys; `render()` catches and returns `None`. Caller treats this as "fall through to Tier 2." Don't substitute a generic apology — the user gets a real Tier 2/Tier 3 answer instead.

**Sentinel `CONTACT_FOR_PRICING`.** A specific string value (not `None`) used to flag pricing-CTA paths. Imported by `tier1_handler` for COST_LOOKUP branching.

**Weekday-aware HOURS.** `_WEEKDAY_NAMES` list is consumed for day-specific parsing in HOURS_LOOKUP variants. Abbreviations fall back to the all-week text.

## Known limitations

**No per-variant scoring.** All variants for an intent are equally valid; rotation is index-based. If certain phrasings perform better empirically, there's no built-in way to weight them.

**Regex brittleness.** New phrasings of an existing intent often need pattern extensions. Tests should cover the new phrasings; otherwise regression risk is high.

**Slot mismatch is silent.** A variant referencing `{phone}` but a caller passing `{phone_number}` yields `None` — looks like "Tier 1 doesn't apply" rather than a coding error. Test coverage is the safeguard.

## Related

- `app/chat/tier1_handler.py` — sole caller (`docs/components/tier1_handler.md`).
- `docs/persona-brief.md` — voice shape rules variants must satisfy.
- `HAVA_CONCIERGE_HANDOFF.md` §3, §7, §8 — the spec reference for Tier 1.
