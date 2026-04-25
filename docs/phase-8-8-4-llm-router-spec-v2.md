# Phase 8.8.4 — LLM-routed comprehension layer + Tier 2 selection bias fix (v2)

Status: Draft for owner review  
Date: 2026-04-24  
Scope: Spec only (no implementation changes in this phase)  
Locked decisions:

- Path 2.5 + Tier 2 selection-bias fix only
- Router model = Haiku 4.5
- Tier 1 remains deterministic fast-path before router
- Router does **not** emit `gap`

---

## 1) Problem statement

Phase 8.8.3 (`6a99f4a`) fixed grounding and reduced early gap short-circuiting, but post-deploy behavior still shows comprehension failures for natural calendar/discovery phrasing.

Key symptoms:

1. "what's happening this summer" often yields honest-but-misaligned near-term events.
2. "what events are happening on july 4" can miss date-specific intent when parser does not extract a precise window.
3. "when is the 4th of july show in havasu" still depends on no-entity DATE lookup behavior when Tier2 extraction is weak.
4. Broad browse asks can be crowded out by recurring early-date rows.

Evidence sources:

- `docs/phase-8-8-4-read-intent-comprehension-audit.md`
- `docs/tier2-gap-explicit-rec-readonly-spelunk.md`
- `app/chat/unified_router.py`, `app/chat/tier2_handler.py`, `app/chat/tier2_parser.py`, `app/chat/tier2_db_query.py`

Architectural root issue:

- Current comprehension is split across deterministic classifier + LLM parser + regex routing gates, with schema limits and cross-component mismatch.

---

## 2) Goals and non-goals

### Goals

1. Consolidate ask-mode comprehension/routing into one structured router decision point (after Tier1 fast-path).
2. Improve temporal understanding for natural phrasings (months, seasons, explicit dates/ranges, next week/month).
3. Reduce Tier2 row-selection bias from recurring early-date crowd-out.
4. Preserve rollback safety using feature-flagged migration.

### Non-goals (8.8.4)

- No semantic answerability check (defer to 8.8.5 candidate).
- No entity matcher threshold/alias retuning.
- No `_EXPLICIT_REC_PATTERNS` broadening.
- No persona voice rewrite.
- No DB schema migration.
- No removal of deterministic legacy path in this phase.

---

## 3) Architecture — LLM router design

## 3.1 Placement in call graph

Ask-mode flow in 8.8.4:

1. Tier1 deterministic fast-path (`try_tier1`) runs first.
2. If Tier1 returns `None`, call new LLM router.
3. Router returns structured decision and Tier2 filters.
4. Execute Tier2 or Tier3 based on router decision.
5. Gap-template remains post-execution outcome under existing no-entity DATE/LOCATION/HOURS + no Tier2 rows behavior.

This keeps Tier1 latency/cost advantages and removes split comprehension for non-Tier1 asks.

## 3.2 Router inputs

- `raw_query` (required)
- `normalized_query` (required)
- optional session context:
  - onboarding hints
  - prior entity
  - current local now-line

## 3.3 Router output schema (v2, no `gap`)

Router JSON output:

```json
{
  "mode": "ask|contribute|correct|chat",
  "sub_intent": "TIME_LOOKUP|HOURS_LOOKUP|PHONE_LOOKUP|LOCATION_LOOKUP|WEBSITE_LOOKUP|COST_LOOKUP|AGE_LOOKUP|DATE_LOOKUP|NEXT_OCCURRENCE|OPEN_NOW|LIST_BY_CATEGORY|OPEN_ENDED|NEW_EVENT|NEW_PROGRAM|NEW_BUSINESS|CORRECTION|GREETING|SMALL_TALK|OUT_OF_SCOPE",
  "entity": "string|null",
  "router_confidence": 0.0,
  "tier_recommendation": "2|3",
  "tier2_filters": {
    "entity_name": "string|null",
    "category": "string|null",
    "age_min": 0,
    "age_max": 0,
    "location": "string|null",
    "day_of_week": ["monday"],
    "time_window": "today|tomorrow|this_week|this_weekend|this_month|upcoming|next_week|next_month|null",
    "month_name": "january|...|december|null",
    "season": "spring|summer|fall|winter|null",
    "date_exact": "YYYY-MM-DD|null",
    "date_start": "YYYY-MM-DD|null",
    "date_end": "YYYY-MM-DD|null",
    "open_now": false,
    "parser_confidence": 0.0,
    "fallback_to_tier3": false
  }
}
```

Rules:

- `tier_recommendation` is only `2` or `3` (Tier1 already handled; router does not output gap).
- Existing sub-intent taxonomy is preserved.
- `tier2_filters` may be null/empty when recommending Tier3.

## 3.4 Model + inference settings

- Model: `claude-haiku-4-5-20251001`
- Temperature: `0.0`
- Max tokens: `500`
- Response format contract: JSON object only, schema-validated
- Timeout: same `LLM_CLIENT_READ_TIMEOUT_SEC` pattern as existing LLM callers

## 3.5 Error handling

On router failure (API, timeout, invalid JSON, validation failure):

