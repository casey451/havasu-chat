# Phase 8.8.4 — LLM-routed comprehension layer + Tier 2 selection bias fix

Status: Draft for owner review  
Date: 2026-04-24  
Scope: Spec only (no implementation in this phase)  
Locked decisions: Path 2.5 + Tier 2 selection-bias fix only; router model = Haiku 4.5

---

## 1) Problem statement

Phase 8.8.3 (`6a99f4a`) improved Tier 2 grounding and gap ordering, but post-deploy behavior still reveals comprehension-layer failures for natural event/calendar phrasing.

Observed failures (from `docs/phase-8-8-4-read-intent-comprehension-audit.md` and prior validation):

1. Natural temporal phrases (for example "this summer", "events in October", "next month") are not reliably represented in current Tier 2 filter schema.
2. Classifier + parser split creates mismatches (deterministic classifier says OPEN_ENDED, LLM parser may return weak or generic filters).
3. Tier 2 event selection uses earliest-date ordering and tight cap (`MAX_ROWS=8`), causing broad queries to over-represent near-term rows.
4. Gap-template behavior still depends on no-entity DATE/LOCATION/HOURS path and Tier 2 parse/result quality.

Pre-8.8.4 comprehension chain:

- `POST /api/chat` -> `unified_router.route` (`app/api/routes/chat.py`, `app/chat/unified_router.py`)
- deterministic classifier (`app/chat/intent_classifier.py`)
- Tier 1 direct handler (`app/chat/tier1_handler.py`)
- Tier 2 parser (LLM, `app/chat/tier2_parser.py`) -> Tier 2 DB query (`app/chat/tier2_db_query.py`) -> Tier 2 formatter (LLM, `app/chat/tier2_formatter.py`)
- Tier 3 fallback (`app/chat/tier3_handler.py` + `app/chat/context_builder.py`)

Architectural issue: intent/routing decisions are split across multiple components that use different representations and confidence semantics.

---

## 2) Goals and non-goals

### Goals

1. Improve intent comprehension for natural-language event/calendar/discovery queries.
2. Produce consistent tier-routing decisions from one structured decision point.
3. Keep Tier 2 row selection aligned with user time intent (reduce earliest-date crowd-out).
4. Preserve safe fallback behavior under model/API failures.

### Non-goals (explicitly out of scope for 8.8.4)

- No semantic answerability check (defer candidate to 8.8.5).
- No entity-matcher threshold/alias overhaul.
- No `_EXPLICIT_REC_PATTERNS` broadening.
- No additional gap-template special-case redesign beyond what the new router inherently governs.
- No persona voice changes.
- No schema/database migrations.

---

## 3) Architecture — LLM router design

## 3.1 Position in call graph

New router module sits in ask-mode orchestration and replaces deterministic intent+routing decision making for the ask path.

Current ask decision points:

- classifier mode/sub_intent (`app/chat/intent_classifier.py`)
- explicit-rec regex (`app/chat/unified_router.py` `_EXPLICIT_REC_PATTERNS`)
- gap-template gate (`_catalog_gap_response`)
- Tier 2 parser confidence/fallback and row emptiness (`app/chat/tier2_handler.py`)

8.8.4 target:

- One LLM router call returns structured routing decision + structured Tier2 filters.
- `unified_router.py` executes tier handlers according to returned decision.

## 3.2 Router input

- Required: raw query string (pre-normalization and normalized form).
- Optional context:
  - existing session hints (visitor/local, kids, location)
  - prior entity (if any)
  - now-line timestamp string (`format_now_lake_havasu()`)

## 3.3 Router output schema (JSON)

Router returns exactly one JSON object:

```json
{
  "mode": "ask|contribute|correct|chat",
  "sub_intent": "string",
  "entity": "string|null",
  "router_confidence": 0.0,
  "tier_recommendation": "1|2|3|gap",
  "tier2_filters": {
    "entity_name": "string|null",
    "category": "string|null",
    "age_min": 0,
    "age_max": 0,
    "location": "string|null",
    "day_of_week": ["monday"],
    "time_window": "today|tomorrow|this_week|this_weekend|this_month|upcoming|next_week|next_month|month_name|season|explicit_date|explicit_range",
    "month_name": "january|...|december|null",
    "season": "spring|summer|fall|winter|null",
    "date_exact": "YYYY-MM-DD|null",
    "date_start": "YYYY-MM-DD|null",
    "date_end": "YYYY-MM-DD|null",
    "open_now": false,
    "parser_confidence": 0.0,
    "fallback_to_tier3": false
  },
  "gap_reason": "string|null"
}
```

