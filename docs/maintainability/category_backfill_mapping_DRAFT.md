# Provider.category → category_id Backfill — Mapping Investigation (DRAFT)

**Status:** investigation only; no code changes; no migration authored.
**Source ticket:** `docs/BACKLOG.md` → "Provider.category (string) → category_id (FK) backfill (no ticket; OPEN, P2)" (lines 2478–2502).
**Author:** Cowork sub-agent (read-only investigation, 2026-05-13).
**Audience:** Cowork primary + Casey, for mapping-review pass before the backfill migration ships.

Scope: this DRAFT enumerates the distinct legacy `Provider.category` string values surfaced in the repo source code and proposes a mapping to the 12 canonical Category slugs locked 2026-05-13:

`eat-and-drink`, `events`, `family`, `home-services`, `health`, `on-the-water`, `outdoors-and-parks`, `shopping`, `auto-and-gas`, `lodging`, `pets`, `community`

`Program.activity_category` strings are explicitly **out of scope** — programs are activities (arts, sports, recreation) and require a separate mapping pass per BACKLOG open question (d).

---

## §1 Observed legacy category strings

Strings come from three populations:

1. **Production catalog vocab** — the 24 keys in `CATEGORY_LABELS` at `app/home/queries.py:27-55`. This is the validator-enforced vocabulary for the operator-typed enrichment CSV ingest path (`scripts/ingest/validate_enrichment_csv.py:88-96` imports `CATEGORY_LABELS` and gates `category` against `set(CATEGORY_LABELS.keys())`).
2. **Places-pull domain vocab** — the 14 `domain` values in `scripts/places_categories.json` plus the fallback `"uncategorized"` that gets written when `_first_seen_domain` is missing (`scripts/places_load.py:79`). These flow into `Provider.category` for every Google-Places-sourced row.
3. **Test-fixture strings** — values like `"misc"`, `"recreation"`, `"other"`, `"food"`, `"services"`, `"barbershop"`, `"plumbing"`, `"veterinary"`, `"education"`, `"music"`, `"fitness"`, etc. used in pytest fixtures. These will not appear in production data unless they were copy-pasted into a manual SQL insert; flagged below in §3.

Table of every distinct `Provider.category` string value observed across source code:

