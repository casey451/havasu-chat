# confabulation_detector

`app/eval/confabulation_detector.py` (~440 lines)

## Purpose

Implements the confabulation harness detector stack (Layers 1-3) that compares model response text against captured evidence rows and emits structured token-level hits.

- **Layer 1 (`1_advisory`)**: per-sentence lemma-diff candidates for human review (non-gating).
- **Layer 2 (`2`)**: phrase-level gating hits from a curated closure lexicon.
- **Layer 3 (`3`)**: canonical token diffs for numeric/temporal/contact-style claims.

Headline confabulation metrics are intentionally based on gating layers, not Layer 1 advisory output.

## Public surface

**`DetectorHit` (frozen dataclass, slots)**:
- `layer: Literal["1_advisory", "2", "3"]`
- `token: str`
- `sentence_index: int`
- `row_ids_in_scope: tuple[str, ...]`

**`InvocationResult` (dataclass)**:
- `response_text: str`
- `evidence_row_dicts: list[dict[str, Any]]`
- `http_degraded: bool = False`
- `is_http_mode: bool = False`

**Note on `InvocationResult` naming:** `app/eval/confabulation_invoker.py` defines a separate `InvocationResult` with invocation/transport metadata (`tier_used`, `latency_ms`, `raw_log`, `error`). The harness bridges from that wider invoker shape to this detector-input shape before calling `detect(...)`; see `scripts/confabulation_eval.py`.

**`detect(inv: InvocationResult) -> list[DetectorHit]`** — Main entrypoint.

**Lexicon/config constants (module-level):**
- `LAYER2` (derived from `_L2`)
- `SAFE`, `VGEN`, `QTY`
- contraction and lemma normalization maps
- phone regex and helper canonicalizers

## Inputs and outputs

**Inputs.**
- Invocation response text.
- Evidence row dicts (may be empty in degraded/HTTP paths).
- Mode flags (`http_degraded`, `is_http_mode`).

**Output.**
- Flat list of `DetectorHit` entries across active layers.

## Internal structure

### Shared normalization helpers

- `_prep_text` normalizes em/en dashes.
- `_row_text` builds evidence blob from selected row fields.
- `_row_id` builds stable row identifiers (`event:name:date` special-case).
- `_sents` sentence splitter.
- `_strip_phone_numbers`, `_nanp_phone_key` phone handling.

### NLP bootstrap and lemma extraction

- `_nltk()` lazy-initializes NLTK resources + lemmatizer.
- `_wpos()` maps Penn tags to WordNet tags.
- `_lemmas(text)` computes filtered lemma set with:
  - stopword removal
  - POS allowlist
  - generic-verb and safe-term suppression
  - explicit indoor/outdoor canon additions

### Layer implementations

**Layer 1 (`_l1`) advisory:**
- per-sentence token pass
- same filtering rules as `_lemmas`
- emits lemmas present in response but absent from evidence lemma set
- dedupes per invocation via `seen`

**Layer 2 (`_l2`) gating:**
- scans response for each `LAYER2` phrase (`_l2_phrase_in`)
- skips phrase when present in evidence unless degraded/no-evidence mode
- assigns first matching sentence index

**Layer 3 token diff:**
- `_l3_tokens` extracts canonical tokens from text:
  - cost tokens (`c:free`, `usd:*`, ranges, lte)
  - phone tokens (`ph:*`)
  - time tokens (`t:HH:MM`) incl ranges and 12h/24h variants
  - duration/day/quantity tokens
- Layer 3 hits are `sorted(_l3_tokens(response) - _l3_tokens(evidence_blob))`

### Main orchestration (`detect`)

1. Build response/evidence text blobs + row ids.
2. Determine degraded web mode (`is_http_mode or http_degraded`).
3. Run Layer 1 only when evidence rows exist and not web-degraded.
4. Run Layer 2 always (with degraded behavior when no evidence/web mode).
5. Run Layer 3 only when evidence rows exist.
6. Return concatenated hit list.

## Conventions

**Layer semantics are explicit.** Layer 1 is advisory only; Layers 2/3 are gating.

**No exceptions on detector path.** Module favors resilient parsing/tokenization behavior and returns best-effort hits.

**Canonical token prefixes.** Layer 3 token families are namespaced (`usd:`, `ph:`, `t:`, `dy:`, `dur:`, etc.) to simplify downstream aggregation.

**Resource lazy-load.** NLTK data downloads/init happen on first NLP path use.

**Evidence-aware degradation.** Degraded/HTTP mode intentionally relaxes L2 evidence comparison to avoid false negatives when rows are unavailable.

## Configuration

No environment variables. Behavioral configuration is module constant driven:
- phrase lexicons (`_L2`, `SAFE`, `VGEN`, `QTY`)
- regexes
- POS allowlist and filtering rules

## Known limitations and design notes

**NLTK runtime dependency.** First run may download corpora/tagger resources; environments without network or NLTK data can fail unless pre-seeded.

**Heuristic-heavy by design.** Token/phrase rules trade recall vs precision; false positives/negatives are expected and tuned operationally.

**Layer 1 POS asymmetry caveats.** Despite phone stripping and filters, POS tagging quirks can still influence advisory outputs.

**Single-language assumptions.** Lexicons and tokenization assume English text.

**Row-text flattening limits structure.** `_row_text` concatenation loses field-level provenance once merged into evidence blob.

## Related

**Direct callers:**
- `scripts/confabulation_eval.py` after invoker result adaptation.
- `tests/test_confabulation_detector.py`.

**Direct dependencies:**
- NLTK (`pos_tag`, `word_tokenize`, stopwords, WordNet lemmatizer)
- Python `re`, dataclasses, typing

**Cross-references:**
- `app/eval/confabulation_invoker.py`
- `app/eval/confabulation_evidence.py`
- `app/eval/confabulation_report.py`
- Lexicon/spec source cited in module docstring (`relay/halt1-closure-final-lexicons.md`)
