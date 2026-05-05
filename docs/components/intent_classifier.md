# intent_classifier

`app/chat/intent_classifier.py` (~250 lines)

## Purpose

Heuristic single-pass classifier that takes a raw user query and produces an `IntentResult` (mode + sub-intent + confidence + entity). Pure regex-and-string rules, no LLM call. Runs on every chat turn before any LLM cost is incurred. The unified router uses this result to pick a downstream handler (Tier 1 / Tier 2 / Tier 3 / chat) and to populate `chat_logs` analytics fields.

## Public surface

**`classify(query: str) -> IntentResult`**

The sole exported function. Pure deterministic — same input → same output, no IO, no DB.

**`IntentResult` (frozen dataclass)** — Fields: `mode` (`'ask' | 'contribute' | 'correct' | 'chat'`), `sub_intent` (string label or `None`), `confidence` (float 0.0–1.0, rounded to 3 places), `entity` (best-match canonical name or `None`), `raw_query` (input verbatim), `normalized_query` (post-normalize form). Frozen so consumers can't mutate.

## Internal structure

`classify()` is four steps:

1. **Mode detection.** `_mode_and_base_confidence(raw, nq)` runs through ordered regex patterns: `_GREETING_ONLY` → `_REAL_ESTATE_CHAT` → `_SMALL_TALK` → contribute hits → correct hits → falls through to `ask`. Returns `(mode, base_confidence, chat_hint)`.
2. **Sub-intent detection.** Mode-specific:
   - `ask` mode: `_ask_sub_intent(nq)` checks `_NEXT_OCCURRENCE` → `_LIST_BY_CATEGORY` → `_OPEN_NOW_DISAMBIG` → falls through to `OPEN_ENDED`.
   - `contribute` mode: `_contribute_sub_intent(raw, nq)` distinguishes `BUSINESS_CONTRIBUTE` vs `PROGRAM_CONTRIBUTE` based on keywords.
   - `correct` mode: hard-coded `("CORRECTION", 0.9)`.
   - `chat` mode: uses `chat_hint` from step 1 or defaults to `SMALL_TALK`.
3. **Entity match.** `match_entity_with_rows(raw, _ENTITY_NAMES)` does fuzzy matching against a canonical-names list. Returns `(name, score)` or `None`. The score (0–100) gets normalized to 0.0–1.0 for the merge step.
4. **Confidence merge.** `_merge_confidence(mode_conf, sub_conf, entity_score)` blends the three signals. Floors at 0.42 specifically for `ask` + `OPEN_ENDED` queries with confidence < 0.4 — prevents the router from treating a low-confidence open-ended query as garbage.

## Conventions

**Pure function, no side effects.** No DB, no network, no logging. Tests can call `classify()` directly with no fixture setup.

**Frozen dataclass for the return.** `IntentResult` consumers can't mutate; this is documented public contract.

**Regex patterns are module-level compiled.** Tests can introspect/patch via `monkeypatch.setattr` if needed; reuse across calls is a perf win.

**Confidence rounding to 3 places.** Avoids float-drift noise in `chat_logs` analytics rows.

**`OPEN_ENDED` floor at 0.42.** Magic number documented inline; justification: "low-confidence open-ended is still legitimate Tier 3 input." Adjust if the unified router's downstream handling changes.

## Sub-intent label space

Sub-intent strings are part of the public contract — they appear in `chat_logs.sub_intent` and are referenced by the unified router's dispatch. Current set:

- **`ask` mode:** `NEXT_OCCURRENCE`, `LIST_BY_CATEGORY`, `OPEN_NOW_DISAMBIG`, `OPEN_ENDED`, plus entity-aware specializations from `app/chat/unified_router.py`.
- **`contribute` mode:** `BUSINESS_CONTRIBUTE`, `PROGRAM_CONTRIBUTE`.
- **`correct` mode:** `CORRECTION`.
- **`chat` mode:** `GREETING`, `REAL_ESTATE_CHAT`, `SMALL_TALK`.

The optional `llm_router.py` (when `USE_LLM_ROUTER` is on) emits the same labels — see its `_SUB_INTENTS` frozenset for the authoritative list.

## Known limitations

**Regex brittleness.** Adding new query phrasings often requires extending one of the patterns. Tests cover known good/bad strings but novel inputs may misroute.

**Entity match is fuzzy.** Score threshold is in `match_entity_with_rows`; tweak there, not here. Spurious matches (e.g., user typed "altitude" meaning a literal noun, classifier matches Provider "Altitude") aren't filtered — Tier 1 / Tier 2 handlers must validate.

**No session context.** The classifier is one-shot per turn. Multi-turn intent requires upstream context, which `unified_router.py` provides separately.

## Related

**Direct consumers:** `app/chat/unified_router.py` (every chat turn), tests.
**Direct dependencies:** `app.chat.normalizer.normalize`, `app.chat.entity_matcher.match_entity_with_rows`, `app.data.canonical_names._ENTITY_NAMES`.
**Adjacent doc:** `app/chat/llm_router.py` (`docs/components/llm_router.md`) emits compatible labels under the optional LLM-routing flag.
