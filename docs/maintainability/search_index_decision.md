# Search Index — Decision Memo

> **Status:** decision only; no implementation, no migration. Output of the architecture-audit-driven design pass on 2026-05-14.
> **Source gap:** Gap #5 in `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.5 + §5.2.
> **Audience:** Cowork primary + Casey; future implementation-lane author.
> **Companion docs:** `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.5 (gap framing), `docs/maintainability/place_model_design.md` (Place is a separately-searchable table; informs §4), `app/chat/tier2_db_query.py` (the LIKE-chain code path this memo replaces), `docs/STRATEGY_PIVOT_2026-05-12.md` (the directory pivot that scoped this need).

---

## §1 Why a search index exists (problem statement)

The current chat tier 2 retrieval path filters Provider / Event / Program rows via SQLAlchemy `ilike` chains in `app/chat/tier2_db_query.py:33+`. Concretely:

- Category match against `Provider.category` and `Provider.google_primary_category`: `_query_providers_orm` at `app/chat/tier2_db_query.py:811-892` builds an `or_(*conditions)` list of `Provider.category.ilike("%plumber%")` clauses, one per synonym variant.
- Entity-name match: `app/chat/tier2_db_query.py:821-827` runs `Provider.provider_name.ilike(needle) OR Provider.description.ilike(needle)`.
- Location match: `app/chat/tier2_db_query.py:828-829` runs `Provider.address.ilike(needle)`.
- Free-text needle helper at `app/chat/tier2_db_query.py:363-366` wraps the term in `%term%` — a guaranteed sequential scan when no functional index covers the column.
- Event / Program use the same shape (`app/chat/tier2_db_query.py:701-797`).

The entity matcher at `app/chat/entity_matcher.py:1-100` runs Rapidfuzz scoring over an in-memory needle list refreshed on schema change. That works as the deterministic Tier 1 lookup but it's not a search index — it's a string-similarity scorer over a fixed needle set, and it does not power Tier 2 / category-page browse queries.

**Where this breaks under the full vision.**

Two scale axes matter:

1. **Catalog size.** Today's catalog is ~100-200 rows (Provider + Program + Event combined). The full Lake Havasu vision targets 1500-3000 directory entries across 15-25 categories at launch (per pivot framing and audit §3.5). Place rows (per `docs/maintainability/place_model_design.md`) add another 200-500 geographic entries on top. At ~2000 Providers + 500 Places, every category-filtered LIKE chain becomes a sequential scan on the combined table. Each `%term%` filter is roughly 2-5ms at 100 rows on Railway's Postgres; that grows roughly linearly with row count plus the overhead of multiple `OR` branches in the `or_(*conditions)` list.

2. **Concurrent user load.** The audit's §5.2 estimates that the tier 2 LIKE chain becomes a p99 bottleneck at ~500 concurrent users or ~500 catalog rows. Thousands of concurrent users (operator's stated target) multiply both the DB-pool pressure (audit §5.1) and the scan-cost-per-query. A SQLAlchemy `ilike` chain over 2000 rows that returns the matched 8 rows costs roughly the same as a full table scan; at 1000 users with even 10% Tier 2 routing and one query each, that's 100 queries/sec — manageable in isolation, painful when multiplied by 5-10 LIKE branches per query.

**Surfaces that need search.**

1. **Manual search bar** on the homepage and category pages. Full-text matching plus faceted filters: district, sub-trade, price band, dietary, operational flags (`emergency_service`, `by_appointment_only`, `licensed`), mode-specific facets (boat-access for marine, kid-friendly for family, dog-friendly for pets).
2. **Chat tier 2 retrieval** from the entity-matcher pipeline. Structured queries that need ranked candidate sets, not just LIKE matches. Tier 3 LLM synthesis consumes the top N candidates from Tier 2 — quality of synthesis is directly bottlenecked by quality of retrieval.

Both surfaces want the same shape: tokenized full-text, faceted filters, ranked output. Building two retrieval stacks for two surfaces is wasted work; the decision below picks one stack that serves both.

**What's NOT in the tree today.** Grep across the codebase for `pg_trgm`, `tsvector`, `tsquery`, `to_tsvector`, `algolia`, `meilisearch`, `typesense`, `fts` returns only references in the architecture audit itself. Nothing exists yet — this is a greenfield decision.

---

## §2 Four options

### §2.1 Option A — Postgres FTS + `pg_trgm` (in-DB)

Use Postgres's built-in `tsvector` + `tsquery` for full-text search; enable the `pg_trgm` extension for fuzzy matching against names and short strings. Index the columns most used in retrieval: `provider_name`, `description`, `attributes` JSON values, `district`, `category_ref.name`. Maintain `tsvector` columns as generated columns (Postgres 12+ syntax) so Postgres keeps them in sync without trigger code.

**Pros:**

- Zero new infrastructure. Same DB; same connection pool; same Alembic migration shape we already use.
- Transactional consistency. Writes to `providers` immediately reflect in search results — no sync lag, no eventual-consistency window between the catalog and the index.
- Postgres FTS handles millions of rows comfortably at the latency budget we care about. The Lake Havasu catalog (1500-3000 entries at launch; 5000-10000 at year 2) is well within that envelope.
- `pg_trgm` gives us workable typo tolerance (`provider_name % 'plummer'` returns "Plumbing Co." rows with a similarity score above 0.3 by default) without bolting on a dedicated typo-correction layer.
- Free; no Railway service to provision; no vendor account to manage.
- Works on SQLite-fallback tests via the existing test infra — we already conditionally enable Postgres extensions in migrations.

**Cons:**

- Faceted-search query construction is hand-written SQL. At 5+ active facets combined with FTS ranking and a `tsquery` term, queries become long; maintainability tracks with operator discipline.
- Ranking tuning is more manual than dedicated tools. Postgres exposes `ts_rank` and `ts_rank_cd`; combining those with custom bonuses (verification freshness, featured, sponsor weight, time-aware factors) is done in application SQL, not in a tunable index config.
- Typo tolerance via `pg_trgm` is good for short strings (names) but weaker than dedicated engines for multi-word phrase queries with one or two misspellings spread across tokens.
- No native search analytics. We'd compute hot queries from `ChatLog` (`app/db/models.py:237`) ourselves.

**Cost at three scale tiers:**

- V1 launch (~2000 entries, ~1000 daily queries): $0 incremental. Within Railway's existing Postgres tier.
- Category-complete (~5000 entries, ~10000 daily queries): $0 incremental. Larger Postgres tier may be needed regardless of search.
- Year 2 (~10000 entries, ~50000 daily queries): $0 incremental for the search itself. DB tier sizing follows the same curve it would without search.

**Ops burden:** essentially zero. Generated `tsvector` columns are maintenance-free. `pg_trgm` is a Postgres extension — enable once via migration, no ongoing care. Vacuum/analyze handled by autovacuum.

**Sync complexity:** none. The index IS the row, kept current by Postgres itself.

### §2.2 Option B — Meilisearch (self-hosted)

Open-source search engine, Rust-implemented, single binary. Low ops overhead for self-hosted search. Excellent typo tolerance out of the box (configurable per-word distance). Native faceted search with one-shot API for filter facets + counts. Clean Python SDK (`meilisearch-python-sdk`).

**Pros:**

- 10x better DX than Postgres FTS for faceted search. Querying "Mexican restaurants in English Village open now under $$" is one API call with a structured filter object; the same query in Postgres FTS is ~50 lines of SQL.
- Excellent typo tolerance, configurable per-index. `pg_trgm` is close but not as polished.
- Native faceted-counts response shape — the search-bar UI gets "filter X has 14 matches, filter Y has 7 matches" for free.
- Schema is JSON; adding new searchable fields is a config change, not a migration.
- Indexes are append-only and fast to rebuild from scratch (full reindex of 10k rows takes seconds).

**Cons:**

- New service to host on Railway. Single instance is fine for V1 (no clustering needed); HA clustering is available but adds ops weight.
- Sync logic between Postgres (source of truth) and Meilisearch (index) is now our problem. Two reasonable patterns: (a) write-through (after each Provider/Place save, push to Meilisearch); (b) periodic reindex job (every N minutes, full sync). Both have edge cases (write-through fails when Meilisearch is down; periodic reindex creates a staleness window).
- Memory footprint: ~256MB-1GB RAM overhead on the Railway plan. Not a big deal but it's a real line item.
- One more thing to monitor, patch, version-pin. Operator complexity tax.

**Cost at three scale tiers:**

- V1 launch: ~$5-10/mo Railway service for a small Meilisearch instance.
- Category-complete: ~$10-15/mo.
- Year 2: ~$20-40/mo or migration to Meilisearch Cloud at higher tier ($50-150/mo depending on plan).

**Ops burden:** small but non-zero. Health checks, version upgrades, backup of the index (or accept that the index is rebuildable from Postgres). Cumulative engineering time: ~1-2 days/quarter.

**Sync complexity:** moderate. Need a sync wrapper module and a recovery procedure if Meilisearch state diverges from Postgres. ~200-300 LOC of glue plus tests.

### §2.3 Option C — Algolia (managed SaaS)

Hosted commercial search service. Best-in-class DX, fastest perceived latency (~10ms p95 globally via their CDN), heavily used by directory products (Yelp-like, AirBnB-like) and developer docs.

**Pros:**

- Zero ops. They run the cluster; we point our SDK at their API.
- Excellent search quality and analytics dashboard out of the box.
- Fastest perceived latency on the market — Algolia's edge POPs serve search responses near the user.

**Cons:**

- Pricing scales aggressively. As of 2026-05, the Build plan is free up to 10k records and 10k operations/month; beyond that it's roughly $1/1000 records/month (storage) + per-query operation fees. At 5000 records + 30000 daily queries, monthly cost is ~$100-200; at 10000 records + 100k daily queries, monthly cost crosses $500.
- Vendor lock-in. Algolia's ranking, faceting, and filter shapes are proprietary; migrating off (to Meilisearch or Postgres FTS) requires rewriting the query layer.
- Cost-prohibitive past ~10k records OR heavy query volume. The vision's "thousands of concurrent users" target multiplied by 1 query/min lands us in the $500+/mo range.
- Sync complexity is the same as Meilisearch — we still own the Postgres→Algolia push.

**Cost at three scale tiers:**

- V1 launch (~2000 records, ~1000 queries/day = 30k/mo): within Build plan. $0/mo.
- Category-complete (~5000 records, ~10000 queries/day = 300k/mo): ~$100-150/mo.
- Year 2 (~10000 records, ~50000 queries/day = 1.5M/mo): ~$500-1000/mo, possibly more.

**Ops burden:** essentially zero on the operate side; high on the vendor-management side (contract review, pricing renegotiations as we scale).

**Sync complexity:** moderate — same shape as Meilisearch.

### §2.4 Option D — Typesense (self-hosted or hosted)

Open-source search engine in the same shape as Meilisearch — C++ implementation, single binary, native facets, good typo tolerance. Typesense Cloud option exists for managed hosting.

**Pros:**

- Similar to Meilisearch — clean API, native faceted search, good DX.
- Cloud option ($25/mo entry-level) if self-hosting feels like too much.
- Slightly more mature than Meilisearch for some workloads (geographic search has been in Typesense longer).

**Cons:**

- Smaller community than Meilisearch; fewer tutorials, fewer Stack Overflow answers.
- Similar self-hosting overhead to Meilisearch — one more service to monitor.
- No compelling advantage over Meilisearch for our shape (catalog search with geo facets). Meilisearch has caught up on geo features.

**Cost at three scale tiers:**

- V1 launch: $5-10/mo self-hosted; $25/mo Typesense Cloud entry tier.
- Category-complete: $10-15/mo self-hosted; $50/mo Typesense Cloud.
- Year 2: $20-40/mo self-hosted; $100-200/mo Typesense Cloud.

**Ops burden:** same as Meilisearch.

**Sync complexity:** same as Meilisearch.

---

## §3 Recommendation — Option A (Postgres FTS + `pg_trgm`) for V1, with clean Option B (Meilisearch) migration path

Ship Postgres FTS + `pg_trgm` as the V1 search layer. Plan an Option B (Meilisearch) migration path as a known-future lane, triggered by specific quantitative signals rather than by hunch.

**Reasoning:**

1. **Current scale lives comfortably in Postgres FTS.** 1500-3000 directory entries at launch with ~1000 daily search-bar queries plus chat Tier 2 lookups is well within Postgres FTS capabilities. Postgres FTS handles million-row indexes at sub-100ms p95 routinely; our V1 catalog is 1000x smaller than that. We are not in the regime where dedicated search wins on raw performance.

2. **Zero new infrastructure on the V1 critical path.** Adding Meilisearch (Option B) is a Railway service to provision, a sync wrapper to write, a recovery procedure to document, a monitoring story to set up. None of that is hard, but all of it is dispatcher time that competes with Place schema, scheduled scrapers, user accounts, image storage, and the rest of the audit's critical-path lanes. The opportunity cost of building Option B first is real.

3. **Transactional consistency is a genuine feature, not a footnote.** When an operator edits a Provider in admin, the catalog page and chat answers see the update on the very next read — no sync lag, no "did Meilisearch catch up yet?" race. For an operator-curated directory in active data-gathering mode, this matters. Meilisearch sync adds a staleness window (seconds to minutes depending on the push pattern) and a class of bugs where Postgres and Meilisearch disagree about what's in the catalog.

4. **`pg_trgm` covers typo tolerance well enough for V1.** Lake Havasu has ~70k residents and a finite vocabulary of business names. The typo tolerance distance from "plumer" to "plumbing" or "havasu" to "havsu" is comfortable within `pg_trgm`'s default similarity threshold (0.3). Where `pg_trgm` falls short is multi-word phrase queries with multiple misspellings — uncommon enough that the chat retry pattern handles the long tail.

5. **Option B is a clean migration path when faceted-search complexity grows.** The §7 migration plan below estimates ~3-5 days dispatch work to move from Postgres FTS to Meilisearch — same data shape, same query interface, dedicated index. Designing the V1 search layer with this migration in mind means the eventual switch is a swap, not a rewrite. The triggers that justify migration are quantitative (catalog past 10k entries; faceted-filter combinations past 5; latency budget past current p95) and we'll see them coming.

6. **Option C (Algolia) is cost-prohibitive past minimum scale.** At year-2 scale the search line item is $500-1000/mo with vendor lock-in. The same workload on self-hosted Meilisearch is $20-40/mo. Algolia makes sense for products that monetize search directly (e-commerce, classifieds); a Lake Havasu directory with sponsor-based monetization can't justify the spend.

7. **Option D (Typesense) is roughly equivalent to Meilisearch with smaller community.** No compelling reason to pick D over B. Both are viable when the migration triggers fire; Meilisearch has the larger community and slightly cleaner Python SDK, so it's the better default.

**Addressing the "skip A and go straight to Meilisearch" pushback.** Some operators (or contributors) will argue for Meilisearch from day one to avoid the eventual migration cost. The pushback is reasonable but the math doesn't favor it for the Lake Havasu shape:

- The migration cost from A to B is ~3-5 days dispatch. The cost of building B from day one is ~5-7 days (Meilisearch service + sync wrapper + monitoring + recovery + tests). Building B first costs more, not less.
- The faceted-search complexity that B handles better than A is V1.5 territory (per `docs/maintainability/architecture_gaps_for_full_vision_audit.md` — category pages ship Home Services + Eat & Drink first; faceted-filter combinations of 5+ active facets are V1.5 territory). V1 will live happily with 2-3 active facets and Postgres FTS.
- Transactional consistency matters more in operator-curated data-gathering mode than it will at steady-state. We're in that mode for the foreseeable future.
- The sponsor / chat-disclosure surface (`app/chat/disclosure_render.py`) gets simpler when the search layer is in-DB — no need to reason about cross-system race conditions between sponsor state and search results.

If quantitative signals fire that justify Option B (see §7), we migrate. Until they do, Option A wins on opportunity cost.

---

## §4 Index design for Option A (Postgres FTS)

### §4.1 Per-entity `tsvector` columns

Add a generated `search_vector` column to Provider (and later Place per `docs/maintainability/place_model_design.md`). Generated columns let Postgres keep the tsvector synchronized with source columns without trigger code:

```sql
ALTER TABLE providers ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(provider_name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(google_primary_category, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(district, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(attributes::text, '')), 'D')
  ) STORED;

