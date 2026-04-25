# Phase 8.8.3 — Tier 2 grounding + gap-routing fix spec (v2)

Status: Draft for owner review  
Date: 2026-04-24  
Phase: **8.8.3** (parallel to 8.9; neither blocks the other)  
Chosen path: **A** = Fix 1 + Fix 2 + Fix 3a (revert Option B)

---

## 1) Problem statement

Validation and diagnostics show four user-facing failures in `/api/chat` ask mode:

1. "What is happening in Havasu this summer" returned April-only framing.
2. "When is the 4th of July show in Havasu" returned gap-template "not in catalog" copy despite July 4 rows existing.
3. "What events are happening on July 4" omitted July 4 while naming other months.
4. "Fireworks on the 4th of July in Lake Havasu" confabulated venue/time details not present in DB rows.

Read-only diagnostics established:

- Tier 2 event query does **not** filter on `provider_id`.
- Validation turns were handled by Tier 2 or `gap_template`, not Tier 3.
- `gap_template` executes before Tier 2 in current ask flow.
- Tier 2 formatter is LLM-based and remains the confabulation surface.

Implication: Tier 3 Option B did not address these failures because these turns did not route through Tier 3.

---

## 2) Evidence summary

- `docs/tier3-diagnostics-section-a-e-report.md`
  - D2/D3: `tier_used` for canonical queries is `2` or `gap_template`, never `3`.
  - D4: July 4 fireworks rows exist and are unlinked.
  - D5: unlinked ordering explains Tier 3 LIMIT-10 blindness, but this did not drive observed failures.
  - D6: Taste/Balloon rows are also unlinked.
- `docs/tier2-gap-explicit-rec-readonly-spelunk.md`
  - Tier 2 filter/query shape.
  - `_catalog_gap_response` ordering and text.
  - `_EXPLICIT_REC_PATTERNS` mismatch with browse/calendar phrasings.

---

## 3) Goals and non-goals

### Goals

1. Stop Tier 2 confabulation of event specifics absent from catalog rows.
2. Stop false gap-template responses when Tier 2 can answer.
3. Remove Option B complexity introduced under a misdiagnosed premise.

### Non-goals

- No schema changes.
- No broad classifier redesign.
- No `_is_explicit_rec` broadening in this phase (documented explicitly in section 9).
- No deploy automation changes in this spec.

---

## 4) Fix 1 — Harden Tier 2 formatter grounding (prompt-only)

### Why

The confabulation symptom is produced in Tier 2 formatter output. Prompt strengthening is lowest-risk/highest-leverage.

### Files

- `prompts/tier2_formatter.txt`

### 4.1 Constraint from persona §6.7 (must coexist, not overwrite)

Persona brief §6.7 explicitly allows a short landscape framing line while requiring factual per-row specifics.

Quoted anchor (from `docs/persona-brief.md` §6.7):

- "§2 firsthand voice applies at the level of local landscape knowledge ..."
- "Curated providers ... can carry firsthand specifics ..."
- "Bulk-imported providers speak factually-descriptive from enrichment data without manufactured opinions."
- "Single-provider lookups ... open with a framing beat ... before shifting to factual specifics."

### 4.2 Framing-vs-confabulation boundary (for implementation)

Allowed:

- One short landscape framing beat that does not add unbacked event facts.
- Category-level framing ("This is one of the bigger seasonal events...") when non-specific.

Not allowed:

- Any concrete event detail not present in row JSON (venue/address/time window/duration/pricing/organizer/attendance claims).
- Any "local color" that implies concrete facts absent from rows.

### 4.3 Draft prompt language (for owner wording review)

Draft block to add under current §6.7 formatter section:

1. "Keep the §6.7 framing beat: one short landscape line is allowed."
2. "After that framing line, every concrete detail must be directly row-backed."
3. "If a row does not contain a detail, do not infer it and do not state it."
4. "Never invent venue, address, time window, duration, organizer, pricing, or schedule specifics."
5. "If asked for a missing detail, say briefly that the rows do not provide it."
6. "When in doubt, be sparse and factual rather than interpolating."

### 4.4 Prompt baseline confirmation

Current `prompts/tier2_formatter.txt` no longer contains explicit-rec routing instructions from older phases. The new grounding rules can be inserted without conflicting with removed explicit-rec content.

### Acceptance criteria

- Formatter output does not state venue/time/other specifics absent from rows.
- Existing plain-text + brevity behavior remains intact.
- §6.7 framing beat remains permitted (one short non-specific framing line).

---

## 5) Fix 2 — Move gap-template behind Tier 2 attempt

### Why

Current order can return `gap_template` for DATE_LOOKUP/no-entity turns where Tier 2 has rows.

### Files

- `app/chat/unified_router.py`

### Required behavior change

Current ask path:

1. `_catalog_gap_response`
2. `_handle_ask`

Target ask path:

1. `_handle_ask` first
2. If ask pipeline returns usable answer (Tier 1/2/3), return it
3. Apply `_catalog_gap_response` only when appropriate fallback conditions are met

### Risk evidence from test suite (ordering-sensitive tests)

Search hits indicate tests currently asserting immediate gap-template behavior:

- `tests/test_tier2_routing.py::test_gap_template_unchanged_skips_tier_handlers`
- `tests/test_phase38_gap_and_hours.py::test_post_api_chat_gap_template_contract`
- `tests/test_phase38_gap_and_hours.py` DATE_LOOKUP gap assertion block (`tier_used == "gap_template"`)
- `tests/test_gap_template_contribute_link.py` (DATE_LOOKUP gap text contract)

Expected update shape (spec only, no edits in this phase):

