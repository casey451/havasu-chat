# Architecture Gaps for Full Lake Havasu Vision — Audit

**Status:** investigation only; no code changes.
**Audience:** Cowork primary + Casey.
**Author:** Cowork sub-agent (read-only audit, 2026-05-14).

---

## §1 Executive summary

This audit walks the working tree against the operator's evolved vision — "a comprehensive Lake Havasu directory covering every useful category for every demographic, plus an AI chat that gives information and makes recommendations, built so the foundation supports thousands of concurrent users at launch" — and identifies the architectural distance from the current 2026-05-13 state to that endpoint.

**Gap count:** 22 distinct gaps. Of these: **6 are must-ship-before-data-gathering** critical-path foundations (Place model, scheduled scraper infra, search index, category-backfill, sub-trade taxonomy decision, chat-to-directory data-source migration); **9 are must-ship-before-launch** (User accounts + Resend auth, image storage, map integration, admin tooling hardening, favorites/lists, Provider/Event/Program cross-entity unification, background-job infrastructure, cache coverage on directory surfaces, scale-tuned rate limits); **5 are V2-territory deferrable** (reviews/ratings, personalization beyond favorites, deals/QR wallet, lead-gen attribution, syndication API); and **5 are dormant-code cleanup items** to flag now but defer to launch prep per operator instruction.

Of the 22 gaps, **16 are monetization-agnostic foundation work** (schema, scrapers, search, accounts, images, map, admin, scale, cache, jobs, etc.) and only **6 are tied to specific monetization choices** (sponsor slot UI, claim/upgrade flows, sponsor reporting, deals engine, lead-gen attribution, premium-tier paywall surfaces). This is intentional: per operator's "build-first, sell-after" sequence, the bulk of the build should be category-and-product agnostic so a later monetization decision plugs into a stable foundation.

**Highest-leverage findings:**

1. **The Place model is the single biggest schema gap.** Pivot §8.2 deferred it; the full vision requires it. Parks, ramps, beaches, dog parks, ball fields, RC tracks, scenic spots — none can be modeled as `Provider` rows without semantic damage to category pages, sponsor logic, and chat recommendations.
2. **Chat is still wired to the pre-pivot River Scene events catalog.** `app/chat/tier2_db_query.py:33` imports `Event, Program, Provider`; chat does not yet understand `Category` (added 2026-05-13 at `app/db/models.py:580` but unread by application code). The chat half of "three front doors" will start returning increasingly irrelevant answers as directory data grows unless the Tier 2 path is rewritten to query the new shape.
3. **No background-job infrastructure exists.** `app/main.py:246` runs a single in-process `_hourly_cleanup_loop`; everything else is operator-triggered (`python scripts/places_discovery.py`). Scheduled scrapers across 12 categories, re-verification cycles, magic-link email, cache warming, and image processing all need a real job runner — picking the right one (Railway scheduled jobs vs RQ/Redis vs in-app APScheduler) is a foundational call.
4. **No first-class search index.** Tier 2 is "structured filters → SQLAlchemy `LIKE` query." That works for ~100 entities. At ~thousand-entity scale across 12 categories with mixed business and place types, this becomes the bottleneck for both chat ("plumber with weekend hours under $200") and category-page filtering (faceted search). Postgres FTS + `pg_trgm` is the cheapest path; Meilisearch the most-polished; Algolia the most-expensive but most-managed.
5. **Admin tooling is a manual-correctness liability that compounds with scale.** `app/admin/router.py:1439` is a free-text `<input>` for `category` with no validation against the 12 canonical slugs. The directory pivot landed the schema and the legacy column still ships side-by-side with no backfill, no validator update on the admin path, no bulk-import tooling, no automated re-verification cycle. Every operator-created Provider is a future data-quality bug.

The remaining sections enumerate each gap with `path:line` citations, sequencing implications, and recommended approaches.

---

## §2 Gap classification table

Sorted by critical-path urgency, then estimated impact.

| # | Gap | Category | Build phase | Monetization | Effort | Blocks |
|---|---|---|---|---|---|---|
| 1 | `Place` model + ingest | schema | data-gathering | agnostic | L | Outdoors-and-parks / On-the-water / Family / Pets category pages |
| 2 | `Category` backfill + admin-form validator | schema/admin | data-gathering | agnostic | M | Reliable category queries from chat + page filters |
| 3 | Sub-trade / facet taxonomy (in `Provider.attributes`) | schema/taxonomy | data-gathering | agnostic | M | Home Services + Eat & Drink filter surfaces |
| 4 | Scheduled scraper infrastructure | infra | data-gathering | agnostic | L | Refreshing all 12 categories at scale; re-verification cadence |
| 5 | Search index (Postgres FTS or external) | infra | data-gathering | agnostic | L | Chat-to-directory queries; category page filtering at scale |
| 6 | Chat → directory data-source migration | core | data-gathering | agnostic | L | Chat front door under the new product shape |
| 7 | Background-job infrastructure (job queue) | infra | launch | agnostic | L | Email sending, scheduled scraping, cache warming, re-verification |
| 8 | User account system (Resend magic-link) | auth | launch | agnostic | L | Claim flow, favorites, alerts, identity for any user-side feature |
| 9 | Image storage (S3 / Railway volume / CDN) | infra | launch | agnostic | M | Owner-uploaded photos; Hero image governance; image-density at scale |
| 10 | Map integration (Leaflet + OSM, §8.4 LOCKED) | UI | launch | agnostic | M | List/map toggle on every category page; place discovery UX |
| 11 | Admin tooling hardening | admin | launch | agnostic | M | Operator data-quality at scale; bulk imports; re-verification UI |
| 12 | Provider/Event/Program cross-entity unification | core | launch | agnostic | M | "What's happening at X this weekend" chat queries |
| 13 | Cache coverage on directory surfaces | infra | launch | agnostic | M | 1000-concurrent-user p99 on category and profile pages |
| 14 | Scale-tuned inbound rate-limits + pool sizing | infra | launch | agnostic | S | 1000-concurrent-user survival; Railway autoscaling readiness |
| 15 | Favorites / saved lists | feature | launch | agnostic | M | "Recommendation" personalization; retention loop |
| 16 | HALT 3 close-out (chat confabulation guardrails) | core | launch | agnostic | M | Flipping `FEATURE_FLAG_DISCLOSURE_RENDERER`; trusted chat recs |
| 17 | Sponsor claim/edit + analytics dashboard | feature | launch | specific | L | Verified Presence sales (Day 30+) |
| 18 | Labeled sponsor slot in category pages + reporting | feature | launch | specific | M | Category Visibility sales (Day 60+) |
| 19 | Native reviews / ratings | feature | V2 | agnostic | L | AI recommendations grounded in first-party signal |
| 20 | Personalization beyond favorites (demographic-aware) | feature | V2 | agnostic | L | "AI recommendations for me" — the headline vision phrase |
| 21 | Deals engine + lead-gen attribution | feature | V2 | specific | XL | Phase 2 sponsor packages (Deals $249, Intent $499) |
| 22 | Syndication API + itinerary builder | feature | V2 | specific | XL | Phase 3 monetization streams |

