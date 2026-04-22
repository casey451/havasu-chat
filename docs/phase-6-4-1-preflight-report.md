# Phase 6.4.1 — Pre-flight report (read-only)

Read `docs/phase-6-4-1-cursor-prompt.md` in full. Below are the **pre-flight checks** from §“Pre-flight checks” (items **1–5** with sub-items **2a–c**, **3a–c**, **4a–b**, **5a–b** — **12** discrete checks; the doc does not list “7” as a count). **No code changes** were made.

---

### 1. Git history — prior 6.4.1 **implementation** on `main`

`git log --oneline -25` scanned; `findstr /i "6.4.1 recommended prior_entity"` on the last 20 lines shows only **docs / planning / session resume** commits, e.g.:

- `34ad30d` — docs: add Phase 6.4.1 implementation prompt
- `ce64b92` — docs: Phase 6.4 known gap → 6.4.1
- `68c65cf` — docs: session resume (6.4.1 planned)

**Finding:** There is **no shipped code** on `main` for “recommended-entity capture” / `prior_entity` from Tier 2/3 responses. Recent `9f8abb0` is **test hygiene only**. Safe to treat **current `main`** as the implementation baseline (tests: **713** passing after that commit).

---

### 2. `app/chat/entity_matcher.py`

**2a. Public API (text in → name + score)**

- **`match_entity(query: str, db: Session) -> tuple[str, float] | None`** — loads/refreshes in-memory rows from distinct `Program.provider_name`, normalizes `query`, scores each canonical’s needle set with `rapidfuzz.fuzz.token_set_ratio`, returns **one** best `(provider_name, score)` or `None`.
- **`match_entity_with_rows(query, canonical_names)`** — same “single best” behavior over an explicit name list (no DB).

**2b. “Match all” vs “match best”**

- **Only “best single match”** exists today. There is **no** `match_all_entities` / sliding-window / multi-hit API.

**2c. Fuzzy threshold**

- Best score must be **strictly above `75.0`** (`best_score <= 75.0` → `None`). Doc’s “>75” matches this.

**STOP-and-ask (per prompt §STOP-and-ask triggers):** With **2b = no match-all** and **2a = single best only**, implementation must choose an approach. Options from the prompt:

| Option | Summary |
|--------|--------|
| **(a)** | Add something like `match_all_entities(text)` / `extract_catalog_entities_from_text` that iterates catalog rows and collects **all** names above threshold (with dedupe). |
| **(b)** | Repeated `match_entity` on substrings (fragile / overlapping windows). |
| **(c)** | Scan response text for every catalog name / alias and score (heavier string work, still bounded). |

**Recommendation for when you reply `proceed`:** **(a)** — aligns with the spec’s `extract_catalog_entities_from_text`, `_rows` / `refresh_entity_matcher` cache, dedupe, and clear semantics. **Please confirm (a), (b), or (c)** in your `proceed` (or “proceed with (a)”).

---

### 3. `app/chat/unified_router.py`

**3a. Where Tier 2 / Tier 3 answers are produced**

- **`_handle_ask`** (lines 99–116): Tier 1 → else **`try_tier2_with_usage(query)`** → if text present, returns **`(t2_text, "2", …)`**; else **`answer_with_tier3(...)`** → **`(text, "3", …)`**.
- **`route()`** assigns that tuple at **lines 341–343** (ask mode) or **354–356** (non-ask falling through to `_handle_ask`): variables **`text`**, **`tier_used`**, token fields.

**Natural hook for response text:** immediately **after** that assignment succeeds (inside the same `try`), when **`tier_used in ("2", "3")`**, you have the **assistant `str`** to scan before **`return _finish(...)`** at **370–378**. On **`_handle_ask` exception** path (**357–367**), do **not** run recommended capture on partial/failed tier paths unless you explicitly want that (current spec: after successful handler return).

**3b. Existing `record_entity` (user-named)**

