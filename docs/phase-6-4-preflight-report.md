# Phase 6.4 — Pre-flight report (session memory)

Pre-flight only — **no Phase 6.4 implementation**. Wait for owner **`proceed`** after reconciling the **classifier architecture mismatch** (check 2).

---

## 1. Git log (`6.4` / `session memory` / `date inject` / `prior entity`)

Ran `git log --oneline -30` filtered for `Phase 6\.4` / `6\.4 session` — **no matches**. Broader earlier scan only surfaced unrelated commits (e.g. Phase 6.3). **No prior Phase 6.4 work on `main` under those labels.**

---

## 2. `app/chat/intent_classifier.py` — schema, “gpt-4.1-mini”, pronouns

### 2a. Response shape today

- There is **no Pydantic/OpenAI response schema** for intent. Output is a **frozen `@dataclass` `IntentResult`** with: `mode`, `sub_intent`, `confidence`, `entity`, `raw_query`, `normalized_query` only.

```203:210:app/chat/intent_classifier.py
@dataclass(frozen=True)
class IntentResult:
    mode: str  # 'ask' | 'contribute' | 'correct' | 'chat'
    sub_intent: str | None
    confidence: float  # 0.0 - 1.0
    entity: str | None
    raw_query: str
    normalized_query: str
```

- **`classify()` is fully heuristic** (regex + keyword passes + `tier1_templates.INTENT_PATTERNS` + `match_entity_with_rows` for entity). **There is no gpt-4.1-mini call in this module.**

### 2b. Where a “classifier LLM” would go

- Today: **`unified_router.route`** calls `classify(nq_safe)` then `_enrich_entity_from_db` (`unified_router.py` ~222–229). Any **new** OpenAI structured call would be **additional** to current `classify()`, unless you **replace or wrap** `classify()` with an LLM-backed implementation.

- **`gpt-4.1-mini`** appears elsewhere (e.g. **`app/core/extraction.py`** for event/message extraction), **not** for intent classification on the concierge path.

### 2c. Pronoun-referent queries

- **No special pronoun handling** in `intent_classifier`. Entity comes from **`match_entity_with_rows`** on the raw query when aliases score > 75. Pronoun-only lines like “what time does it open” would typically be **`entity=None`** unless a venue name appears in the string.

---

## STOP trigger (check 2a) — reconcile before `proceed`

The Phase 6.4 draft assumes **“extend the existing gpt-4.1-mini classifier call and its output schema.”** In this repo **that call does not exist** for intent; extending `IntentResult` is straightforward, but **hint extraction cannot “piggyback” on a non-existent LLM** without one of:

- Adding a **new** OpenAI structured call on the hot path (with logging/cost), or
- Implementing hints **without** an LLM (regex/heuristics — different quality tradeoff), or
- **Replacing** heuristic `classify()` with an LLM classifier (large behavior/risk surface).

Recommend an explicit owner choice here before implementation.

---

## 3. `app/chat/entity_matcher.py` — entry point, hook, pronouns

### 3a. Entry points

- **`match_entity(query, db)`** — DB-backed cache of `Program.provider_name` + fuzzy scoring (threshold > 75).
- **`match_entity_with_rows(query, canonical_names)`** — same scoring over an explicit name list (used from `classify()` without DB).

### 3b. Where prior-entity fallback fits

- **`unified_router._enrich_entity_from_db`** already centralizes “classifier said no entity → try `match_entity`”:

```151:159:app/chat/unified_router.py
def _enrich_entity_from_db(query: str, intent_result: IntentResult, db: Session) -> IntentResult:
    if intent_result.entity is not None:
        return intent_result
    refresh_entity_matcher(db)
    hit = match_entity(query, db)
    if not hit:
        return intent_result
    name, _score = hit
    return replace(intent_result, entity=name)
```

- **Clean options:** (A) Extend this function (or a sibling in `unified_router`) with session + turn + pronoun regex **after** `match_entity` returns `None` — **minimal change to `entity_matcher`**. (B) Add **`match_entity_with_prior(...)`** (or optional args) in **`entity_matcher.py`** so all resolution logic stays in one module — **small, contained API change** (needs `Session`/`prior_entity`/turn passed in).
- **Not a huge refactor** either way; the spec’s “only in `entity_matcher`” is doable with a **new** session-aware wrapper without rewriting fuzzy core.

### 3c. Existing pronoun logic

- **None** in `entity_matcher.py` beyond normal substring matching in fuzzy ratios.

---

## 4. `app/core/session.py` — `onboarding_hints`, `last_*_at`

### 4a. Phase 6.3 pattern

- **`_default_onboarding_hints()`** returns `{"visitor_status": None, "has_kids": None}` (~31–34).
- **`clear_session_state`** seeds `"onboarding_hints": _default_onboarding_hints()` (~138).
- **`get_session`** does `setdefault("onboarding_hints", _default_onboarding_hints())` (~153).

### 4b. `last_*_at` on session root

- **No `last_activity_at`** (or similar) on the top-level session dict today.
- **Related:** `flow["awaiting_since"]` uses `datetime.now(timezone.utc).replace(tzinfo=None)` for **blocking/clarification flow**, not global activity idle.

---

## 5. `context_builder` / `tier3_handler` — `user_text`, timezone helpers

### 5a. `user_text` today (`answer_with_tier3`)