---

## §3 Per-gap detail

### §3.1 — `Place` model + ingest path (Gap 1)

**What's missing.** Pivot §8.2 LOCKED to "defer Place to Phase 2"; `app/db/models.py:100` carries the comment "first-class Place row per pivot §8.2 (Place model deferred to Phase 2)." The current schema represents non-business locations as `Provider` rows with a `district` String(64) column (`models.py:101`). This works for English Village / Downtown labels on Eat & Drink Providers. It does not work for **parks, ramps, beaches, dog parks, ball fields, skating rinks, RC tracks, scenic spots, fishing holes** — these don't have `phone`, `email`, `website` in the business sense, don't have `tier`/`sponsored_until`, don't need `verification_method`, and conflict with the sponsor-eligibility logic in `app/chat/disclosure_render.py:250-276` (which assumes a commercial Sponsor row for any "place" the chat could surface).

**Why it matters for the full vision.** Multiple demographics in the operator's stated vision (families, dog lovers, outdoor lovers, water enthusiasts) need non-business places as first-class destinations. The chat query "what dog-friendly spots are near me" is unanswerable without a Place entity. Category pages for "Outdoors & Parks" and "On the Water" are essentially Place-pages; trying to render them from `Provider` rows means either (a) abuse of the `Provider` table with most fields NULL, or (b) restricting those pages to commercial venues only (rentals, marinas, gear shops), which is exactly the wrong tradeoff for the demographic the page is supposed to serve.

**Recommended approach.** New `Place(Base)` model with: `id`, `slug`, `name`, `place_type` (enum: park / ramp / beach / dog_park / ball_field / skating_rink / rc_track / scenic_spot / fishing_hole / trailhead / ...), `category_id` FK, `lat`, `lng`, `address`, `description`, `attributes` JSON for facet data (lighted, dog-friendly, paved-parking, restrooms, ramp-lanes, etc.), `photo_refs`, `hours_structured` (optional — many places are 24/7), `last_verified_at`, `verification_method`. Reuse the Provider machinery: `Sponsor.business_id` already widens to support non-Provider entities (`app/db/models.py:547` — "no DB-level FK"), so a place-aligned sponsor (e.g. a marina sponsoring a ramp page) plugs in without schema change. Reuse the slug pattern from `app/utils/slug.py`. Reuse the freshness band logic at `app/providers/queries.py:49`.

**Estimated effort.** L (1-2 weeks). Schema + Alembic migration + view-model + at least one ingest path (Google Places "park" type or a curated CSV seed). Real cost is the seed-data work, not the code.

**Sequencing.** Ships **before** the Outdoors-and-Parks / On-the-Water / Family / Pets category landing pages. Can ship **after** the Home Services category page (pivot §5 already sequences that first).

---

### §3.2 — `Category` backfill + admin-form validator (Gap 2)

**What's missing.** The schema landed 2026-05-13 (`Category` model at `app/db/models.py:580`; nullable `category_id` FK on Provider `:91` and Program `:314`). The legacy free-text `Provider.category` string (`:36`) and `Program.activity_category` string (`:276`) still ship side-by-side. There is no application code yet that reads `category_id` (per STATE.md "dormant until application code reads the new columns"). Critically, **the admin Provider create form at `app/admin/router.py:1439` is still a free-text `<input>`** with placeholder `"e.g. recreation, fitness, dining"` — no validation, no dropdown of the 12 canonical slugs, no rejection of out-of-vocab strings. The CSV ingest validator (`scripts/ingest/validate_enrichment_csv.py:88-96`) gates against `CATEGORY_LABELS` keys but that's the 24-key pre-pivot vocab, not the 12 canonical slugs. Backfill investigation is at `docs/maintainability/category_backfill_mapping_DRAFT.md` but the migration itself is not authored.

**Why it matters for the full vision.** Every category-page query, every cross-category chat answer, every per-category sponsor slot, every analytics breakdown depends on a reliable `category_id`. Mixing a free-text column with a structured FK means every join needs both branches forever and the chat tier-routing has to reconcile two representations of "what category is this." This is the single highest-leverage cleanup gap.

**Recommended approach.** Three coordinated lanes. (a) Backfill migration following the DRAFT (`docs/maintainability/category_backfill_mapping_DRAFT.md`) — High-confidence rows auto-mapped, Low/NULL rows surface in an operator queue. (b) Replace `app/admin/router.py:1439` free-text input with a `<select>` populated from `Category.slug` rows, plus a server-side validator. (c) Retarget `scripts/ingest/validate_enrichment_csv.py:88-96` to gate on `Category.slug`. After these three, the legacy string column is read-only deprecated; safe-deprecation pass comes later.

**Estimated effort.** M (1-3 days). Backfill migration is mostly authored; admin form is a 30-line change; validator retarget is 20 lines.

**Sequencing.** Ships **before** any category page beyond Home Services goes live. The Home Services V1 page can read the legacy `Provider.category == "home_services"` filter for now, but Eat & Drink should already be on `category_id`.

---

### §3.3 — Sub-trade / facet taxonomy structure (Gap 3)

**What's missing.** `Provider.attributes` is `JSON | None` (`app/db/models.py:97`) and currently holds free-form keys (`emergency_service`, `by_appointment_only`, `licensed`, `accepts_insurance`, `sub_trades`, `service_chips`, `service_area`, `hero_pin_photo_url`, `service_area_only` — surfaced at `app/providers/queries.py:131-177`). The values are operator-curated; nothing prevents key drift, value drift, or one operator typing `"plumber"` while another types `"Plumbing"`. There is no schema for what attributes are valid per category; no admin UI to set them; no facet vocabulary anywhere on tree.

**Why it matters for the full vision.** Category-page filters (sub-trade, service area, hours, "emergency 24/7" toggle) are the headline value prop of a directory over Google Maps. Without a structured facet taxonomy these end up either (a) brittle string-matches that break the moment an operator misspells `"emergancy"`, or (b) chat-only filtering that loses the browse front door.

