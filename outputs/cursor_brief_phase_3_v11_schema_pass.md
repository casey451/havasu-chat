# Cursor Brief — Phase 3: v1.1 schema pass + operator-curated fields + districts + alerts + category taxonomy rewrite

> **Operator note:** paste this brief to a fresh Cursor chat. **This is Phase 3 of the master build plan** (`docs/maintainability/master_build_plan.md` §4 Phase 3). Phase 2 is COMPLETE on origin (Lane 2A close-out at `5fea2ce`; Lane 2B close-out at the Phase 2B.1 ship — TBD-FILL-AFTER-2B.1-LANDS). Phase 3 is the v1.1 schema pass that lights up the Opus features (heat-aware ranking, conditions panel, crowd notes, seasonal hours, boat-access mode, district paragraphs, alerts) and reshapes the seeded `categories` table to match the locked ChatGPT taxonomy synthesis 12 + executes the audited backfill of legacy `Provider.category` text strings to `category_id` FKs.
>
> The brief is structured around **two explicit sub-phase boundaries** — **Phase 3.1 schema additions** (single additive migration; new tables + columns; no data backfill; no category seed rewrite; no district paragraphs population) and **Phase 3.2 category taxonomy rewrite + audited backfill + district seed + Phase 3 close-out**. Each is independently committable + pytest-green. **You are expected to HALT and report after each sub-phase** so the operator can commit before you proceed. Each sub-phase is sized to one Cursor session.
>
> Authored by Cowork primary at session-19 mid-flight while Phase 2B.1 was running in parallel. Source documents absorbed:
> - `docs/maintainability/master_build_plan.md` §4 Phase 3 — the scope outline (10 schema deliverables + districts table + alerts + category rewrite + backfill)
> - `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md` — the canonical audited mapping for Phase 3.2's backfill; supersedes the original DRAFT
> - `outputs/chatgpt_taxonomy_research_synthesis.md` §1 + §7 — the locked new-taxonomy 12 + V1.5 deferrals
> - `outputs/chatgpt_response_district_paragraphs_v1.md` — operator-authored district paragraphs (Phase 3.2 districts.paragraph seed source); polish required pre-3.2 dispatch
> - Opus design handoff §2.4 + §3 + §6.3 — the heat-exposure / crowd-notes / boat-access / seasonal-hours data shapes that the new entity columns store
> - Conditions + alerts design memo — the alert_subscriptions + alerts_dispatched + external_conditions_cache shapes
> - `outputs/cursor_brief_phase_2b_image_storage_search.md` — brief-shape precedent and Postgres portability checklist (§9) absorbed into §8 below; deviation guardrails in §10; risk register in §11; final report format in §12
> - `outputs/cursor_brief_phase_2a_account_lite.md` §4 — the additive-migration precedent for adding multiple tables in one alembic revision
>
> **No operator prereq.** Phase 3 has no Cloudflare / Resend / external-service prereq. The category seed rewrite + backfill + district seed are all internal-data operations. **However**, Phase 3.2 has **operator decision-locks** that must close before 3.2 dispatches — see §7.

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. `git log --oneline -10` — origin/main should top at the Phase 2 close-out commit chain. Floor SHA chain (pre-Phase-3 dispatch): `c464007` (2B.3 docs) → `8338505` (2B.3 feat) → `aed79ac` (session-18 close-out) → ... → `5fea2ce` (Lane 2A close-out 2A.3). The Phase 2B.1 commit MUST be present on origin before Phase 3.1 dispatches — its alembic head advances the chain by one. Treat the floor as soft; material divergence (top SHA not derivable from this chain, or Phase 2 isn't closed out) is the halt trigger. **Report actual top-10 SHAs.**
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **≥1616** tests (Phase 2B.3 close-out baseline). If 2B.1 has shipped before 3.1 dispatches (which it should have — 2B.1 is the gating Phase 2 sub-phase for Phase 3), count will be higher by the +40-50 net-new tests from 2B.1's six test files (`test_photos_schema.py` + `test_photos_processor.py` + `test_photos_r2_client.py` + `test_photos_routes.py` + `test_photos_sweep.py` + `test_provider_queries_hero_photo.py`). Treat 1616 as soft floor; report actual.
4. `python -m alembic heads` — single head. Floor at authoring: `c8d9e0f1a2b3` (Phase 2B.2 entities FTS + pg_trgm). If 2B.1 shipped first (which it should have), head advanced by one to the photos-table revision. The Phase 3.1 schema-additions migration chains off whatever single head `alembic heads` reports.
5. `python -m alembic current` — should match head when local SQLite is clean. SQLite drift gotchas per `docs/maintainability/dispatch_channels.md` gotcha #10 — chain-walk down_revision before alarming. If the local dev DB has the pre-Phase-1A `slot` duplicate-column drift surfaced in session-19's 2B.3 report, the operator can drop + recreate the dev DB Windows-side; tests don't depend on it.
6. **Read these docs end-to-end before writing any code:**
   - `docs/maintainability/master_build_plan.md` §4 Phase 3 (the deliverables checklist + amended effort estimate)
   - `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md` end-to-end (the audited mapping; §2 buckets A/B/C/E + §3 migration sketch + §4 lock-now items)
   - `outputs/chatgpt_taxonomy_research_synthesis.md` §1 (the locked new-taxonomy 12 slug/name/Tier list) + §7 Q5 (professional-services V1.5 deferral)
   - `outputs/chatgpt_response_district_paragraphs_v1.md` (the district paragraphs draft — 10 paragraphs; polish status depends on operator pre-dispatch action; see §7 below)
   - `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules — anchored Edit on shared files; no `git add` until explicit report; sequential lanes when files overlap)
   - `docs/maintainability/dispatch_channels.md` (15 gotchas as of session-18; especially #4 bash mount staleness + #10 alembic mergepoint diagnostic + #14 reflog forensics + #15 bash mount index.lock corruption)
7. **Read these source files** so you have current line offsets for the anchored edits in §4 + §5:
   - `app/db/models.py` end-to-end (~1000+ lines after Phase 2A.1 + 2B.1; you'll append new model classes — District, AlertSubscription, AlertDispatched, ExternalConditionsCache, PeerRecommendation — at the bottom alongside the Phase 2A.1 + 2B.1 classes; `Entity` is at line ~625 pre-2A.3 — re-grep to verify; extensions follow; `entities.id` is the FK target for `district_id` and follows the same Phase 1 ENTITY pivot pattern as user_favorites/claims/photos)
   - `app/db/entity_types.py` (entity_type constants; no change in Phase 3 — but you'll cite ENTITY_TYPE_COMMERCIAL/PLACE/EVENT/PROGRAM elsewhere)
   - `app/home/queries.py` — `CATEGORY_LABELS` constant at `:27-55` (~28 lines); the slug→display-name mapping that needs updating in Phase 3.2 to reflect the new-taxonomy 12 + Tier 1/2/3 sort ordering. Verify current shape before anchoring edits.
   - `scripts/ingest/validate_enrichment_csv.py` — category vocab allowlist (the validator allowlist for ingest CSVs); needs updating in Phase 3.2 to accept the new slugs and reject the deleted ones
   - `app/admin/router.py` — `:1439` is the admin form free-text category field per the audit memo §4 item 13; after Phase 3.2 ships, this should accept only new-taxonomy slugs (operator may extend in Phase 5, but the validator vocab should already protect against new free-text strings)
   - `app/providers/queries.py` — district-related queries that may need updating once Entity.district_id replaces String district column
   - `app/contrib/approval_service.py` + `scripts/places_load.py` + ingest paths — anything that reads/writes Provider.category text needs awareness during 3.2 backfill
   - `alembic/versions/` directory — verify the current chain; the Phase 3.1 migration chains off whatever single head `alembic heads` reports
   - `tests/conftest.py` — Phase 3 tests should not require new env-var setdefaults (no external services); fixtures may need extending for districts table
8. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches, any file has materially moved from these descriptions, or Phase 2B.1 hasn't shipped (gating dependency), **HALT and report** before proceeding.

---

## §1 Why this lane exists

Phase 1 unified the catalog under `entities` with a discriminator column. Phase 2 gave the directory authentication (Lane 2A) + photo storage + search (Lane 2B). **Phase 3 is the schema-completeness lane**: it lights up the operator-curated fields that the Opus design assumes are present, adds the districts + alerts + conditions-cache infrastructure that Phase 6 UI + Phase 8 background-jobs depend on, and reshapes the seeded `categories` table to match the locked ChatGPT taxonomy synthesis 12.

Repo-wide grep confirms what's missing:

- **No `entities.heat_exposure` column.** Opus #2 (time-aware default ranking + heat-aware bias) reads this column to bias hot-day recommendations toward indoor/shaded venues. Without it, the heat-bias logic has nothing to read.
- **No `entities.crowd_notes` JSON column.** Opus #5 (crowd-aware ranking) renders operator-curated text like "fills up after 5pm Fri-Sun." Without the column, the text has no storage.
- **No `entities.is_mobile_service` bool.** Opus #6 (mobile services like mobile detail / mobile mechanic / mobile vet) needs a flag to surface in "comes to you" filters.
- **No `entities.boat_access` JSON.** Opus #4 (boat-access mode) surfaces restaurants-with-dock, fuel-on-water, marinas-with-pump-out. JSON shape varies per venue type per Opus design.
- **No `entities.seasonal_hours` JSON.** Opus #3 (seasonal-aware operational status) renders "summer hours: 6am-10pm; winter: closed Tue/Wed" on profile pages. Currently the system has only weekly hours.
- **No `districts` table.** The current `entities.district` is a `String(64)` text column with no normalization. Opus design §2.4 + §3 + §6.3 envisions district context paragraphs rendering on every entity profile in that district; that requires a District row + FK + paragraph column.
- **No `entities.district_id` FK.** Replaces the loose String district column with a normalized FK.
- **No `entities.featured` flag on entities directly.** Today, `Provider.featured` lives on the legacy commercial-only table; for Phase 6 unified Hava cards rendering any entity_type, the flag needs to live at the Entity level.
- **No `alert_subscriptions` / `alerts_dispatched` tables.** Phase 8 background-jobs ships the dispatcher; Phase 3 ships the storage. Without the tables, Phase 8 has nowhere to write.
- **No `external_conditions_cache` table.** Opus #1 (conditions panel — AQI, lake temp, weather, AirNow ozone) caches external API responses with TTLs. Storage gated on Phase 3.
- **No `users.preferred_mode`.** Boat-access mode toggle needs server-side persistence per Opus design.
- **No `peer_recommendations` table.** Opus #7 ships disabled-by-flag for V1.5 pilot; storage gated on Phase 3.

And the existing `categories` seed list is structurally stale:

- The migration `e7f8a9b0c1d2` seeded the original 12 categories on 2026-05-13. One day later, on 2026-05-14, the ChatGPT taxonomy synthesis locked a structurally restructured new 12 — 3 identical slugs, 7 renames (1 trivial + 6 rename-plus-scope), 2 deletions (`family` + `community`), 2 net-new (`classes-sports-recreation` + `public-civic-resources`).
- The DRAFT backfill mapping at `docs/maintainability/category_backfill_mapping_DRAFT.md` was authored against the ORIGINAL 12 and is structurally outdated. The audit memo `category_backfill_mapping_audit_2026-05-14.md` is the canonical mapping that supersedes it.
- The 5 professional-services strings (`insurance`, `financial`, `legal`, `real_estate`, `professional_services`) lose their `community` catch-all under the new taxonomy. Synthesis §7 Q5 explicitly defers these to V1.5+ via NULL category_id; the audit memo §4 locks this decision.

**Texture rule reminder:** every existing chat-route response, every Provider profile render, every Tier 2 catalog lookup, every search-bar query, every Photo upload must produce **equivalent output** after Phase 3 as before. The new entity columns are NULL-default in Phase 3.1; population is operator-curated in Phase 5 + 6. The category rewrite is structural but doesn't change row IDs (the seeded rows are renamed in-place; the inserted rows are net-new with new IDs). The district paragraphs are operator-authored content that renders only where templates explicitly reference districts — Phase 6 introduces those template surfaces; Phase 3 only seeds the data.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Phase 3 absorbs the category taxonomy rewrite + backfill | LOCKED 2026-05-14 per audit memo §4 item 1. Alternative (standalone Phase 1.5 ticket) rejected; Phase 3 is the right home. | Audit memo §4 + master plan §10 decision log |
| Effort estimate bumped to M (5-8 days dispatch) + ~2-3 hours operator | LOCKED 2026-05-14 per audit memo §4 item 2. Bump absorbs category rewrite + backfill scope. | Audit memo §4 + master plan §4 Phase 3 amendment |
| Professional-services 5 strings → NULL category_id (V1.5 deferred) | LOCKED 2026-05-14 per audit memo §4 item 3 + synthesis §7 Q5. `insurance` / `financial` / `legal` / `real_estate` / `professional_services` NULL out during backfill; operator queue surfaces them for V1.5 revisit. | Audit memo §4 item 3 + synthesis §7 Q5 |
| Category seed shape: 12 slugs total | LOCKED per synthesis §1. 3 identical + 7 renamed + 2 deleted + 2 net-new. Sort order reflects Tier 1/2/3 ordering. | Synthesis §1 |
| District FK: `entities.district_id → districts.id` (NOT polymorphic) | Phase 1's ENTITY pivot already unified the discriminator. FK targets `entities.id` consistent with user_favorites/claims/photos amendment precedent. `entities.district` String column DROPPED in same migration after backfill. | Master plan §4 Phase 3 + Phase 1 ENTITY pivot |
| Alert tables shape | Per conditions+alerts design memo. `alert_subscriptions(user_id, alert_type, delivery_channel, paused_until, ...)` + `alerts_dispatched(subscription_id, alert_type, trigger_data JSON, dispatched_at, delivery_status, body_snippet)`. SMS-ready but email-only V1. | Conditions+alerts design memo |
| External conditions cache shape | `(source PRIMARY KEY, fetched_at, data JSON, ttl_seconds, last_error, error_count)`. PK on source so upsert is atomic per source. | Opus #1 + conditions+alerts memo |
| Peer recommendations ships disabled-by-flag for V1.5 pilot | Per Opus #7. Schema lands in Phase 3.1; UI + write-paths gated to V1.5. | Opus #7 |
| `entities.featured` migrates from Provider.featured | Phase 6 unified Hava card grammar requires featured-flag at Entity level. Phase 3.1 ADDS `entities.featured`; Phase 3.2 backfills from `providers.featured`. Provider.featured column STAYS (will be dropped in Phase 13 only if/when Provider becomes a thin extension). | Master plan §4 Phase 3 + Opus §6.1 |
| `users.preferred_mode` enum: `default` / `boat` | Per Opus #4 boat-access mode. Default is `default`. Migrates as nullable; backfills NULL → `default` then flip NOT NULL in same migration (mirrors Phase 1A pattern). | Opus #4 |
| Validator vocab update at `scripts/ingest/validate_enrichment_csv.py` | Phase 3.2 in-flight; same window as seed rewrite. | Audit memo §4 item 10 |
| District paragraphs seed source | `outputs/chatgpt_response_district_paragraphs_v1.md` — operator-polished; 5 `[CASEY: ...]` placeholders + 5 verify items must be resolved BEFORE Phase 3.2 dispatches. | District paragraphs draft + master plan §6 |

---

## §3 Sub-phase boundaries (HALT etiquette)

Phase 3 splits into **two** sub-phases. Each is independently committable + pytest-green. **HALT and report between sub-phases** so the operator can commit + push before you proceed.

### Phase 3.1 — Schema additions (additive, no backfill)

**Scope:** Single alembic migration chaining off the current head (Phase 2B.1's photos revision, or earlier if 2B.1 ran later). Adds:

- 7 new `entities` columns (heat_exposure enum, crowd_notes JSON, is_mobile_service bool, boat_access JSON, seasonal_hours JSON, district_id FK nullable, featured bool default false)
- 1 new `users` column (preferred_mode enum default 'default')
- 1 new `districts` table (slug, name, paragraph, display_order, timestamps)
- 1 new `alert_subscriptions` table
- 1 new `alerts_dispatched` table
- 1 new `external_conditions_cache` table
- 1 new `peer_recommendations` table

**No data backfill in 3.1.** All new columns are NULL-default or have safe defaults (`featured=false`, `preferred_mode='default'`). All new tables start empty.

**No category seed rewrite in 3.1.** Phase 3.2 handles the seed rewrite + backfill.

**No district paragraphs seed in 3.1.** Phase 3.2 handles the seed.

**No CATEGORY_LABELS update in 3.1.** Phase 3.2 handles it.

**No validator vocab update in 3.1.** Phase 3.2 handles it.

**No app-layer wiring beyond ORM model additions in 3.1.** The new columns exist as `Mapped[X | None]` properties; no readers / writers added yet. Phase 5 + 6 wire the readers (in admin forms, profile pages, etc.); Phase 8 wires the alerts dispatcher.

**Acceptance gates for 3.1:**
- Pytest stays green (~1660+ collected after Phase 2B.1; +X new tests in `tests/test_phase3_schema_additions.py`)
- `python -m alembic upgrade head` against fresh SQLite reaches the new revision cleanly
- `python -m alembic downgrade -1 && python -m alembic upgrade head` cycles cleanly (reversibility verified)
- Ruff clean
- No raw SQL in `op.execute()` unless verified portable (Postgres + SQLite both)
- No `sa.text("1")` / `sa.text("0")` for Boolean defaults — use `sa.true()` / `sa.false()` per gotcha-absorbed Phase 1A lesson

**Report at §13 format. HALT.**

### Phase 3.2 — Category taxonomy rewrite + audited backfill + district seed + Phase 3 close-out

**Scope:** Multi-part. Single alembic migration (or two chained — Cursor's call per Postgres + SQLite portability):

- **Category seed rewrite:**
  - Rename 7 surviving slugs (per audit memo §3): `eat-and-drink` → `eat-drink`; `home-services` → `home-property-services`; `health` → `health-wellness-care`; `outdoors-and-parks` → `outdoors-parks-trails`; `shopping` → `shopping-essentials`; `auto-and-gas` → `auto-rv-fuel`; `lodging` → `lodging-vacation-rentals`. Display-name string updates per synthesis §1.
  - Delete 2 rows: `family`, `community`. **Pre-flight guard:** ensure no FK references first; if any exist (Phase 2A.1 added `entity_categories` FK to categories.id), re-point per audit memo §2 OR NULL out and queue for operator review. The migration MUST be defensive — `op.execute()` with a SELECT to count references before DELETE.
  - Insert 2 net-new rows: `classes-sports-recreation`, `public-civic-resources`.
  - Reset `sort_order` per synthesis §1 Tier 1/2/3 ordering.

- **Provider/Program category backfill** (per audit memo §2):
  - Bucket A (~24 strings, slug-rename only): `health_medical` → `health-wellness-care`; `food_drink`/`food`/`restaurant`/`bakery` → `eat-drink`; `home_services`/`general_contractor`/`plumbing` → `home-property-services`; `retail` → `shopping-essentials`; `lake_recreation`/`boat_repair`/`boat_rental` → `on-the-water`; `auto` → `auto-rv-fuel`; `lodging` → `lodging-vacation-rentals`; `pet`/`pets`/`veterinary` → `pets`; `event_venue`/`music` → `events`. Plus 7 synthetic strings → NULL (operator queue).
  - Bucket B (5 strings, improved homes): `childcare_education` + `education` → `classes-sports-recreation`; `religion_community` → `public-civic-resources`; subset of `fitness_sports` → `health-wellness-care` (rest deferred to Phase 5 per audit memo §4 item 12); subset of `entertainment_attractions` → various per `google_primary_category` (deferred to Phase 5 per audit memo §4 item 11).
  - Bucket B (5 professional-services strings — V1.5 deferred): `insurance`, `financial`, `legal`, `real_estate`, `professional_services` → NULL category_id. Surfaces in operator queue.
  - Bucket C (operator decisions locked at Phase 3.2 dispatch — see §7 below): `beauty_personal_care`, `tourism`, `barbershop`, K-12 / charter / public schools, bowling / arcades / mini golf.
  - Backfill is idempotent (re-run produces same result; safe to apply downgrade + upgrade cycle).

- **District seed:** Insert 10 rows into `districts` table from operator-polished paragraphs in `outputs/chatgpt_response_district_paragraphs_v1.md`. Slugs: `english-village`, `downtown-main-street`, `north-end`, `lakefront`, `mesquite-bay`, `highway-95-corridor`, `site-six`, `pittsburgh-point`, `castle-rock-area`, `south-side`. Display-order per the order in the draft.

- **`entities.district_id` backfill:** For each Entity with a non-null `district` String column, look up the matching District row by name (after normalization: lowercase + strip) and set `district_id` FK. Unmatched district strings NULL out + surface in operator queue. After backfill, `entities.district` String column DROPPED via batch_alter_table (Postgres + SQLite both supported via batch).

- **`entities.featured` backfill:** For each Entity with `entity_type='commercial'`, copy `Provider.featured → Entity.featured`. Provider.featured column STAYS (not dropped in Phase 3).

- **`users.preferred_mode` backfill:** NULL → `default`; then flip NOT NULL in same migration. Mirrors Phase 1A `entity_type` pattern.

- **`CATEGORY_LABELS` update** at `app/home/queries.py:27-55`: Reflect new 12 slugs + display names + Tier 1/2/3 ordering.

- **Validator vocab update** at `scripts/ingest/validate_enrichment_csv.py`: Accept new slugs; reject deleted slugs.

**Acceptance gates for 3.2:**
- Pytest stays green; +X new tests for category rewrite verification + backfill correctness + district seed + CATEGORY_LABELS coverage
- `python -m alembic upgrade head` against fresh SQLite reaches the new revision cleanly
- `python -m alembic downgrade -1 && python -m alembic upgrade head` cycles cleanly (reversibility verified — note: data backfills aren't strictly reversible in the same way; downgrade should at minimum restore the schema and produce a queryable DB without crashing)
- Ruff clean
- All 41 legacy category strings have been processed (either backfilled, NULL'd with queue surface, or hit operator-decision-locked Bucket C path)
- All 10 district paragraphs land in the seed
- All entities with String district values have either a `district_id` FK (matched) or a queue surface entry (unmatched)
- `entities.district` String column has been dropped after backfill
- `Provider.featured → Entity.featured` backfill complete for all commercial entities
- `users.preferred_mode` NOT NULL after backfill

**Report at §13 format.** After 3.2 ships + commits, **Phase 3 is COMPLETE**. Master plan §4 Phase 3 gets a SHIPPED header; Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable lane.

---

## §4 Phase 3.1 deliverables (in dispatch order)

Author the schema additions in a single new alembic migration `<rev>_phase3_schema_pass.py` chaining off the current single head. The migration is large but additive — no data backfill, no destructive operations.

### §4.1 New `entities` columns (7 columns, all additive)

Append to the `entities` table via `op.batch_alter_table('entities')`:

- `heat_exposure: VARCHAR(20)` nullable, CHECK constraint `IN ('indoor', 'shaded', 'outdoor', 'water_adjacent')`. Default NULL (operator-curated in Phase 5).
- `crowd_notes: JSON` nullable. Default NULL.
- `is_mobile_service: BOOLEAN` NOT NULL default `sa.false()`. Tests pass `is_mobile_service=False` implicitly.
- `boat_access: JSON` nullable. Default NULL.
- `seasonal_hours: JSON` nullable. Default NULL. (NOTE: Phase 1A already added a `seasonal_hours` extension table; verify whether the new Entity column is meant to replace or supplement — re-grep Phase 1A migration. If conflict, halt and report; this may need a brief amendment.)
- `district_id: VARCHAR(36)` nullable, FK to `districts.id` with `ondelete='SET NULL'`. INDEX `ix_entities_district_id`.
- `featured: BOOLEAN` NOT NULL default `sa.false()`. INDEX `ix_entities_featured` (partial Postgres-only via dialect gate would be ideal but plain index on SQLite + Postgres both is acceptable; mirror Phase 2B.2's two partial JSON indexes shape if you want a partial Postgres-only index).

Note: `entities.district: VARCHAR(64)` String column STAYS in Phase 3.1 (drop happens in 3.2 after backfill).

### §4.2 New `districts` table

```
districts:
  id          VARCHAR(36) PRIMARY KEY  (uuid)
  slug        VARCHAR(64) UNIQUE NOT NULL  (e.g., "english-village")
  name        VARCHAR(128) NOT NULL          (display name)
  paragraph   TEXT NOT NULL                  (operator-authored rich text; 1-3 paragraphs typically; renders on profile pages per Opus design §6.3)
  display_order INTEGER NOT NULL default 0   (operator-curated ordering for any list surfaces)
  created_at  TIMESTAMP NOT NULL default sa.func.now()
  updated_at  TIMESTAMP NOT NULL default sa.func.now()  (no on-update trigger in V1; operator-curated infrequent updates)

INDEX ix_districts_slug (UNIQUE)
INDEX ix_districts_display_order
```

### §4.3 New `alert_subscriptions` table

```
alert_subscriptions:
  id              VARCHAR(36) PRIMARY KEY
  user_id         VARCHAR(36) NOT NULL FK users.id ON DELETE CASCADE
  alert_type      VARCHAR(32) NOT NULL CHECK IN ('heat_advisory', 'aqi_alert', 'lake_hazard', 'event_traffic')
  delivery_channel VARCHAR(16) NOT NULL CHECK IN ('email', 'sms') default 'email'   (sms-ready, V1.5 wired)
  paused_until    TIMESTAMP NULL
  created_at      TIMESTAMP NOT NULL default sa.func.now()

INDEX ix_alert_subscriptions_user_id
INDEX ix_alert_subscriptions_alert_type
UNIQUE (user_id, alert_type, delivery_channel)   -- one sub per (user, type, channel)
```

### §4.4 New `alerts_dispatched` table (audit log)

```
alerts_dispatched:
  id              VARCHAR(36) PRIMARY KEY
  subscription_id VARCHAR(36) NOT NULL FK alert_subscriptions.id ON DELETE CASCADE
  alert_type      VARCHAR(32) NOT NULL                    (denormalized for query speed + audit-trail durability if sub deleted)
  trigger_data    JSON NOT NULL                           (the data that triggered the alert — e.g., {"heat_index": 109, "advisory_level": "warning"})
  dispatched_at   TIMESTAMP NOT NULL default sa.func.now()
  delivery_status VARCHAR(20) NOT NULL CHECK IN ('queued', 'sent', 'failed', 'bounced')
  body_snippet    VARCHAR(280) NULL                       (first 280 chars of the email body for audit-debug)

INDEX ix_alerts_dispatched_subscription_id
INDEX ix_alerts_dispatched_dispatched_at
INDEX ix_alerts_dispatched_delivery_status
```

### §4.5 New `external_conditions_cache` table

```
external_conditions_cache:
  source          VARCHAR(64) PRIMARY KEY                 (e.g., "airnow_aqi_lhc", "noaa_weather_lhc", "usgs_lake_temp_havasu")
  fetched_at      TIMESTAMP NOT NULL
  data            JSON NOT NULL                           (the cached response payload)
  ttl_seconds     INTEGER NOT NULL                        (e.g., 600 for AQI / 1800 for weather / 3600 for lake temp)
  last_error      VARCHAR(500) NULL                       (last error message if fetch failed)
  error_count     INTEGER NOT NULL default 0              (resets on successful fetch)

(no separate id PK — source is the natural PK; upserts are atomic)
INDEX ix_external_conditions_cache_fetched_at
```

### §4.6 New `peer_recommendations` table (V1.5 pilot, ships disabled-by-flag)

```
peer_recommendations:
  id               VARCHAR(36) PRIMARY KEY
  recommender_user_id  VARCHAR(36) NOT NULL FK users.id ON DELETE CASCADE
  entity_id        VARCHAR(36) NOT NULL FK entities.id ON DELETE CASCADE
  text             VARCHAR(500) NOT NULL                  ("I love this place because...")
  status           VARCHAR(20) NOT NULL CHECK IN ('pending', 'published', 'rejected') default 'pending'
  created_at       TIMESTAMP NOT NULL default sa.func.now()
  approved_at      TIMESTAMP NULL
  approved_by_user_id  VARCHAR(36) NULL FK users.id ON DELETE SET NULL

INDEX ix_peer_recommendations_entity_id_status
INDEX ix_peer_recommendations_recommender_user_id
INDEX ix_peer_recommendations_status
UNIQUE (recommender_user_id, entity_id)   -- one rec per (user, entity)
```

### §4.7 New `users.preferred_mode` column

Append to the `users` table via `op.batch_alter_table('users')`:

- `preferred_mode: VARCHAR(16)` NOT NULL default `'default'`, CHECK constraint `IN ('default', 'boat')`. (Optional: server_default `sa.text("'default'")` if portable; verify on Postgres + SQLite. Simpler: nullable + backfill + flip NOT NULL in same migration; mirrors Phase 1A `entity_type` pattern.)

### §4.8 Migration anatomy

The Phase 3.1 migration is **additive-only** — no data backfill, no destructive operations. Single file:

```
alembic/versions/<rev>_phase3_schema_pass.py
```

`upgrade()` creates the 5 new tables + adds the 8 new columns (7 on entities + 1 on users) + creates indexes + CHECK constraints. Postgres + SQLite both via `op.batch_alter_table` for the column additions on existing tables; `op.create_table` for the new tables. All defaults use `sa.true()` / `sa.false()` / `sa.func.now()` per Postgres portability rule (NEVER `sa.text("1")` / `sa.text("0")`).

`downgrade()` reverses by `op.drop_table` for the 5 new tables + `op.batch_alter_table('entities')` to drop the 7 columns + `op.batch_alter_table('users')` to drop preferred_mode. Reversibility test required.

The migration chains off the current single head as reported by `alembic heads` at dispatch time. If multiple heads exist (which shouldn't happen but check), halt + report.

### §4.9 ORM model additions in `app/db/models.py`

Append after the Phase 2B.1 Photo class (or after Phase 2A.1 Claim if 2B.1 hasn't shipped — tail-append discipline):

- `District` model class (mirrors User shape)
- `AlertSubscription` model class (mirrors Claim shape with CHECK constraints on enum-like strings)
- `AlertDispatched` model class
- `ExternalConditionsCache` model class
- `PeerRecommendation` model class

Plus extensions to existing models:

- `Entity` class — add 7 new column Mapped[X | None] properties + relationships if any (e.g., `district: Mapped[District | None]` via `relationship(District, foreign_keys=[district_id])`)
- `User` class — add `preferred_mode: Mapped[str]` property

ALL relationships set `viewonly=False` (default) unless there's a specific reason (mirroring 2B.1's Photo viewonly relationship which filters status='live'). District is bidirectional 1:N (one district has many entities).

### §4.10 New tests for Phase 3.1

New test file `tests/test_phase3_schema_additions.py`. ~15-20 tests:

1. Migration upgrade+downgrade+upgrade cycle on fresh SQLite (reversibility)
2. `entities` table has 7 new columns with expected types + defaults
3. Each CHECK constraint on enum-like columns rejects invalid values (3 tests: heat_exposure, alert_type on alert_subscriptions, delivery_status on alerts_dispatched)
4. `districts` table exists with expected columns
5. `alert_subscriptions` UNIQUE (user_id, alert_type, delivery_channel) rejects duplicates
6. `alert_subscriptions` FK CASCADE on user delete: alerts_dispatched audit rows also cascade-delete
7. `external_conditions_cache` upsert pattern (source PK) works
8. `peer_recommendations` UNIQUE (recommender_user_id, entity_id) rejects duplicates
9. `peer_recommendations` status CHECK rejects invalid statuses
10. `users.preferred_mode` defaults to 'default' on new user creation
11. `entities.featured` defaults to False on new entity creation
12. `entities.is_mobile_service` defaults to False on new entity creation
13. ORM relationship `Entity.district` returns District row when `district_id` is set
14. ORM relationship `Entity.district` returns None when `district_id` is NULL
15. Indexes exist (verify via `inspect(engine).get_indexes('entities')`)

### §4.11 What NOT to do in Phase 3.1

- DO NOT seed any data (categories, districts, etc.) — that's 3.2.
- DO NOT backfill `entities.district_id` from String district — that's 3.2.
- DO NOT update `CATEGORY_LABELS` in `app/home/queries.py` — that's 3.2.
- DO NOT update validator vocab in `scripts/ingest/validate_enrichment_csv.py` — that's 3.2.
- DO NOT drop `entities.district` String column — that's 3.2 after backfill.
- DO NOT add app-layer readers/writers for the new columns/tables beyond ORM Mapped properties — those are Phase 5 (admin form) + Phase 6 (profile/card renderers) + Phase 8 (alerts dispatcher).
- DO NOT touch chat-route response shape — Phase 3 ships zero new chat surfaces.
- DO NOT touch the `categories` table — that's 3.2.
- DO NOT touch `app/home/queries.py:CATEGORY_LABELS` — that's 3.2.
- DO NOT relitigate the 7 column choices on entities — they're LOCKED per master plan §4 Phase 3.

---

## §5 Phase 3.2 deliverables (in dispatch order)

Author the category rewrite + backfill + district seed + close-out in a new alembic migration `<rev>_phase3_data_pass.py` chaining off the Phase 3.1 schema-additions revision.

### §5.1 Category seed update

Migration logic:

1. **Rename 7 surviving slugs** via `op.execute()` with portable SQL:
   - `UPDATE categories SET slug='eat-drink', name='Eat & Drink' WHERE slug='eat-and-drink'`
   - `UPDATE categories SET slug='home-property-services', name='Home & Property Services' WHERE slug='home-services'`
   - `UPDATE categories SET slug='health-wellness-care', name='Health, Wellness & Care' WHERE slug='health'`
   - `UPDATE categories SET slug='outdoors-parks-trails', name='Outdoors, Parks & Trails' WHERE slug='outdoors-and-parks'`
   - `UPDATE categories SET slug='shopping-essentials', name='Shopping & Essentials' WHERE slug='shopping'`
   - `UPDATE categories SET slug='auto-rv-fuel', name='Auto, RV & Fuel' WHERE slug='auto-and-gas'`
   - `UPDATE categories SET slug='lodging-vacation-rentals', name='Lodging & Vacation Rentals' WHERE slug='lodging'`

2. **Pre-flight check** for FK references to soon-to-be-deleted rows (`family`, `community`):
   ```
   SELECT COUNT(*) FROM entity_categories WHERE category_id IN (SELECT id FROM categories WHERE slug IN ('family', 'community'))
   ```
   If count > 0, NULL the entity_categories.category_id for those rows (or DELETE the entity_categories rows entirely — Cursor's call per data semantics; flag in §13). Same check for any other FK referencer if discovered during file reads.

3. **Delete 2 rows:** `DELETE FROM categories WHERE slug IN ('family', 'community')`

4. **Insert 2 new rows** with new UUIDs:
   - `classes-sports-recreation` / Classes, Sports & Recreation
   - `public-civic-resources` / Public & Civic Resources

5. **Reset `sort_order`** per synthesis §1 Tier 1/2/3 ordering. Cite synthesis explicitly in migration docstring so future readers know where the order comes from. Suggested ordering (verify against synthesis §1):
   - Tier 1: eat-drink (1), home-property-services (2), health-wellness-care (3), shopping-essentials (4), auto-rv-fuel (5)
   - Tier 2: outdoors-parks-trails (6), on-the-water (7), classes-sports-recreation (8), events (9), lodging-vacation-rentals (10)
   - Tier 3: pets (11), public-civic-resources (12)

### §5.2 Provider/Program category backfill (audited mapping)

The full mapping is in `docs/maintainability/category_backfill_mapping_audit_2026-05-14.md` §2. Author the backfill in two passes:

**Pass 1 — Bucket A (~24 strings, slug-rename only, well-confident):**

For each (legacy_string, new_slug) pair in Bucket A, run:
```
UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug='<new_slug>')
WHERE category = '<legacy_string>' AND category_id IS NULL
```

The same pattern for `programs.activity_category` if it's a separate column on programs (verify via models.py — Phase 1A may have unified this).

**Pass 2 — Bucket B (5 strings, improved homes):**

- `UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug='classes-sports-recreation') WHERE category IN ('childcare_education', 'education', 'edu') AND category_id IS NULL`
- `UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug='public-civic-resources') WHERE category = 'religion_community' AND category_id IS NULL`
- `fitness_sports` partial backfill: `UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug='health-wellness-care') WHERE category = 'fitness_sports' AND category_id IS NULL`. The recreational subset (tennis, pickleball, swimming) gets re-triaged in Phase 5 per audit memo §4 item 12.
- `entertainment_attractions` — DEFER to Phase 5 per audit memo §4 item 11; leave category_id NULL for now, surface in operator queue.

**Pass 3 — Bucket B professional-services (V1.5 deferred, NULL):**

```
UPDATE providers SET category_id = NULL
WHERE category IN ('insurance', 'financial', 'legal', 'real_estate', 'professional_services')
AND category_id IS NULL
```

Surface in operator queue (note in §13 report so operator can see counts; admin form already shows them).

**Pass 4 — Bucket C (operator decisions locked at Phase 3.2 dispatch):**

The 5 operator decisions in §7 below MUST be locked before Phase 3.2 dispatches. The migration encodes the locked decisions as explicit SQL. If any decision is unlocked at dispatch time, HALT.

**Idempotency:** The `AND category_id IS NULL` guard makes the backfill safe to re-run. Downgrade reverses via `UPDATE providers SET category_id = NULL WHERE category_id IS NOT NULL AND category IS NOT NULL` (which restores pre-3.2 state for affected rows).

### §5.3 District seed

For each of 10 districts in `outputs/chatgpt_response_district_paragraphs_v1.md` (operator-polished, all `[CASEY: ...]` placeholders resolved):

```
INSERT INTO districts (id, slug, name, paragraph, display_order, created_at, updated_at)
VALUES (uuid4(), 'english-village', 'English Village', '<paragraph text>', 1, now(), now())
```

Display order: English Village (1), Downtown / Main Street (2), North End (3), Lakefront (4), Mesquite Bay (5), Highway 95 Corridor (6), Site Six (7), Pittsburgh Point (8), Castle Rock area (9), South side (10). Operator can re-order via admin form in Phase 5 if desired.

### §5.4 `entities.district_id` backfill (from String → FK)

For each entity with a non-null `district` String column:

```
UPDATE entities SET district_id = (
  SELECT districts.id FROM districts
  WHERE LOWER(TRIM(districts.name)) = LOWER(TRIM(entities.district))
)
WHERE district IS NOT NULL AND district_id IS NULL
```

Unmatched String values (where the SELECT returns no row — e.g., a district String column has "Unknown" or some typo'd value) leave `district_id` NULL. Count of unmatched rows surfaces in §13 report; operator queue from admin form lets ops fix.

After backfill, drop `entities.district` String column:
```
op.batch_alter_table('entities') as batch_op:
    batch_op.drop_column('district')