CREATE INDEX ix_providers_search_vector ON providers USING gin(search_vector);
```

Weights: A > B > C > D. Provider name (A) > description and google_primary_category (B) > district (C) > attributes JSON dump (D). The weights inform `ts_rank` scoring — name matches outrank description matches.

Equivalent schema for Place (per place model design memo) with weights applied to `name` (A), `description` (B), `place_type` (B), `district` (C), `amenities::text` (D).

Event uses `title` (A), `description` (B), `tags::text` (C), `location_name` (C).

Program uses `title` (A), `description` (B), `activity_category` (B), `tags::text` (C), `location_name` (C), `provider_name` (B).

Category labels join in at query time via `category_id` FK — not embedded in the tsvector because category names are short and the FK is already indexed.

### §4.2 Trigram index for fuzzy matching

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX ix_providers_name_trgm ON providers USING gin (provider_name gin_trgm_ops);
CREATE INDEX ix_places_name_trgm    ON places    USING gin (name gin_trgm_ops);
```

This enables similarity matching for typo tolerance: `provider_name % 'plummer'` returns providers whose name has trigram similarity above 0.3 (default threshold; tunable). Use cases:

- Chat tier 1 entity matcher fallback when Rapidfuzz scoring is uncertain.
- Search-bar "did you mean" suggestions.
- Address fuzzy match against `address` (worth a separate trgm index on `address` once address-search is a real surface).

