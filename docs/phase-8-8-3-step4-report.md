# Phase 8.8.3 Step 4 Report

Date: 2026-04-24

## 1) `git log --oneline -5`

- `6a99f4a feat(tier2): harden formatter grounding and reorder gap-template (Phase 8.8.3)`
- `26bdc32 Revert "feat(tier3): surface unlinked future events in context"`
- `88556bb feat(tier3): surface unlinked future events in context`
- `f84ead8 docs(known-issues): cross-link Tier 3 investigation doc from Entry 1`
- `b99048a docs(known-issues): log five issues surfaced in Phase B validation session`

## 2) Pytest summary

- `tests/test_context_builder.py -v` (post-revert): **9 passed**, **0 failed**, **1.85s**
- `tests/ -k tier2 -v` (post Fix 1+2): **68 passed**, **0 failed**, **26.69s**
- Full suite `pytest -v`: **848 passed, 3 subtests passed**, **0 failed**, **421.54s (0:07:01)**

## 3) Grounding-rules block added to `prompts/tier2_formatter.txt` (verbatim)

```text
**Grounding guardrails (additive to §6.7):**
- Keep the §6.7 framing beat: one short landscape line is allowed.
- After that framing line, every concrete detail must be directly row-backed.
- If a row does not contain a detail, do not infer it and do not state it.
- Never invent venue, address, event time window, duration, organizer, or pricing details.
- If the user asks for a missing detail (for example "where" with no location field), say briefly that the provided rows do not include it.
- When in doubt, be sparse and factual rather than interpolating.
```

## 4) Diff summary of gap-template reorder in `app/chat/unified_router.py`

- `_handle_ask(...)` now takes `allow_tier3_fallback: bool = True` and can return `(None, "placeholder", ...)` when Tier 2 has no rows and fallback is disabled.
- Ask-mode routing now:
  - computes `gap_text = _catalog_gap_response(intent_result)`
  - if `gap_text` exists, calls `_handle_ask(..., allow_tier3_fallback=False)` first
  - returns `gap_template` **only if** `_handle_ask` yields `text is None`
  - otherwise returns Tier 1/2/3 result from `_handle_ask`
- Previous early-return block that emitted `gap_template` before `_handle_ask` was removed.

## 5) Test files modified

- `tests/test_tier2_formatter.py`
- `tests/test_tier2_routing.py`
- `tests/test_phase38_gap_and_hours.py`
- `tests/test_gap_template_contribute_link.py`
- `tests/test_context_builder.py` (via revert commit `26bdc32`)

Also modified (non-test implementation/prompt files):

- `app/chat/unified_router.py`
- `prompts/tier2_formatter.txt`
- `app/chat/context_builder.py` (via revert commit `26bdc32`)

---

No push performed.
