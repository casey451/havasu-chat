# Phase 3.3 — End-to-End Ask-Mode Integration Tests

Implemented exactly one new end-to-end test file for `POST /api/chat` and kept pipeline code untouched.

- **New file:** `tests/test_api_chat_e2e_ask_mode.py`
- **Why this path/name matches convention:** existing HTTP route integration tests live directly under `tests/` with `test_api_chat.py` naming; this file follows the same placement and adds focused e2e coverage for ask-mode routing without modifying existing suites.

## What the new tests cover (4 tests)

- **Tier 1 path:** phone lookup request routes through normalize/classify/unified route to Tier 1 and asserts:
  - `mode == "ask"`
  - `sub_intent == "PHONE_LOOKUP"`
  - `tier_used == "1"`
  - `llm_tokens_used is None` (real implemented behavior in this repo)
  - non-empty `response`
  - `latency_ms >= 0`
- **Tier 3 path:** open-ended ask request routes to Tier 3 with Anthropic mocked; asserts:
  - `mode == "ask"`
  - `sub_intent == "OPEN_ENDED"`
  - `tier_used == "3"`
  - `response == "Mocked Tier 3 answer."`
  - `llm_tokens_used == 32` (deterministic mocked usage sum)
- **OUT_OF_SCOPE path:** weather query asserts real classifier/router behavior:
  - `mode == "chat"`
  - `sub_intent == "OUT_OF_SCOPE"`
  - `tier_used == "chat"`
- **Response contract test:** verifies full `ConciergeChatResponse` field set and runtime types.

## Mock strategy used

- Patched at the Tier 3 layer by injecting a fake `anthropic` module in `sys.modules` so `app.chat.tier3_handler.answer_with_tier3()` imports and uses the fake `Anthropic` client.
- This avoids network calls and keeps mocking at the narrow `tier3_handler.py` call boundary (no pipeline code edits).

## Test runs

- Isolated run: `.\.venv\Scripts\python.exe -m pytest tests/test_api_chat_e2e_ask_mode.py -v`
  - **4 passed**
- Full suite: `.\.venv\Scripts\python.exe -m pytest -v`
  - **389 passed**

## Required count report

- Baseline target: **385**
- Added tests: **4**
- New total: **389** (matches `385 + 4`)

## Commit and push

- **Commit message (exact):** `Phase 3.3: End-to-end ask-mode integration tests`
- **Commit SHA:** `e33313c`
- **Pushed to:** `main` (`origin/main`)

## Divergences from prompt

- **Tier 1 `llm_tokens_used` assertion:** used `None` instead of `0` because the current router implementation returns `None` for Tier 1 (`_handle_ask` returns `None` tokens on Tier 1 path).
- Added test teardown cleanup (within the new test file) for rows tagged `source="phase33-test"` to keep full-suite isolation intact.
