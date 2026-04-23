# Phase 8.3 — Error-path testing (read-first report)

**Date:** 2026-04-22  
**Repo:** `c:\Users\casey\projects\havasu-chat`  
**HEAD:** `66e3568` (Phase 8.0.7)  
**Mode:** Read-only inspection + proposed test plan. **No** code edits, **no** new tests, **no** commit.

---

## Pre-flight

| Check | Spec | Actual | Result |
|--------|------|--------|--------|
| `git log --oneline -1` | `66e3568` Phase 8.0.7 | `66e3568 Phase 8.0.7: reconcile known-issues.md...` | **PASS** |
| `git status` | Clean or only `docs/phase-9-scoping-notes-2026-04-22.md` untracked | `?? docs/phase-9-scoping-notes-2026-04-22.md` only (before this report file) | **PASS** |
| `pytest -q` | 759 passing | `759 passed, 3 subtests passed` | **PASS** |

**STOP triggers (prompt list):** None fired — no unhandled-exception-only paths found on the main `/api/chat` ask stack that bypass `unified_router.route`’s outer `try`/`except`; Tier 2/3 Anthropic failures return `None` / fallback rather than raising; enrichment failures are caught in `enrich_contribution`. **Mocking is compatible** with §3.11-style tests (existing `MagicMock` + `patch.object(anthropic, "Anthropic")` + `patch("app.chat.unified_router.*")` patterns).

---

## 1) §3.11 error-path inventory in code

Handoff **`HAVA_CONCIERGE_HANDOFF.md` §3.11** (lines ~527–533) lists five behaviors. Below: **implementation locus**, **actual behavior**, and **note vs verbatim §3.11 text**.

### 1.1 Tier 1 fails → fall through to Tier 2 silently

| Item | Detail |
|------|--------|
| **Code** | `app/chat/tier1_handler.py` — `try_tier1(...) -> str \| None`. Returns **`None`** when entity missing, sub_intent not in Tier‑1 set, provider row missing, `render()` returns `None`, missing slots (hours/phone/etc.), OPEN_NOW unparseable, etc. Docstring still says “fall through to Tier **3**”; **router behavior is Tier **2** first** (unless explicit-rec bypass). |
| **Router** | `app/chat/unified_router.py` **`_handle_ask`**: `tier1 = try_tier1(...)` → if `tier1 is not None` return tier `"1"`; else (unless `_is_explicit_rec`) call `try_tier2_with_usage`, then Tier 3. **No user-facing “I didn’t understand”** on Tier‑1 miss. |
| **§3.11 match** | **Yes** — silent fallthrough. Wording nit: fallthrough is to **Tier 2**, not straight to Tier 3. |

### 1.2 Tier 2 fails → fall through to Tier 3 silently

| Item | Detail |
|------|--------|
| **Code** | `app/chat/tier2_handler.py` — `try_tier2_with_usage` returns **`(None, None, None, None)`** on: empty query; parser `(None,…)`; `fallback_to_tier3`; confidence `< TIER2_CONFIDENCE_THRESHOLD` (0.7); **zero DB rows**; formatter `text is None`. Each path **`logging.info`** with a reason string. |
| **Anthropic (Tier 2)** | `app/chat/tier2_parser.py` — `except Exception` around `messages.create` → `(None,…)`. `tier2_formatter.py` — same pattern; also `OSError` on missing prompt file → `None`. Missing `ANTHROPIC_API_KEY` → `None` (parser/formatter). |
| **Router** | `_handle_ask`: if `t2_text is not None` return tier `"2"`; else `answer_with_tier3(...)`. |
| **§3.11 match** | **Yes** — silent Tier 3 continuation. |

### 1.3 Tier 3 fails → graceful error + log; admin alert if rate exceeds threshold