**Recommended approach.** Two viable shapes: (i) **stay JSON but add validation** — author `app/providers/attribute_schemas.py` keyed by `Category.slug`, validate at the same three Provider-construction sites the backfill ticket touches; (ii) **first-class `CategoryAttribute(Base)` + `ProviderAttribute(Base)` tables** — heavier-weight but enables per-attribute indexing for fast facet counts at scale. Recommend (i) for V1 (cheap, fits the current 50-business scale), with (ii) on deck the moment any single facet count exceeds ~5k rows. The two are migration-compatible — JSON shape becomes the seed for the structured shape later.

**Estimated effort.** M (1-3 days) for option (i); L for option (ii) if/when it's needed.

**Sequencing.** Ships alongside Home Services category-page filters. Eat & Drink will surface different facets (cuisine type, district, price band, kid-friendly, dog-friendly patio) so per-category schemas are validated category-by-category as each page lands.

---

### §3.4 — Scheduled scraper infrastructure (Gap 4)

**What's missing.** Today's scraper invocation pattern is operator-triggered: `python -m scripts.places_discovery --dry-run`, `python -m scripts.places_enrichment --limit 10`. No scheduling, no idempotent re-runs, no dedup across runs beyond Place-ID matching (`scripts/places_discovery.py:1-80`), no monitoring beyond `_summary.json` outputs. The only in-process background job is `app/main.py:246` `_hourly_cleanup_loop` which marks expired pending review rows. Mention scanning is `BackgroundTasks` (`app/api/routes/chat.py:62`) but that's per-request and dies with the worker process.

**Why it matters for the full vision.** A directory that aspires to be "everything Lake Havasu" needs scheduled discovery across all 12 categories on some cadence (weekly per category? monthly?) plus per-row re-verification when `last_verified_at` ages past the freshness bands (`fresh`/`acceptable`/`aging`/`stale` defined at `app/providers/queries.py:44-46`). Currently every refresh requires Casey to remember to run a script.

**Recommended approach.** Three options ranked by infrastructure weight: (a) **Railway scheduled jobs** — cron-style trigger of `python -m scripts.places_discovery --category $CATEGORY`; cheapest; couples to Railway. (b) **APScheduler in-app** — Python scheduler running on the web process; uses the same `app.main` lifespan that hosts `_hourly_cleanup_loop`; cheap, but ties scrapers to web-server uptime and contends for CPU. (c) **RQ/Redis + worker dyno** — proper separation; costs Redis ($5-10/mo Railway add-on) but unlocks job queues for everything else (email, image processing, cache warming). Recommend (c) given background-job infrastructure (Gap 7) needs Redis-or-equivalent anyway — share the infra.

**Estimated effort.** L (1-2 weeks) including worker process setup, queue design, monitoring, retry logic.

**Sequencing.** Ships **before** systematic data-gathering kicks off across all 12 categories. Manual operator-triggered runs are fine through Home Services V1.

---

### §3.5 — Search index (Gap 5)

**What's missing.** Chat Tier 2 queries the catalog via SQLAlchemy filter chains (`app/chat/tier2_db_query.py`). Provider category match at `:491` is a string-comparison; there is no full-text index, no `pg_trgm` extension enabled, no faceted-search engine. Category landing pages (when they ship) will have the same shape. The matcher at `app/chat/entity_matcher.py` is an in-process Rapidfuzz scorer over an in-memory needle list refreshed on schema changes — efficient at hundreds of entities, untested at thousands.

**Why it matters for the full vision.** At 1000-concurrent-user scale plus thousands of Provider/Place rows plus the chat query "plumber with weekend hours under $200 emergency-service," a SQLAlchemy LIKE chain becomes the p99 bottleneck. The chat half of "three front doors" cannot answer recommendation queries without a real search index because LLM tier routing needs candidate retrieval that is faster and richer than a `LIKE %word%` chain.

**Recommended approach.** Two viable paths: (a) **Postgres FTS + `pg_trgm` + GIN indexes on `attributes` JSONB** — zero extra infra, scales to ~hundred-thousand rows comfortably, requires migration to switch JSON → JSONB (currently `JSON` per `app/db/models.py:97`); (b) **Meilisearch on a Railway sidecar** — better UX out of the box (typo tolerance, facets, instant search), $5-10/mo, adds an infra component. Recommend (a) for the Day 90 cut and re-evaluate at Day 180 when the catalog has 10x grown.

**Estimated effort.** L (1-2 weeks) including migration JSON→JSONB, GIN-index design, FTS tsvector columns, query rewrite in Tier 2.

**Sequencing.** Not blocking through Home Services V1 (50-100 entities is fine without it). Blocking by the time the 4th category page ships or the catalog crosses ~500 rows.

---

### §3.6 — Chat → directory data-source migration (Gap 6)

**What's missing.** `app/chat/tier2_db_query.py:33` imports `Event, Program, Provider` and filters them by legacy `category` strings. The chat surface has **no awareness of `Category` (`app/db/models.py:580`, added 2026-05-13)** — the column is dormant. The Tier 3 LLM context builder at `app/chat/context_builder.py` (referenced from `tier3_handler.py:19-20`) similarly knows only the pre-pivot data shape. As the directory builds out with `category_id`-typed rows, Place rows, and structured `attributes`, chat will keep returning the pre-pivot River Scene event catalog answers.

**Why it matters for the full vision.** The chat half of "three front doors" is the entire AI-recommendation surface. If chat queries the pre-pivot shape and the browse surface queries the post-pivot shape, the two front doors hand back contradictory answers to the same user.

**Recommended approach.** Phased: (a) replace category string filters with `Category.slug` joins in `tier2_db_query.py` once the backfill ships (Gap 2 must precede this). (b) Extend the Tier 3 context builder to surface `attributes` facets to the LLM (so "emergency plumber" can match `attributes.emergency_service == true`). (c) Add Place rows to the Tier 2 query population once Place ships (Gap 1). (d) Re-run the smoke catalog at `docs/maintainability/post_enrichment_smoke_catalog.md` against the post-pivot shape and resolve the 6 open spec questions before flipping `FEATURE_FLAG_DISCLOSURE_RENDERER`.

**Estimated effort.** L (1-2 weeks) spread across the four sub-steps.

**Sequencing.** Sub-step (a) ships immediately after Gap 2 backfill. Sub-step (b) after Gap 3 attribute schema. Sub-step (c) after Gap 1 Place model. Sub-step (d) closes out HALT 3 (Gap 16).