### §4.3 Faceted filters

Standard Postgres `WHERE` clauses combined with the tsvector ranking score. Per-category filters use the indexed `category_id` FK. Operational facets stored in `attributes` JSON use functional indexes when the facet is hot enough to justify the index:

```sql
CREATE INDEX ix_providers_emergency_service
  ON providers ((attributes ->> 'emergency_service'))
  WHERE attributes ->> 'emergency_service' = 'true';

CREATE INDEX ix_providers_dog_friendly
  ON providers ((attributes ->> 'dog_friendly'))
  WHERE attributes ->> 'dog_friendly' = 'true';
```

Partial indexes (only indexing rows where the facet is `true`) keep the index small. Each hot facet gets its own functional index; cold facets stay un-indexed and rely on the broader query plan.

District filtering uses the existing `Provider.district` String(64) column (`app/db/models.py:101`) with a plain b-tree index:

```sql
CREATE INDEX ix_providers_district ON providers (district)
  WHERE district IS NOT NULL;
```

Same shape for Place.

For Eat & Drink filters (price band, dietary): when these land per pivot's category-page sequence, follow the same partial-functional-index pattern as `emergency_service` above. Each hot facet earns an index when query telemetry (chat logs + search-bar analytics) shows it's used in >5% of queries.

### §4.4 Ranking