| Legacy string | Source file:line | Population | Notes |
|---|---|---|---|
| `health_medical` | `app/home/queries.py:28`; `scripts/places_categories.json:106-122` | catalog + places | Validator vocab; Places domain. Display label "Health & medical". |
| `food_drink` | `app/home/queries.py:29`; `scripts/places_categories.json:5-40` | catalog + places | Validator vocab; Places domain. Display label "Food & drink". |
| `home_services` | `app/home/queries.py:30`; `scripts/places_categories.json:160-176` | catalog + places | Validator vocab; Places domain. Display label "Home services". |
| `retail` | `app/home/queries.py:31`; `scripts/places_categories.json:67-89` | catalog + places | Validator vocab; Places domain. Display label "Shops". |
| `lake_recreation` | `app/home/queries.py:32`; `scripts/places_categories.json:42-65` | catalog + places | Validator vocab; Places domain. Display label "On the water". |
| `professional_services` | `app/home/queries.py:33`; `scripts/places_categories.json:147-158` | catalog + places | Validator vocab; Places domain. Display label "Professional". |
| `beauty_personal_care` | `app/home/queries.py:34`; `scripts/places_categories.json:124-133` | catalog + places | Validator vocab; Places domain. Display label "Beauty & care". |
| `auto` | `app/home/queries.py:35`; `scripts/places_categories.json:91-104` | catalog + places | Validator vocab; Places domain. Display label "Auto". |
| `religion_community` | `app/home/queries.py:36`; `scripts/places_categories.json:206-209` | catalog + places | Validator vocab; Places domain. Display label "Community". |
| `fitness_sports` | `app/home/queries.py:37`; `scripts/places_categories.json:135-145` | catalog + places | Validator vocab; Places domain. Display label "Fitness & sport". |
| `general_contractor` | `app/home/queries.py:43` | catalog | Validator vocab. Display label "Contractors". Widened-set entry. |
| `real_estate` | `app/home/queries.py:44` | catalog | Validator vocab. Display label "Real estate". Widened-set entry. |
| `insurance` | `app/home/queries.py:45` | catalog | Validator vocab. Display label "Insurance". Widened-set entry. |
| `financial` | `app/home/queries.py:46` | catalog | Validator vocab. Display label "Financial". Widened-set entry. |
| `legal` | `app/home/queries.py:47` | catalog | Validator vocab. Display label "Legal". Widened-set entry. |
| `event_venue` | `app/home/queries.py:48` | catalog | Validator vocab. Display label "Venues". Widened-set entry. |
| `lodging` | `app/home/queries.py:49`; `scripts/places_categories.json:178-182` | catalog + places | Validator vocab; Places domain. Display label "Lodging". |
| `tourism` | `app/home/queries.py:50` | catalog | Validator vocab. Display label "Tourism". Widened-set entry. |
| `education` | `app/home/queries.py:51` | catalog | Validator vocab. Display label "Education". Widened-set entry. Note: Places-pull uses `childcare_education`, not `education`. |
| `pet` | `app/home/queries.py:52` | catalog | Validator vocab. Display label "Pets". Singular — note Places uses `pets` (plural). |
| `boat_repair` | `app/home/queries.py:53` | catalog | Validator vocab. Display label "Boat repair". |
| `boat_rental` | `app/home/queries.py:54` | catalog | Validator vocab. Display label "Boat rental". |
| `entertainment_attractions` | `scripts/places_categories.json:184-193` | places | Places domain only — NOT in validator's allowed set. Includes parks, museums, art galleries, golf, theaters, bowling, live music venues. |
| `pets` | `scripts/places_categories.json:195-198` | places | Places domain (plural). NOT in validator's allowed set (validator uses singular `pet`). Mismatch flagged below. |
| `childcare_education` | `scripts/places_categories.json:200-204` | places | Places domain only. NOT in validator's allowed set (validator uses `education`). Mismatch flagged below. |
| `uncategorized` | `scripts/places_load.py:79` | places fallback | `domain = row.get("_first_seen_domain") or "uncategorized"`. Written when Places discovery row lacks `_first_seen_domain`. Expected to be rare. |
| `services` | `tests/test_confidence_tier_integration_tier3.py:90`; `tests/test_llm_cache_raw_storage.py:67`; `tests/test_tier3_phone_enforcement.py:92`; `tests/test_tz_aware_datetime.py:29` | test fixtures | Not a production-vocab string. May appear in production only if hand-typed into admin form. |
| `recreation` | `tests/test_context_builder.py:59,93,124`; `tests/test_llm_router_integration.py:131`; `tests/test_phase38_gap_and_hours.py:50`; `tests/test_tier2_db_query.py:141`; `tests/test_tier2_routing.py:96`; `tests/test_unified_router.py:199`; `.split_backup/tests/test_unified_router.py:197` | test fixtures | Not a production-vocab string. |
| `food` | `tests/test_context_builder.py:67` | test fixtures | Not a production-vocab string. |
| `misc` | `tests/test_confabulation_query_gen.py:27`; `tests/test_session_memory.py:68`; `tests/test_tier2_db_query.py:821`; `tests/test_tier3_handler.py:72,96,113,133,232`; `tests/test_tier3_local_voice_injection.py:55,94`; `tests/test_tier3_user_text_context.py:55,90` | test fixtures | Not a production-vocab string. |
| `other` | `tests/test_contribution_model.py:46`; `tests/test_contribution_store.py:105`; `tests/test_provider_slug_migration.py:45,67,76,99,109` | test fixtures | Not a production-vocab string. |
| `barbershop` | `tests/test_chat_route_integration.py:373` | test fixtures | Not a production-vocab string. |
| `plumbing` | `tests/test_chat_route_integration.py:510,631,711`; `tests/test_directory_schema.py:48` | test fixtures | Not a production-vocab string. |
| `fitness` | `tests/test_cleanup_non_river_scene.py:79` | test fixtures | Not a production-vocab string. |
| `music` | `tests/test_cleanup_non_river_scene.py:85` | test fixtures | Not a production-vocab string. |
| `svc` | `tests/test_context_builder.py:141,148,253` | test fixtures | Not a production-vocab string. |
| `edu` | `tests/test_context_builder.py:165` | test fixtures | Not a production-vocab string. |
| `fun` | `tests/test_context_builder.py:208` | test fixtures | Not a production-vocab string. |
| `veterinary` | `tests/test_directory_schema.py:76` | test fixtures | Not a production-vocab string. |
| `education` | `tests/test_tier3_organic_context_wiring.py:147,266` | test fixtures | Also a catalog string (see row above) — collision is benign because the catalog string and the test fixture agree on spelling. |
| `restaurant` | `tests/test_tier2_open_now.py:67,77,87` | test fixtures | Not a production-vocab string. |
| `bakery` | `tests/test_tier2_open_now.py:118,127` | test fixtures | Not a production-vocab string. |
| `bmx` / `bmxcaptest` / `onxcat` | `tests/test_tier2_db_query.py:144,275,361` | test fixtures | Synthetic test-only values. |
| `space_pirates` | `tests/test_enrichment_ingestion.py:100` | test fixtures | Synthetic test-only value used to assert validator rejection. |

