# Layered Scrape Strategy — Lake Havasu Data-Gathering

> **Status:** strategy doc only; no implementation, no scraper code change.
> **Audience:** Cowork primary + Casey; future implementation-lane authors (Cursor / CC); operator running data-gathering passes.
> **Companion docs:** `docs/maintainability/place_model_design.md` (the Place schema this strategy populates), `docs/maintainability/architecture_gaps_for_full_vision_audit.md` Gap #3 (background-job infrastructure for scheduling), `docs/maintainability/manual_recovery_checklist.md` (the operator workflow for what falls through to Layer 5), `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md` (the rate-limiter infrastructure all scrapers share), `docs/STRATEGY_PIVOT_2026-05-12.md` §4 2026-05-14 amendment (full-vision scope).

---

## §1 Problem statement

The operator's full vision is a comprehensive Lake Havasu directory + AI chat with recommendations — every business, every place, every event, every program, every demographic served. At solo-founder pace, gathering this inventory by hand isn't feasible. We need automated data ingestion that fills as much of the directory as possible, then a clean operator workflow for what automation can't reach.

**Google Places API alone leaves real gaps.** Google's commercial business coverage is strong for restaurants, retail, hotels, healthcare, automotive, etc. It's weaker for non-commercial entities (public infrastructure, hobbyist venues, small community facilities) and inconsistent for things like RC tracks, pickleball courts buried inside other facilities, small public boat ramps, weekly farmers markets at variable locations, etc.

The fix is a **layered scrape strategy**: five layers of data sources, each covering a different slice of the gap. Each layer's output flows into the same `providers` + `places` tables (with a `source` field tracking provenance). The manual-recovery list at `docs/maintainability/manual_recovery_checklist.md` only fires for entities that no automated layer covers.

**Why layering beats single-source:** Google Places excels at commercial businesses but misses public infrastructure. OpenStreetMap excels at public infrastructure but has patchier commercial coverage. City open data excels at civic locations and licensed-contractor lists. Specialized APIs excel at category-specific verticals (NPI for healthcare, AZ ROC for contractors, USAP for pickleball, etc.). Each layer is right for its slice. The five-layer pull achieves much higher coverage than any single source.

---

## §2 The five layers (overview)

| # | Layer | Strength | Coverage gap |
|---|---|---|---|
| 1 | **Google Places API (extended for Provider + Place)** | Broadest commercial coverage; well-known schema; existing scrape infrastructure | Small public infrastructure, hobbyist venues, weekly/ephemeral locations |
| 2 | **OpenStreetMap + Overpass API** | Free; excellent public infrastructure coverage (parks, trails, ramps, public buildings) | Patchier commercial; relies on volunteer contribution density |
| 3 | **City of Lake Havasu / Mohave County / AZ state open data** | Authoritative for civic + parks & rec + licensed businesses + permits | Limited to what each jurisdiction publishes; varied format |
| 4 | **Specialized hobbyist + regulatory APIs** | Authoritative for narrow verticals (healthcare, contractors, pickleball, disc golf, etc.) | Per-category coverage only; many small categories have no API |
| 5 | **Manual recovery (operator field-work)** | Catches everything else; operator-verified | Slowest; bounded by Casey's field-trip bandwidth |

**Total expected coverage by combining all five layers:** approximately 95-98% of the comprehensive directory inventory. Layer 5 fills the last 5-10% that no automated layer reaches.

---

## §3 Per-layer detail

### §3.1 Layer 1 — Google Places API (extended)

**Current state:** `scripts/places_discovery.py` + `scripts/places_enrichment.py` operate this layer for `Provider` rows. The just-shipped `app/contrib/rate_limiter.py::GOOGLE_PLACES_LIMITER` handles QPS pacing (4 QPS default; 6.5 QPS for the enrichment sweep) and retry/backoff for the entire layer.

**Extension for Place entities:** the same scrape infrastructure refactored to also discover and enrich non-business entities. Implementation pattern (per `docs/maintainability/place_model_design.md` §11 sequencing):