Notes:

- `tier2_filters` may be `null` when `tier_recommendation` is not `2`.
- `mode`/`sub_intent` remain explicit so downstream logging parity is preserved.
- `gap_reason` is for auditability; not shown to end user.

## 3.4 Model and inference settings

- Model: `claude-haiku-4-5-20251001`
- Temperature: `0.0`
- Max tokens: `400` (router JSON is compact; this leaves margin for robust extraction)
- Response format: strict JSON object only (prompt-enforced + parser validation)
- Timeout: reuse `LLM_CLIENT_READ_TIMEOUT_SEC` pattern used by Tier2/Tier3 modules.

## 3.5 Error handling and safe fallback

If router call fails (API error, import error, empty response, invalid JSON, schema validation failure):

- Log router failure with reason.
- Fallback behavior: route ask-mode to Tier 3 (`answer_with_tier3`) directly using existing safe path.
- Do not emit synthetic gap-template from router-failure path.

Rationale: Tier 3 gives best graceful degradation without brittle parser assumptions.

---

## 4) Architecture — filter schema expansion (Tier2Filters v2)

Current limitation:

- Existing `time_window` supports only:
  - `today`, `tomorrow`, `this_week`, `this_weekend`, `this_month`, `upcoming` (`app/chat/tier2_schema.py` + parser prompt).

Mismatch:

- `app/core/slots.py` already extracts richer temporal concepts (for example `next_week`, `next_month`, explicit dates), but Tier 2 parser contract cannot express them.

## 4.1 Proposed Tier2Filters v2

```python
class Tier2FiltersV2(BaseModel):
    entity_name: str | None = None
    category: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    location: str | None = None
    day_of_week: list[str] | None = None

    # window token (expanded)
    time_window: Literal[
        "today",
        "tomorrow",
        "this_week",
        "this_weekend",
        "this_month",
        "upcoming",
        "next_week",
        "next_month",
        "month_name",
        "season",
        "explicit_date",
        "explicit_range",
    ] | None = None

    # disambiguation fields
    month_name: Literal[
        "january","february","march","april","may","june",
        "july","august","september","october","november","december"
    ] | None = None
    season: Literal["spring","summer","fall","winter"] | None = None
    date_exact: date | None = None
    date_start: date | None = None
    date_end: date | None = None

    open_now: bool = False

    parser_confidence: float = Field(..., ge=0.0, le=1.0)
    fallback_to_tier3: bool = False
```

## 4.2 Resolution rules

- `explicit_date` -> exact day (`date_exact`)
- `explicit_range` -> bounded by `date_start/date_end`
- `month_name` -> full calendar month in current/next year based on now context
- `season` -> deterministic season-to-range mapping in Arizona context for current/next cycle
- `next_month` and `next_week` resolved deterministically at query time

---

## 5) Architecture — Tier 2 row selection bias fix

Current behavior:

- `_query_events` orders `Event.date ASC, Event.start_time ASC`, SQL limit 80, then truncates to `MAX_ROWS=8` (`app/chat/tier2_db_query.py`).
- Broad windows over multiple months overweight earliest events.

## 5.1 Options considered

1. Random sample across window  
   - Pros: reduces earliest bias  
   - Cons: non-deterministic outputs, unstable UX
2. Even distribution across range (bucketed by time slices)  
   - Pros: deterministic, covers near/mid/far range  
   - Cons: slightly more logic
3. Recurring event dedupe/grouping first  
   - Pros: mitigates repeated series dominance  
   - Cons: needs recurring signal quality
4. Increase `MAX_ROWS` only  
   - Pros: easy  
   - Cons: token/cost pressure, does not fully remove bias

## 5.2 Recommended 8.8.4 approach

Adopt **deterministic even-distribution sampling** for wide windows:

- If resolved window span <= 30 days: keep existing earliest-date ordering behavior.
- If span > 30 days:
  - fetch candidate events in date order
  - divide window into `MAX_ROWS` buckets
  - select first qualifying event from each bucket
  - fill remaining slots by next unselected events in order

File target:

- `app/chat/tier2_db_query.py` (`_query_events`, plus helper function for bucket sampling)

This keeps determinism, reduces near-term crowd-out, and avoids raising row cap.

---

## 6) Migration path (feature-flagged)

## 6.1 Stepwise rollout

