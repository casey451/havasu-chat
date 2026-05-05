# tier2_schema

`app/chat/tier2_schema.py` (~153 lines)

## Purpose

Pydantic schema for Tier 2 parser output. Defines `Tier2Filters`, the structured filter object that `tier2_parser` produces from a free-form query and `tier2_db_query` consumes when assembling SQL. The schema enforces both per-field validation (date types, day-of-week labels, age ranges) and structural rules (the "one temporal plan at a time" constraint that the parser prompt also documents).

## Public surface

**`Tier2Filters` (Pydantic v2 BaseModel)** — The filter object. Fields:
- **Entity:** `entity_name`, `category`.
- **Demographic:** `age_min`, `age_max`.
- **Spatial:** `location`.
- **Temporal:** `day_of_week` (list), `time_window` (canonical token), `month_name`, `season`, `date_exact`, `date_start`/`date_end`.
- **Hours filter:** `open_now` (bool, defaults False).
- **Confidence + fallback:** `parser_confidence` (0.0–1.0, required), `fallback_to_tier3` (bool, defaults False).

All fields are `Optional` except `parser_confidence`. The schema's structural validators enforce:
- At most one of `time_window`, `month_name`, `season`, `date_exact`, or `(date_start + date_end)` may be set per response (the "one temporal plan at a time" rule).
- `day_of_week` values must be in the canonical lower-case list.
- `age_min ≤ age_max` when both set.

## Conventions

**Schema mirrors the parser prompt.** `prompts/tier2_parser.txt` documents the same temporal-plan rules. Drift between prompt and schema causes parser failures (LLM emits valid-by-prompt JSON that the schema rejects). Treat schema and prompt as a coupled pair.

**`parser_confidence` is required.** Every parse response must include it. The handler's confidence-gate (`tier2_handler.TIER2_CONFIDENCE_THRESHOLD = 0.7`) reads this field directly.

**`fallback_to_tier3` is the LLM's escape hatch.** When the LLM thinks the query isn't Tier-2-shaped, it sets this to `True` and the handler falls through. Important: this is the LLM's self-report; trust it.

**Lowercase day names, lowercase month names, lowercase seasons.** The parser prompt instructs the LLM to emit lowercase; the schema validates against frozensets defined at module top.

## Known limitations

**Single temporal plan limit.** Real-world queries sometimes mix temporal qualifiers ("Saturdays in July"). The schema rejects multi-plan combinations; the parser prompt's priority list resolves which to pick. If multi-plan support becomes important, the schema's structural validator is the place to relax.

**Prompt-schema drift.** Adding a new field to the schema requires updating `prompts/tier2_parser.txt` to describe it. Forgetting either side breaks parser output validation silently for the new field.

**No range validation on `time_window` tokens.** The schema accepts any string; canonical tokens (`today`, `tomorrow`, `this_week`, etc.) are documented in the parser prompt but not strictly enforced by the schema.

## Related

- `app/chat/tier2_parser.py` — produces Tier2Filters from a query (`docs/components/tier2_parser.md`).
- `app/chat/tier2_db_query.py` — consumes Tier2Filters to build SQL.
- `app/chat/tier2_handler.py` — orchestrates the parser → DB query → formatter chain (`docs/components/tier2_handler.md`).
- `prompts/tier2_parser.txt` — the system prompt that the LLM uses to emit schema-shaped JSON.
