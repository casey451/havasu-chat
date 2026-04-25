# Tier 2 grounding + gap-routing spec v2 — inline report

Date: 2026-04-24

This file captures the four inline confirmations requested alongside the v2 spec revision.

## Output file created

- `docs/tier2-grounding-and-gap-fix-spec-v2.md`

## 1) §6.7 quote constraining Item 1

From `docs/persona-brief.md` §6.7:

- "§2 firsthand voice applies at the level of local landscape knowledge ..."
- "Curated providers ... can carry firsthand specifics ..."
- "Bulk-imported providers speak factually-descriptive from enrichment data without manufactured opinions."
- "Single-provider lookups ... open with a framing beat ... before shifting to factual specifics."

Interpretation used in spec:

- Keep one short landscape framing beat.
- Require all concrete per-row specifics to be row-backed.

## 2) Item 2 — test grep results (gap-template / ordering)

Primary ordering-sensitive matches:

- `tests/test_tier2_routing.py::test_gap_template_unchanged_skips_tier_handlers`
- `tests/test_phase38_gap_and_hours.py::test_post_api_chat_gap_template_contract`
- `tests/test_phase38_gap_and_hours.py` DATE_LOOKUP gap assertion block (`tier_used == "gap_template"`)
- `tests/test_gap_template_contribute_link.py` (DATE_LOOKUP gap behavior)

Additional DATE_LOOKUP coverage found (likely indirect impact checks):

- `tests/test_ask_mode.py`
- `tests/test_intent_classifier.py`
- `tests/test_tier1_templates.py`

## 3) Item 3 — git output

Command:

`git log 88556bb..HEAD --oneline`

Output:

`<no commits after 88556bb>`

## 4) Item 5 — t3-02 through t3-05 confirmation

From `docs/known-issues.md`, the adjacent open issues remain applicable and are not addressed by this phase:

- embeddings not generated in approval flow
- 32-dim embedding fallback mismatch
- River Scene multi-day drop behavior
- Approach X auto-admit unspecified

These remain open and should be explicitly reaffirmed in the `known-issues` docs sub-phase for 8.8.3.
