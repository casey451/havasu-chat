# Plan — full category parity + completeness with golakehavasu & River Scene

**Date:** 2026-07-03
**Author:** Coverage audit follow-up (companion to `COVERAGE_GAP_golakehavasu_riverscene_2026-07-03.md`)
**Status:** Plan only — no code changes. Every implementation step ships as a feature branch → PR, and every prod data op is dry-run → show counts → Casey approves → apply.

## Decisions (Casey, 2026-07-03) — these are locked

1. **New leaves — YES.** Add `wildlife-and-nature` (Outdoors & Recreation) and `event-venues` (Things to Do & Attractions); **fold air-tours into `tours-and-sightseeing`** (no separate leaf). No primary/department restructuring.
2. **Scope — Lake Havasu ONLY.** *This reverses the audit's original "literally everything including regional day-trips" objective.* We do **not** ingest Laughlin, Bullhead City, Needles, Parker, Oatman, Hoover Dam, or Grand Canyon West listings/events. The `locality`/`region` field is now an **exclusion filter**, not an ingest-everything tag: out-of-area listings are recorded in the ledger as `excluded` with reason `outside-service-area`, never imported.
3. **Event history — don't show expired.** Backfill history for completeness/matching, mark past events `expired`, and keep them **out of every user-facing view** (calendar and search). History is retained in the DB for the ledger/matching only, not surfaced.
4. **Ambiguous CVB tags — name signal decides.** When a CVB tag is generic (`activities`, `boating`), the name-signal rule picks the leaf and the reconciliation ledger flags any that land wrong for human review.

---

## Objective (as revised by the decisions above)

1. **Categorize the same way golakehavasu and River Scene do** — their category is the authority, not our Google-type guess.
2. **Miss nothing *within Lake Havasu*** — every in-area golakehavasu listing and every River Scene / golakehavasu event is present in Ask Hava, or is *explicitly* excluded with a logged reason (out-of-area is a valid logged reason).
3. **Scope = Lake Havasu only.** Regional day-trips are enumerated by the reconciliation job but excluded-with-reason, not ingested.

## The core idea

Today, categorization is decided by **our** signals (Google Places `types`, then legacy fallback), and the source's own category is collapsed or discarded. We invert that:

> **A single authoritative crosswalk makes the *source's* category the primary signal for the leaf, and a reconciliation ledger proves — on every run — that every in-area source URL is either matched or excluded-with-reason.**

Two durable artifacts do the work:

- **The Source Category Crosswalk** (`app/contrib/source_category_map.py`, new): `(source, source_category, name_signal) → canonical leaf` for businesses and `(source, source_category) → canonical event_category` for events. This is the "categorize the same way they do" mechanism.
- **The Coverage Ledger** (`source_listing` table + reconciliation job, new): one row per external listing/event ever seen, with match status (including `excluded` for out-of-area). This is the "miss nothing" mechanism — completeness becomes a measured, alerting invariant.

---

## Part A — Categorization parity

### A0. Taxonomy changes (locked by decision #1)

- **Keep the 15-department / ~150-leaf display taxonomy.** No new Tier-1 primaries.
- **Add exactly two new business leaves:**
  - `wildlife-and-nature` (Outdoors & Recreation) — golakehavasu `birding` + wildlife refuges (Bill Williams NWR, Havasu NWR). Today dumped in `hiking-trails`/`landmarks`.
  - `event-venues` (Things to Do & Attractions) — golakehavasu `venues` (Stetson Winery Event Center, performing-arts halls used as venues).
- **Air tours fold into `tours-and-sightseeing`** (no leaf).
- **Add an event-category dimension** (~22 values, §C1) stamped at ingest. Events currently have no category column.
- **Add a `locality`/`region` field to providers and events.** Per decision #2 this is an **exclusion gate**: values like `havasu-core` are kept; anything resolving outside Lake Havasu (`parker`, `laughlin-bullhead`, `needles`, `oatman`, `other-daytrip`) is excluded at ingest and logged in the ledger.

Net taxonomy change: **+2 business leaves, +1 event-category dimension (~22 values), +1 locality field (used as an exclusion filter).**

### A1. The Source Category Crosswalk — businesses

New module `app/contrib/source_category_map.py`. Single source of truth, unit-tested, CI-guarded (A4). golakehavasu tag → Ask Hava leaf:

**On the Water**
| golakehavasu category | Ask Hava leaf | notes |
|---|---|---|
| `charters`, `boat rental with captain` | `boat-tours-and-charters` | captained/charter ⇒ charter leaf, **never** rentals |
| `water tours` | `boat-tours-and-charters` | guided water tour |
| `guided tour` (water name) | `boat-tours-and-charters` | else → `tours-and-sightseeing` (name decides) |
| `fishing`, `fishing guide` | `fishing-charters-and-guides` | |
| `water sports` | `jet-ski-and-watersports` | → `kayak-and-paddle` if name has kayak/paddle/canoe/SUP |
| `boating` | `marinas-and-launch-ramps` if name has "marina"; else `boat-and-watercraft-rentals` | name override can lift to charters |
| `launch ramps and marinas` | `marinas-and-launch-ramps` | |
| `beaches and swimming` | `beaches-and-swim-areas` | |
| `boat-in beaches and campsites` | `beaches-and-swim-areas` | cross-list `rv-parks-and-campgrounds` |

**Outdoors & Recreation**
| `parks` → `parks-and-playgrounds` · `dog parks` → `dog-parks` · `hiking`/`easy hikes`/`moderate hikes…`/`difficult hikes…`/`walks` → `hiking-trails` · `camping` → `rv-parks-and-campgrounds` · `ohv`/`offroad` → `off-road-and-ohv` · `birding` → **`wildlife-and-nature`** (new) · `golf` → `golf-courses` |

**Things to Do & Attractions**
| `attractions` → `landmarks-and-sights` · `family fun`/`family-fun` → `family-fun-and-arcades` · `entertainment` → `family-fun-and-arcades` · `activities` → `tours-and-sightseeing` (name-driven) · `venues` → **`event-venues`** (new) · `guided tour`(land)/`tours`/`outdoor land tours`/`air tours` → `tours-and-sightseeing` · `gaming and casinos` → `casinos-and-gaming` · `movie theaters` → `theaters-and-cinema` · `performing arts` → `theaters-and-cinema` |

**Eat & Drink / Lodging / Shopping / Transportation**
| `restaurant bar` → `restaurants` · `breweries and wine bar` → `bars-and-breweries` · `diner` → `restaurants` · `hotels motels suites` → `hotels-and-motels` · `resorts` → `hotels-and-motels` · `rv parks` → `rv-parks-and-campgrounds` · `vacation rentals / condos` → `vacation-rentals` · `shopping` → `gifts-and-boutiques` (default; name-driven) · `transportation` → `shuttles-and-transportation` |