- Adjust tests that assert "gap before Tier2" to assert "Tier2 attempted first; gap only when no data path succeeds."
- Keep contract tests for true no-match DATE/LOCATION/HOURS gap responses.
- Preserve explicit-rec and Tier1 expectations unchanged.

### Acceptance criteria

- DATE_LOOKUP/no-entity with matching rows does not immediately return `gap_template`.
- True no-match asks can still produce gap-template response.

---

## 6) Fix 3a — Revert Tier 3 Option B (chosen)

### Why

Option B targeted a Tier 3 path not used by the failing validation turns.

### Revert mechanism (required)

Use a clean **git revert** of commit:

- `88556bb` — `feat(tier3): surface unlinked future events in context`

Do **not** manually re-edit files as primary mechanism.

### Expected revert surface

At minimum, revert touches introduced by that commit:

- `app/chat/context_builder.py`
- `tests/test_context_builder.py`
- any additional files in that commit diff (if present in final repo state)

### Conflict handling

Check divergence before revert:

- `git log 88556bb..HEAD --oneline`

In current branch snapshot, this range is empty (no commits on top of `88556bb` in history). If non-empty at implementation time:

1. Run `git revert 88556bb`.
2. Resolve conflicts preserving post-88556bb intentional changes unrelated to Option B.
3. Re-run tests for `context_builder` and router behavior.
4. Document conflict resolutions in PR notes.

### Acceptance criteria

- Tier 3 context behavior returns to pre-Option-B shape.
- Option B-specific tests are removed/updated via the revert.

---

## 7) Test plan

## 7.1 Unit tests

1. **Fix 1 prompt regression test (deterministic)**
   - Add test that mocks `client.messages.create` in `app/chat/tier2_formatter.py` path and inspects loaded system prompt text.
   - Assert new grounding rule strings are present.
   - Purpose: catches prompt regression in source text (not model behavior).

2. **Fix 2 routing order tests**
   - Update ordering-sensitive gap tests listed in section 5.
   - Add/adjust case: DATE_LOOKUP/no-entity with rows should not short-circuit to gap.
   - Keep no-match gap path assertions.

3. **Fix 3a revert verification**
   - `tests/test_context_builder.py` aligns with pre-Option-B behavior after revert.

## 7.2 Manual validation gate (launch-blocking)

After deploy, run each canonical query **3 times**:

1. "what is happening in havasu this summer"
2. "when is the 4th of july show in havasu"
3. "what events are happening on july 4"
4. "i am looking for fireworks on the 4th of july in lake havasu"

Pass criteria:

- Across all 12 responses, no venue/time/detail claims absent from supporting rows.
- Any single confabulation = fail gate and rollback.

Checklist action:

- Add this as launch-blocking entry in `docs/pre-launch-checklist.md`.

What each gate validates:

- Unit prompt test validates that hard grounding instructions exist in prompt text.
- Manual 3x gate validates real model behavior under production inference.

---

## 8) Deploy plan and documentation sub-phases

## 8.1 Code phase (single PR)

- Implement Fix 1 + Fix 2 + Fix 3a.
- Run targeted tests + owner-run pytest in local venv.
- Hold for push approval.

## 8.2 Docs sub-phase commit: `known-issues` update

Separate commit after code verification:

- Update `docs/known-issues.md`:
  - Prior Tier-3 provider-id gating issue entry (historical t3-01 framing) -> mark **RESOLVED-BY-MISDIAGNOSIS** and cross-reference:
    - `docs/tier3-diagnostics-section-a-e-report.md` (D5)
    - `docs/tier2-gap-explicit-rec-readonly-spelunk.md` (Q1.a)
  - Confirm t3-02 through t3-05-equivalent open items remain unaffected by this phase.

## 8.3 Docs sub-phase commit: `START_HERE` refresh

Separate commit after merge/deploy:

- Update intended tip hash.
- Add Phase 8.8.3 completed-work entry.
- Verify pre-launch sequence still reads correctly.

## 8.4 Handoff update task (Phase ledger)

Update `HAVA_CONCIERGE_HANDOFF.md` §5 with a new entry:

- **Phase 8.8.3 — Tier 2 grounding + gap-routing fix**
- mark parallel relation with 8.9 (no blocking dependency either direction).

---

## 9) Considered but not changed: `_is_explicit_rec` breadth

Diagnostics confirmed the four validation queries do not match current `_EXPLICIT_REC_PATTERNS`, so they do not reach Tier 3 via explicit-rec.

This phase intentionally does **not** broaden `_is_explicit_rec`.

Reasoning:

1. User-visible failures are directly addressed in Tier 2 by Fix 1 (grounding) and Fix 2 (gap order).
2. Broadening explicit-rec would route more browse traffic to Tier 3, increasing cost and complexity.
3. Keeping explicit-rec narrow keeps routing surface smaller and easier to reason about pre-launch.

This section is explicit so future readers understand why explicit-rec expansion was deferred.

---

## 10) Risks and rollback

1. Gap-order change may alter DATE/LOCATION/HOURS behavior where canned copy was previously immediate.
2. Harder grounding may produce terser answers.
3. Revert conflicts possible if branch diverges after this draft.

Rollback:

- Revert merged 8.8.3 code commit if confabulation gate fails.
- Preserve logs and failing prompts for postmortem.

---

## 11) Owner decision record

Direction locked for implementation prompt:

- **Implement:** Fix 1 + Fix 2 + Fix 3a
- **Do not implement:** explicit-rec broadening in this phase
- **Do include:** two docs sub-phase commits (`known-issues`, `START_HERE`) and handoff §5 phase ledger update