- **Lines 306–310:** after **`_enrich_entity_from_db`**, if **`raw_sid`** and **`current_turn`** and **`intent_result.entity`** non-empty → **`record_entity(raw_sid, intent_result.entity, current_turn, db)`**.

**3c. Session / `turn_number` in scope at capture point**

- **`raw_sid`**, **`session_obj`**, **`current_turn`** are set **269–277** (when `session_id` provided).
- **`record_entity`** for user-named uses **`raw_sid`** (not the hashed `sid`). Recommended capture should use the **same** **`raw_sid`** + **`current_turn`** for consistency.
- **`db`** is in scope for the whole `route()`.

**Precedence (spec §5):** User-named **`record_entity`** runs **before** `_handle_ask`. Recommended-entity capture **after** `_handle_ask` returns **overwrites** `prior_entity` if exactly one entity is extracted — **matches** the locked “written last wins” rule **without** any contradiction in the current control flow.

---

### 4. `tier2_handler.py` & `tier3_handler.py`

**4a. Return shapes**

- **`try_tier2_with_usage(query) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]`** — **`(response_text, llm_tokens_used, llm_input_tokens, llm_output_tokens)`**; on fallback, **`text is None`**.
- **`answer_with_tier3(...) -> tuple[str, int | None, int | None, int | None]`** — **`(assistant_text, total_tokens, input_tokens, output_tokens)`**; may return fallback string with `None` tokens.

**4b. Response text**

- **Plain `str`** in both cases — **no** extra struct to unwrap for scanning. Tier 3 may return `FALLBACK_MESSAGE` string; extraction should treat that like any other text (likely **no** catalog hits).

**Assessment:** **No STOP for §4b** — not buried in a non-text shape.

---

### 5. Existing tests

**5a. `tests/test_prior_entity_router.py`**

- **6 tests** (pytest functions): **`test_prior_entity_fresh_boundary`**, **`test_enrich_pronoun_uses_prior_when_fuzzy_misses`**, **`test_enrich_explicit_entity_wins_over_prior`**, **`test_enrich_stale_prior_not_used`**, **`test_enrich_there_matches_prior`**, **`test_enrich_no_pronoun_no_prior_fallback`**.
- Uses **`db` fixture** (`SessionLocal`), imports **`_enrich_entity_from_db`**, **`_prior_entity_fresh`** — **does not** call **`route()`** today.
- **Pattern:** `IntentResult` / `replace`, in-memory **`session`** dict with **`prior_entity`** shape **`{id, name, type, turn_number}`**.

**5b. End-to-end Tier 2 / Tier 3 through `route()`**

Examples to mirror for 6.4.1 **`route()`** + patches:

- **`tests/test_unified_router.py`** — patches **`extract_hints`**, **`try_tier2_with_usage`**, **`answer_with_tier3`**.
- **`tests/test_tier2_routing.py`**, **`tests/test_phase2_integration.py`**, **`tests/test_api_chat_onboarding.py`**, **`tests/test_tier3_mention_scan.py`**, **`tests/test_api_chat_e2e_ask_mode.py`** — various **`route`** + **`unified_router`** patch stacks.

**`tests/test_entity_matcher.py`** exists for matcher unit tests (good home for **`extract_catalog_*`** unit tests per spec §8).

---

## Summary / next step

| Item | Status |
|------|--------|
| 6.4.1 implementation already on `main`? | **No** (docs + test fix only). |
| Entity matcher: multi-entity from text? | **No** — need new API (see options **a/b/c**). |
| Router hook + precedence | **Clear** — after `_handle_ask`, before `_finish`; user-named `record_entity` already earlier. |
| Tier 2/3 response text | **Plain `str`** — straightforward. |
| Prior-entity tests | **6** direct tests; extend or add file per spec. |

Per the prompt: **STOP here — do not implement until you reply `proceed`.**

When you do, **please include your choice for extraction approach (a), (b), or (c)** (or explicit “proceed with (a)”); otherwise implementation can’t finalize `extract_catalog_entities_from_text` per the STOP-and-ask rule.
