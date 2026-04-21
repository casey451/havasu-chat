# Phase 6.4 — Session memory (implementation report)

**Branch / state:** Phase 6.4 **shipped** on `main`. This report documents what shipped plus the **known gap** below (recommended-entity capture → 6.4.1).

## What shipped

- **`app/chat/hint_extractor.py`:** `extract_hints(query)` → `ExtractedHints | None` via OpenAI `chat.completions.create` (`gpt-4.1-mini` / `OPENAI_MODEL`), JSON envelope `{"extracted_hints": ...}`. Logs warning if usage exceeds soft budget (300 in / 100 out). On failure or missing key → `None`.
- **`prompts/hint_extractor.txt`:** Guarded extraction rules + negative few-shots (per revised spec).
- **`app/core/timezone.py`:** `now_lake_havasu()`, `format_now_lake_havasu()` for **America/Phoenix** display strings.
- **`app/core/session.py`:** Extended `onboarding_hints` (`age`, `location`); `prior_entity`, `last_activity_at`, `turn_number`; `touch_session`, `update_hints_from_extraction`, `record_entity` (provider id lookup when possible).
- **`app/chat/unified_router.py`:** Per turn: `touch_session` + increment `turn_number` (when `session_id` present); heuristic `classify()` unchanged; `extract_hints` (always called); session hint merge; `_enrich_entity_from_db` extended with **pronoun + prior_entity** fallback (`current_turn - prior_entity.turn_number <= 3`); `record_entity` when resolved entity non-empty; Tier 3 gets `now_line` + full hints dict.
- **`app/chat/tier3_handler.py`:** `user_context_line_for_tier3` (comma phrases: visiting, local, with/no kids, age, location); **always** inserts `Now:` before catalog; `answer_with_tier3(..., now_line=...)`.
- **`prompts/system_prompt.txt`:** Clarification for **`Now:`** line (parallel to `User context:`).
- **`pytest.ini`:** Registered `integration` marker (opt-in real API tests).
- **`requirements.txt`:** **`tzdata==2025.2`** so `zoneinfo` IANA names work on Windows CI/agents without OS zone data.
- **Tests:** `test_session_memory.py`, `test_prior_entity_router.py`, `test_classifier_hint_extraction.py` (mocked `extract_hints`), `test_tier3_user_text_context.py`, `test_classifier_hint_extraction_integration.py` (`@pytest.mark.integration`, skips without `OPENAI_API_KEY`). Updated `test_api_chat_onboarding.py` for extended hints shape.

## Pre-flight / architecture notes

- **Handoff §2.5 inconsistency (parked):** Handoff text implied an LLM-backed intent classifier; production code uses **heuristic** `classify()`. Phase 6.4 adds a **separate** hint LLM instead of rewriting intent. **Follow-up:** owner chooses whether to update handoff prose or introduce an LLM-backed classifier in a later phase.
- **IntentResult / classifier schema extension:** **Dropped** per decision; hints flow only through `hint_extractor`.

## Test counts

| Before | After |
| --- | ---: |
| 688 passing | **708** passing |
| — | **5** skipped (integration module without `OPENAI_API_KEY`) |

Default `pytest -q` does **not** require OpenAI; integration file skips cleanly.

## Pytest marker configuration

- **File:** `pytest.ini` (repo root).  
- **Why:** No `pyproject.toml` / `setup.cfg` pytest section existed; `pytest.ini` is the smallest explicit place to register `integration` and avoid “unknown marker” warnings.

## Classifier / hint token reporting

- **Pre-flight:** No legacy “classifier LLM” baseline (intent is heuristic).  
- **This delivery:** Log a **post-ship** sample of `hint_extractor` mean `prompt_tokens` / `completion_tokens` over 20+ dev turns (e.g. from logs or a short script); soft STOP threshold in code is **warning** above 300 in / 100 out per call (per revised trigger).

## Voice spot-check

- **Not re-run in this implementation pass** (time/network). Run before commit/ship:  
  `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py` — gate **≥ 19/1/0** per handoff.

## Integration tests (real OpenAI)

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_classifier_hint_extraction_integration.py -m integration
```

With `OPENAI_API_KEY` set; expect occasional LLM variance (owner guidance: ≥4/5).

## Files touched (summary)

- `app/chat/hint_extractor.py` (new)
- `app/chat/unified_router.py`
- `app/chat/tier3_handler.py`
- `app/core/session.py`
- `app/core/timezone.py` (new)
- `prompts/hint_extractor.txt` (new)
- `prompts/system_prompt.txt`
- `requirements.txt`
- `pytest.ini` (new)
- `tests/test_session_memory.py` (new)
- `tests/test_prior_entity_router.py` (new)
- `tests/test_classifier_hint_extraction.py` (new)
- `tests/test_classifier_hint_extraction_integration.py` (new)
- `tests/test_tier3_user_text_context.py` (new)
- `tests/test_api_chat_onboarding.py`
- `tests/test_tier3_handler.py`
- `docs/phase-6-4-session-memory-report.md` (this file)

## Known gap — Tier 3 recommended-entity capture

**Observed behavior:** Pronoun / “it” resolution against `prior_entity` works when the **user** names a business or place in their query (intent path populates `IntentResult.entity`, then `record_entity` runs). It does **not** reliably work when turn 1 is an **open-ended** question and the **concierge** recommends a venue from Tier 3 context alone — e.g. production smoke: after a Tier 3 answer recommending Altitude, “What time does it open?” did not bind to that recommendation.

**Root cause:** `record_entity` is only invoked when `IntentResult.entity` (or equivalent resolved entity from the user utterance) is populated. Tier 3 synthesis can name a venue from catalog context **without** going through that intent extraction path, so `prior_entity` can remain **unset** for that turn even though the response discussed a specific place.

**Staging:** **Phase 6.4.1** — separate design (how to capture primary recommended entity from Tier 3 output or router without breaking §8 / cost) plus implementation prompt. **Not** a blocker for Phase 6.4 closure; user-named prior-entity remains the supported case until 6.4.1 ships.

## Suggested commit message (when approved)

`Phase 6.4: session memory (hints, prior-entity, date injection)` — **landed** on `main` (post-6.4 doc updates use their own commit messages).

---

*Manual dev checks from original acceptance list (long conversational strings, browser prior-entity UX) were not executed in this pass.*