| Item | Detail |
|------|--------|
| **Code** | `app/chat/tier3_handler.py` — `FALLBACK_MESSAGE = "Something went sideways on my end — try that again in a sec."` (**shorter** than handoff §3.11, which adds *“or call the business directly if you're in a hurry.”*). `unified_router.py` defines **`_GRACEFUL`** with the **same short string** for normalize/classify/mode-handler failures. |
| **Tier 3 paths** | No API key → fallback. `ImportError` on anthropic → fallback. **`messages.create`** wrapped in `try/except Exception`** → `logging.exception` → fallback. Empty assistant text → fallback. `answer_with_tier3` docstring: **“Never raises”** for the Anthropic branch; **`build_context_for_tier3`** and prompt assembly run **outside** that inner `try` — DB/context failures **propagate** to `unified_router`’s handler `try/except`, which returns **`_GRACEFUL`**. |
| **HTTP** | `/api/chat` returns **200** with JSON body containing the graceful string (see `tests/test_phase2_integration.py`). |
| **Logging** | Failures use `logging.exception` / `logging.info` as appropriate. |
| **Admin alert / rate threshold** | **Not found** in codebase (no counter, no hook to admin notification for Tier‑3 error rate). **Gap vs §3.11** — **spec / product**, not a missing test only. |
| **§3.11 match** | **Partial** — user-facing grace + logging **yes**; verbatim copy + **admin rate alert** **no**. |

### 1.4 Intake fails mid-flow → preserve partial state + regroup copy

| Item | Detail |
|------|--------|
| **Chat concierge** | `app/chat/unified_router.py` **`_handle_contribute`** returns a **placeholder** string: *“Contribute mode: … Intake flow will be implemented in Phase 4.”* — **not** a live intake state machine. |
| **Legacy Track A** | `app/chat/router.py` — `_handle_missing_field_reply`, `FIELD_PROMPTS`, retry counts, `REVIEW_OFFER_MESSAGE`, `MISSING_FIELD_GLITCH`, etc. This is **add-event style** intake on **`POST /chat`**, not §3.6 “chat-based intake” on unified concierge. |
| **§3.11 applicability** | **Unified `/api/chat` contribute mode:** **N/A** (no mid-flow intake to fail). **Track A add-event flow:** **partially analogous** (retries + regroup-style copy on field errors); **not** wired to `log.error` + exact §3.11 quote. |
| **Recommendation** | Phase **8.3 tests** should **scope intake** to: **(A)** document N/A for unified contribute placeholder, **optional (B)** Track A field-retry tests if owner wants §3.11 extended to Track A. |

### 1.5 Correction fails sanity check → polite rejection

| Item | Detail |
|------|--------|
| **Unified** | `_handle_correct` → *“Correct mode: received. Correction flow will be implemented in Phase 5.”* **No** sanity-check path. |
| **Known issues** | Correction flow still **deferred** post–8.0.7 handoff narrative. |
| **§3.11 applicability** | **N/A** for unified concierge correction. |

---

## 2) External-dependency mocking infrastructure

| Dependency | Mechanism | Where / how used |
|------------|-----------|------------------|
| **Anthropic (Tier 2 / Tier 3)** | `unittest.mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "…"})` + **`patch.object(anthropic, "Anthropic", return_value=fake_client)`** with `MagicMock` and `messages.create` return or `side_effect`. | `tests/test_tier3_handler.py` (canonical), `tests/test_tier2_formatter.py`, `tests/test_tier2_parser.py` (real key in env + mocked client where needed). |
| **OpenAI** | Used in **`app/chat/hint_extractor.py`** (`gpt-4.1-mini` JSON), **`app/core/extraction.py`**, **`app/core/search.py`** — **not** in `intent_classifier.classify()` (deterministic regex + `match_entity_with_rows`). | Integration: `tests/test_classifier_hint_extraction_integration.py` (real API, `-m integration`). Unit paths: mock **`extract_hints`** at **`app.chat.unified_router.extract_hints`** (`tests/test_classifier_hint_extraction.py`, `test_unified_router.py`). |
| **“Classifier” for §8.3 prompt** | **`classify`** is pure Python — “kill OpenAI” maps to **hint extraction** and any **Tier 2/3** paths; **mock `classify`** only simulates **exceptions**, not OpenAI outage. | `patch("app.chat.unified_router.classify", …)` widely used. |
| **Database “slow”** | **No** dedicated slow-DB or pool-exhaustion fixture found. Tests use **`SessionLocal()`** + in-memory/SQLite per project defaults. | **Gap for 8.3** — would need **new** pattern (e.g. `patch` session execute delay, or transaction lock) if slow DB is in scope. |
| **Google Places / URL fetch (enrichment)** | `patch("app.contrib.enrichment.fetch_url_metadata", …)` and `lookup_provider`. | `tests/test_enrichment.py`, `tests/test_url_fetcher.py`, `tests/test_places_client.py`. |

**Infrastructure verdict:** **Sufficient** for Anthropic failure + router integration tests. **OpenAI** mocking should target **`hint_extractor`** / **`extract_hints`**, not `classify`. **Slow DB** = **new infra** if required.

---

## 3) Existing test coverage inventory (§3.11-relevant)

### Tier 1 → Tier 2 silent

| Test | File | What it does | §3.11 assertion quality |
|------|------|----------------|-------------------------|
| Tier 1 happy + **Tier 2 not called** | `tests/test_tier2_routing.py::test_tier1_unchanged_no_llm_tokens` | Real `try_tier1` success; patches `try_tier2` and asserts **`assert_not_called`**. | Confirms Tier‑1 short-circuit; **not** Tier‑1-miss → Tier‑2 invocation. |
| Tier 2 / Tier 3 routing | `tests/test_tier2_routing.py::test_open_ended_tier2_none_falls_back_to_tier3` | Patch `try_tier2_with_usage` → `None`, Tier 3 stub. | Asserts **`tier_used == "3"`** and response — **silent fallthrough** from Tier‑2 failure side; **Tier 1 not explicitly asserted**. |
| `test_ask_tier3_when_tier1_misses` | `tests/test_unified_router.py` | Patch Tier 2 `None`, Tier 3 stub; real classify. | End-to-end **Tier 3** when Tier 2 fails; **does not spy on `try_tier1`**. |
| `try_tier1` unit returns `None` | `tests/test_tier1_handler.py` | Many cases for `None` / success. | **Unit-only**; not router silence. |

### Tier 2 → Tier 3 silent (failure modes)

| Test | File | Failure mode | Notes |
|------|------|--------------|-------|
| `test_try_tier2_with_usage_*` / `test_answer_with_tier2_*` | `tests/test_tier2_handler.py` | Parser `None`, low confidence, empty rows, formatter `None` | **Unit** coverage of return `None`. |
| `test_open_ended_tier2_none_falls_back_to_tier3` | `tests/test_tier2_routing.py` | Tier 2 returns `None` | **Integration** with `route()`. |
| Parser/formatter tests | `tests/test_tier2_parser.py`, `tests/test_tier2_formatter.py` | Mocked Anthropic; invalid JSON, etc. | **Does not** go through `unified_router` for Anthropic **transport** errors. |

### Tier 3 graceful + router graceful

| Test | File | Condition | Asserts |
|------|------|-----------|---------|
| `test_missing_api_key_graceful` / `test_api_exception_graceful` / `test_empty_assistant_text_graceful` | `tests/test_tier3_handler.py` | No key, `RuntimeError` on create, empty text | `text == FALLBACK_MESSAGE` |
| `test_ask_tier3_no_tokens_when_handler_returns_none` | `tests/test_unified_router.py` | Tier 3 returns fallback tuple | `tier_used == "3"`, tokens `None` |
| `test_classify_raises_still_logs_and_graceful` | `tests/test_unified_router.py` | `classify` raises | Exact **`_GRACEFUL`** short string |
| `test_mode_handler_raises_graceful` | `tests/test_unified_router.py` | `_handle_ask` raises | Substring “Something went sideways” |
| `test_classify_raises_second_call_graceful_e2e` | `tests/test_phase2_integration.py` | Patched classify boom on 2nd call | HTTP 200 + sideways + `chat_logs` |

### Intake / correction (§3.11)

| Area | Tests | Notes |
|------|-------|-------|
| Unified contribute/correct | `tests/test_unified_router.py::test_contribute_placeholder_*`, `test_correct_placeholder` | **Placeholder copy only** — no failure/regroup semantics. |
| Track A add-event | Various in `tests/test_router.py` / phase tests (not re-listed exhaustively here) | **Separate** from unified §3.11 promise unless scope expands. |

### Hint extraction (OpenAI) failure

| Test | File | Notes |
|------|------|-------|
| `extract_hints` mocked / integration | `test_classifier_hint_extraction.py`, `test_unified_router` (patches), optional real `test_classifier_hint_extraction_integration.py` | **`hint_extractor`** catches exceptions and returns **`None`** (`app/chat/hint_extractor.py`); **`unified_router`** wraps `extract_hints` in **`try/except`** and logs — **continues**. **No** dedicated test asserting “route still returns 200 when OpenAI hints fail” may exist — **gap to confirm** in implement (grep suggests mostly mock `return_value=None`, not `side_effect=Exception`). |

---

## 4) Gap analysis (table)

| §3.11 path | Coverage | Rationale |
|------------|----------|-----------|
| Tier 1 fail → Tier 2 silent | **Partial** | Tier‑1 **success** skips Tier‑2 (`test_tier2_routing`). Tier‑2 `None` → Tier‑3 covered. **Missing:** explicit **`try_tier1` returns `None` → `try_tier2_with_usage` invoked** spy test on `route()` (non–explicit-rec query). |
| Tier 2 fail → Tier 3 silent | **Partial** | Unit handler covers parser/formatter/rows/confidence. **Missing:** **`tier2_parser` / `tier2_formatter` Anthropic `messages.create` exception** → `try_tier2_with_usage` → **`route()` ends at Tier 3** (integration). |
| Tier 3 fail → graceful message | **Partial** | Strong **`tier3_handler`** + some router tests. **Missing:** **`POST /api/chat` e2e** with Tier 3 path failing (mock `answer_with_tier3` or Anthropic at router boundary) asserting body + `tier_used`. **Copy vs handoff:** short message only — **document** or align in product pass. |
| Tier 3: log + admin rate alert | **Uncovered** / **spec gap** | Logging exists; **no rate-based admin alert** implementation. |
| Intake mid-flow failure | **N/A** (unified) | Placeholder contribute. Optional **Track A** scope. |
| Correction sanity failure | **N/A** | Not shipped on unified path. |
| `classify` exception | **Covered** | Router + e2e tests. |
| `normalize` / session touch / `record_entity` / hint extraction exceptions | **Partial** | Normalize failure → `_GRACEFUL` (**no** dedicated test found beyond classify). Hint extraction → swallowed; **weak** test for `side_effect=Exception` on **`extract_hints`**. |
| Explicit-rec bypass Tier 2 | **Covered** | `tests/test_unified_router.py` parametrized explicit-rec tests. |
| Enrichment / Places / URL | **Covered** (contrib scope) | `test_enrichment.py`, url/places tests — **outside** ask-tier §3.11 unless owner extends Phase 8.3 scope. |
| Rate limit (`slowapi`) | **Separate** | Existing rate-limit tests; **not** Tier graceful copy. |
| Entity matcher empty | **Implicit** | Normal operation; **no** test named for “empty matcher → still graceful ask response”. |

---

## 5) Additional failure modes (not literal §3.11 bullets)

| Finding | Behavior today | Owner decision |
|-----------|----------------|----------------|
| **Graceful string shorter than §3.11** | `tier3_handler` / `unified_router` use  short fallback. | Extend copy to **match handoff verbatim** vs keep short UX — **docs vs code** decision. |
| **No admin alert on Tier‑3 error rate** | Not implemented. | **Defer**, add to Phase 9+ ops, or implement minimal counter + log threshold — **product**. |
| **`intent_classifier` has no OpenAI** | Phase 8.3 triage doc says “kill OpenAI (mock)” for classifier — **current code** uses **regex-only `classify()`**. | Rephrase 8.3 scope to **hint extraction + embeddings callers** or **regression test** if OpenAI is reintroduced to classify later. |
| **DB errors inside `build_context_for_tier3`** | Propagate to `unified_router` → `_GRACEFUL`. | **Optional** test with patched DB session raising. |
| **`log_unified_route` failure** | Caught in `_finish` inner `try`; still returns `ChatResponse`. | Low priority; **optional** test. |
| **Contribution enrichment** | `enrich_contribution` broad `except` + rollback. | Already tested; **optional** §3.11 appendix if scope includes “background failures never crash request path”. |

**STOP (scope too large):** **Not triggered** — core gaps are **concentrated** in router integration + Tier‑2 Anthropic transport + optional hint/OpenAI + handoff copy/alert spec. **Est. 12–22** new tests cover it without a multi-phase split **if** slow DB and full Track A intake are **out of scope**.

---

## 6) Proposed 8.3-implement test plan

**Target file(s):** primarily **`tests/test_unified_router.py`** and **`tests/test_tier2_routing.py`**; optionally **`tests/test_api_chat.py`** or **`tests/test_phase2_integration.py`** for HTTP e2e; one test in **`tests/test_hint_extractor.py`** (new) if file exists — else **`tests/test_classifier_hint_extraction.py`**.

**Estimated new tests:** **14–20** (within 10–30 band).

| # | Proposed test name (suggested) | File | Mock setup | Assert | §3.11 / extra |
|---|-------------------------------|------|------------|--------|----------------|
| 1 | `test_tier1_none_invokes_tier2_then_tier3` | `test_tier2_routing.py` | `patch("app.chat.unified_router.try_tier1", return_value=None)`, Tier 2 returns success stub | `try_tier2_with_usage` called (wrap with `MagicMock(wraps=real)` or patch object), `tier_used=="2"` | Tier 1 miss → Tier 2 |
| 2 | `test_tier1_none_tier2_none_silent_tier3` | `test_tier2_routing.py` | Both patched `None` / stubs | No error substring like “didn’t understand”; `tier_used=="3"` | Silent fallthrough chain |
| 3 | `test_tier2_parser_anthropic_error_falls_through_to_tier3_route` | `test_tier2_routing.py` | Patch `app.chat.tier2_parser.parse` to call real impl **or** patch `anthropic.Anthropic` inside parser module + `side_effect` | End `tier_used=="3"` with stubbed Tier 3 | Tier 2 transport fail |
| 4 | `test_tier2_formatter_anthropic_error_falls_through_route` | `test_tier2_routing.py` | Similar for `tier2_formatter.format` path (rows non-empty, formatter raises) | `tier_used=="3"` | Formatter API fail |
| 5 | `test_explicit_rec_still_skips_tier2_when_parser_would_fail` | `test_unified_router.py` | Optional: ensure explicit-rec query + parser mock error still never calls Tier 2 | `tier_used=="3"` | Locks 8.0.2 behavior under stress |
| 6 | `test_api_chat_tier3_graceful_when_anthropic_fails` | `test_phase2_integration.py` or `test_api_chat.py` | `TestClient` + `patch.object(anthropic, "Anthropic", …)` on **`tier3_handler`** import path | `status_code==200`, `"Something went sideways"` in JSON, `tier_used=="3"` | E2e Tier 3 §3.11 |
| 7 | `test_api_chat_graceful_when_build_context_raises` | same | Patch `build_context_for_tier3` `side_effect=RuntimeError` | `200`, graceful body, **`placeholder`** tier from router except path | DB/context failure |
| 8 | `test_normalize_failure_returns_graceful` | `test_unified_router.py` | `patch("app.chat.unified_router.normalize", side_effect=ValueError)` | Response equals **`_GRACEFUL`**, `tier_used=="placeholder"` | Router edge |
| 9 | `test_extract_hints_openai_failure_still_ask_200` | `test_classifier_hint_extraction.py` | `patch("app.chat.unified_router.extract_hints", side_effect=RuntimeError("openai down"))` + stub Tier paths | `route()` returns normal ask/tier; **no** raise | OpenAI kill scenario for hints |
| 10 | `test_record_entity_failure_still_returns_answer` | `test_unified_router.py` | `patch("app.chat.unified_router.record_entity", side_effect=RuntimeError)` | 200-equivalent `ChatResponse`, logging not required assert | Resilience |
| 11 | `test_tier2_low_confidence_logs_and_tier3` | `test_tier2_handler.py` or routing | Already partially in unit tests — add **integration** one-liner if missing | `tier_used=="3"` | Confidence path |
| 12 | `test_tier3_fallback_message_matches_constant` | `test_tier3_handler.py` | Assert exact string vs **`FALLBACK_MESSAGE`**; **optional** second test for handoff **full** sentence if product updates copy | Doc sync |
| 13 | `test_unified_router_logs_placeholder_on_classify_fail` | `test_unified_router.py` | Already have message assert — extend to **`sub_intent is None`** on classify fail | chat_logs row (existing pattern) | Logging |
| 14 | **Optional slow DB** | new `tests/test_db_resilience.py` | `patch` `Session.execute` sleep — **flaky risk**; consider **skip** unless infra agreed | Timeout / grace | **Flag** — may defer |

**Not proposed as 8.3-implement blockers:** full **slowapi** suite duplication; full **enrichment** re-test (already covered); **correction** sanity (N/A); **admin rate alert** (no code — **separate** task).

---

## 7) One-paragraph summary (for owner)

**Pre-flight passed** (`66e3568`, clean tree modulo `phase-9` notes, **759** tests). **§3.11 Tier 1→2 and Tier 2→3** behavior is **implemented** as **`None`**-driven silent fallthrough in **`_handle_ask`** with Tier‑2 Anthropic failures returning **`None`** in parser/formatter; **Tier 3** returns a **short** sideways fallback and **`route()`** wraps broader failures in the same string. **Gaps:** **no** explicit integration test that **Tier‑1 `None` invokes Tier‑2**; **no** `route()`-level test that **Tier‑2 Anthropic transport failure** lands on **Tier 3** without user error copy; **no** **`extract_hints` OpenAI failure** surfacing as still-graceful ask; **handoff §3.11** **longer** fallback string and **admin error-rate alerting** are **not** in code. **Intake / correction** lines in §3.11 are **N/A** on **`POST /api/chat`** as shipped (**placeholders**). **STOP:** none on “unmockable” or “unhandled only” — existing **`MagicMock` + `patch.object(anthropic, "Anthropic")`** patterns are enough. **Proposed 8.3-implement:** **~14–20** focused tests (mostly **`test_tier2_routing.py`** / **`test_unified_router.py`** / one **`TestClient`** Tier‑3 failure case). **Report path:** `docs/phase-8-3-read-first-report.md` (**local, uncommitted**).

---

## 8) Post-save working tree

After adding this file: expect **`?? docs/phase-8-3-read-first-report.md`** plus any existing **`?? docs/phase-9-scoping-notes-2026-04-22.md`**. **No** tracked file modifications.
