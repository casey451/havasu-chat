# Phase 8.8.4 — HALT 4 Follow-up (Failure Classification + Test Policy)

Date: 2026-04-25  
Scope: Postmortem of `USE_LLM_ROUTER=true` full-suite failures during Step 4 integration.

## 1) Classification of 17 flag-on failures

### Category A — deterministic-path implementation detail (correct to scope to flag-off)

1. `tests/test_classifier_hint_extraction.py::test_extract_hints_openai_failure_still_returns_ask_response` — **A**
2. `tests/test_gap_template_contribute_link.py::test_date_lookup_gap_includes_contribute` — **A**
3. `tests/test_gap_template_contribute_link.py::test_location_lookup_gap_includes_contribute` — **A**
4. `tests/test_gap_template_contribute_link.py::test_hours_lookup_gap_includes_contribute` — **A**
5. `tests/test_phase38_gap_and_hours.py::test_catalog_gap_skips_tier3[What are the hours for zzznonexistent999xyz?-HOURS_LOOKUP]` — **A**
6. `tests/test_phase38_gap_and_hours.py::test_catalog_gap_skips_tier3[Where is Totally Fictional Venue XYZ?-LOCATION_LOOKUP]` — **A**
7. `tests/test_phase38_gap_and_hours.py::test_catalog_gap_skips_tier3[When is the zzznonexistentevent999abc?-DATE_LOOKUP]` — **A**
8. `tests/test_phase38_gap_and_hours.py::test_post_api_chat_gap_template_contract` — **A**
9. `tests/test_prior_entity_router.py::test_recommended_capture_tier2_single_provider` — **A**
10. `tests/test_tier2_routing.py::test_open_ended_tier2_happy_path_logs_split_tokens` — **A**
11. `tests/test_tier2_routing.py::test_tier1_none_invokes_tier2_then_tier3` — **A**
12. `tests/test_tier2_routing.py::test_gap_template_runs_after_tier2_no_rows` — **A**
13. `tests/test_unified_router.py::test_ask_tier3_when_tier1_misses` — **A**
14. `tests/test_unified_router.py::test_explicit_rec_bypasses_tier2_to_tier3[What should I do Saturday?]` — **A**
15. `tests/test_unified_router.py::test_non_trigger_keeps_tier2_path` — **A**
16. `tests/test_unified_router.py::test_record_entity_failure_still_returns_answer` — **A**

Reasoning: these tests patch deterministic internals (`try_tier2_with_usage`, `answer_with_tier3`) and/or assert deterministic `tier_used` flow that no longer applies when router-on branch runs first.

### Category B — semantically equivalent user behavior but different exact text

- None observed in this run.  
  Count: **0**

### Category C — user-visible behavior that is wrong/worse

1. `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results` — **C (pre-existing baseline failure, not introduced by Step 4)**

Count summary:
- Category A: **16**
- Category B: **0**
- Category C: **1** (same known pre-existing `test_phase3` issue)

## 2) Test policy going forward

### Legacy deterministic suites

Suites that validate deterministic classifier/legacy Tier 2 ask-flow behavior are pinned to:

- `USE_LLM_ROUTER=false` via an autouse fixture.

This preserves their original contract and prevents false negatives when router-on flow is intentionally different.

### Router-on suites

Tests targeting router-on behavior must:

- explicitly set `USE_LLM_ROUTER=true`, and
- mock `llm_router.route(...)` to deterministic `RouterDecision` fixtures.

This avoids incidental coupling to live model behavior and ensures route intent is under test control.

## 3) Pre-existing `test_phase3` failure note

### First observed

Observed during full-suite runs in Step 4 validation under both flag states:

- `USE_LLM_ROUTER=false` full run: fails.
- Clean baseline check (`git stash -u`, run `tests/test_phase3.py`, `git stash pop`): fails.

### What we know

- Failure reproduces on baseline without Step 4 working tree changes.
- Test assertion expects weekend search response to include seeded `"Basketball Clinic"` rows.
- Actual response in failing run: `"Nothing on for that time. Want to peek at what's coming up later?"`
- This indicates a divergence between expected weekend retrieval behavior and current search output path.

### What we do not know yet

- Exact root cause (test drift vs non-test code regression vs fixture/data assumption mismatch).
- Whether failure is fully deterministic across environments/time windows or conditionally sensitive.
- Which component changed relative to the last known green baseline for this test.

### Tracking intent

Treat as a pre-existing known issue for separate triage; it is not a blocker specific to Phase 8.8.4 Step 4 router integration.
