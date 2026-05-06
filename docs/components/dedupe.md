# dedupe

`app/core/dedupe.py` (~74 lines)

## Purpose

Embedding-based duplicate detection for `Event` rows. Used during ingestion to decide whether an inbound event matches an already-stored one. Three signals must all align: cosine similarity ≥ 0.85 on stored embeddings, dates within ±1 day, and locations textually similar. The strict three-signal requirement prevents false positives that any single signal would produce on its own.

Currently `cosine_similarity` is the only `dedupe` symbol imported by other production code (`app/core/search.py`). `find_duplicate` retains test coverage but has no live runtime caller after the 2026 ingestion-lane cleanup; River Scene's `run_pull` does its own URL-based dedupe before this layer would see the candidate.

## Public surface

**`find_duplicate(candidate_event: dict[str, Any], db: Session) -> Event | None`** — Search for an existing `Event` that matches the candidate. Returns the best-matching `Event` row or `None`. The candidate dict needs `embedding`, `date`, and `location_name` fields; missing `embedding` short-circuits to `None` (no embedding, no dedupe).

**`cosine_similarity(left: list[float], right: list[float]) -> float`** — Pure math helper. Returns the cosine similarity in `[0.0, 1.0]`. Returns `0.0` for empty inputs or zero-magnitude vectors (defensive against float divide-by-zero).

## Inputs and outputs

**`find_duplicate` input.** A dict shaped like `{"embedding": list[float], "date": date | str, "location_name": str}`. Other fields ignored.

**`find_duplicate` output.** A single `Event` row (the highest-scoring match passing all three gates) or `None`. Searches all live events via `db.query(Event).all()` — full table scan; not optimized for large catalogs.

**`cosine_similarity` input/output.** Two equal-length float vectors. Output is a float in `[0.0, 1.0]` (no clamping; cosine is bounded by definition for non-zero vectors).

## Internal structure

`find_duplicate` is a five-step linear scan:

1. **Embedding short-circuit.** Missing/empty `embedding` → return `None`. Dedupe requires the embedding signal.
2. **Date + location normalization.** `_coerce_date` parses string dates to `date` objects; `_normalize_text` handles location string normalization.
3. **Per-existing-event loop:** for each event in `db.query(Event).all()`:
   - Skip if no `embedding` on the existing event.
   - Compute `cosine_similarity`. Skip if < 0.85 (the embedding gate).
   - Check `_dates_within_one_day`. Skip if dates differ by > 1 day.
   - Check `_locations_similar`. Skip if locations don't match textually.
   - If all gates pass: track as best match if `similarity > best_score`.
4. **Return best match or `None`.**

`cosine_similarity` is the standard math: dot product divided by the product of magnitudes, with explicit handling for empty/mismatched vectors and zero-magnitude inputs.

## Conventions

**Three-gate AND.** Embedding similarity, date proximity, location similarity — all three must pass. Loosening any single gate would create false-positive cascades.

**0.85 cosine threshold.** Empirically chosen. Tighter than typical "semantic similarity" cutoffs (~0.7) because event titles repeat verbatim across providers; loose threshold collapses unrelated events into one. Adjust only with data.

**±1 day date window.** Accommodates timezone-edge ingestion (event published in PST might be parsed as next-day UTC by another lane). Wider would conflate same-event-different-day cases.

**Best-match (not first-match).** When multiple existing events pass all gates, return the highest-similarity. Preserves the strongest dedupe; returning first-match would be order-dependent on `db.query(Event).all()`.

**Full table scan.** No indexed embedding search. At current scale (~hundreds of events) this is fast; at thousands it becomes a bottleneck. pgvector or similar would be the upgrade path; not currently warranted.

**Pure-function math.** `cosine_similarity` is testable without DB and without Pydantic. No exceptions raised; defensive returns of `0.0` for edge cases.

## Known limitations and design notes

**Embedding-required.** Events without embeddings can't be deduped. The ingestion lane is responsible for embedding generation; bypassing it skips dedupe.

**0.85 threshold is global.** Per-category thresholds aren't supported. If a category has known title-collision patterns (e.g., recurring weekly events with identical titles), the global threshold can't be loosened just for that category.

**Date window is symmetric.** ±1 day. A 2-day-shifted ingestion (rare; usually a timezone-handling bug at the source) wouldn't dedupe.

**No event-status filtering.** `db.query(Event).all()` doesn't filter by status; live and pending events are both candidates. If a draft event matches an inbound, the draft "wins" the dedupe tracking. Acceptable in current ingestion order.

**`_normalize_text` and `_locations_similar` are not exported.** Internal helpers; their text-normalization rules (lowercasing, whitespace squashing, etc.) are tunable but require code changes.

**Performance scales with event count.** O(n) full scan. Adding 10x events makes dedupe 10x slower. Acceptable until catalog crosses ~10,000 rows.

## Configuration

No environment configuration. All thresholds are module-level constants embedded in the code (the literal `0.85`, the literal `1` day window).

## Related

**Direct callers:**

- `app/core/search.py` — imports `cosine_similarity` for embedding scoring only (`find_duplicate` is not used here).
- `tests/test_phase8_9_event_ranking.py` — dedupe coverage in event ranking tests.

**Direct dependencies:**

- `app/db/models.Event` — stores the `embedding` column being compared.
- `sqlalchemy.orm.Session` — database session.

**Cross-references:**

- `docs/search-pipeline-for-claude.md` — historical context for embedding-driven catalog reasoning.
- `app/contrib/river_scene_pull.py` — does URL-based dedupe BEFORE this embedding-based dedupe ever sees the candidate (different layer).