Also: the admin Provider create form (`app/admin/router.py:1439`) uses a free-text `<input>` for `category` with placeholder `"e.g. recreation, fitness, dining"`, so operator-created Providers can carry *any* string. The validator gate only fires on the CSV-ingest path, not the admin form. This is the single biggest source of "unknown unknowns" in production data and reinforces the §5 caveat that a production `SELECT DISTINCT` is required before the migration locks.

**Distinct legacy strings found in source code: 41** (26 production-vocab + 15 test-fixture-only).

---

## §2 Proposed mapping

Mapping from observed legacy strings to canonical Category slugs. Confidence values: **High** (obvious mapping), **Medium** (defensible but operator should confirm), **Low** (genuinely ambiguous — operator MUST decide).

### Production-vocab strings (catalog + places)

| Legacy string | → Canonical slug | Confidence | Rationale |
|---|---|---|---|
| `health_medical` | `health` | High | Direct rename. Display label was "Health & medical"; canonical scope is identical. |
| `food_drink` | `eat-and-drink` | High | Direct rename. Display label was "Food & drink"; canonical wording change only. |
| `home_services` | `home-services` | High | Direct rename (underscore → hyphen). Identical scope. |
| `retail` | `shopping` | High | Direct rename. Display label was "Shops"; canonical name is "Shopping". |
| `lake_recreation` | `on-the-water` | High | Direct rename. Display label was "On the water"; canonical wording matches. |
| `beauty_personal_care` | *(see §3)* | Medium | No direct canonical equivalent. Closest is `health` (wellness/spa framing) or `community` (no clean fit). Defer to operator. |
| `auto` | `auto-and-gas` | High | Direct rename. Includes auto repair, dealers, gas stations, towing — matches the Places `auto` domain scope which covers gas stations (line 102). |
| `religion_community` | `community` | High | Direct rename. Display label was "Community"; canonical is identical. |
| `fitness_sports` | *(see §3)* | Medium | No direct canonical fit. Closest is `health` (wellness scope) but Places `fitness_sports` includes pickleball/tennis/swimming which lean recreational. Defer to operator. |
| `general_contractor` | `home-services` | High | Contractor trade fits cleanly into home-services umbrella. |
| `real_estate` | *(see §3)* | Low | No clear canonical fit; not a business-category in the pivot taxonomy. Defer to operator. |
| `insurance` | `community` | Medium | Professional service; "community" is the catch-all for non-trade local businesses in V1. Operator should confirm. |
| `financial` | `community` | Medium | Same rationale as `insurance`. |
| `legal` | `community` | Medium | Same rationale as `insurance` / `financial`. |
| `event_venue` | `events` | High | Display label was "Venues"; events category is the natural home. |
| `lodging` | `lodging` | High | Identical name. |
| `tourism` | *(see §3)* | Low | Ambiguous — could be `lodging` (hotels/resorts) or `community` (visitor info, tours) or `events` (attractions). Defer to operator. |
| `education` | `family` | Medium | Pivot taxonomy uses `family` for kid-oriented categories (childcare, schools). Operator confirms whether adult education (driving school, music lessons) belongs here. |
| `pet` / `pets` | `pets` | High | Direct rename. Both singular and plural variants exist in observed data; both map to canonical `pets`. |
| `boat_repair` | `on-the-water` | High | Boat-specific trade fits cleanly under on-the-water scope. |
| `boat_rental` | `on-the-water` | High | Same rationale. |
| `entertainment_attractions` | *(see §3)* | Low | Multi-target: parks/museums → `outdoors-and-parks` for parks, but museums/galleries are not parks. Movie theaters/bowling/arcades fit `community`. Live music venues → `events`. Operator must split. |
| `childcare_education` | `family` | High | Daycare, preschool, tutoring, music lessons, driving schools — all family/kids-oriented. |
| `professional_services` | `community` | Medium | Catch-all in the legacy schema (lawyers, accountants, banks, photographers, real estate agents, insurance agents, mortgage brokers). Mostly `community` in V1; operator confirms. |
| `uncategorized` | `NULL` (operator queue) | High | Explicit fallback string; should remain unmapped and surface in the operator review queue. |

