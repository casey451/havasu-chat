# Ask Hava Intent Layer — Phase 2 Implementation Plan

> Synthesized 2026-06-01 by a multi-agent design workflow (3 independent
> proposals — migration-first, matcher-first, data-first — reconciled by a
> synthesis pass). Each agent read the live tree; the conflicts below were
> resolved against real files. Phase 1 (the flag-on, fall-through-on-empty
> intent layer) is shipped; this plans Phase 2. **HALT-gated: do not start a
> slice before the prior slice's gate passes.**

## Conflicts resolved against the code

1. **Alembic head** is a single revision `v1c3d4e5f6a8`. All new migrations
   chain `down_revision = "v1c3d4e5f6a8"`; no merge revision is needed.
   Re-verify `alembic heads == 1` before authoring each migration.
2. **Double-logging (confirmed real bug).** Two writers hit `query_log` per
   "ask" turn: `app/chat/intents/runtime.py::_log` (intent path) and a second
   writer on every `mode == "ask"` turn. Every aggregate built on `query_log`
   counts is inflated until deduped → **Slice 0, a hard prerequisite.**
3. **Layer not logged.** `ResolvedIntent.layer` ("L1"/"L2") exists but
   `runtime._log` never persists it and `QueryLog` has no column for it.
4. **Flag polarity.** `USE_INTENT_LAYER` defaults ON. Every NEW Phase-2
   capability ships dark behind its OWN default-OFF flag
   (`INTENT_L3_FUZZY`, `INTENT_CLARIFY`, `USE_INTENT_CATALOG_DB`,
   `INTENT_L4_EMBED_MODEL`). Do not reuse `USE_INTENT_LAYER`.
5. **Stray repo-root files** (`acc50395da86`, `a9b0c1d2e3f4`, `b1c2d3e4f5a6`,
   `c2d3e4f5a6b7`, `ask`, `the`) are empty accidental shell-redirect droppings,
   NOT migrations. Delete before Slice 1.

## Slices (smallest valuable first)

- **Slice 0 — Dedupe `query_log` writers** (tiny prerequisite). Make the intent
  path the single writer on turns it claims; one row per ask turn proven by test
  on both intent-claimed and fall-through paths. No response change.
- **Slice 1 — Telemetry columns + layer threading** (small). Additive nullable
  `min_layer String(8)` (indexed) + `sub_intent String(64)` on `query_log`;
  thread `resolved.layer` and the real `sub_intent` through `runtime._log` and
  `app/v1/query_log.py`. Migration reversible; no behavior change.
- **Slice 2 — ~5k-phrase CI regression gate** (medium, no app code). Generator
  expands the dicts × templates into phrases with derived `intent_key`/`min_layer`;
  committed dataset; ordinal-layer assertion (`order[resolved.layer] <=
  order[declared]`) so it survives L3/L4; dataset-in-sync test. **(The seed of
  this is already done — see `tests/fixtures/intent_phrase_bank.json` +
  `tests/test_intent_phrase_bank.py`.)**
- **Slice 3 — L3 fuzzy + clarify-don't-guess** (medium-large, top leverage).
  `resolve_ex()` alongside `resolve()` (keeps the contract byte-identical);
  rapidfuzz exemplars per intent; per-intent `min_layer` policy (urgent_care /
  cheapest_gas can only PROPOSE at L3, never finalize); `clarify_chips` component
  that runs no row query. All behind `INTENT_L3_FUZZY` / `INTENT_CLARIFY` (default
  off) + an `INTENT_L3_SHADOW` logging-only branch for risk-free threshold tuning.
- **Slice 4 — "Popular in Havasu" + coverage dashboard** (medium, owner value).
  Aggregate `query_log` into popular chips (hit-rate + min-count gated) and an
  admin coverage endpoint (asks / answered / zero-row gaps / `layer_mix`).
  Depends on Slice 0 (clean counts) + Slice 1 (layer).
- **Slice 5 — DB-backed intent catalog** (large, OPTIONAL, last). Move routing
  PARAMETERS (subcats, tokens, labels) into an `intent_catalog` table with code
  as the fallback floor; pure refactor, zero user-visible benefit until no-deploy
  catalog edits are actually needed. Parity test proves byte-identical answers.

## Dependency order

```
Slice 0 (dedupe) -> Slice 1 (telemetry cols) -> Slice 4 (popular/coverage)
                        |
Slice 2 (5k gate) -----+-> Slice 3 (L3 + clarify) -> [Slice 5 DB catalog, optional]
```
Slices 0 and 2 are independent and can run in parallel.

## Cross-slice invariants

- `USE_INTENT_LAYER` gate untouched; all NEW behavior behind its own default-OFF flag.
- Fall-through-on-empty preserved: zero rows log the coverage signal THEN return None.
- Clarify runs no row query and fabricates nothing.
- Entity/factual guards fire before any matching (incl. L3/L4).
- Exactly one `query_log` row per ask turn (Slice 0) or every downstream count is wrong.

## Open questions (need a human decision)

1. **L4 embeddings provider + API key** (blocking for any L4 work). Recommendation:
   hold L4 out of Phase 2 — build only the `Embedder` Protocol seam + `NullEmbedder`;
   revisit if shadow data shows L3 recall is insufficient.
2. **L3/L4 thresholds + per-intent min_layer.** Ship Slice 3 with `INTENT_L3_SHADOW`
   logging first, tune from real `match_score` data, THEN enable. Who signs off?
3. **Clarify UX.** `clarify_chips` needs client-side chip rendering + re-submit. Is
   the front end ready, or does `INTENT_CLARIFY` stay off until the UI lands?
4. **Is Slice 5 (DB catalog) wanted in Phase 2?** Pure refactor; defer past Phase 2
   if no-deploy catalog edits aren't needed yet.
5. **Delete the stray repo-root files** before Slice 1? (Recommended.)
6. **Slice 0 claim signal** — confirm which field the unified router exposes to tell
   the second writer the intent layer claimed the turn.

## Key files

`app/chat/intents/{runtime,resolver,queries,dicts}.py`, `app/v1/query_log.py`,
`app/db/models.py` (QueryLog), the second `query_log` writer on the ask path,
`app/chat/unified_router.py`, `alembic/versions/v1c3d4e5f6a8_provider_subcategory.py`
(current single head).