---

### §3.7 — Background-job infrastructure (Gap 7)

**What's missing.** The only background work runs in-process: `app/main.py:246` `_hourly_cleanup_loop` (`asyncio.create_task`) and per-request `BackgroundTasks` for mention scanning (`app/api/routes/chat.py:62`) and contribution enrichment (`app/contrib/enrichment.py:18`). When Railway restarts a web process, anything in flight dies. Anything scheduled is wall-clock-coupled to web-process uptime.

**Why it matters for the full vision.** Scheduled scrapers (Gap 4), email sending for Resend magic-link (Gap 8), image processing for owner-uploaded photos (Gap 9), cache warming, re-verification cycles — all of these need a real job runner with retry, dead-letter handling, and a worker process separate from the web tier.

**Recommended approach.** RQ + Redis is the lowest-friction Python answer. Railway has a Redis add-on for ~$5/mo and `python-rq` is ~200 lines of integration. Alternatives: Celery (heavier, broader feature set), Dramatiq (similar to RQ, more rigorous about reliability), Hatchet/Trigger.dev (managed, recently popular). Recommend RQ as the V1 cut — easy to migrate to Dramatiq or Celery later if reliability bar tightens.

**Estimated effort.** L (1-2 weeks) — worker process Procfile entry, queue design, monitoring, the first three job types (scraper, email, image processing).

**Sequencing.** Ships **before** Gaps 4, 8, 9 — they're all dependent. Could ship as the next foundational lane after Home Services V1 lands.

---

### §3.8 — User account system (Resend magic-link) (Gap 8)

**What's missing.** Zero auth code. No `User` model anywhere in `app/db/models.py`. No login route, no session cookie for end users, no `app/auth/` directory. The pivot §8.3 LOCKED to "Resend magic-link" but nothing has been built. Admin auth at `app/admin/router.py` uses a password-checked guard (`_guard`), distinct from end-user auth.

**Why it matters for the full vision.** Without user accounts: no merchant claim flow (Verified Presence requires claiming), no favorites (which the recommendation surface depends on), no alerts (retention loop), no identity for "AI recommendations for me." Every part of the full vision that says "for me" or "my" or "remember" needs accounts.

**Recommended approach.** Minimal `User(Base)` model: `id`, `email` (unique, indexed), `email_verified_at`, `display_name` (optional), `created_at`, `last_login_at`. New `MagicLinkToken(Base)`: `id`, `user_id` FK, `token_hash`, `expires_at`, `consumed_at`. Resend API integration via the new background-job runner (Gap 7). Session via signed cookie (no DB-side session table for V1; revisit if logout-everywhere becomes a requirement). Merchant claim flow attaches a `User` to a `Provider` via a new `ProviderClaim(Base)` row: `user_id`, `provider_id`, `state` (pending / verified / rejected), `verification_token`, `claimed_at`.

**Estimated effort.** L (1-2 weeks).

**Sequencing.** Gap 7 (background jobs) must ship first (for email delivery). Then this is the foundation for the claim flow (Gap 17), favorites (Gap 15), and any "for me" personalization (Gap 20).

---

### §3.9 — Image storage (Gap 9)

**What's missing.** `Provider.google_photo_refs` (`app/db/models.py:83`) is a `list[str] | None` JSON of Google Place photo URLs. `Provider.attributes.hero_pin_photo_url` is a single URL string. There is no owner-uploaded photo path, no S3 / Railway-volume / Cloudflare R2 wiring, no image-processing pipeline (resize, format conversion, EXIF strip), no CDN. Hot-path photo serves go straight to Google's CDN via stored URLs — which works for read but doesn't survive the owner saying "use this photo instead of the Google one."

**Why it matters for the full vision.** Verified Presence sponsors at $79/mo expect to upload their own hero photo. Place pages (parks, beaches, ramps) often need operator-uploaded photos because Google doesn't have them. At scale, image-density on category pages is the single biggest perceived-quality difference between a polished directory and a stub.

**Recommended approach.** Cloudflare R2 (S3-compatible, $0 egress) + a presigned-upload flow from the admin UI and merchant claim UI. Job-queued thumbnail generation (Gap 7) via Pillow for three sizes (thumb / card / hero). Photos addressed by hash so dedupe is free. New `Photo(Base)` table: `id`, `entity_type`, `entity_id`, `url`, `width`, `height`, `alt_text`, `uploaded_by_user_id`, `uploaded_at`. The view-model layer's `derive_hero_photo` (`app/providers/queries.py:80`) gets a third source-of-truth tier: `Photo` table > `attributes.hero_pin_photo_url` > first `google_photo_refs`.

**Estimated effort.** M (1-3 days for the basic upload + serve path; the long-tail polish takes longer).

**Sequencing.** Needed before paid Verified Presence sponsors expect photo control. Could defer until first Verified Presence customer asks for it — but at scale, R2 + presigned uploads is so cheap to wire that doing it early reduces friction.

---

### §3.10 — Map integration (Leaflet + OSM) (Gap 10)

**What's missing.** Pivot §8.4 LOCKED to "Leaflet + OSM tiles." Zero map code on tree. Searches for `leaflet` / `mapbox` / `map.html` return only the mockup at `mockups/11-chat-renderers-demo.html` and doc/handoff references. The Provider profile page renders a `directions_url` link out to Google Maps (`app/providers/queries.py:112-128`) but no in-page map.

**Why it matters for the full vision.** Every category page is supposed to ship with a list/map toggle (pivot §4 Day 42-60 block). Place pages (parks, ramps) almost universally lead with map UX. Map presence is the single biggest visual cue that this is a directory and not a chat box.

**Recommended approach.** Leaflet via CDN (no build step matches the existing vanilla-JS frontend pattern at `app/static/index.html`). One reusable `app/static/js/map.js` component with `init(containerId, points[])` API. Tile server: OSM default for V1; consider CARTO Voyager for prettier tiles when bandwidth allows. Server side: a `GET /api/category/<slug>/points` endpoint returning `[{slug, name, lat, lng, category_id}]` keyed by viewport bounding box. Re-use the lat/lng already on `Provider` (`models.py:65-66`) and on the to-be-built `Place`.

**Estimated effort.** M (1-3 days) for the shared component + one category page integration; per-page replication is faster after that.

**Sequencing.** Per pivot Day 42-60 block — ships alongside Eat & Drink category page.

---

### §3.11 — Admin tooling hardening (Gap 11)