### Test-fixture-only strings

These do not appear in production source-of-truth code paths. The migration should treat them as production-uncertain — if any rows surface with these values (e.g. a stale dev DB snapshot got into production), they're operator-review candidates rather than auto-mappable.

| Legacy string | → Canonical slug | Confidence | Rationale |
|---|---|---|---|
| `services` | `home-services` | Low | Test-only; semantically too broad. Best guess only. |
| `recreation` | `outdoors-and-parks` | Low | Test-only; recreation could be on-the-water, outdoors-and-parks, or community center. |
| `food` | `eat-and-drink` | Medium | Test-only but obvious mapping. |
| `misc` | `NULL` (operator queue) | High | Test-only catch-all; no production meaning. |
| `other` | `NULL` (operator queue) | High | Same as `misc`. |
| `barbershop` | `community` | Medium | Test-only; barbershops sit under personal-care in legacy vocab (which has no clean V1 home — see §3). |
| `plumbing` | `home-services` | High | Test-only but unambiguous trade. |
| `fitness` | *(see §3)* | Medium | Same ambiguity as `fitness_sports`. |
| `music` | `events` | Low | Test-only; music could be a venue (events) or a lesson (family) or a store (shopping). |
| `svc` | `NULL` (operator queue) | High | Test-only abbreviation. |
| `edu` | `family` | Medium | Test-only abbreviation. |
| `fun` | `NULL` (operator queue) | High | Test-only; semantically too vague. |
| `veterinary` | `pets` | High | Test-only but unambiguous. |
| `restaurant` | `eat-and-drink` | High | Test-only but unambiguous. |
| `bakery` | `eat-and-drink` | High | Test-only but unambiguous. |
| `bmx` / `bmxcaptest` / `onxcat` | `NULL` (operator queue) | High | Synthetic test-only values; will not exist in production. |
| `space_pirates` | `NULL` (operator queue) | High | Synthetic test-only validator-rejection probe; will not exist in production. |

**Mapping totals (source-code strings only):**

