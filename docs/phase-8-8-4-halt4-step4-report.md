# Phase 8.8.4 — HALT 4 (Step 4 Integration Report)

## `_handle_ask` integration logic (verbatim)

```python
def _handle_ask(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    onboarding_hints: dict | None = None,
    now_line: str | None = None,
    allow_tier3_fallback: bool = True,
    router_meta: dict | None = None,
) -> tuple[str | None, str, int | None, int | None, int | None]:
    tier1 = try_tier1(query, intent_result, db)
    if tier1 is not None:
        return tier1, "1", None, None, None
    if _use_llm_router():
        context: dict[str, object] = {}
        if onboarding_hints:
            context["onboarding_hints"] = onboarding_hints
        if now_line:
            context["now_line"] = now_line
        if (intent_result.entity or "").strip():
            context["prior_entity"] = intent_result.entity
        decision = llm_router.route(query, intent_result.normalized_query, context or None)
        if decision is None:
            text, total, tin, tout = answer_with_tier3(
                query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
            )
            return text, "3", total, tin, tout
        if router_meta is not None:
            router_meta["mode"] = decision.mode
            router_meta["sub_intent"] = decision.sub_intent
            router_meta["entity"] = decision.entity
        routed_intent = replace(
            intent_result,
            mode=decision.mode,
            sub_intent=decision.sub_intent,
            entity=decision.entity,
        )
        if decision.tier_recommendation == "2" and decision.tier2_filters is not None:
            t2_text, t2_total, t2_in, t2_out = try_tier2_with_filters_with_usage(
                query, decision.tier2_filters
            )
            if t2_text is not None:
                return t2_text, "2", t2_total, t2_in, t2_out
            if not allow_tier3_fallback:
                return None, "placeholder", None, None, None
            text, total, tin, tout = answer_with_tier3(
                query, routed_intent, db, onboarding_hints=onboarding_hints, now_line=now_line
            )
            return text, "3", total, tin, tout
        text, total, tin, tout = answer_with_tier3(
            query, routed_intent, db, onboarding_hints=onboarding_hints, now_line=now_line
        )
        return text, "3", total, tin, tout
    if _is_explicit_rec(query):
        text, total, tin, tout = answer_with_tier3(
            query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
        )
        return text, "3", total, tin, tout
    t2_text, t2_total, t2_in, t2_out = try_tier2_with_usage(query)
    if t2_text is not None:
        return t2_text, "2", t2_total, t2_in, t2_out
    if not allow_tier3_fallback:
        return None, "placeholder", None, None, None
    text, total, tin, tout = answer_with_tier3(
        query, intent_result, db, onboarding_hints=onboarding_hints, now_line=now_line
    )
    return text, "3", total, tin, tout
```

## What was changed

- `app/chat/unified_router.py`
  - Added env flag read via `_use_llm_router()`.
  - In ask-mode after Tier1 miss:
    - Flag off: existing classifier/explicit-rec/Tier2/Tier3 flow unchanged.
    - Flag on: calls `llm_router.route(...)`.
      - `None` => Tier3 direct fallback.
      - Tier2 decision => parser-bypass Tier2 execution with router filters.
      - Tier3 decision => Tier3 direct.
  - Router `mode/sub_intent/entity` now flow through to final logging metadata.
- `app/chat/tier2_handler.py`
  - Added `try_tier2_with_filters_with_usage(query, filters)` (DB+formatter only; no parser call).
- `tests/test_llm_router_integration.py` (new)
  - Covers:
    - flag-on Tier2 route with parser bypass,
    - flag-on Tier3 route,
    - flag-on router failure => Tier3 fallback,
    - flag-off legacy path,
    - Tier1 fast-path under both flag states.
- Additional legacy test stabilization
  - Added `USE_LLM_ROUTER=false` autouse fixtures to older deterministic-path suites so they continue validating legacy behavior explicitly:
    - `tests/test_unified_router.py`
    - `tests/test_tier2_routing.py`
    - `tests/test_classifier_hint_extraction.py`
    - `tests/test_gap_template_contribute_link.py`
    - `tests/test_phase38_gap_and_hours.py`
    - `tests/test_prior_entity_router.py`

## Pytest run summaries

- `USE_LLM_ROUTER=false` full run:
  - `1 failed, 879 passed, 3 subtests passed`
  - Failure: `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results`
- `USE_LLM_ROUTER=true` full run:
  - `17 failed, 863 passed, 3 subtests passed`
  - Failures were largely legacy deterministic-path tests expecting old flow when flag is globally true; explicit flag-off scoping was added in those suites.
- Post-fix targeted validation:
  - Router + affected suites run: `67 passed, 1 failed`
  - Remaining failure: `tests/test_prior_entity_router.py::test_recommended_then_pronoun_followup_resolves_altitude`

## Test files modified beyond new integration file

- `tests/test_unified_router.py`
- `tests/test_tier2_routing.py`
- `tests/test_classifier_hint_extraction.py`
- `tests/test_gap_template_contribute_link.py`
- `tests/test_phase38_gap_and_hours.py`
- `tests/test_prior_entity_router.py`

## Deferred observations

- Full-suite pre-existing/non-Step-4 instability remains (`test_phase3` failure under flag-off).
- One residual targeted failure remains in prior-entity follow-up (`test_prior_entity_router`).
- Known issues captured for Step 6 docs phase:
  1. Example 9 in `prompts/llm_router.txt` routes breakfast query to `OUT_OF_SCOPE` (restaurants may be in product scope).
  2. Prompt hardcodes current year `2026` for `date_exact` inference and will stale at 2027.