- Log failure reason.
- Fallback to Tier3 directly for ask-mode.
- Do not emit synthetic gap-template from router failure.

Rationale: avoid hallucinated router-level answerability claims.

---

## 4) Router prompt specification (authoritative, not deferred)

This section defines the behavioral architecture of the LLM router.

## 4.1 System prompt structure

Proposed sections in `prompts/llm_router.txt`:

1. Role + output contract (JSON-only, exact schema, no prose).
2. Mode/sub-intent taxonomy map (must use existing labels).
3. Tier recommendation policy (`2` vs `3`; Tier1 already tried).
4. Temporal extraction rules (verbatim mapping rules below).
5. Ambiguity handling and confidence guidance.
6. Few-shot examples.

## 4.2 Temporal extraction rules (verbatim policy)

Router must apply:

1. If query says **today/tonight** -> `time_window=today`.
2. If query says **tomorrow** -> `time_window=tomorrow`.
3. If query says **this weekend** -> `time_window=this_weekend`.
4. If query says **this week** -> `time_window=this_week`.
5. If query says **this month** -> `time_window=this_month`.
6. If query says **next week** -> `time_window=next_week`.
7. If query says **next month** -> `time_window=next_month`.
8. If query names a month (for example "october") -> set `month_name=<month>`, leave `time_window=null`.
9. If query names a season (for example "summer") -> set `season=<season>`, leave `time_window=null`.
10. If query includes explicit single date -> set `date_exact`.
11. If query includes explicit date range -> set `date_start` and `date_end`.
12. If no temporal signal -> leave temporal fields null and use `time_window=upcoming` only when clearly asking for future events generally.

## 4.3 Tier recommendation policy (verbatim)

1. Recommend Tier2 when query is retrieval/filter shaped and can be expressed in Tier2 filters.
2. Recommend Tier3 when query is open-ended synthesis/recommendation/discovery that likely needs broader synthesis.
3. Never output `gap`; router does not decide catalog answerability.
4. For ambiguous cases, prefer Tier2 if confidence >=0.7 and meaningful filters exist; otherwise Tier3.

## 4.4 Ambiguity/confidence policy

- `router_confidence` reflects confidence in overall route decision.
- `parser_confidence` reflects confidence in Tier2 filter quality.
- If temporal intent is clear but exact extraction is weak, prefer Tier3 unless broad fallback (`upcoming`) is strongly justified.

## 4.5 Few-shot examples (12)

1. **Query:** "what's happening this weekend"  
   **Output:** `mode=ask`, `sub_intent=OPEN_ENDED`, `tier_recommendation=2`, `time_window=this_weekend`.

2. **Query:** "what's happening this summer"  
   **Output:** `tier_recommendation=2`, `season=summer`, `time_window=null`.

3. **Query:** "what events are happening on july 4"  
   **Output:** `tier_recommendation=2`, `date_exact=<YYYY-07-04>`.

4. **Query:** "when is the 4th of july show in havasu"  
   **Output:** `sub_intent=DATE_LOOKUP`, `tier_recommendation=2`, `date_exact=<YYYY-07-04>`, `entity=null`.

5. **Query:** "anything to do tomorrow night"  
   **Output:** `tier_recommendation=2`, `time_window=tomorrow`.

6. **Query:** "events in october"  
   **Output:** `tier_recommendation=2`, `month_name=october`, `time_window=null`.

7. **Query:** "what's coming up next month"  
   **Output:** `tier_recommendation=2`, `time_window=next_month`.

8. **Query:** "what should I do friday night"  
   **Output:** `tier_recommendation=3`, `sub_intent=OPEN_ENDED`.

9. **Query:** "best place for breakfast in havasu"  
   **Output:** `mode=chat`, `sub_intent=OUT_OF_SCOPE`, `tier_recommendation=3` (or chat-handled per route wrapper policy).

10. **Query:** "where is the london bridge"  
    **Output:** `sub_intent=LOCATION_LOOKUP`, `tier_recommendation=2`, `entity=null`, location hint if available.

11. **Query:** "fireworks july 4"  
    **Output:** `tier_recommendation=2`, `date_exact=<YYYY-07-04>`, `category=fireworks`.

12. **Query:** "I'm visiting next week, what should I plan"  
    **Output:** `tier_recommendation=3` (synthesis/planning intent), optional temporal extraction `next_week`.

(Implementation will encode exact JSON objects with full fields; above defines mandatory behavioral shape.)

---

## 5) Filter schema v2 (cleaned)

Structured temporal fields are primary. Avoid redundant encoding.

- `time_window` is only for simple canonical windows:
  - `today`, `tomorrow`, `this_week`, `this_weekend`, `this_month`, `upcoming`, `next_week`, `next_month`, or `null`.
- Do not set `time_window=month_name` or `time_window=season`.
- Use dedicated fields:
  - `month_name` for named-month queries,
  - `season` for seasonal queries,
  - `date_exact`, `date_start`, `date_end` for explicit date constraints.

---

## 6) Tier2 selection bias fix (revised priority)

## 6.1 Primary strategy: recurring dedupe