**Location tags (exclusion filter, NOT categories):** `laughlin-bullhead-city`, `needles`, `parker` set **`locality`** → **excluded-with-reason `outside-service-area`** (decision #2). They are never imported.

### A2. Categorization precedence (the new decision order)

Replace "Google type → legacy" with, in priority:

1. **Explicit high-trust source category** (golakehavasu CVB tag, River Scene event-category) via the crosswalk. Authoritative — overrides Google.
2. **Name signal** (`app/contrib/name_leaf_signals.py`, new): `charter|captain|captained|cruise|sunset|excursion|guided tour` → `boat-tours-and-charters`; `fishing guide|guided fishing|fishing charter` → `fishing-charters-and-guides`; analogous rules for other ambiguous leaves. This is the tie-breaker for generic CVB tags per decision #4. Mirrors `_marine_subcat_from_name` (`app/categories/subcategories.py:648-662`).
3. **Google Places `types`** — fallback only.
4. **Legacy category** — last-ditch fallback.

Deterministic and logged (`category_provenance` column records which rule fired) so miscategorizations are debuggable and backfills auditable.

### A3. Loader changes to honor the crosswalk

- `app/contrib/golakehavasu_partners.py:75-121, 153-163` — replace the coarse `CVB_PRIMARY_CATEGORY_TO_SLUG` / `…_TO_LEGACY` collapse with a call into `source_category_map` returning a **leaf**, not `on-the-water`.
- `scripts/golakehavasu_partners_load.py:570-583` + `_fill_gaps` (`:168-181`) — **stop discarding the CVB category on reconcile.** When a partner carries a high-trust CVB category, re-file the provider's primary `entity_categories` link to the crosswalk leaf even when matching an existing Google-derived row.
- `app/contrib/leaf_type_mapping.py:80-85, 208-235` — feed the name signal in before the primary-Google-type-only mapping.
- `app/categories/water_misfiled_rules.py:62-67` — remove `charter`, `tour`, `guide` from `rental_markers` so a charter/tour/guide can leave the rentals leaf.
- **Locality gate** — the loader consults `locality` and drops out-of-area partners to the ledger as `excluded/outside-service-area` before import (decision #2).

### A4. Guardrail — no unmapped category ever again

- **CI test**: enumerate every distinct `source_category` seen from each source's sitemap/DOM; assert each has a crosswalk entry. A new golakehavasu tag or River Scene event-category we've never mapped **fails CI**.
- **Runtime alert**: the loader emits `unmapped_source_category` metrics; the reconciliation job lists them.

---

## Part B — Completeness ("miss nothing")

### B1. The Coverage Ledger

New table `source_listing` (and `source_event`): one row per external item, keyed `(source, source_url)`, columns: `source_category`, `name`, `address`, `region`, `first_seen`, `last_seen`, `match_status` (`matched|missing|miscategorized|excluded`), `matched_provider_id`/`matched_event_id`, `exclusion_reason`.

### B2. The reconciliation job

New `scripts/reconcile_sources.py` (scheduled via GitHub Actions). Each run:

1. **Enumerate** every URL from both sitemaps (golakehavasu `partnerDirectory` p1/p2 + `event-default`; River Scene `wp-sitemap-posts-events-*` + `events-river-cities`).
2. **Extract** `(name, address, source_category, region)` from each listing page (golakehavasu exposes `data-dms-category-name`; River Scene exposes event-category + JSON-LD date/time).
3. **Match** to `providers`/`events`: businesses via `google_place_id` → normalized name+address → fuzzy name within locality; events via `(normalized_title, date, venue)` (existing dedup key, `app/contrib/event_ingest.py`).
4. **Classify** each into `matched` / `missing` / `miscategorized` / `excluded`. **Out-of-area listings classify as `excluded/outside-service-area`** (decision #2) — they count as reconciled, not missing.
5. **Emit** a coverage report (Markdown + CSV to `docs/audits/`, plus metrics): counts per source/department, and the full `missing` + `miscategorized` lists.

**Completeness invariant:** success = `missing == 0 AND miscategorized == 0 AND every excluded row has a reason`.

### B3. Closing the gaps the ledger finds

- `missing` businesses → fix matching, or import as a new provider (in-area only).
- `miscategorized` → run A2 precedence + backfill (dry-run → counts → approve → apply).
- **Exclusions must be explicit.** Extend `app/contrib/ingest_suppression.py` so every excluded listing carries a reason (`outside-service-area`, `program-not-a-business`, `duplicate-of-X`, …).

---

## Part C — Events: parity + in-area ingest

### C1. Category parity — adopt River Scene's scheme

Canonical ~22-value event-category set, crosswalking River Scene's 90 + golakehavasu's event tags. Stamp `event.category` at ingest (in addition to existing tags):

- **boating-and-lake** ← boating, on-the-lake, on-the-river, boat-tours, boat-show, yacht-club
- **racing-and-motorsports** ← racing, off-road, car-show, rodeo
- **air-show** ← air-show
- **music** ← music, bands, new-years-eve-bands
- **festival** ← festival, london-bridge-days, fair, community-fair, spring-break
- **arts-and-theater** ← theater, art, art-fair, arts-and-crafts, creative-comrades, fashion-show
- **comedy** ← comedy-show
- **film** ← movies
- **food-and-drink** ← dinner, food, adult-beverages, bars, potluck
- **farmers-market** ← farmers-market, farmers
- **family-and-kids** ← family-party, youth, cub-scouts, bunco-bingo, adult-game-night
- **sports-and-fitness** ← sports-event, fitness, gyms, dance, special-olympics, dodgeball
- **education-and-lecture** ← lecture, educational, workshops, book-signing, library, school, summer-camp, summer-school, telesis-school, high-school, web-design-digital-marketing
- **health-and-wellness** ← health, health-fair, wellness, awareness
- **community-and-civic** ← chamber-of-commerce, networking, open-to-public, community, fire-department, first-friday
- **fundraiser-and-charity** ← fundraiser
- **holiday** ← holiday, christmas, new-years-eve, halloween, easter, fireworks
- **faith** ← church, ceremony
- **military-and-veterans** ← military, veterans-military
- **museum** ← museum-of-history, gem-show
- **outdoors-and-camping** ← outdoors, camping
- **pets** ← pets · **pageant** ← pageant · **shopping** ← shopping · **senior** ← assisted-living
- **misc/uncategorized** ← events, select-category, uncategorized (flag for review)

The A4 CI guardrail applies here too.

### C2. Ingest, retain, but don't show expired (decision #3)

- **Ingest**: relax the ingest-time "past" drop in `app/contrib/river_scene_pull.py:179,186` (and golakehavasu equivalent) for a **one-time full-history backfill**, and normalize dates to **America/Phoenix** so UTC skew stops dropping same-day/edge events.
- **Store** all events regardless of date; `status` distinguishes past/expired from live. `scripts/expire_past_events.py` marks past events `expired` (retained for matching, not deleted).
- **Display**: past/expired events are **not shown anywhere** — live calendar (`status == "live" AND coalesce(end_date,date) >= today` — `app/chat/tier2_db_query.py:772-774`, `app/events/queries.py:107-117`) and search stay upcoming-only. **No user-facing archive view** (per decision #3). History exists solely for the ledger and dedup.

### C3. Fix the three event-loss bugs

1. **Start-time gate** — `app/contrib/approval_service.py:331`: allow all-day / `event_time_start IS NULL` events from trusted sources (`river_scene`, `go_lake_havasu`, `chamber`) to auto-approve as all-day.
2. **266 recurring-without-RRULE rows** — `app/events/recurrence.py:148-158`: synthesize `rrule`/`rdate` from source cadence or clear the stray `is_recurring` flag; add an ingest validator rejecting `is_recurring=True` with no recurrence data.
3. **Crons actually run in prod** — verify every `*-events.yml` is merged to `main`, enabled, and `secrets.DATABASE_URL` is set; surface per-source "last successful ingest." (No Railway worker — GitHub Actions is the only scraper runtime.)

### C4. Work the pending queue

Aggregator/eventbrite/bandsintown/reddit + the 3 vision/flyer sources land pending by design. A standing `/admin` review cadence (or scheduled pending-count digest) keeps them from being invisible. Out of scope for two-site parity but the other half of "miss nothing."

---

## Part D — Generalize + prevent regressions

- **One crosswalk for all sources.** After golakehavasu + River Scene, route `downtown_lhc` and `chamber` loaders through the same `source_category_map`; Google-type-only assignment becomes the fallback, never the default.
- **Provenance everywhere.** `category_provenance` on providers, `category` + source on events.
- **The ledger is the contract.** Green reconciliation job ⇒ "everything in-area on both sites is on Ask Hava, categorized their way" is measured, not asserted.

---

## Rollout (phased; each phase = branch → PR → review; data ops dry-run first)

- **Phase 0 — Measure (read-only, no risk).** Reconciliation job + `source_listing` ledger in report-only mode. Output: today's exact counts of missing + miscategorized + excluded(out-of-area) per source/department. Becomes the regression baseline. *No writes.*
- **Phase 1 — Business parity.** `source_category_map` + name signals + precedence + golakehavasu loader changes + 2 new leaves + `locality` exclusion gate. Backfill mis-bucketed rows: **dry-run → counts → Casey approves → apply.** Success = golakehavasu `miscategorized` → 0.
- **Phase 2 — Business completeness.** Resolve every in-area `missing` golakehavasu listing (matching fixes, imports, or explicit exclusions). Success = in-area `missing` → 0.
- **Phase 3 — Events parity + backfill.** Event-category taxonomy + crosswalk; full-history backfill (dry-run → counts → approve); AZ-time normalization; fix start-time gate + 266 recurring rows; verify crons; keep expired hidden. Success = River Scene + golakehavasu events `missing`/`miscategorized` → 0.
- **Phase 4 — Guardrails + generalize.** CI unmapped-category test; scheduled reconciliation with alerting; route downtown_lhc + chamber through the crosswalk.

## Acceptance criteria (definition of done)

1. Reconciliation job runs on schedule and reports **0 unexplained `missing`** and **0 `miscategorized`** for in-area golakehavasu businesses, golakehavasu events, and River Scene events. Out-of-area rows are all `excluded/outside-service-area`.
2. Every in-area golakehavasu on-the-water operator lands in the leaf golakehavasu assigns — validated against `on_the_water_reconcile_golakehavasu_2026-07-03.csv`.
3. Every event carries a canonical `event.category` mapped from the source category; no source category unmapped (CI-enforced).
4. All-day events from trusted sources appear on the calendar; the 266 recurring rows render correctly; no same-day events dropped to UTC skew; **no expired events shown**.
5. Every excluded listing has a logged reason; "everything in-area is present" is provable from the ledger.

## New files / touch-list

**New:** `app/contrib/source_category_map.py`, `app/contrib/name_leaf_signals.py`, `scripts/reconcile_sources.py`, `source_listing`/`source_event` tables (+ alembic), `.github/workflows/reconcile-sources.yml`, 2 leaf seeds (`wildlife-and-nature`, `event-venues`), event-category column (+ alembic), `locality`/`region` column (+ alembic), `category_provenance` column.
**Edit:** `golakehavasu_partners.py`, `golakehavasu_partners_load.py`, `leaf_type_mapping.py`, `water_misfiled_rules.py`, `subcategories.py` (name rule), `approval_service.py`, `recurrence.py`, `river_scene_pull.py`, `ingest_suppression.py`, `event_ingest.py`.