**What's missing.** `app/admin/router.py:1439` free-text `<input>` for category (covered in Gap 2). No bulk-import UI (operators run `scripts/ingest/ingest_enrichment_csv.py` from shell). No automated re-verification cycle UI — operator manually re-runs scrapers and re-touches rows. No bulk-edit shape ("set `attributes.emergency_service = true` on all rows where `sub_trades` contains 'after-hours'"). No staleness dashboard ("show me all Providers where `last_verified_at` is `aging` or `stale`").

**Why it matters for the full vision.** Manual admin tooling caps the data-gathering velocity at one human's typing speed. To get to "comprehensive Lake Havasu directory" across 12 categories with thousands of entries plus places, the admin surface needs to be a productive tool, not a free-form form.

**Recommended approach.** Three sub-lanes: (a) Replace `app/admin/router.py:1439` free-text input with `<select>` (covered in Gap 2). (b) Add a bulk-import admin route that wraps `ingest_enrichment_csv.py` behind an upload form, surfaces validation errors per-row, and shows a dry-run diff. (c) Add a "staleness queue" admin tab that lists Providers with `last_verified_at` in `aging`/`stale` bands and provides one-click "mark verified now" + "re-run scraper enrichment" actions.

**Estimated effort.** M (1-3 days for each sub-lane; can ship in parallel).

**Sequencing.** Sub-lane (a) immediate (with Gap 2). (b) and (c) ship before manual data-gathering kicks off across all categories.

---

### §3.12 — Provider / Event / Program cross-entity unification (Gap 12)

**What's missing.** `Provider`, `Event`, `Program` are three SQLAlchemy classes (`app/db/models.py:31`, `:159`, `:270`). Each carries its own `category` / `activity_category` string and its own (now) `category_id`. The chat query "what's happening at Altitude Trampoline this weekend" needs to join Provider → Event/Program but the current Tier 2 code paths render each in isolation (`tier2_catalog_render.render_tier2_events` is event-only; mixed responses fall through to an LLM formatter per `docs/PROJECT.md:32-40`).

**Why it matters for the full vision.** A real-world business is often a Provider (the venue) with associated Programs (recurring classes) and Events (one-offs). The chat answer should weave these together; the Provider profile page should surface upcoming Events + active Programs. Today this is partial: `Provider.events` and `Provider.programs` relationships exist (`models.py:128-129`, `:331`) but no view-model uses them.

**Recommended approach.** Extend `app/providers/view_models.py:ProviderProfileVM` (`view_models.py:40`) with `upcoming_events: list[dict]` and `active_programs: list[dict]` populated via the existing relationship attributes. Then extend `app/chat/tier3_handler.py` context builder to include event/program rows linked to a resolved Provider entity. This is a re-use job, not a build job — the relationships already exist; nothing reads them.

**Estimated effort.** M (1-3 days) for view-model + chat context updates.

**Sequencing.** Ships **after** the Provider profile page is live (which is in flight per STATE.md line 54). Before Day 90 chat-surface re-evaluation.

---

### §3.13 — Cache coverage on directory surfaces (Gap 13)

**What's missing.** `LlmResponseCache` (`app/db/models.py:421`) caches Tier 3 LLM responses. There is **no cache for Provider profile pages, category landing pages, or sponsor lookups**. Every `/provider/<slug>` request runs the full view-model build (`app/providers/view_models.py:99`) plus N relationship reads. Every category page (when it ships) will do the same.

**Why it matters for the full vision.** At 1000-concurrent-user scale, an uncached Provider profile page that does 4 DB roundtrips per render will be the p99 latency bottleneck.

**Recommended approach.** Two layers: (a) **HTTP caching** — `Cache-Control: public, max-age=300, stale-while-revalidate=600` on `GET /provider/<slug>` and `GET /category/<slug>` for anonymous responses; serve from Railway's edge if available, otherwise from FastAPI directly. (b) **In-memory view-model cache** — Python `functools.lru_cache(maxsize=2048)` on `app/providers/view_models.build(provider_id, now_minute_truncated)` keyed by provider_id and minute (so `is_open_now` updates at minute boundaries). Invalidate at write time via SQLAlchemy `after_update` hook on Provider. Same shape on category pages keyed by `(category_slug, page_number, filter_hash)`.

**Estimated effort.** M (1-3 days).

**Sequencing.** Ships during the "scale-tune for 1000-concurrent-users" lane just before launch.

---

### §3.14 — Scale-tuned inbound rate-limits + DB pool sizing (Gap 14)

**What's missing.** Inbound chat rate-limit is `@limiter.limit("120/minute")` at `app/api/routes/chat.py:46` — slowapi in-memory keyed by IP. At 1000 concurrent users with even one chat per minute average, this caps at 8 unique IPs/sec — fine in theory but slowapi's in-memory store doesn't shard across worker processes. DB pool sizing: `app/db/database.py:34` returns `{"pool_pre_ping": True}` for Postgres with no `pool_size` / `max_overflow` — falls back to SQLAlchemy defaults (5 + 10 = 15 connections per worker). With 4 Railway workers and 15 connections each, the pool ceiling is 60 — fine for tens of concurrent users, undersized for thousands.

**Why it matters for the full vision.** At 1000 concurrent users, default pool sizing causes connection exhaustion under burst. Slowapi's per-worker in-memory rate-limit means the 120/min cap is actually 120/min/worker — so a 4-worker deployment effectively caps at 480/min. Either is a real bug at the target scale, but both are easy fixes.

**Recommended approach.** (a) Migrate slowapi to a Redis-backed store via `slowapi.extension.Limiter(storage_uri="redis://...")` once Gap 7's Redis is in place. (b) Tune Postgres pool: `create_engine(DATABASE_URL, pool_size=20, max_overflow=20, pool_pre_ping=True, pool_recycle=300)` at `app/db/database.py:37`. (c) Add a connection-count alert via Sentry breadcrumb when pool checkout takes >100ms.

**Estimated effort.** S (hours).

**Sequencing.** Ships during launch-prep scale tuning. Cheap to do; high payoff at the target scale.

---

### §3.15 — Favorites / saved lists (Gap 15)

**What's missing.** Zero favorites schema. `Provider`, `Event`, `Program` have no `Favorite` relation. No "save" button on any rendered page. User accounts don't exist yet (Gap 8).

**Why it matters for the full vision.** Operator's vision phrase "AI chat that gives information AND makes recommendations" implies recommendations to **someone**. Without favorites, recommendations are generic-to-anyone — which is the Google-search experience, not what the directory differentiates on. Favorites are the minimum viable personalization signal.