- High confidence: 19
- Medium confidence: 11
- Low confidence: 5
- NULL (operator queue): 6
- Ambiguous (§3): 6 distinct strings (counted in §3)

Note: §2 confidence totals include the §3 entries (those rows show "see §3" in the slug column and are individually counted in §3 below).

---

## §3 Ambiguous strings (operator review queue)

Strings that map to multiple slugs, no slug, or no clean home. Each gets a brief recommendation + the question the operator needs to answer.

1. **`beauty_personal_care`** (observed at `app/home/queries.py:34`; includes hair salons, barbers, nail salons, spas, massage therapists, tanning, tattoo, eyebrow threading, waxing per `scripts/places_categories.json:124-133`) — no direct canonical fit in the 12-category taxonomy. Closest candidates: `health` (spa/massage wellness framing), `community` (catch-all for non-trade local businesses), or file a 13th category. **Recommendation:** map to `community` for V1; revisit if beauty becomes a sponsor category (likely candidate given LHC market). **Operator question:** approve `community` mapping, or file a 13th category (e.g. "beauty-and-wellness")?

2. **`fitness_sports`** (observed at `app/home/queries.py:37`; includes gyms, personal trainers, yoga/pilates/crossfit studios, martial arts, dance studios, swimming pools, tennis courts, pickleball per `scripts/places_categories.json:135-145`) — splits between `health` (wellness scope: gyms, yoga, pilates) and `outdoors-and-parks` (recreational scope: tennis courts, pickleball, swimming pools). **Recommendation:** map to `health` for V1 since the dominant entries are gym/studio businesses (operator-typed); the recreational facility entries can be triaged into `outdoors-and-parks` post-backfill if SELECT DISTINCT reveals them as a meaningful subset. **Operator question:** approve bulk-map to `health` with manual triage of the recreational subset, or split now via a regex pass?

3. **`real_estate`** (observed at `app/home/queries.py:44`) — no direct canonical fit. The pivot taxonomy doesn't carry a real-estate category; closest are `community` (generic local business) or `home-services` (loose adjacency — agents and home services serve the same homeowner). **Recommendation:** map to `community` for V1; revisit if real estate becomes a sponsor category. **Operator question:** approve `community` mapping or file a 13th category?

4. **`tourism`** (observed at `app/home/queries.py:50`) — ambiguous between `lodging` (hotels/resorts), `community` (visitor centers, tours), and `events` (attractions, festivals). Operator-typed values under this string are unknown — the validator allows it but we have no production sample. **Recommendation:** defer mapping; bulk-flag rows with `category='tourism'` for operator triage post-backfill (write `category_id = NULL` so they surface in the review queue). **Operator question:** is `tourism` worth keeping as a category at all, or should each row be reclassified individually?

