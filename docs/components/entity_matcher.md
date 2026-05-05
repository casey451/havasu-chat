# entity_matcher

`app/chat/entity_matcher.py` (~236 lines)

## Purpose

Fuzzy-match user queries to a canonical `Program.provider_name` so the unified router can resolve "iron wolf" or "the trampoline place" to the actual catalog entity ("Iron Wolf Golf & Country Club", "Altitude Trampoline Park — Lake Havasu City"). Used by `unified_router._enrich_entity_from_db` after intent classification, and by `unified_router` again post-Tier-3 to capture LLM-mentioned providers via `extract_catalog_entities_from_text`.

The match is rapidfuzz `token_set_ratio` against a process-cached index of `_EntityRow` records. Each row carries the canonical name plus a `frozenset` of needles: the canonical itself (normalized), its lowercased form, and any explicit aliases from the `CANONICAL_EXTRAS` dictionary.

## Public surface

**`refresh_entity_matcher(db: Session) -> None`** — Load distinct `Program.provider_name` values, build the `_EntityRow` index, store on the module-level `_rows`. Call after bulk program imports or whenever the catalog changes.

**`reset_entity_matcher() -> None`** — Clear the cache. Tests use this in fixtures so each case starts from a known empty state.

**`match_entity(query: str, db: Session) -> tuple[str, float] | None`** — Return `(provider_name, score)` if best fuzzy match is strictly above 75. Lazy-loads the index if not cached.

**`extract_catalog_entities_from_text(text: str, db: Session) -> list[EntityMatch]`** — Return all catalog providers mentioned in `text` with score > 75. Deduplicated by canonical name. `EntityMatch.type` is always `"provider"` (Phase 6.4.1).

**`match_entity_with_rows(query: str, canonical_names: Sequence[str]) -> tuple[str, float] | None`** — Match against an explicit name list (no DB). Test/utility use.

**`CANONICAL_EXTRAS: dict[str, list[str]]`** — Hand-curated alias map for providers whose query patterns differ from their formal name (e.g., "iron wolf" → "Iron Wolf Golf & Country Club"). Keys MUST match canonical `Program.provider_name` strings exactly.

**`EntityMatch`** (dataclass, frozen) — `name: str`, `type: str` (always `"provider"`), `id: str` (Provider.id when present, else falls back to name).

## Inputs and outputs

**`match_entity` input.** Free-text user query. Normalized via `app.chat.normalizer.normalize` before scoring.

**`match_entity` output.** `(canonical_name, score)` tuple where `score` is a rapidfuzz ratio in `[0.0, 100.0]`, or `None` if no match exceeds the 75 threshold.

**`extract_catalog_entities_from_text` output.** Sorted-by-canonical list of `EntityMatch` objects. Empty list if no matches > 75 or query normalizes to empty.

## Internal structure

`_needles_for_canonical` builds the per-canonical needle set: normalized canonical, lowercased canonical, plus normalized aliases from `CANONICAL_EXTRAS`. Stored as `frozenset` so the row is hashable and immutable post-construction.

`_best_score` iterates needles, returns max `fuzz.token_set_ratio(norm_query, needle)`. `token_set_ratio` is order-insensitive — "wolf iron golf" matches "iron wolf golf" — which matters because users phrase entities loosely.

`refresh_entity_matcher` queries `Program.provider_name DISTINCT`, sorts canonically, builds rows. The `_rows` global is the cache; `match_entity` lazy-loads it on first call after a `reset_entity_matcher` (or process start).

`extract_catalog_entities_from_text` differs from `match_entity` in two ways: (1) returns *all* matches above threshold, not just the best, and (2) deduplicates by canonical so multiple needles for the same canonical produce a single result.

## Conventions

**Score threshold = 75 (strict greater-than).** Empirically chosen. Below 75 produces too many false positives (common words like "lake" overlap many canonicals); above 75 misses valid abbreviations. Tune only with data.

**Tie-breaking by canonical name.** When two canonicals tie on score, the alphabetically earlier name wins. Deterministic across runs; otherwise dict insertion order would leak through.

**Process-local cache.** `_rows` lives in the module. Multi-worker uvicorn would have one cache per worker — acceptable because the cache rebuilds in milliseconds and bulk-import paths call `refresh_entity_matcher` explicitly.

**`CANONICAL_EXTRAS` keys must mirror `Program.provider_name` exactly.** Including punctuation and casing. Mismatches mean the alias never lights up because the canonical isn't in the index.

## Known limitations and design notes

**No fuzzy-typo handling on the canonical side.** If a contribution mis-spells "Altittude Trampoline Park", the canonical row in `Program.provider_name` is also mis-spelled, and matching gets confused. The dedupe / normalization happens upstream (in approval flows), not here.

**Provider-only.** Phase 6.4.1 limited matches to providers; events/programs aren't entities. Adding event-name matching would require a parallel index and threshold tuning (events have shorter, more generic names like "Concert in the Park" — false-positive risk).

**`CANONICAL_EXTRAS` is the maintenance debt.** New providers don't get aliases until someone hand-edits the dict. Slice 36's River Scene work is the bulk import lane, but it doesn't populate aliases. A future improvement: derive aliases from contribution review notes or chat-log mention frequency.

**Fallback `id` is the name itself.** When `_provider_id_for_name` can't find a `Provider` row (the catalog has historic `Program.provider_name` strings that don't have `Provider` table rows yet), it returns the name as the id. Downstream consumers must treat `EntityMatch.id` as "stable display key," not "DB primary key."

**Normalization is one-way.** `normalize()` lowercases and strips punctuation. The needles store normalized forms; queries are normalized at match time. Any change to `normalizer` invalidates the cache — but the cache rebuild is automatic on next call after a process restart, so the practical risk is low.

## Configuration

No environment configuration. The 75 threshold is a module constant. The `CANONICAL_EXTRAS` dict is the only "configuration" surface and lives in code (intentional — alias maintenance is reviewed via PR).

## Related

**Direct callers:**

- `app/chat/unified_router.py` — `_enrich_entity_from_db` calls `match_entity`; `route` calls `extract_catalog_entities_from_text` to capture LLM-mentioned providers post-Tier-3.
- `tests/test_entity_matcher.py` — direct surface coverage including `match_entity_with_rows` for no-DB tests.
- `tests/test_prior_entity_router.py` — integration coverage via the router.

**Direct dependencies:**

- `rapidfuzz.fuzz.token_set_ratio` — the scoring function.
- `app.chat.normalizer.normalize` — query/needle preprocessor.
- `app.db.models.Program`, `app.db.models.Provider`.

**Cross-references:**

- `docs/components/normalizer.md` — the canonical text-normalization rules.
- `docs/components/unified_router.md` — describes the router's two calls into this module.
- `docs/persona-brief.md` §5.1 — entity-resolution discipline.
