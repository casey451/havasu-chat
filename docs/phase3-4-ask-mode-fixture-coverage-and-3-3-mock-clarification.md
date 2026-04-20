# Session 3.3 mock clarification + Phase 3.4 completion (for Claude)

## First — session 3.3 mock strategy (process check)

We did **not** try a narrow `patch("anthropic.Anthropic", ...)` first and watch it fail. The implementation went straight to **`monkeypatch.setitem(sys.modules, "anthropic", ...)`** because `answer_with_tier3` does a **lazy `import anthropic` inside the function** (after the API-key check), so injecting a fake module before the call is a small, deterministic way to supply `anthropic.Anthropic` without depending on import order or loading the real package. A narrow patch on `anthropic.Anthropic` is still viable **after** `import anthropic` has run, but it ties you to the real package being importable; **`patch("app.chat.unified_router.answer_with_tier3", ...)`** (as in `tests/test_api_chat.py`) avoids the real Tier 3 path entirely, which did not match the “exercise `tier3_handler` + mocked client” goal for 3.3.

---

## Second — Phase 3.4 completion

### Tier 1 sub-intents handled in code

`_TIER1_SUB_INTENTS` in `tier1_handler.py`:

`TIME_LOOKUP`, `HOURS_LOOKUP`, `PHONE_LOOKUP`, `LOCATION_LOOKUP`, `WEBSITE_LOOKUP`, `COST_LOOKUP`, `AGE_LOOKUP`, `DATE_LOOKUP`, `NEXT_OCCURRENCE`, `OPEN_NOW` (**10 total**).

`tier1_templates.INTENT_PATTERNS` also lists lookup intents used by the classifier; **`LIST_BY_CATEGORY` is not Tier-1-handled** (not in `_TIER1_SUB_INTENTS`) and routes to Tier 3 when Tier 1 does not answer.

### Seed data

Default pytest DB has **no** concierge seed; coverage uses a **module-scoped fixture** that inserts `Provider` / `Program` / `Event` rows with `source="phase34-test"` (two providers: `AskAlpha Services`, `AskBeta Services`) plus teardown cleanup and `refresh_entity_matcher` / `reset_entity_matcher`.

### Existing voice helpers

Grep found **no** reusable filler/length helpers in `tests/`; helpers are **inline** in `tests/test_ask_mode.py`.

### Mock

Same pattern as `tests/test_api_chat_e2e_ask_mode.py`: fake `anthropic` module + `ANTHROPIC_API_KEY`, canned Tier 3 text and token sum.

### Distribution

**41 Tier 1 + 34 Tier 3 = 75** fixture queries (~55% / ~45%). Tier 1: **4 queries per sub-intent × 10 + 1 extra PHONE** = 41.

### Voice

No Tier 1 (or mocked Tier 3) failures on the four helpers; **no template §8.2 violations** surfaced.

### Test totals

Was **389**, now **465** (75 parametrized API cases + **1** meta test `test_fixture_counts_total_75` → **76** new tests in this file).

### Divergences

1. **`pytest` count:** The suite reports **76** tests in `test_ask_mode.py` because of the extra **`test_fixture_counts_total_75`** guard; the **75** are the parametrized fixture rows.
2. **Rate limiting:** After each test, **`app.core.rate_limit.limiter.reset()`** runs so **76** fast `/api/chat` calls do not exhaust the shared **120/min** limit and break later tests (e.g. `test_phase2_integration.py` with **429**). No `conftest.py` change.

### Commit

- **SHA:** `7c02cf5`
- **Message:** `Phase 3.4: Ask-mode fixture coverage suite (75 queries)`
- **Branch:** pushed to `main`

---

## Review checklist (owner)

1. **Contract / templates:** No voice-helper failures → **no production template violations caught** by these four checks.
2. **Distribution:** **41 / 34** with **4× per Tier-1 sub-intent + one spare PHONE**; not padded with junk lists.
3. **Helpers:** **Inline** in `tests/test_ask_mode.py` for §3.6 scope; easy to move to a shared module later for Phase 4+ reuse.