1. Implement new LLM router module (no behavior change yet).
2. Wire router into `unified_router.py` behind env flag `USE_LLM_ROUTER` (default `false`).
3. Keep existing deterministic path intact as fallback path when flag is off.
4. Run tests with both flag states (`on` and `off`) and validate parity where expected.
5. Enable flag in production after pre-prod validation.
6. **Do not remove deterministic classifier in 8.8.4.** Keep for rollback; evaluate removal in follow-up phase after soak.

## 6.2 Flag-off behavior

- Preserve current behavior exactly (8.8.3 state):
  - deterministic classifier path
  - existing `_handle_ask` flow and gap handling
  - Tier2 parser/formatter path unchanged

---

## 7) Test plan

## 7.1 Unit tests

1. **LLM router schema tests**
   - mock router LLM response
   - assert strict parsing/validation for valid and invalid payloads
2. **Routing execution tests**
   - verify `tier_recommendation` maps to correct tier calls
   - verify fallback to Tier3 on router parse/API failure
3. **Tier2 selection bias tests**
   - synthetic event sets across long windows
   - assert distributed selection behavior for spans >30 days

## 7.2 Integration tests

- Trace the 20 query shapes from `docs/phase-8-8-4-read-intent-comprehension-audit.md`.
- For each, assert expected tier path under flag-on mode.

## 7.3 Regression tests

- Full suite must pass with:
  - `USE_LLM_ROUTER=false`
  - `USE_LLM_ROUTER=true`

## 7.4 Manual validation gate

Post-deploy (flag on), run 12 representative queries (4 canonical + 8 additional) **3 times each**:

- routing correctness
- grounding correctness
- no confabulation

Any confabulation or severe routing mismatch fails gate.

## 7.5 Cost/latency monitoring

- Log router tokens per turn and router latency.
- Compare against baseline to confirm expected uplift is in target range.

---

## 8) Risk and rollback

## 8.1 Risks

1. Router non-determinism across similar phrasing.
2. Per-turn latency increase due to additional LLM call.
3. Per-turn cost increase from router call.
4. Potential drift between router output and Tier2 execution semantics.

## 8.2 Mitigations

- Temperature `0.0`
- Strict schema validation
- deterministic fallback to Tier3 on router failure
- feature flag rollback
- parity tests under both flag states

## 8.3 Rollback

- Set `USE_LLM_ROUTER=false` and redeploy.
- No migration or data rollback required.

---

## 9) Phase ledger and docs

- Phase number: **8.8.4**
- Parallel to 8.9; neither blocks the other.

Docs to update during implementation phase:

- `docs/START_HERE.md`
- `HAVA_CONCIERGE_HANDOFF.md` §5
- `docs/known-issues.md`
- `docs/pre-launch-checklist.md`

Deferred candidate:

- **8.8.5** semantic answerability check (Tier2 rows may exist but not answer intent).

---

## 10) Implementation file list

## 10.1 New files

- `app/chat/llm_router.py` (new router module)
- `prompts/llm_router.txt` (router system prompt)
- `tests/test_llm_router.py` (router unit tests)
- `tests/test_llm_router_integration.py` (flag-on routing tests)

## 10.2 Modified files

- `app/chat/unified_router.py` (flag wiring + router path)
- `app/chat/tier2_db_query.py` (selection bias fix)
- `app/chat/tier2_schema.py` (Tier2Filters v2 fields/validation)
- `app/chat/tier2_parser.py` (if retained for fallback/compat path)
- `tests/test_tier2_db_query.py` (new selection tests)
- `tests/test_tier2_routing.py` (flag on/off routing coverage)
- `tests/test_unified_router.py` (router path assertions)

## 10.3 Deferred deletion list (not in 8.8.4)

- Deterministic classifier/routing removal is deferred until post-soak phase.
- `_EXPLICIT_REC_PATTERNS` cleanup deferred.
- legacy parser-only routing cleanup deferred.

---

## 11) Proposed router prompt sketch (for implementation authoring)

Router prompt should require:

1. JSON-only output.
2. Exact schema with typed fields.
3. Clear rules for temporal extraction mapping (months, seasons, explicit dates/ranges).
4. Tier recommendation policy:
   - `1` when direct entity lookup intent and entity present
   - `2` for structured retrieval-capable asks
   - `3` for open-ended synthesis/recommendation/discovery
   - `gap` only when intent is clear but catalog answerability likely absent
5. Conservative fallback flagging (`fallback_to_tier3`) when extraction uncertain.

Final prompt text should be authored in implementation phase and checked into `prompts/llm_router.txt`.

---

This document is a draft spec for owner approval. No code or prompt changes are included in this phase.