1. Extract the shared scrape loop from `places_discovery.py` + `places_enrichment.py` into a library module (`app/contrib/google_places_scraper.py` or similar). Pure refactor; no behavior change.
2. New wrapper `scripts/places_discovery_places.py` (or extend the existing with a `--target-table=places` flag) that runs Place-shape queries against Google.
3. New `google_types_mapping.md` doc that maps Google's `types` array values to our `Category.slug` + `Place.place_type` discriminator. Operator-maintainable.

**Query patterns Google handles well for Places:**

- `"dog park in Lake Havasu City"` → returns parks with `types: ["dog_park", "park", "point_of_interest"]`
- `"park in Lake Havasu City"` → returns parks (some without dog_park flag)
- `"beach in Lake Havasu City"` → returns named beaches
- `"library in Lake Havasu City"` → civic
- `"boat ramp in Lake Havasu"` → marinas and major ramps
- `"hiking trail in Lake Havasu"` → major trails

**Field mask differences vs Provider scrapes:** drop `phone`/`website` (rarely apply to Places); add `editorialSummary` (Google has short blurbs on parks/landmarks); keep `userRatingCount` + `rating` (parks often have them); keep `regularOpeningHours` (civic locations + some parks have them).

**Effort to extend:** roughly 2-3 days of dispatch work (per the Place model memo §11). Reuses the existing rate-limiter, HTTP client, pagination handling, retry/backoff.

**Output → tables:**

- Provider scrapes write to `providers` (current behavior, unchanged)
- Place scrapes write to `places` (new; requires the Place model migration to have shipped first)
- Both set `source` field to track provenance: `source="google_places"` or similar

**Operator scheduling:** for V1 data-gathering, Layer 1 runs once per category as an operator-triggered batch. After initial population, scheduled monthly re-pulls catch newly-listed entities + close-down detection. Scheduling lives in the Railway scheduled-jobs service per `docs/maintainability/background_job_infrastructure_decision.md`.

### §3.2 Layer 2 — OpenStreetMap + Overpass API

**Why this layer:** OSM is volunteer-maintained but often has better coverage of non-commercial infrastructure than Google. Lake Havasu specifically has active OSM contribution density (the lake, the parks, the bridge, marinas are well-mapped). Free to use; no API key required for moderate usage; respects fair-use rate limits.

**Implementation approach:** new module `app/contrib/osm_overpass_client.py` + script `scripts/osm_overpass_pull.py`. Uses Overpass QL queries to fetch tagged elements within a bounding box around Lake Havasu City. Example queries:

```overpassql
[out:json][timeout:60];
(
  node["leisure"="dog_park"](34.43,-114.41,34.59,-114.30);
  way["leisure"="dog_park"](34.43,-114.41,34.59,-114.30);
);
out body geom;
```

Categories well-covered by OSM tags:

- `leisure=dog_park` — dog parks
- `leisure=park` — parks
- `leisure=playground` — playgrounds
- `leisure=pitch` (with `sport=tennis`/`basketball`/`baseball`/`pickleball`) — sports fields/courts
- `leisure=marina` + `amenity=boat_launch` — marinas + boat ramps
- `natural=beach` — beaches
- `amenity=library` — libraries
- `tourism=viewpoint` — scenic overlooks
- `tourism=attraction` — landmarks
- `historic=monument` / `historic=memorial` — historical markers
- `highway=path` + `route=hiking` — trails
- `amenity=public_building` — civic

**Rate limits:** Overpass public servers ask for max 10000 requests/day total + reasonable query sizes. For Lake Havasu (small bounding box) usage will be well under limits. Single batched query per category is the right shape.

**Output mapping:**

- OSM `name` → `Place.name`
- OSM `lat`/`lon` → `Place.lat`/`Place.lng`
- OSM tags (e.g., `leisure=dog_park`) → `Place.category_id` + `Place.place_type` via mapping table
- OSM `opening_hours` (when present) → `Place.hours_freetext` (parse to structured if simple)
- OSM `wheelchair=yes/no/limited` → `Place.amenities.ada_accessible`
- OSM `fee=yes/no` → `Place.amenities.free` (inverted)
- `source="osm"`