- Builds **`User query`**, **`Classifier:`** line, optional **`User context:`** from `compact_onboarding_user_context_line(onboarding_hints)`, then **catalog `context`** from `build_context_for_tier3`. There is **no `Now:`** line yet; catalog block is not prefixed with a separate “Context:” label in code (the catalog string itself starts with `Context — Lake Havasu…` from `context_builder`).

### 5b. Date/time / timezone in `app/core/`

- **No `zoneinfo` / `America/Phoenix` helper** found under `app/core/` (only naive UTC usage for `awaiting_since` in `session.py`).
- **Check 5b (no helper):** Adding **`zoneinfo` + a small helper** (e.g. `app/core/timezone.py` with `now_lake_havasu()`) is reasonable and matches “stdlib only” direction in the spec — **confirm once** if you want it under `app/core/` vs `app/chat/`.

---

## 6. `prompts/system_prompt.txt` — existing “User context” clarification (Phase 6.3)

Adjacent lines to mirror for the future **“Now:”** clarification:

```46:47:prompts/system_prompt.txt
Use only the "Context" block below for factual claims about businesses, programs, and events. Treat missing fields as unknown.
If a "User context" line appears before the Context block, treat it as a tone-and-recommendation bias signal (e.g. family-friendly when kids are along, visitor-oriented for out-of-towners). It is not a source of catalog facts — the Context block remains the only factual source.
```

---

## 7. `tests/test_intent_classifier.py` — fixtures / structure

- Large table **`_CLASSIFY_FIXTURES`**: tuples `(query, expected_mode, expected_sub_intent)` with a comment targeting **~80 rows** (Phase 2.1); **`test_classify_fixture_count` asserts `len(_CLASSIFY_FIXTURES) >= 80`**.
- **One parametrized test** drives all rows: `test_classify_modes_and_sub_intents`.
- **Four small tests** for `IntentResult` fields, entity alias, confidence.
- **New hint-extraction tests** should **not** assume an LLM inside `classify()` unless you add one; today they’d mock **`IntentResult`-shaped** outputs or a new extraction function.

---

## 8. Classifier token baseline (check 8)

### Intent “classifier” (heuristic `classify()`)

- **No LLM** → **no input/output tokens** on the intent path today. Baseline for “classifier call” in the spec’s LLM sense is **`0` mean input / `0` mean output** (or **N/A** if you only count paid API calls).

### `chat_logs` / `analyze_chat_costs.py`

- **`ChatLog`** has `llm_input_tokens` / `llm_output_tokens` for **logged router tiers** (Tier 2/3 etc.), **not** a separate “classifier” column.
- **`scripts/analyze_chat_costs.py`** aggregates by **`tier_used`**; it does **not** report intent-classifier tokens.

### Sample run (local DB, last 30 days — **not** “classifier”, for orientation only)

From `python scripts/analyze_chat_costs.py` on the workspace DB (154 rows in window):

| `tier_used` | n (split rows) | mean `llm_input_tokens` | mean `llm_output_tokens` |
| --- | ---: | ---: | ---: |
| `3` | 42 | **3186.81** | **61.36** |
| `2` | 15 | **2143.33** | **173.67** |

Use these only as **Tier 2/3** baselines. **Post-implementation “classifier delta”** should be defined once the new behavior exists (e.g. log a dedicated row or new columns for the OpenAI hint pass), or compare **total** new tokens per turn if hints share an existing logged call.

---

## Prior-entity turn math (item 11 — explicit semantics)

Documented for implementation so nothing is inverted:

- Store **`turn_number`** when `prior_entity` is recorded.
- At use time: **`current_turn - prior_entity.turn_number <= 3`** ⇒ valid on the **recorded turn and the next three turns** (four turns total, e.g. recorded on 5 → valid on 5–8, stale from 9 onward).
- Stale read: **do not use** for resolution; **do not** require clearing `prior_entity` on stale read (per spec; idle reset is separate).

---

## Tests: mock vs real LLM (items 19–20)

- **Recommendation aligns with repo needs:** default **heavy unit tests with mocks** for threading `extracted_hints` → session → Tier 3 `user_text`; **small optional integration file** with `@pytest.mark.integration` **on demand**.
- **Today:** **no** `@pytest.mark.integration` (or similar) appears under `tests/`; **no** `pytest.ini` / `pyproject.toml` markers section found in repo root — you’ll need **`pytest.ini` (or `pyproject.toml`) `markers = integration(...)`** so `-m integration` doesn’t warn and default runs exclude integration tests.

---

## Summary table: STOP triggers vs findings

| Check | Result |
| --- | --- |
| **2a** Schema / coupling | **Major mismatch:** no LLM classifier today; `IntentResult` is a small dataclass. **STOP / design fork** before coding to spec verbatim. |
| **3b** Entity matcher hook | **Feasible** in `_enrich_entity_from_db` or a thin session-aware wrapper in `entity_matcher.py`; not a large refactor. |
| **5b** Timezone helper | **None today**; **`zoneinfo` + small helper** is appropriate — quick owner nod per spec. |
| **8** Token growth > ~30% | **Baseline for intent LLM is 0**; “30% growth” applies once a **new** billed call exists — define measurement in delivery doc. |

---

**Stopped here.** Reply **`proceed`** after you decide how hint extraction should relate to the **current heuristic `classify()`** (new LLM call vs replace vs non-LLM hints).