```

### §5.5 `entities.featured` backfill

For each commercial entity, copy `Provider.featured → Entity.featured`:

```
UPDATE entities SET featured = (
  SELECT providers.featured FROM providers
  WHERE providers.entity_id = entities.id
)
WHERE entity_type = 'commercial' AND id IN (SELECT entity_id FROM providers WHERE featured = TRUE)
```

Non-commercial entities keep `featured=false` default.

### §5.6 `users.preferred_mode` backfill + NOT NULL flip

If Phase 3.1 added `preferred_mode` as nullable, 3.2 backfills NULL → 'default' then flips NOT NULL:

```
UPDATE users SET preferred_mode = 'default' WHERE preferred_mode IS NULL
```

Then `op.batch_alter_table('users')` with `batch_op.alter_column('preferred_mode', nullable=False)`.

If 3.1 already shipped preferred_mode as NOT NULL with `default='default'`, this step is a no-op.

### §5.7 CATEGORY_LABELS update at `app/home/queries.py:27-55`

Replace the ~28-line constant with the new-taxonomy 12 slug→display name mapping, ordered per Tier 1/2/3 sort. Anchor on the existing constant via Edit.

### §5.8 Validator vocab update at `scripts/ingest/validate_enrichment_csv.py`

Find the category allowlist (likely a list constant or a set literal). Update to contain the new 12 slugs. Add the deleted slugs (`family`, `community`, plus the 7 old renamed slugs like `eat-and-drink`) to a "rejected" list so legacy CSVs fail validation with a clear error.

### §5.9 New tests for Phase 3.2

New test file `tests/test_phase3_data_pass.py`. ~15-20 tests:

1. Migration upgrade reaches the new revision cleanly
2. Migration downgrade restores pre-3.2 state (categories have 12 rows including family + community; providers' category_id values are NULL for renamed-slug references — note backfill semantics)
3. After upgrade, categories table has exactly 12 rows
4. After upgrade, slugs match the new-taxonomy 12 list (assert set equality)
5. After upgrade, `family` and `community` slugs are absent
6. After upgrade, `classes-sports-recreation` and `public-civic-resources` slugs are present
7. After upgrade, sort_order reflects Tier 1/2/3 ordering
8. Bucket A backfill: a fixture provider with `category='food_drink'` has `category_id` pointing to `eat-drink` row
9. Bucket B backfill: a fixture provider with `category='childcare_education'` has `category_id` pointing to `classes-sports-recreation`
10. Bucket B backfill: a fixture provider with `category='religion_community'` has `category_id` pointing to `public-civic-resources`
11. Bucket B V1.5 deferral: a fixture provider with `category='insurance'` has `category_id IS NULL` after backfill
12. Districts table has exactly 10 rows after seed
13. Slug `english-village` exists in districts; paragraph field non-empty
14. `entities.district_id` backfill: fixture entity with `district='English Village'` has `district_id` pointing to the `english-village` row
15. After backfill, `entities.district` String column has been dropped (verify via `inspect(engine).get_columns('entities')`)
16. `entities.featured` backfill: fixture provider with `featured=TRUE` produces an Entity with `featured=TRUE`
17. CATEGORY_LABELS now contains new-taxonomy slugs (assert in `app/home/queries.py`)
18. Validator vocab now rejects deleted slugs (`family`, `community`) and accepts new slugs
19. Backfill is idempotent (running the migration's data-pass logic twice produces the same result)
20. Pre-flight FK guard: fixture with `entity_categories` row pointing at `family` produces a defensive resolution before the DELETE (either re-point or NULL — Cursor's call per data semantics; pin behavior in test)

### §5.10 Acceptance gates for 3.2

- Pytest stays green; +X new tests pass per §5.9
- `alembic upgrade head` reaches new revision cleanly on fresh SQLite
- `alembic downgrade -1 && alembic upgrade head` cycles cleanly
- Ruff clean
- All 41 audit-memo strings have been processed (count check)
- All 10 district paragraphs land in seed
- `entities.district` String column dropped after backfill
- `entities.featured` backfilled for all commercial entities
- `users.preferred_mode` is NOT NULL after migration

### §5.11 What NOT to do in Phase 3.2

- DO NOT skip the pre-flight FK guard on `entity_categories → categories` before deleting `family` + `community` rows. If you skip and any FK exists, the migration crashes mid-flight.
- DO NOT drop `entities.district` String column BEFORE backfilling `district_id` — order matters; drop column AFTER backfill.
- DO NOT drop `Provider.featured` column — that's Phase 13+ only if/when Provider becomes a thin extension.
- DO NOT drop legacy `Provider.category` text column — V1.5 / Phase 13 only after the operator queue surfaces are reviewed.
- DO NOT process Bucket C decisions inline without operator lock. The 5 Bucket C items in §7 MUST have explicit operator decisions BEFORE Phase 3.2 dispatches.
- DO NOT modify the audit memo or synthesis docs.
- DO NOT change the order of the new-taxonomy 12 sort_order without re-verifying against synthesis §1.
- DO NOT change CATEGORY_LABELS or validator vocab beyond what the audit memo + synthesis specify.
- DO NOT touch admin form free-text category field at `app/admin/router.py:1439` — Phase 5 owns admin form extensions; the validator vocab update is the V1 safety net.
- DO NOT touch chat-route response shape — Phase 3 is a schema-data pass, zero chat-surface changes.

---

## §6 What's already locked vs what's not

Locked (do not relitigate):
- The 12-slug new-taxonomy list (synthesis §1; see §2 row "Category seed shape")
- Professional-services 5 strings → NULL (synthesis §7 Q5 + audit memo §4 item 3)
- District FK targets entities.id (not polymorphic)
- Effort estimate M (5-8 days dispatch) + ~2-3 hours operator
- Phase 3 absorbs the category rewrite + backfill (audit memo §4 item 1)
- District paragraphs come from `outputs/chatgpt_response_district_paragraphs_v1.md` (10 paragraphs)

Open (must lock BEFORE Phase 3.2 dispatches — see §7):
- 5 Bucket C operator decisions (`beauty_personal_care`, `tourism`, `barbershop`, schools, recreational-entertainment)
- Operator polish of the 5 `[CASEY: ...]` district paragraph placeholders + 5 verify items in the draft

Open (deferred to Phase 5 per audit memo §4):
- `entertainment_attractions` per-row triage via `google_primary_category`
- `fitness_sports` recreational subset re-triage
- Production `SELECT DISTINCT category FROM providers` audit (catch new free-text strings since DRAFT audit)

---

## §7 Operator decision-locks needed BEFORE Phase 3.2 dispatches

Five Bucket C decisions from the audit memo §4 "lock-during-Phase-3" list:

1. **`beauty_personal_care` final disposition.** Options:
   - (a) Force into `health-wellness-care` (defensible — spa/massage framing). Risk: framing mismatch with the "medical+wellness" identity of that category.
   - (b) File a 13th category (e.g., `personal-care-beauty`). Risk: breaks the locked 12-slug count.
   - (c) NULL category_id (V1.5 deferral, same shape as professional-services). Risk: barbershops + salons disappear from category landing pages until V1.5.
   - **Recommendation:** (c) NULL queue for V1; revisit at V1.5 if cold-pitch demand justifies a 13th category. **Operator locks at dispatch.**

2. **`tourism` final disposition.** Options:
   - (a) NULL queue for operator triage (DRAFT recommendation).
   - (b) Force into `lodging-vacation-rentals` for hotels + visitor-info-leaning bits.
   - (c) Split: hotels → `lodging-vacation-rentals`, attractions → `events`, visitor-info → `public-civic-resources`.
   - **Recommendation:** (a) NULL queue. The split logic is operator-triage-friendly; backfill doesn't have enough signal to auto-split. **Operator locks at dispatch.**

3. **`barbershop` test fixture disposition.** Test-only string. Options:
   - (a) NULL category_id (test fixture; doesn't matter).
   - (b) Force into whatever `beauty_personal_care` resolves to.
   - **Recommendation:** (a) NULL. Tests don't need a category for fixtures; deviation is documented. **Operator locks at dispatch.**

4. **K-12 / charter / public schools** disposition. Options:
   - (a) `classes-sports-recreation` (educational schedules; same bucket as childcare_education).
   - (b) `public-civic-resources` (public-school institutional framing).
   - **Recommendation:** (a) `classes-sports-recreation` for consistency with `childcare_education`. Charter + private schools fit cleanly; public schools also fit since they're scheduled educational programs (the bucket name explicitly contains "classes"). **Operator locks at dispatch.**

5. **Bowling / arcades / mini golf** disposition. Options:
   - (a) `classes-sports-recreation` (entertainment-as-activity).
   - (b) New entertainment category (breaks 12-slug count).
   - (c) Split: bowling → classes-sports-rec; arcades → ??? — no clean home; arcades-as-entertainment doesn't fit anywhere.
   - **Recommendation:** (a) `classes-sports-recreation`. The slug name explicitly includes "recreation" and these venues are recreational. **Operator locks at dispatch.**

Plus operator polish of the district paragraph draft:
- 5 `[CASEY: ...]` placeholders in `outputs/chatgpt_response_district_paragraphs_v1.md` — Mesquite Bay (1), Pittsburgh Point (2), Castle Rock area (1), South side (1)
- 5 "Casey to verify" items at the bottom of the same draft
- Estimated time: ~15-20 minutes operator polish

**Operator reality check, session-20 (2026-05-12):** Lake Havasu is too small (~57k pop, ~46 sq mi) for a 10-district paragraph-landing-page UX. McCulloch is the main commercial strip — street-based search ("bars on McCulloch") would match user mental models better than district filters. English Village is the only district with bounded character. The other 8 in the draft are directional ("North End", "South side"), landmark-based ("Site Six", "Mesquite Bay"), or geographic ("Castle Rock area", "Highway 95 Corridor") — not user-mental-model districts. Phase 3.1 schema is forward-compatible and ships unaffected. **Phase 3.2 district UX direction is OPEN — three candidate paths:** (a) pare to 2-3 real districts (English Village + Downtown/McCulloch + maybe Lakefront commercial) + "Greater Lake Havasu" default, drop the 10-paragraph plan; (b) ship 3.2 with `district_id` backfill from existing String district column but defer paragraph landing pages to V1.5, use district as a backend tag; (c) re-think the primitive — districts demoted to backend tag, surface streets/landmarks as the user-facing filter dimension (highest cost; reopens 3.1 scope). **Decision deferred to Phase 3.2 dispatch authoring time.** When Phase 3.1 closes out, the dispatch-prompt author re-engages this question before authoring the 3.2 dispatch prompt. The district paragraphs draft at `outputs/chatgpt_response_district_paragraphs_v1.md` should be treated as illustrative not canonical until this resolves.

---

## §8 Postgres portability checklist (carried forward from Phase 2 brief §9)

- The bash sandbox + tests run SQLite; production runs Postgres.
- Phase 2A.1 (`92ce4899dc08_account_lite_v01.py`) and Phase 2B.2 (`c8d9e0f1a2b3_entities_fts_pgtrgm.py`) are the recent precedents for portable migrations. Mirror their shape.
- Use `sa.true()` / `sa.false()` (NOT `sa.text("1")` / `sa.text("0")`) for Boolean server_default values. Cite Phase 1A's hotfix `5132162` lesson — Postgres rejects text("1") as boolean default.
- Use `sa.func.now()` (NOT `sa.text("CURRENT_TIMESTAMP")`) for default timestamps.
- No raw SQL inside `op.execute()` unless verified portable across both dialects. SQLite is loose about quoting + keyword strictness + NULL handling in unique constraints + JSON syntax; Postgres is strict. Test backfill SQL against both engines before committing.
- For JSON columns: `sa.JSON()` is portable; both dialects support it (SQLite stores as TEXT, Postgres as JSONB if explicitly typed — for Phase 3 just use `sa.JSON()` and the dialect handles it).
- For enum-like columns: VARCHAR + CHECK constraint is portable. Native ENUM type is NOT (Postgres-only). Mirror Phase 2A.1's `users.role` shape.
- For partial indexes (Postgres only): if you add any, gate via `bind.dialect.name == "postgresql"` early return. Phase 2B.2 added two partial JSON indexes this way.
- For batch_alter_table on existing tables: SQLite requires it for column drops; Postgres prefers it for consistency. Phase 1D and Phase 2A.1 both use this pattern.
- Idempotency: Use `IF NOT EXISTS` / `IF EXISTS` in raw SQL where supported. SQLite supports both; Postgres supports both. Don't assume — verify per construct.

---

## §9 Acceptable deviations (open-doors for Cursor)

### Phase 3.1

- **Table ordering in the migration.** The `op.create_table()` calls can land in any order as long as FKs are satisfied (e.g., `districts` before `entities.district_id` FK addition; `alert_subscriptions` before `alerts_dispatched`). Brief assumes top-down order in §4; Cursor may reorder for clarity. Flag in §13.
- **`entities.featured` partial Postgres-only index** — flag if you skip this performance optimization. Mirroring Phase 2B.2's two partial JSON indexes is acceptable. If you skip, simple INDEX is fine for V1.
- **`alerts_dispatched.alert_type` denormalization** — brief specifies denormalized alert_type (also present on alert_subscriptions row). If Cursor finds this redundant + the FK chain doesn't break audit-trail-after-sub-deleted semantics, flag in §13 to discuss removal.
- **`Entity.seasonal_hours` JSON column vs existing extension table** — Phase 1A added a `seasonal_hours` extension table per master plan. Phase 3 §4.1 specifies an `entities.seasonal_hours` JSON column. If both exist, this is a redundant shape. **Halt and flag in §13 before authoring the column** — operator may want to clarify whether to use the existing extension table or the new column. If the operator confirms the new column is intentional (rendering simpler for Opus #3), proceed. Otherwise, skip the column and document the deviation.
- **users.preferred_mode NULL backfill timing** — §4.7 says NULL → 'default' flip in 3.2; alternatively, add as NOT NULL with `server_default='default'` directly in 3.1 (Postgres + SQLite both support). If you go the direct-NOT-NULL route in 3.1, flag in §13 — 3.2 skips the backfill + flip step.
- **`peer_recommendations` schema deviation invitations** — V1.5 pilot; Cursor may identify shape improvements during authoring. Flag any deviations in §13.

### Phase 3.2

- **`entity_categories` orphan handling on family/community delete.** Brief §5.1 says "NULL the entity_categories.category_id for those rows (or DELETE the entity_categories rows entirely — Cursor's call per data semantics; flag in §13)". Either is acceptable. NULL preserves the entity row's category-list (just shorter); DELETE removes the entity-category-pair record. Cursor's call; document.
- **Bucket A SQL pattern.** Brief shows `UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug='...') WHERE category = '...'` — this works on Postgres + SQLite. Cursor may prefer a JOIN-style UPDATE on Postgres but the subquery shape is portable. Document if you deviate.
- **District seed paragraph rendering.** Brief assumes the paragraphs from the draft are inserted verbatim (post-polish). If during dispatch Cursor finds operator's polished draft has paragraphs with embedded markdown, HTML, or special characters that need escaping for the SQL INSERT, flag in §13. Standard SQL-injection-safe parameter binding (via Alembic's `op.bulk_insert` for `Table` objects, not raw INSERT string concat) is the right shape.
- **Bucket B partial backfill semantics for `fitness_sports`.** Brief §5.2 says "force `fitness_sports` to `health-wellness-care` in Pass 2; Phase 5 re-triages the recreational subset." Cursor may want a different shape (e.g., NULL queue for the whole `fitness_sports` bucket if the operator queue posture is preferred). Flag if deviating.
- **CATEGORY_LABELS Tier ordering** — verify the Tier 1/2/3 list in synthesis §1 against the suggested ordering in §5.1. If synthesis lists differ, synthesis wins.
- **`scripts/ingest/validate_enrichment_csv.py` allowlist shape** — if the file uses a different data structure (e.g., a dict not a list, or imports from a constants module), follow the existing shape; flag any deviation from the brief's "set literal" assumption.

---

## §10 Risk register (12 rows + monitoring)

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | `entity_categories` orphan FKs to `family` / `community` cause migration crash | M | H | Pre-flight COUNT(*) check before DELETE; NULL or DELETE orphans per §5.1 step 2 |
| 2 | Backfill SQL works on SQLite but fails on Postgres (or vice versa) | M | H | All raw SQL uses portable shape (subquery UPDATE, CHECK constraints not ENUM); test against both dialects in CI |
| 3 | Operator polished draft has special chars breaking SQL inserts | L | M | Use `op.bulk_insert` with proper parameter binding, not raw string concat |
| 4 | `Entity.seasonal_hours` JSON column conflicts with Phase 1A's seasonal_hours extension table | M | M | Halt + flag in §13 BEFORE authoring column; operator clarifies |
| 5 | `users.preferred_mode` NOT NULL flip fails on production DB with NULL rows | L | H | Backfill NULL→'default' in same migration before flip; Phase 1D precedent |
| 6 | Bucket A backfill picks wrong row (e.g., legacy 'auto' string matches 'auto-rv-fuel' partially) | L | M | Exact match in UPDATE WHERE clause (no LIKE); test fixtures verify exact-match semantics |
| 7 | `entities.district` String column drop fails on Postgres due to FK reference somewhere we missed | L | M | Test downgrade + upgrade cycle on fresh SQLite + Postgres staging before deploy |
| 8 | District paragraph render breaks on profile page (Phase 6) due to HTML / special-char issue in seed | L | M | Seed validates content as plain text (no embedded HTML); Phase 6 renders via Jinja `|safe` only if explicitly trusted |
| 9 | Phase 3.2 backfill non-idempotent — re-run produces different state | M | H | `AND category_id IS NULL` guard on UPDATEs; idempotency tested in §5.9 test 19 |
| 10 | CATEGORY_LABELS update at `app/home/queries.py:27-55` accidentally breaks home-page rendering | L | H | Test home page render in Phase 3.2 test suite (smoke-test via `client.get('/home')` returns 200 + contains expected category names) |
| 11 | Bucket C operator decisions unlocked at dispatch time | M | H | Phase 3.2 HALTS at §0 step 8 if decision-locks aren't documented in operator commit message; operator must lock before dispatch |
| 12 | `peer_recommendations` table ships disabled-by-flag but feature-flag plumbing not added | L | L | Phase 3.1 ships table only; admin form + write-paths gated to V1.5 per Opus #7; no flag plumbing needed in Phase 3 |

---

## §11 What NOT to do (Phase 3 overall — design rails)

- DO NOT relitigate the locked decisions in §2.
- DO NOT propose a 13th category. The 12-slug count is locked per synthesis §1.
- DO NOT force any of the 5 professional-services strings into an imperfect home. NULL queue is locked.
- DO NOT add Phase 3 deliverables that aren't in master plan §4 Phase 3 + this brief. Scope discipline is critical — Phase 3 is already amended to absorb the category rewrite + backfill; further additions push it into Phase 4 territory.
- DO NOT touch chat-route response shape. Phase 3 is a schema-data pass.
- DO NOT add ENUM types (Postgres-only). VARCHAR + CHECK constraint per Phase 2A.1 precedent.
- DO NOT skip CHECK constraints "for SQLite parity." Both dialects support CHECK on column definitions.
- DO NOT use `sa.text("1")` / `sa.text("0")` for Boolean defaults. Phase 1A's `5132162` hotfix is the canonical lesson.
- DO NOT modify existing tables beyond the explicit columns/changes in §4 + §5. Touching extensions tables (locations, hours, contact_points, features, offerings, service_areas, schedules, source_evidence, sponsorship_slots) requires a separate brief.
- DO NOT change the existing `Provider.category` text column or `Programs.activity_category`. Backfill READS them; doesn't modify.
- DO NOT delete legacy data without operator approval. Bucket A backfill UPDATEs rows but doesn't DELETE; same pattern for Bucket B; only categories.family + categories.community are deleted (with pre-flight guard).
- DO NOT push without operator approval. Rules 2 + 12.

---

## §12 Final report format (for §13)

After Phase 3.1 OR 3.2 ships (HALT and report after EACH), produce a report with:

1. **Sub-phase identifier** (3.1 schema additions OR 3.2 data pass)
2. **§0 baseline as observed:**
   - `git log --oneline -10` top SHAs
   - `git status` clean state
   - `python -m alembic heads` single head + revision name
   - `python -m alembic current` (note any drift)
   - pytest collected count (entering)
3. **Files created** — table of `path | role`
4. **Files modified** — table of `path | change description`
5. **Migration:** Revision ID + chain-off ID. Postgres-only DDL flagged. CHECK constraints listed. Indexes listed.
6. **Tests added** — file path + brief test list per test file
7. **Final pytest count** (passed / skipped); diff vs entering baseline
8. **`alembic upgrade head` + `alembic downgrade -1 && alembic upgrade head` cycle** results (against fresh dev DB if you can boot one)
9. **Ruff** clean status
10. **Manual smoke** (if applicable; Phase 3.1 has none; 3.2 may smoke admin form free-text + home page render)
11. **Pragmatic deviations from §9** — flagged + rationale + impact assessment
12. **Surprises / operator notes** — anything unexpected; FK violations encountered; performance concerns; backfill counts (e.g., "44 of 47 providers backfilled to category_id; 3 NULL'd to operator queue: insurance / financial / real_estate")
13. **Git status** — confirm no `git add` / commit / push / amend was attempted (Rule 2 + 12)
14. **Next** — Phase 3.2 dispatchable if 3.1 shipped; Phase 4 dispatchable if 3.2 closes out Phase 3.

The §13 report is what the operator pastes back to the Cowork primary chat for review against the §4.11 + §5.10 acceptance gates.

---

*Authored by Cowork primary at session-19 mid-flight, 2026-05-12. Phase 3 closes out when 3.2 ships; Phase 4 (background-jobs + layered scrape infrastructure) becomes the next dispatchable lane. The 5 Bucket C operator decision-locks in §7 must close before Phase 3.2 dispatches; the district paragraphs draft must be operator-polished before Phase 3.2 dispatches.*