**Reconciliation note:** OSM and Google will both return some entities (e.g., a city park). Dedupe logic in §4 handles this.

**Effort:** new layer; roughly 3-5 days of dispatch work (new client module + script + mapping table + tests).

### §3.3 Layer 3 — City of Lake Havasu / Mohave County / AZ state open data

**Why this layer:** civic data sources are authoritative for entities the city itself maintains (parks & rec facility lists, public works inventory, licensed contractors, registered businesses). Often missing both from Google and OSM if no consumer-facing online presence exists.

**Sources to investigate (operator action — verify each is accessible):**

- **City of Lake Havasu Parks & Recreation department** — likely has a public facility list (parks, ball fields, dog parks, community centers). May be a PDF, JSON, or only HTML.
- **City of Lake Havasu business license database** — registered businesses. Often more comprehensive than Google for small operators.
- **Mohave County GIS** — if they have a parcel/POI layer, useful for places at the address level.
- **Arizona ROC (Registrar of Contractors)** — licensed home-services trades (plumbers, HVAC, electrical, etc.). Already cited in editorial copy for cross-verification.
- **AZ Office of Tourism** — visit-az.gov POI data; mostly tourist-relevant.

**Implementation approach:** per-source ad-hoc. Some sources have JSON APIs; some require HTML scraping; some only publish PDFs requiring extraction. Module structure: `app/contrib/lhc_open_data_client.py`, `app/contrib/az_roc_client.py`, etc. Each source is its own implementation effort.

**Coverage estimate:** Layer 3 catches things Layer 1 + Layer 2 miss for: small public infrastructure not popular enough to be in Google or OSM (school playgrounds, county-managed boat ramps, civic meeting rooms), small businesses without Google/Yelp presence, licensing status (which is critical for verified-listing trust signals).

**Effort:** 2-4 days per source. Likely 3-4 sources total at V1 = ~10-15 days dispatch work. **Per-source implementation is reasonable to defer to launch-prep phase** if Layer 1 + Layer 2 cover enough.

**Output mapping varies per source.** General pattern: `source="lhc_parks_rec"` / `source="az_roc"` / etc. Cross-reference fields where possible (e.g., AZ ROC license number lands in `Provider.attributes.license_number`).

### §3.4 Layer 4 — Specialized hobbyist + regulatory APIs

**Why this layer:** narrow verticals have purpose-built directories that beat any general source. For categories Google doesn't cover well (RC tracks, pickleball, disc golf, healthcare specialties), specialized APIs are sometimes the ONLY good source.

**Candidate sources (each gets its own implementation lane):**

- **NPI Registry** (`https://npiregistry.cms.hhs.gov/`) — healthcare providers. Already integrated per `Provider.verification_method="npi_registry"` enum. Free; well-documented JSON API.
- **AZ Registrar of Contractors** (overlaps with Layer 3) — licensed home-services. Used for cross-verification.
- **USAPickleball Club Locator** — pickleball venues; may require scraping.
- **PDGA Course Directory** — disc golf courses; public JSON-ish endpoint.
- **National Skating Rink directories** — varies by source.
- **AMA Aerodynamics (model airplane) club locator** — RC airplane clubs.
- **Local kayak / paddle group registries** — if they exist for Havasu specifically.

**Implementation approach:** per-source. Each becomes a small Python client module + ingest script + mapping table. Most are S-M effort each (hours to 1-2 days).

**Coverage estimate:** Layer 4 catches the long tail of category-specific entities. Per-category coverage estimates:

- Healthcare: NPI Registry covers ~95% of credentialed providers; remaining 5% are unlicensed or alternative-medicine.
- Pickleball: USAP covers club locations but not unregistered courts; remaining 30-40% manual.
- Disc golf: PDGA covers most public courses; remaining 10-20% manual.
- RC tracks: AMA covers most clubs; some private/informal tracks not listed; ~30% manual.

