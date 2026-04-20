# Phase 4.1 — Completion summary (for review)

## Overview

Phase 4.1 (Tier 2 filter schema + intent parser) was implemented, verified, and pushed to `main` as commit `9a30909` with commit message:

`Phase 4.1: Tier 2 filter schema + intent parser`

The pre-commit hook appended a `Made-with: Cursor` trailer; it was left as-is per project policy.

---

## Files created

| File | Purpose |
|------|--------|
| `app/chat/tier2_schema.py` | `Tier2Filters` Pydantic model per cross-phase contract |
| `app/chat/tier2_parser.py` | `parse(query) -> Optional[Tier2Filters]` using Anthropic Messages API with ephemeral system prompt cache |
| `prompts/tier2_parser.txt` | Role, schema description, and 8 required few-shot query → JSON examples (verbatim anchors) |
| `tests/test_tier2_parser.py` | 15 tests: 10 high-confidence, 3 fallback, 2 error (mocked SDK) |

**No existing production files were modified** (scope: new modules + prompt + tests only).

---

## Verification (agent-run)

1. **Full pytest:** `python -m pytest -q` from repo root — **493 passed** (includes 15 new tests; prior baseline was 478 + new tests).
2. **Track A battery:** `python scripts/run_query_battery.py` against production — **116 / 120** matches (meets ≥116 acceptance bar).

---

## Test approach

**Mocked Anthropic client**, following the same pattern as `tests/test_tier3_handler.py` (`patch.object(anthropic, "Anthropic", …)` and canned assistant text).

**Rationale:** Deterministic CI, no live API key requirement for the structured-path tests, while still exercising JSON coercion, Pydantic validation, and `messages.create` kwargs (including `max_tokens=300`, `temperature=0.3`, and ephemeral `cache_control` on the system block in one of the high-confidence tests).

---

## Design decisions beyond the literal spec text

1. **`Tier2Filters` validators (field set unchanged):**
   - `time_window`, when non-null, must be one of: `today`, `tomorrow`, `this_week`, `this_weekend`, `this_month`, `upcoming`.
   - `day_of_week`, when non-null, must be English weekday names; values are normalized to lowercase.

   This ensures invalid enum-like strings from the LLM fail `model_validate`, so `parse()` returns `None` with the distinct schema-validation log line — aligned with acceptance criteria and Phase 4.2 expectations.

2. **JSON coercion:** If the model wraps JSON in Markdown code fences, the parser strips fences and parses the inner payload; otherwise invalid text still yields `None` with the invalid-JSON log line.

---

## Parser behavior (aligned with `tier3_handler.py`)

- Default model: `claude-haiku-4-5-20251001`; `ANTHROPIC_MODEL` env override supported.
- Temperature **0.3**, **300** `max_tokens`.
- System prompt loaded from `prompts/tier2_parser.txt` with **ephemeral** prompt cache on the system block.
- User message format mirrors Tier 3’s pattern (`User query:\n…`) for the API payload only.
- Logging: fixed `tier2_parser:` prefixes; no new log lines that embed raw user query text beyond existing Tier 3–style patterns.

**Failure modes returning `None` (with distinct logging where specified):**

- Missing `ANTHROPIC_API_KEY`
- Missing / unreadable parser prompt file
- Anthropic SDK import failure
- `messages.create` exception
- Assistant output not parseable as a JSON object
- Pydantic `ValidationError` on `Tier2Filters`
- Unexpected errors in the post-response path

---

## Commit / push

- **Branch:** `main`
- **Remote:** pushed to `origin/main` after acceptance checks passed.

---

## Checklist for reviewer

- [ ] `Tier2Filters` in `app/chat/tier2_schema.py` matches Phase 4.1 / 4.2 field contract.
- [ ] `prompts/tier2_parser.txt` contains role, schema section, and 8 few-shots in required order with unchanged example queries/outputs.
- [ ] Tests cover: 10 high-confidence, 3 fallback, 2 error paths; no production imports wired yet (parser is import-only until 4.3).