5. **`entertainment_attractions`** (observed at `scripts/places_categories.json:184-193`; includes movie theaters, bowling alleys, arcades, mini golf, golf courses, parks, museums, art galleries, live music venues, event venues) — multi-target. Parks → `outdoors-and-parks`; movie theaters/bowling/arcades → `community`; live music venues / event venues → `events`; museums / art galleries — no clean home (probably `community`). **Recommendation:** treat as NULL (operator queue) for the bulk migration, then run a regex / sub-category pass against the underlying Places `_first_seen_category` field to split (one row's Provider.category may be `entertainment_attractions` but its `google_primary_category` will distinguish "movie_theater" from "park" from "art_gallery"). **Operator question:** approve a follow-up triage pass using `google_primary_category` for the entertainment_attractions cohort, or pick a single fallback slug for the whole bucket?

6. **`professional_services`** (observed at `app/home/queries.py:33`; includes lawyers, accountants, tax preparers, real estate agents, insurance agents, financial advisors, notary, banks, credit unions, title companies, mortgage brokers, photographers per `scripts/places_categories.json:147-158`) — listed in §2 as Medium → `community`, but worth flagging here because (a) it's a high-volume catch-all in the legacy vocab and (b) `photographers` arguably belongs in `family` (weddings, portraits) or `events`. **Recommendation:** bulk-map to `community` for V1; accept that `community` will be heterogeneous in the early data. **Operator question:** confirm `community` is the right catch-all bucket, or carve photographers / financial-services off?

---

## §4 Recommended next steps for the backfill migration

1. **Operator reviews this DRAFT** and edits the mapping table to lock canonical decisions on the §3 ambiguous strings.
2. **Cowork primary moves the locked mapping** into `docs/maintainability/category_backfill_mapping.md` (no DRAFT suffix).
3. **Backfill migration author (Cursor or CC) reads the locked mapping** + writes the alembic migration per the BACKLOG ticket's "Proposed approach" section (lines 2484–2490). The migration should read the mapping from the locked-file table (parse markdown or a sibling YAML) so the source of truth is reviewable in `git log`.
4. **Production SELECT DISTINCT.** `SELECT DISTINCT category FROM providers ORDER BY 1;` (Railway SQL console per Rule 9 of `dispatch_protocol.md`) will likely surface additional strings not in seed/scripts — the admin Provider create form at `app/admin/router.py:1439` is a free-text input (placeholder: `"e.g. recreation, fitness, dining"`), so any operator-typed value bypassing the CSV validator is possible. Operator runs that SELECT against production + dev and adds any net-new strings to the mapping before the migration ships.
5. **Verify ingest-path coverage.** The mapping should be applied at three Provider-construction sites (per BACKLOG step 4):
   - `scripts/places_load.py:82` (Google Places ingest)
   - `scripts/ingest/ingest_enrichment_csv.py:201` (operator CSV ingest)
   - `app/admin/router.py:1553` (admin direct-create)
   - `app/contrib/approval_service.py:79` (contribution-approval ingest)
6. **Validator vocab update.** Once the backfill ships and the legacy string column is being deprecated, the validator at `scripts/ingest/validate_enrichment_csv.py:88-96` should be retargeted to gate on `Category.slug` rather than `CATEGORY_LABELS.keys()`.

---

## §5 Caveats

- This investigation enumerates strings observed in **SOURCE CODE only**. Production data may contain strings from operator-typed enrichment rows or admin-form direct-creates that don't appear in seed/script code paths. **Run `SELECT DISTINCT category FROM providers ORDER BY 1;` against Railway production before locking the mapping for the actual migration.** The admin form at `app/admin/router.py:1439` is free-text and ungated.
- The Places-pull `domain` vocab and the `CATEGORY_LABELS` validator vocab partially overlap but are NOT identical:
  - Places-pull uses `pets` (plural); validator uses `pet` (singular). Both may exist in production.
  - Places-pull uses `childcare_education`; validator uses `education`. Both may exist in production.
  - Places-pull has `entertainment_attractions` which is NOT in the validator's allowed set, so operator-typed enrichment CSV will be rejected for that string while Places-pull writes it freely.
- The same investigation should run for `Program.activity_category` separately (programs map differently — they're activities, not business types, and the parks-rec loader at `app/contrib/parks_rec_loader.py:95-104` defines its own `CONTENT_CATEGORY_KEYWORDS` vocab: `aquatics`, `arts`, `food`, `sports`, `fitness`, plus the fallback `recreation`). Out of scope for this DRAFT; file as a follow-up.
- `Contribution.submission_category_hint` (referenced at `app/admin/categories_html.py:81`) is a third free-text category surface for pending contributions. Out of scope for this Provider-only DRAFT but worth noting that the slug→category_id work will eventually need to touch it too.
- Test-fixture strings (§1 last block, §2 second table) will not appear in production data **unless** a dev DB snapshot or test data was somehow imported into production. The §3 NULL-recommendation for these (`misc`, `other`, `svc`, `fun`, `bmx*`, `space_pirates`) is defensive — if any do surface, they should route to the operator review queue rather than being auto-mapped from this DRAFT's guesses.
