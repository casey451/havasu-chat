# Phase 6.4.1 — Recommended-entity capture for prior_entity

## Context

Phase 6.4 shipped session memory including prior-entity recall, but with a documented gap: prior-entity capture fires only when `IntentResult.entity` is populated (user-named entity), not when Tier 2 or Tier 3 recommends an entity. Result: "I asked about Altitude, what time does it open" works; "Recommend something, what time does it open" does not.

This sub-phase closes that gap. When Tier 2 or Tier 3 produces a response that mentions exactly one catalog-known entity, capture it as `prior_entity` so the next turn's pronoun-referent query can resolve it.

Current state: `main` at implementation time (snapshot at prompt authoring: `ce64b92`); use **current `main` test count** as baseline. Railway production healthy. Phase 6 remaining after this sub-phase: 6.5 (owner editorial blurbs).

## Design decisions (locked with owner before this prompt)

- **Single-entity rule.** Capture only when the response mentions exactly one catalog-known entity. If zero or multiple, do not capture (leave prior_entity as whatever it was — do not clear).
- **Extraction method.** Use existing `entity_matcher.match_entity` (or equivalent API) against the response text. Do not use the Phase 5.5 mention scanner (that's for contribution discovery, different concern).
- **Placement.** In `unified_router.py` after Tier 2 or Tier 3 returns. Synchronous, not BackgroundTask. Consistent with existing `record_entity` calls in the router.
- **Tier scope.** Apply to both Tier 2 and Tier 3. Tier 1 is single-entity deterministic templates — already covered by user-named capture. gap_template and chat mode don't produce entity recommendations.
- **Backwards compat.** Existing user-named capture stays as-is. 6.4.1 adds recommended-entity capture as an additional path. **Precedence (locked):** whatever writes `prior_entity` **last** on a turn wins. Recommended-entity capture runs **after** the Tier 2/3 handler returns, so it **overwrites** any `prior_entity` set earlier on that same turn (including user-named). Trace the router to confirm order before implementing; see In scope §5 and acceptance criteria.

## Pre-flight checks (read-only — STOP and report before any implementation)

Run each of these and report findings. Do NOT proceed to implementation until owner replies `proceed`.

1. `git log --oneline -20 | grep -i "6.4.1\|recommended.entity\|prior_entity.capture"` — confirm no prior 6.4.1 work exists on main. (On Windows without `grep`, use `git log --oneline -20` and scan, or pipe to `findstr /i`.)
2. View `app/chat/entity_matcher.py` and report:
   a. The public API for entity matching against arbitrary text — specifically, what function(s) accept a text string and return matched entity name(s) plus confidence scores.
   b. Whether there's an existing pattern for "match all entities in text" (returning a list) vs. "match best entity in text" (returning one). If only the latter exists, we'll need a small extension.
   c. The current fuzzy-match threshold (per pre-flight 6.4 this was >75).
3. View `app/chat/unified_router.py` and report:
   a. Where Tier 2 and Tier 3 handlers return their responses (the exact return point where we'd capture the response text for entity scanning).
   b. Where the existing `record_entity` call fires for user-named entities (so recommended-entity capture sits adjacent and the precedence rule is clear).
   c. Whether the session state and current turn_number are in scope at those return points (they should be, but confirm).
4. View `app/chat/tier2_handler.py` and `app/chat/tier3_handler.py` and report:
   a. The response object shape returned by each handler.
   b. Whether response text is directly accessible or requires extraction from a structured response.
5. Check existing tests:
   a. `tests/test_prior_entity_router.py` — report current fixture count and structure so new tests match the existing pattern.
   b. Any integration test that runs a full Tier 2 or Tier 3 query end-to-end through the router — report existence and whether it's usable as a pattern for end-to-end 6.4.1 tests.

STOP after reporting. Wait for `proceed`.

## Git scope fence

- Trailer-accepted policy: leave any `Made-with: Cursor` trailer alone.
- No amends to prior commits.
- No hook bypass, no `--no-verify`, no edits to `core.hooksPath`.
- **`docs/phase-6-4-1-cursor-prompt.md`** may ship in a **preceding docs-only commit** (process artifact) or be **folded into** the single implementation commit — either matches the Phase 6.1.x pattern. The implementation commit for code/tests/docs-report still uses message `Phase 6.4.1: recommended-entity capture for prior_entity`.
- Hold the implementation commit pending explicit owner approval.

## STOP-and-ask triggers (do not continue until owner replies)

- If pre-flight check 2b reveals no existing "match all entities in text" pattern AND check 2a reveals that `match_entity` only returns the best match, STOP and propose one of: (a) add a new `match_all_entities(text)` function, (b) repeatedly call `match_entity` on substrings, (c) scan the response text for every catalog name and record matches above threshold. Different tradeoffs — let owner pick.
- If pre-flight check 4b reveals response text is buried in a structured response that requires non-trivial extraction, STOP and describe.
- If voice spot-check regresses below 19/1/0 at end of implementation, STOP and report.
- If the new entity-extraction pass adds **>50ms p95** to Tier 2 or Tier 3 response time **as measured in local dev** on the existing voice-battery queries (or an equivalent fixed set of Tier 2/3 calls), STOP and report — optimize or escalate before ship. (Unlikely: fuzzy match over ~100 names is cheap; this is an explicit gate.)
- If any acceptance criterion below cannot be met, STOP and describe why.

## Goal

After a Tier 2 or Tier 3 response that mentions exactly one catalog entity, that entity is captured as `prior_entity`. Subsequent pronoun-referent queries resolve to it. No existing flow breaks. Voice does not regress.

## In scope

### Backend — entity extraction from response text

1. Add a function in `app/chat/entity_matcher.py` (or adjacent module if that's cleaner per pre-flight check 2) that takes a response text string and returns the list of catalog-known entities mentioned, above the existing fuzzy-match threshold. Function signature something like:
   ```python
   def extract_catalog_entities_from_text(text: str, db: Session) -> list[EntityMatch]
   ```
   where `EntityMatch` contains at minimum name, type (provider/program/event), and id.

2. The function should:
   - Use the same canonical-names cache pattern the existing `match_entity` function uses.
   - Return all entities matching above threshold (not just the best).
   - Deduplicate — if the same entity is mentioned twice in the response, return it once.
   - Be efficient — called on every Tier 2/3 turn, should not blow up latency.

3. If pre-flight check 2b reveals an existing "match all" pattern, use or extend it instead of adding a new function. Match existing idioms.

### Backend — router integration

4. In `app/chat/unified_router.py`, after Tier 2 or Tier 3 handler returns and the response text is known:
   - Call `extract_catalog_entities_from_text(response_text, db)`.
   - If exactly one entity returned: call `record_entity(session_id, entity, current_turn_number)`. This overwrites any existing prior_entity (same semantics as user-named capture).
   - If zero or multiple entities returned: do not write. Do not clear existing prior_entity.

5. Precedence rule: user-named entity capture (existing from 6.4) runs **before** the Tier 2/3 handler and may set `prior_entity` first. Recommended-entity capture runs **after** the handler returns. **Written last wins:** if recommended-entity capture records exactly one entity, it **overwrites** `prior_entity` for that turn (including overwriting user-named from earlier on the same turn).

   Verify this order by tracing the router flow. If the trace differs, STOP and confirm with owner before implementing.

6. Both Tier 2 and Tier 3 paths get this capture. Tier 1 (single-entity deterministic templates) is already covered by user-named capture. gap_template and chat mode do not produce entity recommendations — skip them.

### Tests

7. Extend `tests/test_prior_entity_router.py` or add `tests/test_recommended_entity_capture.py` with:
   a. Tier 3 response mentioning exactly one catalog entity → prior_entity captured with correct name, type, id, turn_number.
   b. Tier 3 response mentioning two catalog entities → prior_entity not written (or unchanged from before).
   c. Tier 3 response mentioning zero catalog entities → prior_entity unchanged.
   d. Tier 2 response mentioning exactly one catalog entity → prior_entity captured.
   e. **Overwrite across turns (no contrived cross-tier conflict):** Turn 1: open-ended query X → Tier 3 response mentions exactly one catalog entity **A** → `prior_entity` is **A** (with `turn_number`). Turn 2: different open-ended query Y → Tier 3 response mentions exactly one catalog entity **B** (B ≠ A) → `prior_entity` is now **B** with updated `turn_number` (overwrite confirmed).
   f. Edge: response mentions same entity twice → captured once.
   g. End-to-end: turn 1 open-ended query → Tier 3 response mentions Altitude → turn 2 "what time does it open" → prior_entity resolution fires, response uses Altitude.

8. `tests/test_entity_matcher.py` (or wherever the new function lives) gets unit tests:
   a. Text with one catalog entity → returns that entity.
   b. Text with two catalog entities → returns both.
   c. Text with no catalog entities → returns empty list.
   d. Text mentioning same entity twice → returns once (dedup).
   e. Text with near-matches below threshold → returns nothing for those.

9. Run full test suite: must pass **current `main` count + new tests**.

10. Run voice spot-check: `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py --base http://127.0.0.1:8765` (local). Must hold at 19/1/0 or better. Explicit numeric score required in report.

## Out of scope

- Multi-entity prior_entity stack (still one deep; out of scope per 6.4 locked decisions).
- Structured output changes to Tier 2 or Tier 3 to explicitly return entities.
- Reusing or modifying the mention scanner (Phase 5.5) — that's for contribution discovery, separate concern.
- Cross-session entity persistence.
- UI changes.

## Acceptance criteria

- [ ] `extract_catalog_entities_from_text` function (or equivalent) exists and is unit tested.
- [ ] Tier 2 and Tier 3 paths in unified_router call the extraction and conditionally write prior_entity per the single-entity rule.
- [ ] Single-entity rule: capture fires only when exactly one catalog entity is mentioned.
- [ ] Precedence: when both user-named and recommended-entity capture fire on the same turn, recommended-entity wins (written last).
- [ ] End-to-end: open-ended query → Tier 3 recommends a single entity → follow-up with "what time does it open" resolves to that entity.
- [ ] Full test suite passes at **current `main` count + new tests**.
- [ ] Voice spot-check holds at 19/1/0 or better with explicit numeric score in report.
- [ ] No regression on existing 6.4 prior-entity behavior (user-named capture still works).
- [ ] No regression on existing Tier 1, gap_template, chat mode, feedback loop, contribute, admin.

## Completion workflow

1. Implement all in-scope items after owner replies `proceed` to pre-flight report.
2. Run full test suite: `.\.venv\Scripts\python.exe -m pytest -q`. Report the number.
3. Run voice spot-check locally: `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py --base http://127.0.0.1:8765`. Provide explicit PASS/MINOR/FAIL numeric score and query numbers for any MINOR/FAIL.
4. Manual verification in local dev:
   a. Fresh session, ask "what should I do tomorrow" (expect Tier 3 recommendation mentioning a single entity). Follow up with "what time does it open" — confirm prior-entity resolution.
   b. Fresh session, ask "what's good for kids Saturday" (Tier 3 likely mentions multiple options). Follow up with "what time does it open" — confirm no resolution (ambiguous, concierge should ask which).
   c. Fresh session, explicitly ask about Altitude. Follow up with "what time does it open" — confirm user-named capture still works (unchanged 6.4 behavior).
5. Update `docs/known-issues.md` — remove or close the 2026-04-21 entry for recommended-entity capture (since we're closing it). Add a note referencing the 6.4.1 commit.
6. Update `docs/phase-6-4-session-memory-report.md` with a new section noting 6.4.1 shipped and closed the known gap.
7. Write `docs/phase-6-4-1-recommended-entity-capture-report.md` covering: what shipped, pre-flight findings, test counts before/after, voice score, manual verification results, files-changed list, any deviations from spec.
8. Report completion summary. DO NOT COMMIT. Wait for owner to reply `approved, commit and push`.
9. On approval: single consolidated commit with message `Phase 6.4.1: recommended-entity capture for prior_entity`. Push to main.
10. After push, wait 3 minutes for Railway auto-deploy. Report deploy status + production smoke:
    a. Fresh session: "I'm visiting with my 8-year-old, we're near the channel, what should we do tomorrow?" → note which entity Tier 3 recommends.
    b. Follow up: "What time does it open?" → confirm prior-entity resolution now fires on production (this was the failing smoke test from 6.4).