**Recommended approach.** New `Favorite(Base)` table: `user_id`, `entity_type` (provider / event / program / place), `entity_id`, `created_at`. Unique `(user_id, entity_type, entity_id)`. New `POST /api/favorites/toggle`, `GET /api/favorites`. UI: heart-icon button on every entity card. Chat integration: surface "you've favorited X in this category" hint to Tier 3 LLM context.

**Estimated effort.** M (1-3 days).

**Sequencing.** Ships after Gap 8 (user accounts). Before any V2 personalization (Gap 20).

---

### §3.16 — HALT 3 close-out (Gap 16)

**What's missing.** Chat confabulation guardrails are gated behind `FEATURE_FLAG_DISCLOSURE_RENDERER=false` (STATE.md). The disclosure renderer is built (`app/chat/disclosure_render.py`) and tested but not active in production. Per `docs/maintainability/halt3_closeout.md` and `docs/maintainability/post_enrichment_smoke_catalog.md`, 6 spec questions remain open before the flag flip, and pivot §6 deprioritized this lane ("can defer 4-8 weeks past current expectation").

**Why it matters for the full vision.** The full vision says "AI chat that gives information and makes recommendations." Recommendations from an LLM front door without confabulation guardrails are a liability — both legally (FTC disclosure) and reputationally (recommendations that name nonexistent businesses). The HALT 3 framework exists precisely to gate this.

