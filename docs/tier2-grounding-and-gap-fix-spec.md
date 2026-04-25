# Tier 2 grounding + gap-routing fix spec

Status: Draft for owner review  
Date: 2026-04-24  
Scope: Pre-launch behavior correction for Tier 2/Tier 3 routing and grounding  
Primary decision default: 3a (revert Tier 3 Option B), with explicit owner gate for 3b

---

## 1) Problem statement

Validation and diagnostics show four user-facing failures in `/api/chat` ask mode:

1. "What is happening in Havasu this summer" returned April-only framing.
2. "When is the 4th of July show in Havasu" returned a gap-template "not in catalog" response despite July 4 rows existing.
3. "What events are happening on July 4" omitted July 4 while naming other months.
4. "Fireworks on the 4th of July in Lake Havasu" confabulated venue/time details not present in rows.

Root finding from read-only diagnostics:

- Tier 2 event query does **not** filter on `provider_id`; unlinked events were already eligible in Tier 2.
- The four validation turns were handled by Tier 2 or `gap_template`, not Tier 3.
- `gap_template` currently executes before Tier 2 in ask-mode routing.
- Tier 2 formatter is LLM-based and prompt constraints are not strict enough to prevent invented specifics.

Implication: Option B in Tier 3 (`_unlinked_future_events` tail block) does not address the observed production failures because those turns did not use Tier 3.

---

## 2) Evidence summary (source docs)

- `docs/tier3-diagnostics-section-a-e-report.md`
  - D2/D3: validation queries logged as `tier_used in {2, gap_template}`, never `3`.
  - D4: July 4 fireworks rows exist and are `provider_id IS NULL`, `status='live'`.
  - D5: 28 unlinked live future rows; 16 before `2026-07-04`; `LIMIT 10` in Tier 3 unlinked path excludes July 4 if Tier 3 path is used.
  - D6: Taste/Balloon are also unlinked (not linked-provider-only rows).
- `docs/tier2-gap-explicit-rec-readonly-spelunk.md`
  - Tier 2 DB query shape and formatter path.
  - `_catalog_gap_response` execution order and return text.
  - `_EXPLICIT_REC_PATTERNS` list and mismatch with calendar-browse phrasings.

---

## 3) Goals and non-goals

### Goals

1. Eliminate Tier 2 confabulation of event details not present in catalog rows.
2. Prevent false "not in catalog" gap-template responses when Tier 2 can answer.
3. Simplify and de-risk architecture by removing Tier 3 Option B if it is not required for real ask traffic.

### Non-goals

- No schema migration.
- No broad classifier redesign.
- No change to persona voice beyond grounding safety in Tier 2 formatter.
- No push/deploy in this spec; implementation will hold for owner approval.

---

## 4) Proposed fixes

## Fix 1 — Harden Tier 2 formatter grounding (prompt-only)

### Why

Confabulation surfaced on fireworks query (invented venue/time not present in rows). Current prompt says "Do not invent facts," but does not impose hard field-level prohibitions.

### Files

- `prompts/tier2_formatter.txt`

### Required changes

Add strict grounding rules in formatter prompt (exact wording can be tuned, semantics must be preserved):

- If a detail is not present in the provided row JSON, do not state it.
- Never invent venue, address, schedule time, duration, organizer, or pricing.
- If user asks for a missing field (for example "where" and row lacks location), explicitly say the row does not provide that detail.
- Prefer omission over interpolation; no "local color" details unless directly row-backed.
- Keep existing plain-text and brevity constraints.

### Acceptance criteria

- Formatter output for a row lacking venue/time does not include venue/time claims.
- Prompt retains current formatting constraints and remains plain text.

---

## Fix 2 — Move gap-template behind Tier 2 attempt

### Why

Current ask flow applies `_catalog_gap_response` before Tier 2. DATE_LOOKUP with no entity returns canned gap copy even when Tier 2 rows exist.

### Files

- `app/chat/unified_router.py`

### Required behavior change

Current order (ask mode):
1. `_catalog_gap_response`
2. `_handle_ask` (Tier 1 / explicit-rec Tier 3 / Tier 2 / Tier 3 fallback)

