# search

`app/core/search.py` (~25 lines post–Slice 71)

## Purpose

Provides **`_deterministic_embedding_1536`**, used by **`app/admin/router.py`** when synthesizing a contribution embedding if no real OpenAI embedding is available. The former keyword + embedding event-search pipeline (`search_events`, `format_search_results`, strategy dispatch, etc.) was removed under Backlog #36 Option A; Tier 2 SQL retrieval and Tier 3 paths in `app/chat/` replaced that surface.

## Public surface

**`_deterministic_embedding_1536(text: str) -> list[float]`**

Tokenizes `text` with a lowercase `[a-z0-9]+` regex, hashes each token into 16 bucket offsets modulo 1536 with decreasing weights, L2-normalizes. Same-process deterministic given stable `hash()`; cross-process variance follows Python hash randomization.

## Inputs and outputs

Input is raw text; output is a length-1536 `list[float]` suitable for storing alongside OpenAI `text-embedding-3-small` vectors.

## Conventions

**Admin-only runtime caller.** Chat routing does not import this module.

## Related

- **`app/admin/router.py`** — lazy-imports `_deterministic_embedding_1536` for synthetic embeddings on contribution save/approve paths.
- **`docs/components/extraction.md`** — contrasts 32-dim deterministic extraction fallback vs 1536-dim OpenAI vectors on `Event` rows.
- **`docs/maintainability/intent_module_disposition_decision.md`** — §7 scope extension covering `search.py` disposition.
