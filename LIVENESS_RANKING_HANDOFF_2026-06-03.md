# Liveness ranking handoff — bury stale listings across all categories
Date: 2026-06-03 · Author: Casey via Cowork session · Status: ready to implement

## Goal
Stop surfacing likely-dead businesses at normal rank. Do NOT deactivate or delete
anything — a dead business should be *buried* (ranked low), never removed. Casey's
explicit preference: false-negative (dead business still listed but low) is fine;
false-positive (active business hidden) is not.

Validated prototype: `outputs/listing_liveness_ranking.xlsx` (built from
`scripts/output/places_pull/enrichment_raw.jsonl`, pull of 2026-05-18, 2,647 places).
Distribution with the formula below: 2,008 OK / 164 stale-verify / 90 likely-inactive /
385 no-review-data.

## Scoring formula (validated, use these constants)
Three components, each 0–1:

- **recency** = `exp(-ln(2) * days_since_newest_review / grace)` where
  `grace = 90 + 1095 / sqrt(max(review_count, 1))` days.
  If no review timestamp available: recency = **0.5** (neutral — no evidence either way).
  Rationale: a 2-review business going quiet for a year is normal; a 46-review business
  silent for 2 years is a death signal. Grace shrinks as volume grows.
- **quality** = `((rating * n) + (GLOBAL_MEAN * 10)) / ((n + 10) * 5)` — Bayesian rating,
  prior m=10, scaled 0–1. `GLOBAL_MEAN = 4.46` (citywide weighted mean from the May pull;
  define as a module constant, recompute opportunistically on future pulls).
  If rating is null, use GLOBAL_MEAN as the rating.
- **popularity** = `ln(1 + n) / ln(1 + MAX_COUNT)`, `MAX_COUNT = 10164` (module constant).

**liveness = 0.45 * recency + 0.35 * quality + 0.20 * popularity**

Tier labels (for admin/triage UI, not user-facing):
- `likely_inactive`: review_count >= 10 AND recency < 0.15
- `stale_verify`: recency < 0.25
- `no_review_data`: no review timestamps
- `ok`: everything else

## Data gap to close
`scripts/places_load.py` populates `google_rating` / `google_review_count` /
`google_review_snippets` but does **not** extract review `publishTime`. The newest-review
timestamp is the core signal.

1. Add `newest_review_at` (TZAwareDateTime, nullable) + `liveness_score` (Float, nullable,
   indexed) to **providers**, and `liveness_score` to **entities** (forward-compat with the
   unified abstraction). One Alembic migration, standard `versions/` pattern.
2. In `places_load.py` row-mapping (~lines 140–173): extract
   `max(review.publishTime)` from the enrichment payload (note: fractional seconds have
   9 digits — strip before `fromisoformat`), store `newest_review_at`, compute and store
   `liveness_score` at load time.
3. Backfill script `scripts/backfill_liveness.py` reading
   `scripts/output/places_pull/enrichment_raw.jsonl`, matching on `google_place_id`
   (providers + `locations.google_place_id` for entity join). Must support `--dry-run`
   printing counts (matched / updated / unmatched) — per CLAUDE.md, prod apply waits for
   Casey's explicit approval.

## Scoring code location
New pure module `app/core/liveness.py` (mirrors `app/core/ranking.py` style: dataclass
input, no DB imports). Functions: `compute_liveness(rating, review_count,
newest_review_at, ref_now) -> float` and `liveness_tier(...) -> str`. All constants
(weights, grace params, GLOBAL_MEAN, MAX_COUNT, tier thresholds) module-level and named.

Known drift: recency decays between pulls but the stored score is static. Acceptable —
pulls are roughly monthly and the backfill recomputes. Pass `ref_now` explicitly for
testability.

## Ranking integration — bury, don't filter
Apply as a **multiplicative dampener** on existing rank scores so relative order within
healthy listings is preserved and nothing is excluded:

`final = base_rank * (0.5 + 0.5 * liveness)`  — worst case halves a listing's rank,
never zeroes it. Treat NULL liveness as 1.0 (no dampening) so non-Google-sourced
entities are unaffected.

Integration points (from codebase scan):
- `app/search/ranking.py`: `composite_rank_float()` + `tier2_rank_score_sql()` /
  `build_rank_score_expr_for_filters()` — apply dampener in both the Python and SQL
  paths. SQL path can use the **stored** `liveness_score` column directly (avoid
  exp/sqrt in SQL; SQLite fallback at `app/search/routes.py:327` must mirror it).
- `app/core/ranking.py`: add optional `liveness_score` field to `CardRankInput`
  (default None → no dampening), apply in `compute_card_rank()`.
- `app/api/routes/category_pages.py`: `rank_inputs_for_category()` (~line 608) passes
  the new field — this is what covers **all category pages** including the
  `closest_now` default sort and the `top_rated` mode.
- Browse tile counts (`app/home/browse_tiles.py`): no change (count-only).

## Tests (same commit as behavior changes, per repo rules)
- Unit: `compute_liveness` — high-volume stale (47 reviews / 772 days → tier
  likely_inactive), low-volume stale (4 reviews / 400 days → ok), zero reviews →
  recency 0.5, fresh high-volume → ~0.9 recency. Edge: count=0, rating=None.
- Unit: dampener — NULL liveness leaves base rank unchanged; liveness=0 halves it;
  ordering of two equal-base listings follows liveness.
- Integration: category page ordering with a seeded stale-heavy entity sinks below a
  fresh peer; search route SQLite fallback applies dampener.
- `places_load.py` resolver tests: newest_review_at extraction incl. 9-digit
  fractional-second timestamps.

## Process guardrails (CLAUDE.md — restating, they apply here)
- Feature branch off `main`; open a PR and STOP. No merge — that's Casey's gate
  (main auto-deploys to Railway prod with alembic upgrade).
- `python -m pytest -q` green and `ruff check .` clean before every commit
  (PowerShell: use `.venv\Scripts\python.exe`).
- Backfill: dry-run → show counts → wait for Casey → apply. Never run against prod
  without approval. No `railway` commands, no secrets.

## Out of scope (don't do now)
- Auto-deactivating `likely_inactive` entities (Casey explicitly wants bury-only).
- Re-pulling Places data (cost); use the May 18 JSONL.
- User-facing "possibly closed" badges — maybe later, after Casey reviews tiers.
- Tuning weights — they're constants; Casey iterates via the xlsx prototype first.