New order:
1. `_handle_ask`
2. If `_handle_ask` returns Tier 2/Tier 1/Tier 3 output, return it.
3. Apply gap-template only when the ask pipeline cannot produce a result.

Implementation note:

- Keep Tier 1 and explicit-rec behavior unchanged.
- Keep existing `tier_used` semantics.
- Ensure gap-template still works for true catalog holes.

### Acceptance criteria

- DATE_LOOKUP no-entity query with matching rows returns a data-backed answer (not immediate `gap_template`).
- Queries with no Tier 2 rows and no Tier 1/Tier 3 usable answer can still return gap-template path.

---

## Fix 3 — Tier 3 Option B disposition (owner decision gate)

## 3a (default recommended) — Revert Option B

### Why

- Observed failures were not Tier 3 path failures.
- Option B adds complexity and can drift from actual routing behavior.
- Primary user-visible issues are solved by Fix 1 + Fix 2.

### Files (if reverting)

- `app/chat/context_builder.py` (remove unlinked-tail section and constants introduced by Option B)
- `tests/test_context_builder.py` (remove/update Option B-specific tests)
- any Option B implementation report docs if needed (doc note only)

### Acceptance criteria

- `build_context_for_tier3` returns pre-Option-B provider/program/event context behavior.
- Test suite updated to match intended Tier 3 scope.

## 3b (alternative) — Keep Option B but redesign event selection

Only if owner explicitly wants Tier 3 "general calendar" to remain.

Potential redesign constraints:

- Avoid strict earliest-10 bias that excludes mid-year events.
- Use bucketed sampling (for example near-term + later-year) or query-aware selection.
- Preserve context budget guarantees.

This path needs a separate mini-spec before implementation.

---

## 5) Test plan (implementation phase)

## Unit tests

1. Tier 2 formatter grounding prompt
   - Add/adjust tests asserting output does not introduce fields absent from rows.
   - At minimum, cover missing venue/time response behavior.

2. Unified router gap ordering
   - Query classified as DATE_LOOKUP/no-entity with Tier 2 rows available should not return `gap_template`.
   - True no-match path should still allow gap-template.
   - Existing explicit-rec and Tier 1 tests remain green.

3. Option B disposition
   - If 3a: remove/replace Option B tests and ensure Tier 3 context tests match baseline.
   - If 3b: add dedicated tests for redesigned selection logic.

## Regression checks

- No regressions in:
  - Tier 1 deterministic responses
  - explicit-rec -> Tier 3 fast path
  - ask-mode logging fields (`tier_used`, `mode`, `sub_intent`)

## Manual validation queries (post-deploy)

Re-run:

1. "what is happening in havasu this summer"
2. "when is the 4th of july show in havasu"
3. "what events are happening on july 4"
4. "i am looking for fireworks on the 4th of july in lake havasu"

Expected:

- No invented venue/time not present in rows.
- No false gap-template for queries with matching rows.

---

## 6) Deploy + rollback plan

## Deploy

- Single PR containing Fix 1 + Fix 2 + Fix 3a (unless owner selects 3b).
- Owner runs local pytest in Windows venv.
- Merge and deploy once, then immediate manual validation with four canonical queries.

## Rollback

- If post-deploy responses regress materially, rollback to prior commit.
- Preserve logs from validation window to identify regression source (prompt grounding vs routing order).

---

## 7) Risks

1. Reordering gap-template could change behavior for edge DATE/LOCATION/HOURS asks that currently rely on canned copy.
2. Stronger formatter grounding may make some replies shorter/more conservative.
3. If 3a revert is chosen, any downstream work that assumed Option B section exists must be updated.

Mitigation: targeted tests + explicit post-deploy validation queries.

---

## 8) Decision required from owner

Approve one of:

- **A (recommended):** Implement Fix 1 + Fix 2 + Fix 3a (revert Option B) in one PR.
- **B:** Implement Fix 1 + Fix 2 only, defer Option B decision.
- **C:** Implement Fix 1 + Fix 2 + keep Option B (3b), with follow-up mini-spec for redesigned Tier 3 selection.

Recommended current path: **A**.