**Effort:** scoped per source. Total layer 4 effort across all candidate sources: roughly 8-12 days. **Reasonable to phase by category priority** — implement only the APIs for categories that ChatGPT taxonomy research identifies as Lake Havasu inventory.

### §3.5 Layer 5 — Manual recovery (operator field-work)

**What survives the first four layers:** ephemeral / informal / hyperlocal entities that have no online presence. Examples:

- Small dog parks not in Google or OSM and not on the city's facility list
- Informal pickleball courts in HOA neighborhoods
- Hobbyist meet-ups at irregular locations (car shows, model railroad gatherings)
- Local farmers market vendors (the market itself may be in Layer 1; the vendors aren't)
- Small home-based businesses operating mostly word-of-mouth
- Specialty venues operators (skating rinks, RC tracks) that aren't in national directories
- Recent additions Google hasn't indexed yet

**Operator workflow:** see `docs/maintainability/manual_recovery_checklist.md` for the scaffold. Casey's workflow:

1. Use the checklist (populated by ChatGPT taxonomy research) as a list of expected items per category.
2. After Layers 1-4 have run, compare what's in the database against the checklist. Items not yet in `providers` or `places` are the manual-recovery targets.
3. Plan field-trip routes by district cluster.
4. For each location: visit, photograph (one hero + signage/hours photos), note address, hours, amenities. Use phone's location pin if no street address.
5. Enter data via the admin form (requires the admin form to support Place entry — gated on the Place model migration).
6. Mark items `entered` then `verified` in the checklist.

**Estimated bandwidth:** 5-15 items per Saturday afternoon field-trip depending on geographic spread. At ~50 items in the checklist (estimate; will be refined by taxonomy research), 4-10 field-trips to clear. Reasonable to phase across 4-8 weeks.

---

## §4 Reconciliation across layers

Multiple layers will return the same entity. Lake Havasu Aquatic Park might appear in Google Places, OSM, and the City Parks & Rec list. Each layer's pass shouldn't create three rows; it should merge into one.

**Dedupe logic at ingest time:**

1. **Match by geo proximity.** If `lat`/`lng` within 50m of an existing row in `providers` or `places` — likely the same entity. Operator-tunable threshold.
2. **Match by normalized name.** `slugify(name)` matched against existing slugs in the table. If match: likely same entity.
3. **Match by `google_place_id`** when both source and existing row have it set. Definitive match.
4. **Match by OSM `id` or other source-specific stable IDs** when available.

**Field merge priority** (when same entity matched across layers):

1. Operator-typed fields (from admin form / manual recovery) — highest authority
2. Google Places (most recent enrichment)
3. OpenStreetMap
4. City / state open data
5. Specialized API (for fields that source is authoritative for, e.g. NPI for healthcare license)

**Implementation:** dedupe logic lives in a shared `app/contrib/ingest_reconciler.py` module that all five layer scripts call before writing. Returns either "insert new row" or "update existing row id X with these new fields, preserving operator-typed fields."

**`last_verified_at` semantics:** updated to latest across all sources. `verification_method` set to whichever source most-recently verified.

**`source` field on Provider/Place:** comma-separated list of source identifiers, or a `sources` JSON array. Records which layers have seen this entity. Useful for operator visibility ("this entity is in Google + OSM but not the city list — is the city list incomplete?").

---

## §5 Sequencing for initial population vs ongoing

### §5.1 Initial population (one-time, gated on Place model migration)

Sequential, layer-by-layer, full-batch each layer before moving to next. Reason: dedupe at Layer 2+ is easier with Layer 1 data fully in place.

1. **Layer 1 — Google Places** runs for all categories. Probably 1-2 days operator-attended (kick off batch, monitor, review errors).
2. **Layer 2 — OSM Overpass** runs for all Place-type tags. Most queries return quickly; 1 day operator-attended.
3. **Layer 3 — city/state open data** runs per available source. May take 1-2 weeks of integration work first; then days to run.
4. **Layer 4 — specialized APIs** prioritized by category importance. Phased over weeks; per-API work.
5. **Layer 5 — manual recovery** field-trips. Spread over 4-8 weeks; can overlap with Layer 3/4 work.

### §5.2 Ongoing scheduled passes (after initial population)

| Layer | Frequency | Purpose |
|---|---|---|
| Layer 1 (Google Places) | Monthly | Catch new businesses + closed businesses + updated info |
| Layer 2 (OSM) | Quarterly | OSM updates more slowly; quarterly captures most changes |
| Layer 3 (city/state) | Quarterly | Civic facility lists change rarely |
| Layer 4 (specialized) | Quarterly to annually | License renewals, club rosters |
| Layer 5 (manual) | Ad-hoc | When operator notices a gap; when running spot-checks |

Scheduled passes use the background-job infrastructure per `docs/maintainability/background_job_infrastructure_decision.md`. Railway scheduled-jobs services run the per-layer scripts on cron schedules. Failure modes: log + alert; don't retry the full batch automatically (operator review on failure).

---

## §6 Per-category coverage estimate

(Approximate; refined when taxonomy research returns + per-category inventory is populated)

| Category | Layer 1 (Google) | Layer 2 (OSM) | Layer 3 (city/state) | Layer 4 (specialized) | Layer 5 (manual) |
|---|---|---|---|---|---|
| Restaurants / Eat & Drink | ~95% | <5% | minimal | minimal | ~5% (food trucks, ephemeral) |
| Home Services | ~80% | minimal | ~15% (AZ ROC) | ~5% (NPI overlap) | minimal |
| Healthcare | ~70% | minimal | minimal | ~25% (NPI) | ~5% (alt-med) |
| Lodging | ~95% | minimal | minimal | minimal | ~5% (vacation rentals) |
| Shopping | ~90% | minimal | minimal | minimal | ~10% (mom-and-pop) |
| Auto & Gas | ~95% | minimal | minimal | minimal | ~5% |
| On the Water (incl. ramps) | ~50% | ~30% | ~10% (city) | minimal | ~10% |
| Outdoors & Parks | ~30% | ~50% | ~10% (city) | minimal | ~10% |
| Pets (incl. dog parks) | ~50% (vets) ~70% (dog parks) | ~30% (dog parks) | minimal | minimal | ~20% (small parks) |
| Family (incl. parks/playgrounds) | ~40% | ~40% | ~10% (city) | minimal | ~10% |
| Community / Civic | ~30% | ~30% | ~30% (city) | minimal | ~10% |
| Events | ~50% (recurring) | minimal | ~10% | minimal | ~40% (ephemeral) |
| Classes / Lessons | ~30% | minimal | ~10% | ~20% (USAP, etc.) | ~40% |
| Specialty venues (RC, skate, etc.) | ~20% | ~10% | minimal | ~30% (AMA, etc.) | ~40% |

**Net:** Layers 1-4 cover roughly 80-90% of total directory inventory; Layer 5 fills the last 10-20%. Casey's field-trip workload is bounded — not "visit every business in Havasu" but "visit the 50-100 entities no API surfaces."

---

## §7 Operator workflow + observability

**For each scrape run (Layer 1-4):**

- Log: total queries issued, total rows discovered, total rows new, total rows updated, total rows skipped (dedupe), total errors.
- Per-run summary written to a `docs/scrape_logs/` directory (or a `scrape_run_log` table) for audit.
- Failure alert: scrape that returns zero new rows or >50% errors triggers operator notification.

**For each manual-recovery field-trip:**

- Checklist items marked `field-trip-scheduled` → `info-gathered` → `entered` → `verified`.
- Operator notes captured in the admin form.

**For dedupe events:**

- Log when two layers return the same entity. Useful signal that dedupe logic is working.
- Surface ambiguous matches (geo within 50m but names differ significantly) to operator review queue.

**Observability tooling for V1:** plain log files + per-run markdown summaries. V2 could surface in an admin dashboard ("last scrape run for category X was N days ago, found Y new rows").

---

## §8 Open questions for Casey

1. **Layer 3 source prioritization.** Which Lake Havasu open data sources to invest in first? My recommendation: start with City Parks & Rec (highest signal for Place coverage) + AZ ROC (already wired in via verification_method). Defer Mohave County GIS + AZ Office of Tourism until ROI is clearer.

2. **Layer 4 specialized API prioritization.** Which specialized APIs to invest in first? My recommendation: NPI (already integrated per verification_method) + USAPickleball (high-value for the Family/Sports demographic). Defer PDGA, AMA, skating-rink directories until inventory pressures it.

3. **Dedupe geo-proximity threshold.** 50m feels right but operator may want to tune based on real data. Worth surfacing in `docs/maintainability/` as a tunable constant.

4. **`source` field shape.** Comma-separated string vs JSON array vs separate `entity_sources` table. My recommendation: JSON array on the entity row for V1 (simpler, queryable enough); separate table if multi-source provenance becomes a real query pattern.

5. **Schedule cadence.** Monthly Layer 1 / quarterly Layer 2 + 3 + 4 — is that the right cadence, or do we want more aggressive freshness? My recommendation: start with the cadences above; tune based on observed staleness.

6. **Re-verification responsibility.** When Google says a business is closed but our last operator-typed verification says it's open, who wins? My recommendation: operator-typed wins; flag the Google "closed" signal for operator review rather than auto-flipping the status.

7. **Manual-recovery scheduling.** Field-trips spread across 4-8 weeks vs front-loaded vs back-loaded vs alongside-API-scrapes. My recommendation: front-load the field-trips for categories with high Layer 5 fraction (Outdoors & Parks, Specialty venues, Events) since those need the most manual time; back-load for categories where Layers 1-4 cover 90%+.

---

## §9 Effort estimate

Per-layer implementation effort (excluding initial Place model migration):

- **Layer 1 extension for Place** (refactor shared scrape lib + new wrapper for Places + Google types mapping table): M (2-3 days dispatch work).
- **Layer 2 (OSM + Overpass client + script + mapping table)**: M (3-5 days dispatch work).
- **Layer 3 (per-source clients)**: M-L per source; total across LHC + AZ ROC + AZ Tourism: 6-10 days.
- **Layer 4 (per-API clients)**: S-M per source; total across NPI extension + USAP + PDGA: 5-8 days.
- **Reconciliation logic** (dedupe at ingest time, shared module): M (1-2 days).
- **Scheduled job infrastructure** (Railway cron services per layer): S per layer; ~1 day total wiring once infrastructure is in place.
- **Tests across all layers**: M (2-3 days).
- **Layer 5 manual recovery — operator field-trip time**: 4-8 weeks calendar time (~30-60 operator-hours).

**Total dispatch engineering work for Layers 1-4 + reconciliation + scheduling + tests: ~20-30 engineering days**, dispatchable as 5-7 lanes. Layer 5 is operator workload that runs alongside.

**Sequencing:** Place model migration → Layer 1 Place extension → Layer 2 OSM → reconciliation logic → Layers 3 + 4 phased by category priority → ongoing scheduled passes.

---

## §10 Summary

Five-layer pull (Google + OSM + city/state + specialized + manual) achieves ~95% inventory coverage of the comprehensive Lake Havasu directory. Each layer is right for its slice; combining them eliminates most blind spots. Total dispatch engineering work: 20-30 days for Layers 1-4 infrastructure; operator field-work ~30-60 hours over 4-8 weeks for Layer 5. Sequencing: gated on Place model + background-job infrastructure landing first, then layer-by-layer initial population, then scheduled ongoing passes.

The strategy intentionally avoids over-engineering: no paid Yelp/TripAdvisor/Foursquare integration (cost not justified; coverage doesn't expand meaningfully); no real-time scraping (batch is sufficient); no automated re-verification beyond freshness flagging (operator-typed wins on conflicts). The result is a directory that's measurably broader than Google for hyperlocal Lake Havasu queries because it pulls from sources Google can't or doesn't.