`ts_rank` provides the FTS contribution. Combine with deterministic ranking bonuses computed per-row at query time:

- **Verification freshness:** `last_verified_at within 30 days = +30 points; 30-90 days = +15; 90+ days = 0`. Implementation: `CASE WHEN last_verified_at > NOW() - INTERVAL '30 days' THEN 30 ...`. The bands mirror `app/providers/queries.py:44-46` `fresh`/`acceptable`/`aging`/`stale`.
- **Featured ("Hava's pick"):** `+25` when `featured = true`. Mirrors the editorial flag at `app/db/models.py:124`.
- **Sponsor:** sponsored placement is rendered in a separate sponsor slot (per pivot §3 + `app/chat/disclosure_render.py`), not in organic ranking. Organic ranking does not include sponsor weight. Sponsor slots use the existing `Sponsor` table machinery (`app/db/models.py:503+`) at the disclosure layer.
- **Distance:** when geolocation is available (search bar with browser geo permission, or chat with location context), add a haversine-distance bonus capped at `+20` for "very close" (under 1 mile) tapering to 0 at 5 miles. Lake Havasu City's radius is ~10 miles edge-to-edge so distance bonus is meaningful inside the city.
- **Time-aware ranking heuristic (per Opus #2 locked design):**
  - `currently_open = +30` when `attributes`/`hours_structured` indicates open at the query instant.
  - `heat_aware = bias indoor/shaded under advisory` — when the conditions panel (Opus #1) reports heat advisory and the query is for outdoor activity, indoor venues get `+15`.
  - `matching cuisine/sub-trade = +25` when the query mentions a specific cuisine ("Mexican") or sub-trade ("emergency plumber") and the row's attributes match.
  - `matching district = +15` when the query mentions a district ("English Village") and the row's `district` matches.

Sum the FTS rank (normalized to 0-100 scale via `ts_rank(...) * 100`) with the bonuses, sort descending, take top N. N=8 for chat Tier 2 (matches current `MAX_ROWS` at `app/chat/tier2_db_query.py:35`), N=20 for category-page search-bar (paginated).

Ranking formula lives in a single Python helper (`app/search/ranking.py` new module) that emits the SQL `CASE`/`COALESCE` expression for the order-by clause. Operator-tunable weights via a small config module — see §8 question 3.

---

## §5 Maintenance + reindex

Generated `tsvector` columns update automatically on row change — Postgres handles the synchronization. No manual reindex needed in normal operation.

Operations to document:

- **Postgres extension enablement.** `CREATE EXTENSION IF NOT EXISTS pg_trgm` runs once in the migration. Railway's Postgres supports `pg_trgm` (confirm during implementation — see §8 question 1).
- **Autovacuum.** Default settings are fine. The `gin` index on `search_vector` updates incrementally on insert/update; autovacuum keeps it tidy.
- **REINDEX after bulk loads.** When the scheduled scraper (audit gap 4) imports a large batch of new rows (e.g., 500 Place rows from a Google Places sweep), trigger a `REINDEX INDEX CONCURRENTLY ix_providers_search_vector` afterward. Concurrent reindex avoids locking writes during the operation. Schedule this as a post-import step in the scraper job rather than a separate cron.
- **Statistics refresh.** After bulk loads, `ANALYZE providers` updates query planner stats. Autovacuum handles this normally but explicit `ANALYZE` after a bulk import speeds up planner convergence.

No nightly index maintenance. No separate reindex job needed for V1.

---

## §6 Chat tier 2 integration

Replace the LIKE chains at `app/chat/tier2_db_query.py:33+` with FTS + `pg_trgm` queries. The migration shape:

1. **Build a query helper** at `app/search/fts.py` (new module) that wraps the FTS query construction. Inputs: the existing `Tier2Filters` shape from `app/chat/tier2_schema.py`. Outputs: a SQLAlchemy query with the `search_vector @@ websearch_to_tsquery('english', :term)` clause plus the faceted-filter `WHERE` predicates plus the ranking `ORDER BY`.

2. **Update `_query_providers_orm`** (`app/chat/tier2_db_query.py:811`) to route through `app/search/fts.py` when `filters.entity_name` or `filters.category` is set. Preserve the existing synonym-expansion logic (`_category_needle_set` at `app/chat/tier2_db_query.py:469`) — synonyms expand into `tsquery` `OR` clauses (`'plumber | plumbing | plumber\'s'`).

3. **Update `_query_events`** (`app/chat/tier2_db_query.py:683`) and `_query_programs` (`app/chat/tier2_db_query.py:766`) similarly.

4. **Preserve the open-now filter** (`app/chat/tier2_db_query.py:946-954`). It runs in Python after SQL fetch because hours are JSON; that stays as-is until we move `hours_structured` to a structured table or a generated column. The FTS path returns un-sorted candidates; open-now filters the candidate set; the ranking re-applies on the filtered set before the `MAX_ROWS=8` slice.

5. **Tier 3 LLM prompt** (`app/chat/context_builder.py` referenced from `app/chat/tier3_handler.py:19-20`) receives the top N FTS results as candidate entities. The shape is unchanged from current Tier 2 → Tier 3 handoff; only the ranking + retrieval logic differs.

The matcher at `app/chat/entity_matcher.py:1-100` continues to power Tier 1 deterministic lookup (Rapidfuzz over the in-memory needle set). It's a complementary mechanism, not a replacement target. Tier 1 catches exact and near-exact name hits; Tier 2 FTS catches everything else.

Estimated migration effort: M (1-3 days). The query construction is the only novel work; the surrounding tier-routing machinery is stable.

---

## §7 Migration path to Option B (Meilisearch) — when needed

**When to trigger the migration.** Specific quantitative signals, not vibes:

1. **Catalog grows past 10000 entries.** At that scale, Postgres FTS p95 latency starts climbing past ~100ms for complex multi-facet queries on Railway's Postgres tier. The catalog is unlikely to hit 10k for ~12-18 months given Lake Havasu's bounded business population.
2. **Faceted-search complexity reaches 5+ active facets combined with FTS ranking.** When category pages start surfacing 5-facet filter UIs (e.g., Eat & Drink with cuisine + price + district + dietary + open-now + dog-friendly), the SQL becomes painful enough to maintain that Meilisearch's structured filter API wins on DX alone.
3. **Query latency budget tightens past P95 ~50ms.** If the search-bar UX wants instant-search-as-you-type with 16ms response time, Postgres FTS is going to be the long pole even at small catalog sizes — Meilisearch is 5-10x faster at the same query shape.

Until at least one of these fires, stay on Option A.

**Migration steps when the trigger fires:**

1. **Spin up Meilisearch instance** as a Railway service. Single instance to start; clustering only if SLA needs justify it. Estimated provisioning time: half a day including health checks and backup-of-index policy.
2. **Sync Provider + Place + Event + Program rows into Meilisearch indexes.** One index per entity type. Initial sync is a `python -m scripts.search_reindex --all` run that pulls every row from Postgres and pushes to Meilisearch. Ongoing sync uses a background job (per audit gap 7's RQ+Redis infra) that writes through after every Provider/Place/Event/Program save. Estimated initial sync time: minutes for the V1 catalog; under an hour for year-2 scale.
3. **Add a Meilisearch wrapper module** at `app/search/meilisearch.py` (new) that mirrors the Postgres FTS query interface from `app/search/fts.py`. Same input/output shapes so the calling code (chat Tier 2, category-page search-bar) doesn't change.
4. **Feature-flag chat tier 2 + search-bar to route through Meilisearch.** Flag default off; flip per-surface once parity tests pass. Pattern mirrors `FEATURE_FLAG_DISCLOSURE_RENDERER` (per STATE.md).
5. **Validate parity.** Run a saved query battery (search-bar queries + chat Tier 2 queries from `ChatLog`) against both backends; diff the top-N results. Tolerance for ranking differences depends on operator judgment — exact ranking parity is not achievable across engines, but the top 3-5 results should agree on most queries.
6. **Flip the flag, monitor for one week, then remove Postgres FTS columns** (`search_vector`, the `gin` index) in a follow-up migration. Or leave them dormant if rollback insurance is wanted — they cost negligible storage and zero query overhead when un-used.

**Estimated migration effort when needed:** ~3-5 days dispatch work, spread across the steps above. Plus ongoing ops burden of ~1-2 days/quarter on Meilisearch maintenance.

---

## §8 Open questions for Casey

1. **pg_trgm enabled on Railway by default?** Confirm during the schema-migration lane. Railway's standard Postgres image ships with `pg_trgm` available but the extension needs `CREATE EXTENSION` to enable per-database. Should be a non-issue, flagging to make the implementation lane confirm rather than assume.

2. **Search-bar UX shape — does it support voice input in V1?** Mobile feature; per audit framing and the V1.5 deferral list in §11, voice search is V1.5. Confirming the V1 search bar is text-only.

3. **Ranking tuning — operator-tunable via config file, or hardcoded weights?** Three viable shapes: (a) hardcoded in `app/search/ranking.py`; (b) `app/search/ranking_config.py` Python constants the operator edits and redeploys; (c) `Setting`-table-backed values the operator edits through admin without a deploy. Recommendation: (b) for V1 (simple, low-magic, easy to roll back), (c) when the operator wants to A/B-test weights without a deploy. Defer (c) until the operator has a real desire to tune.

4. **Faceted-filter combinations — should V1 support "Mexican AND Open Now AND English Village AND $$" (4 facets) or limit to 2-3 simultaneous?** My recommendation: technically support arbitrary combinations from day one (the SQL composes them fine); UX-wise, the category-page filter panel surfaces at most 4-5 facets at a time per category. Eat & Drink's facet set is cuisine + price + district + dietary + open-now; that's 5, and the SQL handles it. The UX question is "how do we lay out 5 filter dropdowns on mobile" — that's a `docs/PROJECT.md`-flagged UX call, not a search-layer question.

5. **Search analytics — how do we log + monitor search-bar usage?** Options: (a) extend `ChatLog` shape with a new `surface = "search_bar"` row per query (single table, single query model); (b) new `SearchQueryLog(Base)` table dedicated to search-bar queries with `query_text_hashed`, `result_count`, `selected_result_id`. Recommendation: (b), distinct from chat logs because the schema is different and the analytics surface is different. Defer table creation until the search bar ships and we have a real need for the data.

6. **Place searchability — when does Place enter the search index?** Per `docs/maintainability/place_model_design.md` §11 sequencing, Place ships before the first category landing pages. The FTS `search_vector` for Place should land in the same migration as the Provider `search_vector` — additive, minimal cost, future-proof. Confirming this is the plan.

---

## §9 Effort estimate

Per sub-lane (assuming Option A; Option B migration deferred):

- **Schema migration** — `tsvector` generated columns for Provider + Place + Event + Program; `pg_trgm` extension; `gin` indexes on `search_vector`; trigram indexes on names; functional partial indexes on hot `attributes` facets. **S-M (1 day).** Alembic migration is mostly templated.
- **Chat tier 2 LIKE → FTS migration** — replace `app/chat/tier2_db_query.py:33+` LIKE chains with FTS queries via new `app/search/fts.py` module. Preserve synonym-expansion, open-now filter, time-bucket logic. **M (2-3 days.)** The risk is regression on existing tier-2 voice-battery cases (currently tracked in chat-logs) — needs parity testing.
- **Search-bar UI + endpoint** — new `GET /api/search` route accepting `q`, facet params, pagination cursor; new search-bar component on homepage + category pages; results page or inline result dropdown. **M (2-3 days.)** UX-bound; back-end is straightforward once FTS exists.
- **Ranking heuristic implementation** — `app/search/ranking.py` with the §4.4 ranking formula; tests for each bonus tier; integration with the time-aware locked design from Opus #2. **M (1-2 days.)**
- **Tests** — schema tests for `tsvector` content; ranking tests for each bonus tier; tier 2 parity tests against the current voice battery; search-bar endpoint tests. **M (1-2 days.)** Test surface is bounded.

**Total: 5-7 engineering days**, dispatchable as 1-2 lanes. One lane is the schema + tier 2 migration; the second lane is the search-bar UI + endpoint + ranking. They can run in parallel if dispatch capacity allows; serial is fine.

---

## §10 Sequencing

Lands alongside or shortly after the v1.1 schema pass (per audit §6 Phase 1 sequencing). Foundational for category-page filtering at scale; needed before category pages beyond Home Services ship (Eat & Drink's faceted-filter UX needs search infrastructure).

Sequenced relative to the audit's Phase 1 critical path:

1. **Gap 2 — Category backfill + admin-form validator** (must precede; FTS query joins on `category_id`)
2. **Gap 1 — Place model** (must precede or co-ship; Place needs its own `search_vector`)
3. **Gap 3 — Sub-trade / facet taxonomy** (must precede; functional indexes on `attributes` need stable facet keys)
4. **This lane (search index)**
5. **Gap 6 — Chat → directory data-source migration** (depends on this lane; tier 2 LIKE → FTS migration is part of Gap 6's scope)

If Place ships in Phase 1 per the recommendation in `docs/maintainability/place_model_design.md` §3, then this lane's schema migration is one ticket covering both Provider and Place `search_vector` columns. If Place defers, the Place index lands later — cheap to add but worth co-shipping to avoid double migrations.

---

## §11 What we DON'T build in V1

Explicit defer list to keep V1 scope honest:

- **Vector / semantic search (embedding-based).** Already have `Provider.embedding` (`app/db/models.py:67`) populated but unused for retrieval. Defer until FTS proves insufficient. Embedding-based retrieval adds OpenAI cost per query (embeddings API) and infra complexity (pgvector extension or external vector store). Justified only if FTS recall is provably poor on real queries.
- **Search analytics dashboard.** Operator can see hot queries via DB query or LLM logs (`ChatLog`). Build a dashboard when operator has a real need.
- **Search-as-you-type autocomplete.** V1.5. Basic search bar with submit button is enough for V1. Autocomplete needs sub-50ms p99 which Postgres FTS can do but the UX work is non-trivial.
- **Voice search.** V1.5; mobile-specific feature; defer with the rest of the mobile-polish work.
- **Spelling correction beyond `pg_trgm`.** `pg_trgm` covers the common-case typos. Multi-token spelling correction (the kind that handles "playgound" → "playground" AND "in halvasu" → "in havasu" in the same query) defers until either a real signal appears in chat logs or Option B (Meilisearch) lands and gets it for free.
- **Multi-language search.** English-only `to_tsvector('english', ...)` per §4.1. If Lake Havasu's Spanish-speaking population becomes a meaningful search-bar audience, add a `'spanish'` config alongside the English index. Defer until signal.
- **Geo-bounded search.** Distance bonus in §4.4 is implemented; bounding-box queries (return only rows within X miles of point Y) are V1.5 territory — needs the map integration (audit gap 10) to motivate the UX.
- **Synonym dictionaries beyond the current Tier 2 synonym groups.** `app/chat/tier2_db_query.py:444-450` `_CATEGORY_SYNONYM_GROUPS` ships as the V1 synonym set. Expanded synonyms (e.g., user-facing synonym editor in admin) defer to V1.5.

---

## §12 Summary

Search is a critical-path gap in the architecture for the full Lake Havasu vision. The current LIKE-chain pattern at `app/chat/tier2_db_query.py:33+` breaks around the same scale as the audit's §5.2 prediction — ~500 catalog rows or ~500 concurrent users. The V1 directory targets 1500-3000 entries with thousands of concurrent users; LIKE chains will be the bottleneck before launch absent a search layer.

The decision is **Option A (Postgres FTS + `pg_trgm`) for V1**, with **Option B (Meilisearch) as the clean migration path** when quantitative triggers fire (catalog past 10k entries, faceted-filter complexity past 5 active facets, latency budget past P95 ~50ms). Option A wins on opportunity cost, transactional consistency, and zero infrastructure burden at the V1 scale; Option B is the right next stop when scale or DX complexity outgrows Postgres FTS. Option C (Algolia) is cost-prohibitive past the free tier and adds vendor lock-in. Option D (Typesense) is roughly equivalent to Option B with a smaller community.

Total V1 effort: 5-7 engineering days dispatchable as 1-2 lanes. Sequences after the Category backfill + Place + facet-taxonomy lanes from the audit's Phase 1 critical path; before category pages beyond Home Services ship. Six open questions for operator decision; most are minor / defer-until-V1.5.

**Next step after this memo is reviewed:** lock the open questions, then file a dispatch brief for the §9 sub-lanes — schema migration first (Provider + Place `tsvector` columns + `pg_trgm` extension + indexes), then chat tier 2 FTS migration, then search-bar UI + endpoint + ranking.