Root problem is recurring-series crowd-out (for example weekly BMX rows consuming capped slots).

Primary fix:

- Collapse recurring series into one representative row when query window is broad.
- Use recurring signal (`is_recurring` where available) and/or heuristic grouping fallback for events with same title pattern/date cadence.

## 6.2 Secondary strategy: temporal bucketing

If dedupe alone still clusters near-term results:

- Apply even-distribution selection over remaining candidates.

## 6.3 File targets

- `app/chat/tier2_db_query.py` (`_query_events` + helper functions)

Behavior:

- Narrow windows (<=30 days): existing earliest-date logic acceptable.
- Broad windows (>30 days): dedupe recurring first, then bucket if needed, then cap.

---

## 7) Migration path (feature-flagged)

1. Add new module `app/chat/llm_router.py`.
2. Add new prompt `prompts/llm_router.txt`.
3. Wire `unified_router.py` ask path:
   - Tier1 first (unchanged),
   - then LLM router under `USE_LLM_ROUTER`.
4. Keep deterministic path when `USE_LLM_ROUTER=false` (default off initially).
5. Validate in both modes.
6. Enable flag in production.
7. Keep deterministic path in code for soak period; defer removal to follow-up phase.

---

## 8) Test plan

## 8.1 Unit tests

1. Router output schema parse/validation tests.
2. Router tier recommendation mapping tests.
3. Router failure fallback-to-Tier3 tests.
4. Tier2 recurring-dedupe selection tests.

## 8.2 Integration tests

Use the 20 query shapes from `docs/phase-8-8-4-read-intent-comprehension-audit.md` as structured trace tests (flag on).

## 8.3 Parity tests (explicit)

- Tier1 queries: identical responses expected under flag off/on.
- Tier2 queries: semantically equivalent responses allowed (wording can differ).
- Tier3 queries: no strict text parity requirement.

## 8.4 Manual validation gate

Run each query 3 times post-deploy.

Canonical 4:

1. what's happening this summer
2. what events are happening on july 4
3. when is the 4th of july show in havasu
4. i am looking for fireworks on the 4th of july in lake havasu

Additional 8 (from audit):

- #2, #3, #4, #6, #7, #9, #13, #14 query shapes:
  - what's happening this summer
  - what events are happening on july 4
  - when is the 4th of july show in havasu
  - events in october
  - what's coming up next month
  - where is the london bridge
  - where should I take my kids on a hot day
  - is the london bridge worth seeing

Pass criteria:

- no confabulation
- routing consistent with intent
- no false brick-wall gaps where data exists

---

## 9) Cost, latency, monitoring

Expected uplift target:

- Cost increase target: **+10-15%** per turn
- Alert threshold: **+25%**

Monitoring:

- Log router input/output token counts and latency per turn.
- Compare p50/p95 latency and per-turn token cost against 8.8.3 baseline.

---

## 10) Risk and rollback

Risks:

1. Router non-determinism.
2. Added per-turn latency.
3. Cost drift above target.
4. Incorrect route on ambiguous phrasing.

Mitigations:

- temperature 0.0
- strict schema validation
- robust few-shot coverage in router prompt
- feature flag control

Rollback:

- set `USE_LLM_ROUTER=false`
- redeploy
- no data migration rollback needed

---

## 11) Phase ledger and docs

- Phase number: **8.8.4**
- Parallel with 8.9 (no direct blocking dependency)

Docs to update during implementation:

- `docs/START_HERE.md`
- `HAVA_CONCIERGE_HANDOFF.md` §5
- `docs/known-issues.md`
- `docs/pre-launch-checklist.md`

Deferred:

- 8.8.5 candidate: semantic answerability check.

---

## 12) Implementation file list

### New

- `app/chat/llm_router.py`
- `prompts/llm_router.txt`
- `tests/test_llm_router.py`
- `tests/test_llm_router_integration.py`

### Modified

- `app/chat/unified_router.py`
- `app/chat/tier2_db_query.py`
- `app/chat/tier2_schema.py`
- `app/chat/tier2_handler.py` (if needed for compatibility path)
- related tests for routing and Tier2 selection behavior

### Deferred deletions (not in 8.8.4)

- deterministic classifier/routing path removal
- explicit-rec legacy path cleanup

---

## Appendix A — v1 -> v2 changes

1. **Prompt spec expanded:** Section 4 now defines router prompt architecture, verbatim extraction/routing rules, and 12 few-shot examples.
2. **Removed router `gap` output:** `tier_recommendation` now excludes `gap`; gap remains post-execution behavior.
3. **Selection fix priority changed:** recurring dedupe is primary; bucketing is secondary.
4. **Tier1 boundary fixed:** Tier1 deterministic fast-path remains before router.
5. **Schema tightened:** removed redundant `time_window=month_name/season` pattern; structured fields are primary.
6. **Cost target added:** +10-15% target, +25% alert.
7. **Validation set fixed:** explicit additional 8 query shapes listed.
8. **Parity rules specified:** exact/semantic parity definitions by tier category.
9. **Sub-intent taxonomy locked:** router uses existing taxonomy labels.
