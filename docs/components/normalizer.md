# normalizer

`app/chat/normalizer.py` (~55 lines)

## Purpose

Pre-classification text normalizer. Takes a raw user query and produces a deterministic normalized form for downstream consumers — primarily `intent_classifier.classify()` (which needs predictable casing for regex matching) and `tier1_templates.INTENT_PATTERNS` (which expects lowercased input). Pure function, no IO.

## Public surface

**`normalize(query: str) -> str`** — Sole exported function. Returns the normalized form. Empty input returns empty string. Idempotent — applying twice yields the same result.

## Internal structure

`normalize()` is four steps:

1. **Lowercase + edge strip.** Lowercase the whole string; strip leading/trailing whitespace and punctuation via `_strip_edge_punct_ws` (uses a frozen set of edge characters: punctuation + whitespace).
2. **Contraction expansion.** Apply the `_CONTRACTIONS` table. Apostrophe forms first (`what's` → `what is`), then apostrophe-less informal variants (`whats` → `what is`). Order matters because the apostrophe-less form would also match the apostrophe form's substring.
3. **Internal whitespace collapse.** Multiple spaces collapse to single. Tabs and newlines normalize to spaces.
4. **Preserve internal hyphens and apostrophes.** `o'clock`, `co-op`, etc. survive — only edge punctuation is stripped.

## Conventions

**Pure function, no IO.** Tests can call `normalize()` directly with no fixture setup. Idempotent.

**Lowercase early.** All downstream consumers expect lowercase. Doing it here once means classifiers and patterns don't have to.

**Apostrophe-form first.** `_CONTRACTIONS` order is load-bearing. `what's` would also match a regex looking for `whats`, so the apostrophe variant runs first to avoid double-replacement edge cases.

**Edge-only punctuation stripping.** Internal hyphens and apostrophes preserve word identity. Only leading/trailing edge characters get removed. A query like "what's the address?" loses the `?` but keeps the `'`.

## Known limitations

**Contraction list is hard-coded.** Adding a new contraction requires a code change. At current scale (a dozen) this is fine; if the list grew significantly, a config file would help.

**No spell-correction.** Misspellings pass through unchanged. Downstream regex patterns must accept common variants explicitly.

**No locale awareness.** English-only normalization. Non-English queries pass through but downstream classifiers won't match them.

**No emoji stripping.** Emojis survive. The classifier regexes don't match them, so they're effectively no-ops downstream — but they do contribute to query length.

**No stop-word removal.** "the", "a", "is" all preserved. Downstream regexes expect them in some patterns; removing would break those.

## Related

- `app/chat/intent_classifier.py` — direct caller; uses normalized output for regex patterns (`docs/components/intent_classifier.md`).
- `app/chat/tier1_handler.py` — also calls `normalize()` as a fallback when `IntentResult.normalized_query` is missing (`docs/components/tier1_handler.md`).
- `app/chat/llm_router.py` — passes the normalized query to the LLM router as `normalized_query` arg (`docs/components/llm_router.md`).
- `tests/test_normalizer.py` — coverage of the four-step pipeline.