**Recommended approach.** Resolve the 6 open smoke-catalog questions; ship the v2 confabulation harness (#64 SHIPPED per STATE.md); run the harness against the post-pivot data shape; lock the band cutoffs; flip the flag. Sequenced after Gap 6 (chat-to-directory migration) because the smoke catalog needs to run against the new shape.

**Estimated effort.** M (1-3 days for the close-out, assuming the harness rerun reveals no surprises).

**Sequencing.** Closes out before chat-surface recommendations are surfaced to launch users.

---

### §3.17 — Sponsor claim/edit + analytics dashboard (Gap 17)

**What's missing.** No claim flow UI. No merchant-facing edit UI for sponsored Providers. No per-merchant analytics dashboard (impressions, profile views, click-to-call, click-to-directions, click-to-website). The `Provider.tier`, `sponsored_until`, and `Sponsor` table all exist but there's no operator-facing or merchant-facing surface to manage them.

**Why it matters for the full vision.** Verified Presence at $79/mo (pivot §7) requires a claim flow + edit UI + basic analytics. Without these the package can't be cold-sold meaningfully.

**Recommended approach.** Sequenced sub-lanes: (a) claim flow at `/claim/<slug>` (`app/providers/view_models.py:175`) — currently a placeholder URL, no route handler. Phone-verification via Twilio or a code emailed to a public-record email address; uses Gap 7's background jobs. (b) merchant edit UI scoped to claimed Providers; reuses admin form components. (c) analytics dashboard reading from new `ProfileView(Base)` and `Click(Base)` event tables (or a more compact `SponsorEvent` aggregate); per-merchant page accessible only to claimed users.

**Estimated effort.** L (1-2 weeks).

**Sequencing.** After Gap 8 (user accounts). Before any Verified Presence sales.

---

### §3.18 — Labeled sponsor slot in category pages + reporting (Gap 18)

**What's missing.** Provider profile page renders sponsor labeling via `app/providers/view_models.py:122` (`sponsor_disclosure_label = DISCLOSURE_WORD if is_sponsored else None`). But there's no **category-page sponsor slot** — i.e. a designated slot at the top of `/category/home-services` that surfaces a sponsored Provider with the "Sponsored" label per pivot §3 ("disclosure_renderer + placement_regime reused for sponsor labeling on category page cards").

**Why it matters for the full vision.** Category Visibility at $349/mo (pivot §7) is the second-tier package; it needs this slot to exist.

**Recommended approach.** Re-use the disclosure_renderer machinery: `app/chat/disclosure_render.py:419 render_sponsored_block` already builds the block deterministically for a chat surface. Extract the body/attribution/CTA builders into a category-page-friendly view-model (the heavy lifting is the tone allowlist regex pass which is reusable as-is). One new `app/categories/sponsor_slot.py` module + Jinja partial.

**Estimated effort.** M (1-3 days).

**Sequencing.** After Home Services + Eat & Drink category pages ship (pivot §5 Day 46-90 block). Ships alongside Category Visibility sales push.

---

### §3.19 — Native reviews / ratings (Gap 19)

**What's missing.** `Provider.google_review_snippets` (`app/db/models.py:82`) and `google_rating` (`:80`) carry surfaced Google review data. No native reviews schema, no review-submission UI, no review moderation queue.

**Why it matters for the full vision.** AI recommendations grounded only in Google review snippets are thinner-signal than native first-party reviews. Operator chose to defer this per pitch-doc framing; under the full vision the call deserves a second look — if recommendations are the headline value prop, more signal helps.

**Recommended approach.** Defer per operator's existing stance. When re-opened: new `Review(Base)` table with `user_id` (or `submitter_email` for unauth), `entity_type`, `entity_id`, `rating` (1-5), `body`, `status` (pending / live / hidden), moderation surface via admin. Tier 3 chat context includes review snippets when relevant.

**Estimated effort.** L (1-2 weeks) when V2 time arrives.

**Sequencing.** V2 — explicit operator deferral.

---

### §3.20 — Personalization beyond favorites (Gap 20)

**What's missing.** No demographic preference capture (singles / families / dog lovers / outdoor lovers / etc. from the vision statement). No location-radius preferences. No history-based recommendation surface. The audience signal column (`ChatLog.audience_signal` at `app/db/models.py:260`) exists but #39 is DEFERRED.

**Why it matters for the full vision.** The operator's vision explicitly names demographic segmentation: "every demographic (singles/party, families, couples/date night, elderly, dog lovers, outdoor lovers, water enthusiasts, etc.)." Without personalization, every demographic gets the same recommendations — defeating the purpose of segmenting.

**Recommended approach.** Two stages: (a) **opt-in demographic onboarding** during account creation — a 4-question quiz that captures the user's primary demographic anchors. Stored on `User.demographic_preferences` JSON. (b) **chat context injection** — Tier 3 system prompt receives the user's demographic anchors, biases LLM recommendations accordingly. (c) **eventually:** implicit signals from favorites + chat history feed back into the same JSON.

**Estimated effort.** L (1-2 weeks) for the V2 surface.

**Sequencing.** V2 — after Gaps 8, 15 in place.

---

### §3.21 — Deals engine + lead-gen attribution (Gap 21)

**What's missing.** Pivot §4 explicitly defers both to Phase 2 (Deals Engine $249/mo — QR wallet, merchant verification app, redemption ledger; Intent Capture $499/mo — Twilio + lead attribution + reporting). Zero code on tree for either.

**Why it matters for the full vision.** Both are sponsor packages that unlock additional revenue but aren't on the launch path.

**Recommended approach.** Defer per pivot. Build when first revenue covers the build cost.

**Estimated effort.** XL each (2-4 weeks per package).

**Sequencing.** V2 / Phase 2 explicit deferral.

---

### §3.22 — Syndication API + itinerary builder (Gap 22)

**What's missing.** Pivot §4 defers to Phase 3.

**Why it matters for the full vision.** Optional revenue stream — syndication is "give chambers the data feed for their websites." Not on the launch path.

**Recommended approach.** Defer per pivot.

**Estimated effort.** XL each.

**Sequencing.** Phase 3.

---

## §4 Dormant / partial-dead code from chat-first → directory-first pivot

Per operator's instruction: flag these now; **do NOT recommend immediate removal**. Cleanup happens at launch prep.

- **Smoke catalog spec infrastructure** at `docs/maintainability/post_enrichment_smoke_catalog.md` — 42 queries across 8 classes drafted for the flag-flip; pivot §6 deprioritized to "resolve when HALT 3 close-out activates." Six open spec questions remain unanswered. **Dormant until HALT 3 reopens.**

- **HALT 3 close-out scaffolding** — `docs/maintainability/halt3_closeout.md` template with the 5 spec ambiguities recently resolved (STATE.md `aa3abd4`). Harness v2 (#64) shipped 2026-05-12 emitting `category`/`activity_category` in `per_row.csv`. **Dormant** behind `FEATURE_FLAG_DISCLOSURE_RENDERER=false` until HALT 3 reopens.

- **Audience signal threading** (#39 DEFERRED) — `ChatLog.audience_signal` (`app/db/models.py:260`) column exists; column-gated AUTOMATIC persistence runs per STATE.md feature-flags block. No downstream consumer reads it; pivot §6 says this matters less now. **Dormant until V2 personalization (Gap 20) lands.**

- **`chat_logs` disclosure telemetry columns** (`app/db/models.py:262-267`) — `disclosure_regime`, `disclosure_sponsor_id`, `disclosure_tone_allowlist_passed`, `disclosure_eligible` — all nullable, populated only when the disclosure renderer runs, which requires the flag flip. **Dormant until flag flip.**

- **Legacy `Provider.category` string column** (`app/db/models.py:36`) — coexists with new `category_id` FK (`:91`). Becomes redundant once Gap 2 backfill ships **and** every read path migrates to `category_id`. **Plan to deprecate at launch prep.**

- **Legacy `Program.activity_category` string column** (`app/db/models.py:276`) — same situation; same plan.

- **Pre-pivot ad inventory** (`AdSlot` enum at `app/db/models.py:466`: `MARQUEE` / `SPOTLIGHT` / `PROMOTED` / `SUPPORTER`) — designed for the chat-surface placement concept; pivot §6 says this is "effectively deprecated" and reborn as Category Visibility. The `Sponsor` table itself remains load-bearing; only the slot enum and the chat-surface placement code need re-scoping. **Keep until directory-surface sponsor packaging lands then revisit.**

- **Pre-pivot session handoff scaffolding** — `docs/SESSION_HANDOFF_2026-05-08.md` through `_05-11.md` are historical records pivot §6 deprioritized. `docs/maintainability/pre_pivot_doc_banner_audit.md` §5 flags these as operator-review for a banner. Not code; doc-cleanup-only.

- **`mockups/11-chat-renderers-demo.html`** — references Leaflet for the map mockup; concrete map integration (Gap 10) will likely supersede the mockup approach entirely. **Keep as design reference until Gap 10 ships.**

- **`tier3_postprocess` / `tier3_phone_enforcement`** — chat-surface guardrails per pivot §3 "still validates the chat front door (now scoped to Ask Hava handoff)." **Stays load-bearing under either vision** — not actually dormant; called out here only because pivot reduced the chat surface area, so the relative leverage is lower than pre-pivot.

---

## §5 Scaling concerns for "thousands of concurrent users"

### §5.1 — DB connection pool exhaustion (breaks first; ~200 concurrent users)

**Risk.** `app/db/database.py:34` returns `{"pool_pre_ping": True}` with no `pool_size`/`max_overflow` override — SQLAlchemy defaults to 5+10=15 per worker. With 4 Railway workers, ceiling is 60 concurrent DB-using requests; chat-route requests can hold a connection for 1-3 seconds in Tier 3, so ~20-60 concurrent chat requests will starve everything else.

**Mitigation.** Tune to `pool_size=20, max_overflow=20, pool_recycle=300` (Gap 14). Add a connection-checkout-time Sentry breadcrumb.

### §5.2 — Search latency without an index (breaks next; ~500 concurrent users or ~500 catalog rows)

**Risk.** Tier 2 SQLAlchemy filter chains over `Provider.category` LIKE matches will scale O(N) per query. At 500 rows + 500 concurrent users running 1 query/sec, that's 250k row-scans/sec — exceeds Railway's Postgres tier even with `pool_pre_ping`.

**Mitigation.** Gap 5 search index. Until then, a covering index on `(category, is_active)` is a cheap intermediate step.

### §5.3 — Slowapi in-memory rate-limit per-worker (mis-counts above ~500 concurrent users)

**Risk.** `app/api/routes/chat.py:46 @limiter.limit("120/minute")` keyed by IP via slowapi's in-process counter — 4 workers means the "120/min" is actually "120/min/worker" → 480/min effective for the same IP. A burst from one IP gets through; a coordinated burst won't be rate-limited correctly.

**Mitigation.** Redis-backed slowapi store once Gap 7 lands.

### §5.4 — Outbound LLM rate limit (breaks via OpenAI / Anthropic 429 around 1k concurrent users)

**Risk.** Tier 3 calls OpenAI; Anthropic is also called per `app/chat/llm_messages.py` references. OpenAI tier-1 limits are ~500 RPM for gpt-4.1-mini. At 1000 concurrent users with even 20% Tier 3 routing and one call each, that's 200/sec → 12000/min → 24x over limit.

**Mitigation.** Aggressive `LlmResponseCache` (already shipped, `app/db/models.py:421`) with broader hit coverage. The query_embedding fuzzy-match v2 in the same model helps. Longer-term: contract-tier OpenAI bumps or fallback to Anthropic when OpenAI saturates.

### §5.5 — Uncached Provider profile + category pages (breaks p99 around 1k concurrent users)

**Risk.** Every `/provider/<slug>` request runs `view_models.build` (`app/providers/view_models.py:99`) plus N relationship reads. No HTTP cache, no view-model cache.

**Mitigation.** Gap 13.

### §5.6 — Static asset serving from FastAPI (breaks bandwidth)

**Risk.** `app/main.py:297 app.mount("/static", StaticFiles(...))` serves CSS/JS/images through the Python app. At 1000 concurrent users loading even 200KB of assets per page, that's 200MB/sec sustained — saturates the FastAPI workers.

**Mitigation.** Serve `/static/*` via Cloudflare or Railway's edge CDN. One-line config change at the proxy/CDN; no app code change.

### §5.7 — Background-job blocking (breaks reliability of email + scheduled work)

**Risk.** Per-request `BackgroundTasks` (`app/api/routes/chat.py:62`) die with the worker process on Railway restart. Anything time-sensitive (magic-link email after a user signup) silently fails.

**Mitigation.** Gap 7.

---

## §6 Recommended build-phase sequencing

### Phase 1 — data-gathering critical path (next 6-10 weeks)

Goal: unblock systematic data-gathering across all 12 categories. Monetization-agnostic.

1. **Gap 2 — `Category` backfill + admin-form validator.** Easiest leverage; gates every category-typed read path.
2. **Gap 7 — Background-job infrastructure (RQ + Redis).** Foundation for Gaps 4, 8, 9.
3. **Gap 4 — Scheduled scraper infrastructure.** Plug into Gap 7.
4. **Gap 1 — `Place` model + ingest path.** Unblocks 4 of the 12 category pages.
5. **Gap 3 — Sub-trade / facet taxonomy decision (JSON schema route for V1).**
6. **Gap 6 — Chat → directory data-source migration (step a + b: category_id + attributes).**

### Phase 2 — launch-blocking (weeks 10-22)

Goal: make the directory shippable to public users at 1000-concurrent scale.

7. **Gap 8 — User account system (Resend magic-link).** Plug into Gap 7.
8. **Gap 9 — Image storage (R2 + presigned uploads).** Plug into Gap 7.
9. **Gap 10 — Map integration (Leaflet + OSM).**
10. **Gap 11 — Admin tooling hardening (bulk import + staleness queue).**
11. **Gap 12 — Provider/Event/Program cross-entity unification.**
12. **Gap 5 — Search index (Postgres FTS).**
13. **Gap 15 — Favorites / saved lists.** Plug into Gap 8.
14. **Gap 16 — HALT 3 close-out.** After Gap 6.

### Phase 3 — pre-launch scale tuning + monetization-specific (weeks 22-30)

Goal: confirm 1000-concurrent-user p99 holds; ship monetization surface once model is locked.

15. **Gap 13 — Cache coverage on directory surfaces.**
16. **Gap 14 — Scale-tuned rate limits + pool sizing.**
17. **(Monetization model locks here.)** Operator decides: Verified Presence + Category Visibility, or some other shape.
18. **Gap 17 — Sponsor claim/edit + analytics dashboard.** Specific to the chosen monetization.
19. **Gap 18 — Labeled sponsor slot in category pages.** Same.

### Phase 4 — V2 post-launch (post-launch)

20. **Gap 19 — Native reviews / ratings.** Re-evaluate operator deferral under the full vision.
21. **Gap 20 — Personalization beyond favorites.** Operator's "for every demographic" vision phrase activates.
22. **Gap 21 — Deals engine + lead-gen attribution.** Pivot Phase 2 packages.
23. **Gap 22 — Syndication API + itinerary builder.** Pivot Phase 3.

---

## §7 Open questions for Casey

1. **Place model scope at V1 — overturn pivot §8.2?** Pivot §8.2 LOCKED Place to Phase 2. Under the evolved full vision (parks / ramps / dog parks / etc. as first-class), this lock should probably be revisited. Is Casey ready to overturn that decision and add Place to the Phase 1 build sequence?

2. **Background-job runner choice — RQ+Redis vs APScheduler vs Railway scheduled jobs?** All three are viable. RQ+Redis is the most general (unblocks email, image processing, scrapers in one infra add). APScheduler is in-process (no infra add but reliability is web-process-coupled). Railway scheduled jobs are cheapest if Casey is OK with platform lock-in. Recommended path is RQ+Redis ($5/mo Redis on Railway) but the call needs operator sign-off.

3. **Sub-trade taxonomy — JSON-with-validation now, structured table later?** Or jump straight to first-class `CategoryAttribute` + `ProviderAttribute` tables? The former is faster to ship; the latter is the eventual right answer. Splitting this in two is fine; combining is also fine.

4. **Search index — Postgres FTS or external (Meilisearch / Algolia)?** Postgres FTS is zero-infra-add. Meilisearch is best UX/$. Algolia is best UX/build-time but costs $. Recommend Postgres FTS for the directory's scale through Year 1; revisit if catalog crosses ~10k entities.

5. **HALT 3 close-out — defer past Day 90 per pivot §6, or close-out earlier?** The full vision's "AI chat with recommendations" leans heavier on the chat surface than the post-pivot framing implied. Worth reconsidering whether the 4-8 week deferral still makes sense, or whether it should reopen as a Phase 2 lane.

6. **Native reviews — defer to V2 per existing stance, or move forward under the full vision?** Operator chose to defer per pitch-doc framing. The full vision's "AI recommendations" stance arguably argues for native reviews earlier. Re-decide?

7. **CDN / static-asset strategy — Cloudflare in front of Railway, Railway edge, or stay on FastAPI for V1?** Easy to defer until traffic shape demands it; flagging now so the call is conscious.

8. **Monetization model lock-in timing — Phase 3 (week 22-30) or earlier?** The operator's "build-first, sell-after" sequencing leaves the monetization decision late. The Phase 3 sequencing in §6 lock-targets month 6. Is that the right cadence, or should ground-truth cold-pitch conversations start earlier with mockups?

---

## §8 Confirmation

No git or state-mutating command was run. The only file created in this audit is `docs/maintainability/architecture_gaps_for_full_vision_audit.md` (this file). All other operations were read-only `Read` and `Grep` calls against the working tree.
