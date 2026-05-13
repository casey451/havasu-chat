# Cursor Brief — Phase 6: Tier 1 UI build

> **Operator note:** Phase 6 builds the user-facing pages residents look at — six Tier 1 category landing pages, the unified Hava card grammar, the map view, boat-access mode toggle, time-aware ranking, district context paragraphs, homepage hero. Phase 6 runs **in parallel with Phase 5** (data gathering); Phase 6 builds against the schema (Phase 1+3, SHIPPED), Phase 5 fills against the schema. Phase 6 pages render empty with "more coming soon" copy until Phase 5 data lands; both phases finish in roughly the same ~6-8 week window with Phase 5 likely running a bit longer.
>
> **Pre-dispatch prereqs:** the 10 operator decisions + 6 technical verifications in `outputs/phase6_prereq_checklist.md` should close out before Phase 6 dispatches. Lead-up window: ~1-2 weeks of operator + Cowork primary time, mostly design decisions (lighter than Phase 5's lead-up).
>
> The brief is structured around **5 sub-phase boundaries** (§3.1-§3.5). Each sub-phase is independently committable + pytest-green. **HALT and report after each sub-phase** so the operator can commit + push before you proceed. Sub-phase decomposition:
>
> - **Phase 6.1** — Unified Hava card grammar (the critical first deliverable; ~4-7 days)
> - **Phase 6.2** — First category page template + Eat & Drink as proof (~4-6 days)
> - **Phase 6.3** — Remaining 5 Tier 1 category pages + district context + time-aware ranking + seasonal hours (~5-8 days)
> - **Phase 6.4** — Map view + boat-access mode + themed group landing pages (~5-7 days)
> - **Phase 6.5** — Homepage + Provider profile extension + mobile polish + close-out (~4-6 days)
>
> Total estimate: 22-34 days dispatch over 4-6 weeks calendar.

---

## §0 Baseline + reads + halt etiquette

Before dispatching Phase 6 (or before any sub-phase Cursor session):

1. **`git log --oneline -10`** — origin/main should top at the Phase 4 close-out + Phase 5 prep chain. Floor: `62ab3b7` (Phase 5 types-mapping expansion) → `08bca69` → `ac94b6c` → `2eb2759` → `2f87211` → `997cdc3` → `2ab5f07` → `86eeaf8` → `aaac4db` → `a75cfe8`.
2. **`git status`** — clean unless mid-operator-session.
3. **`python -m alembic heads`** — single head: `0a1b2c3d4e5f` (Phase 4.1 outbox table). **Phase 6 ships no schema migrations** — Phase 3 + 4 shipped every column Phase 6 reads.
4. **`python -m pytest -q --collect-only 2>&1 | tail -3`** — floor: **1803 collected** (Phase 5 §4.a baseline at `62ab3b7`). Phase 6 sub-phases add ~10-25 net-new tests each.
5. **Production deploy status** — Phase 4 + 5 prep on origin; production not yet redeployed since session-22. Phase 6 doesn't gate on redeploy — UI work renders against any deploy that has Phase 1+3 schema (all production deploys since session-22).
6. **Read these docs end-to-end before starting:**
   - `outputs/phase6_prereq_checklist.md` (this brief's companion — 10 operator decisions + 6 verifications + workload audit + risk register)
   - `docs/maintainability/master_build_plan.md` §4 Phase 6 (UI deliverables + Opus design references)
   - `docs/maintainability/master_build_plan.md` §4 Phase 7 (forward context — Phase 6 leaves hooks for Phase 7 chat integration + snowbird-return panel)
   - `outputs/cursor_brief_phase_5_tier_1_data.md` (parallel-lane brief — Phase 6 needs to know what data Phase 5 is producing so empty-state copy + per-category sort defaults are right)
   - `docs/operations/boat_access_rubric.md` (Phase 5 lead-up — Phase 6 boat-mode toggle consumes this JSON shape)
   - Opus design handoff (if linked from master plan; informs unified card grammar §3.1)
7. **Read these source files** so sub-phase Cursor sessions resolve cleanly:
   - `app/templates/home.html` (current homepage — Phase 6.5 replaces; preserve search bar + topbar shape from Phase 2B.3 `8338505`)
   - `app/templates/provider_profile.html` (current profile page — Phase 6.5 extends with "What's on at this venue" hook region)
   - `app/static/styles/home.css` (current CSS — Phase 6 extends; mobile-first responsive rules added per sub-phase)
   - `app/static/js/search.js` (Phase 2B.3 search bar JS; Phase 6.5 may re-position but preserves behavior)
   - `app/providers/queries.py` (`derive_hero_photo` + `derive_gallery` from Phase 2B.1; Phase 6 cards consume these)
   - `app/providers/view_models.py` (existing view model surface; Phase 6 sub-phases extend)
   - `app/search/routes.py` (Phase 2B.3 `/api/search`; Phase 6 category-page server-side rendering consumes this OR builds parallel server-rendered paths)
   - `app/db/models.py` (Entity columns Phase 6 reads: `heat_exposure`, `crowd_notes`, `boat_access`, `seasonal_hours`, `district_id`, `featured`, all from Phase 3.1)
8. Report all baseline values. **HALT and report** if any baseline value materially mismatches floor.

**Halt etiquette:** HALT at each sub-phase boundary (§3.1 close → operator commits → §3.2 starts in fresh Cursor session). Phase 5 chat may be in flight in parallel — gotcha #18 governs file-scope disjointness (Phase 5 touches `app/contrib/*` + `scripts/*` + `app/db/*`; Phase 6 touches `app/templates/*` + `app/static/*` + `app/providers/view_models.py` + new routes in `app/api/routes/`).

---

## §1 Why this phase exists

Phase 1-3 built the schema. Phase 4 built the runtime. Phase 5 fills the data. **Phase 6 makes the directory feel real to residents.** The 6 Tier 1 category landing pages are the resident-critical surface — when a Lake Havasu resident types "plumber" or "marina" into the search bar or browses the homepage, they need to land somewhere that immediately surfaces 15+ relevant entries with honest freshness signals, time-aware ranking, and the texture that makes Hava feel different from Google Maps.

**Texture rule (carry-forward):** every existing UI surface that doesn't get a Phase 6 rebuild stays unchanged. The existing `/api/search` JSON response, the existing magic-link auth flow, the existing photo upload UX, the existing chat-route response shape — all preserved. Phase 6 replaces `/home` template, adds 6 new category pages, adds the map view, adds the boat-mode toggle, extends `/provider/<slug>` with one new region — all additive to existing shapes.

**Phase 6 is engineering-driven** (unlike Phase 5 which is operator-driven). Cursor ships per sub-phase; operator reviews at boundaries; Phase 5 keeps running its 4-8 week data-gathering arc in parallel.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Frontend stack | LOCKED — Jinja2 server-side templating + vanilla JS for interactivity (per prereq §4.5). No React / Vue / Svelte / Next. Same shape as Phase 2B.3 `app/static/js/search.js`. | Prereq §4.5 |
| Unified Hava card grammar | LOCKED — single Jinja partial `app/templates/components/hava_card.html` renders any ENTITY in any context (category page / search results / group landing / profile reference). Place vs event vs commercial differentiation via status-line color + content, NOT separate templates. | Master plan §4 Phase 6 critical first deliverable + Opus design §6.1 |
| Card freshness band thresholds | LOCKED per prereq §3.i — green <30 days / amber 30-90 days / red >90 days for Phase 6 places. (Phase 9 events use tighter thresholds per master plan §4 Phase 9.) | Prereq §3.i |
| Mobile breakpoint | LOCKED at 768px per prereq §3.a. Below 768px: bottom-sheet patterns. At/above 768px: side panel / inline. | Prereq §3.a |
| Sponsor slot styling | LOCKED — subtle "Sponsored" pill + same card shell per prereq §3.b. No fancy paid-sponsor rendering. | Prereq §3.b |
| Sort defaults per category | LOCKED per prereq §3.c — Eat & Drink "Closest now"; On the Water "Closest + boat-access populated"; Home & Property "Verified first"; Health "Closest + NPI-verified first"; Auto/RV/Fuel "Closest + mobile-service variant"; Shopping "Closest + open-now". | Prereq §3.c + §2 table |
| District paragraph rendering | LOCKED — graceful fallback (chip-only display, no placeholder ribbon) per prereq §3.d. V1.5 may add paragraphs. | Prereq §3.d |
| Search bar placement | LOCKED — hero center on desktop + sticky-top on mobile per prereq §3.e. Matches Phase 2B.3 `8338505` shape. | Prereq §3.e |
| Map view default state | LOCKED — collapsed default everywhere except on-the-water + outdoors-parks-trails (Tier 2 but treated same). | Prereq §3.f |
| Boat-mode persistence | LOCKED — URL param + localStorage for anonymous; User.preferred_mode write for logged-in. | Prereq §3.g |
| Time-aware ranking | LOCKED — server clock; heat-bias kicks in at >100°F; +20% rank boost indoor, +10% shaded; tunable constants in code. | Prereq §3.h |
| Snowbird-return panel | DEFERRED to Phase 7 per prereq §3.j. Phase 6 ships homepage WITHOUT the snowbird panel. | Prereq §3.j |
| Conditions strip data | STUB in Phase 6; Phase 8 wires real AirNow + NWS + USGS data. Phase 6 ships the slot with "Conditions data coming soon" microcopy. | Master plan §4 Phase 8 |
| Admin form for operator-curated entry | DEFERRED to Phase 6 LATE (sub-phase 6.5 close-out) OR V1.5. Phase 5 operator uses direct DB SQL. If Phase 6.5 has bandwidth, ship a minimal admin form; otherwise defer. | Phase 5 prereq §8 + brief §4.f |

Locks from prereq checklist §3 populate this table once operator closes them. Currently §2 is fully locked per the recommended answers in the prereq; operator confirms or revises during lead-up.

---

## §3 Sub-phase playbooks

### §3.1 Phase 6.1 — Unified Hava card grammar (the critical first deliverable)

**Scope:**
- New `app/templates/components/hava_card.html` Jinja partial that renders ANY ENTITY in ANY context — single template, ~150-250 lines including the freshness-band logic + sponsor-pill + status-line variants
- Card variants by entity_type:
  - `commercial` (Provider) — status line color: green / amber / red per freshness band; content: "Open until 10pm" / "Closed; opens 9am" / "Hours unknown"
  - `place` (Park / Marina / Beach) — status line color: green / amber / red per freshness; content: "Open" / "Limited access" / "Seasonal"
  - `event` (Event) — status line color: lake-blue; content: "Tonight at 6:00pm" / "This Saturday" / "Last week"
- Card slots for sponsor pill (per prereq §3.b), district chip (per prereq §3.d), category chip, hero photo (via `derive_hero_photo` from Phase 2B.1), boat-access badge (only renders when `boat_access IS NOT NULL`), heat-exposure pill (only renders when `heat_exposure NOT IN ('indoor', null)` — shaded / outdoor / water_adjacent venues get visible signal)
- CSS rules for the card go in new `app/static/styles/components/hava_card.css` (imported from `home.css`)
- New `app/providers/view_models.py::HavaCardViewModel` dataclass — the shape the card template consumes; constructed from Entity + Location + Photo by `app/providers/queries.py::build_card_view_model(entity_id)` (or similar)
- Tests across the four render contexts (category page mock / search results mock / group landing mock / profile reference mock): card renders, all slots populate correctly, freshness band thresholds work, sponsor pill renders only when sponsored

**Acceptance gates:**
- New `app/templates/components/hava_card.html` exists + works in isolation (Jinja `{% include %}` from a test template renders cleanly)
- 10-15 net-new tests in `tests/test_phase6_hava_card.py`
- Ruff clean
- Pytest stays green
- Mobile rendering correct at 320px / 375px / 768px breakpoints (operator visual check — `python -m fastapi run app.main:app` + browser DevTools responsive view)

**Pragmatic deviations invited:**
- ViewModel placement: brief suggests `app/providers/view_models.py`; if a fresh `app/components/view_models.py` reads cleaner, flag in §13
- CSS file location: brief suggests `app/static/styles/components/hava_card.css`; alternative `app/static/styles/hava_card.css` flat-file is fine if directory creation overhead seems wasteful
- Test file: brief suggests `tests/test_phase6_hava_card.py`; if existing `tests/test_provider_profile.py` shape carries the regression coverage already, augment instead of new file
- Freshness anchor: brief locks `entities.updated_at`; alternative `entities.last_verified_at` (Phase 3.1 column) is also valid — flag if you switch

**HALT at §3 boundary. Report. Operator commits before §3.2 dispatches.**

---

### §3.2 Phase 6.2 — First category landing page template + Eat & Drink proof

**Scope:**
- New `app/templates/category_landing.html` template — base shape consumed by all 6 Tier 1 category pages (§3.3 extends)
- Page structure:
  - Compact sub-hero (search bar + category title + brief description)
  - 3-row chip filter system: row 1 cuisine/sub-trade chips; row 2 district chips (10 districts from Phase 3.2); row 3 operational+time chips (open-now / hours / freshness band)
  - Sort dropdown (default per category per prereq §3.c)
  - Sponsor slot (renders empty in Phase 6; Phase 11 wires actual sponsors)
  - Organic stream of Hava cards (calls `hava_card.html` from §3.1; pagination via cursor like Phase 2B.3's search API)
  - Map view toggle (stub button in 6.2; full map in 6.4)
  - Editorial copy footer (operator-authored short paragraph per category)
- New `app/api/routes/category_pages.py` (or extend `app/api/routes/home.py` if cleaner) — `GET /category/<slug>` route; reads from `/api/search` internally with `category=<slug>` filter; renders the new template
- Implement for **Eat & Drink** as the proof (highest data density per Phase 5 §3.1; warm-up category)
- Eat & Drink chips: cuisine sub-trade chips ("Mexican", "BBQ", "Pizza", "Cafes", "Bars", "Bakery", "Seafood", etc. — pulled from `Provider.attributes.sub_trades` or hardcoded list pending Phase 10 lock); district chips from Phase 3.2 seed (10 districts); operational chips ("Open now", "Open past 9pm", "Brunch", "Dock-and-dine" — the boat_access cross-filter)
- Eat & Drink default sort: "Closest now" — server clock + Haversine from user location (or city center for anonymous users); heat-bias if >100°F
- Empty-state copy when Eat & Drink has <15 entries: "More Eat & Drink coming soon — Hava is still building this section. Check back this week!"
- ~10-15 net-new tests in `tests/test_phase6_category_landing.py`

**Acceptance gates:**
- `/category/eat-drink` renders correctly with mock entity fixtures (or real Phase 5 data when available)
- Chip filtering works (clicking "Mexican" chip filters the result stream)
- Sort dropdown works (Closest / Alphabetical / Top-rated / Editorial-pick)
- Mobile responsive at 320px / 768px / 1024px+
- Tests green, ruff clean

**Pragmatic deviations invited:**
- Server-side rendering vs hydration: brief assumes server-side Jinja rendering with vanilla JS for chip interactivity; if you find rendering via JSON + JS reads cleaner (e.g., chip filter triggers `/api/search?q=&category=eat-drink&filter=mexican` then re-renders), flag in §13 with rationale
- Editorial footer text source: brief assumes hardcoded constant in template; if you want a `category_editorial.json` operator-maintainable file, flag in §13

**HALT at §3 boundary. Report.**

---

### §3.3 Phase 6.3 — Remaining 5 Tier 1 category pages + district context + ranking + seasonal hours

**Scope:**
- Apply the §3.2 template to the other 5 categories: On the Water, Home & Property, Health & Wellness, Auto/RV/Fuel, Shopping & Essentials
- Per-category chip customizations (each category has different cuisine-or-trade primary chips per Phase 5 brief §3.2-§3.6 + prereq §2 table)
- **District context paragraph** rendering on every Tier 1 entity's profile (single SQL join from entities → districts; renders as chip only per prereq §3.d locked decision)
- **Time-aware default ranking + heat-aware bias** implementation per prereq §3.h: new `app/core/ranking.py::compute_card_rank(entity, now, temperature)` helper; threshold at 100°F; +20% indoor / +10% shaded boost; tunable constants `HEAT_BIAS_THRESHOLD_F` + `HEAT_BIAS_INDOOR_WEIGHT` + `HEAT_BIAS_SHADED_WEIGHT`
- **Seasonal hours rendering** on profile pages (Opus #3): reads `entities.seasonal_hours` JSON column; renders the active season's hours by current date; falls back to `Provider.hours` for venues without seasonal_hours; tested across 4 calendar-window scenarios (summer / fall / winter / spring)
- ~15-25 net-new tests across `tests/test_phase6_category_landing.py` (additions per category) + `tests/test_phase6_ranking.py` + `tests/test_phase6_seasonal_hours.py`

**Acceptance gates:**
- All 6 Tier 1 category pages render at `/category/<slug>` with mock or real data
- Per-category sort defaults work (prereq §3.c spec)
- District context chip appears on profile pages
- Heat-bias ranking shifts demonstrable in test at >100°F
- Seasonal hours render correctly across calendar windows
- Tests green, ruff clean

**Pragmatic deviations invited:**
- Heat-bias threshold: prereq §3.h says 100°F; if local data suggests 95°F is the practical threshold (mid-day discomfort in shoulder months), flag in §13
- Time-of-day default sort vs "Closest now" math: brief assumes simple Haversine + time-decay; if more sophisticated ranking math reads cleaner, flag in §13 with rationale
- Seasonal hours fallback shape: brief assumes "if seasonal_hours empty/null then Provider.hours"; if you want a separate fallback config, flag in §13

**HALT at §3 boundary. Report.**

---

### §3.4 Phase 6.4 — Map view + boat-access mode + themed group landing pages

**Scope:**
- **Map view** via Leaflet + OSM tile server (per prereq §4.1 — free tier OK for production scale). Marker clustering via `Leaflet.markercluster` plugin (CDN-loaded; no new Python deps). Renders all Tier 1 entities with Hava-styled markers.
- Map view default-collapsed on most categories; default-expanded on on-the-water + outdoors-parks-trails per prereq §3.f. Toggle button persists state in localStorage per category.
- **Boat-access mode toggle** in topbar — opt-in toggle with prereq §3.g persistence (URL param + localStorage for anonymous; `User.preferred_mode` write for logged-in). When active: (a) category pages filter `boat_access IS NOT NULL`; (b) on-the-water page expands map by default; (c) profile pages add a top-of-fold boat-access region rendering the JSON from `boat_access` per `docs/operations/boat_access_rubric.md` shapes; (d) chat route (Phase 7 work — Phase 6 just leaves the hook in route headers + cookie/header propagation).
- **Themed group landing pages** for the 4 Tier 1 groups: Eat & Drink, Health & Fitness, On the Water, Home & Auto. Each group landing page bundles its constituent categories with an organic stream of Hava cards.
- Cross-category surfacing: themed-group pages may interleave events + places (Phase 9 wires real interleaving; Phase 6.4 ships the static stream).
- ~15-20 net-new tests in `tests/test_phase6_map.py` + `tests/test_phase6_boat_mode.py` + `tests/test_phase6_themed_groups.py`

**Acceptance gates:**
- Map renders correctly at `/category/<slug>?map=expanded` and on dedicated `/map` route if added
- Marker clustering works at zoom-out (500-marker test fixture per prereq §6.7)
- Boat-mode toggle persists across page navigations + sessions
- 4 themed group pages render at `/group/eat-drink`, `/group/health-fitness`, `/group/on-the-water`, `/group/home-auto`
- Tests green, ruff clean
- Manual smoke (deferred-to-operator): toggle boat-mode on, navigate across category pages, verify filter behavior

**Pragmatic deviations invited:**
- Map technology: brief locks Leaflet + OSM; if MapLibre + alternative tiles reads cleaner, flag in §13 (recommendation: stay with Leaflet; widely-deployed + well-documented)
- Marker clustering threshold: brief assumes default plugin settings; if you find Lake Havasu's geo extent needs custom cluster radius, flag in §13
- Themed-group page routes: brief uses `/group/<slug>`; alternative `/themes/<slug>` or similar acceptable with rationale
- Group constituent categories: brief lists 4 groups; if a 5th theme (e.g., "Civic & Public Services") would help residents, flag in §13 (recommendation: stay at 4 for V1)

**HALT at §3 boundary. Report.**

---

### §3.5 Phase 6.5 — Homepage + Provider profile extension + mobile polish + close-out

**Scope:**
- **New homepage** at `/home` (replaces existing Phase 2B.3 template):
  - Hero with search bar (center-on-desktop / sticky-top-on-mobile per prereq §3.e)
  - Ask Hava box prominent (consumer of existing chat route)
  - "Today in Havasu" conditions strip — STUB with "Conditions data coming soon" microcopy (Phase 8 wires real data)
  - 8 themed group tiles (clickable to group landing pages from §3.4)
  - Recent activity stream (last 20 entity adds + photo uploads, optional — operator decision during sub-phase)
- **Provider profile extension**: add "What's on at this venue" region to `/provider/<slug>`. Renders empty in Phase 6 (Phase 9 fills with event entities scheduled at that venue). Operator review at sub-phase boundary: should the region render at all in Phase 6 (with "Coming soon" copy) or stay invisible until Phase 9?
- **Mobile-first polish**: bottom-sheet patterns finalized for category pages + profile pages, swipe-gallery for photo galleries, sticky-action elements (favorite button, share button), responsive tested across iOS Safari + Android Chrome at the operator-locked device matrix per prereq §4.3
- **Phase 6 close-out work**:
  - master plan §4 Phase 6 SHIPPED 2026-XX-XX header
  - STATE.md Production block refresh
  - STATE.md Recently shipped §1 prepend
  - All 6 Tier 1 category landing pages confirmed rendering at `/category/<slug>` against current Phase 5 data
  - 5-10 net-new close-out tests in `tests/test_phase6_close_out.py` (regression smoke for homepage + profile extension + mobile breakpoint behaviors)

**Acceptance gates:**
- New `/home` renders correctly with hero + Ask Hava + conditions stub + 8 themed group tiles
- `/provider/<slug>` extended with the "What's on at this venue" region (rendering empty per Phase 9 hook)
- Mobile QA passes on operator's test devices (iOS Safari + 1 Android per prereq §4.3)
- Tests green, ruff clean
- master plan §4 Phase 6 marked SHIPPED
- STATE.md refreshed

**Pragmatic deviations invited:**
- Recent activity stream: brief includes as optional; if you find it adds clutter without data density, defer to V1.5
- "What's on at this venue" empty-state: render with "Coming soon" copy OR stay invisible — operator's call at §13 review
- 8 themed group tiles on homepage: master plan §4 Phase 6 specifies 8; if 6 or 10 reads cleaner with the actual category set, flag in §13 (recommendation: stay at 8 — matches Opus design)
- Editorial copy authoring: ~6 category editorial paragraphs + 4 themed group editorial paragraphs needed; defer to operator + Cowork primary during sub-phase OR Phase 10 polish

**HALT at §3 boundary. Phase 6 is COMPLETE.** Phase 6 SHIPS at the end of §3.5.

---

## §4 What Phase 6 explicitly does NOT do

Per master plan §4 Phase 6 + brief §3 design rails:

1. **No new schema migrations.** Phase 3 + 4 shipped every column.
2. **No Tier 2 / Tier 3 category pages.** Outdoors / Parks / Trails, Lodging, Pets are Phase 7. Events + Classes/Sports/Rec are Phase 9.
3. **No real conditions data.** Phase 8 wires AirNow + NWS + USGS. Phase 6 ships stub.
4. **No alert subscription UI.** Phase 8.
5. **No Cloudflare Pages migration.** Phase 10 polish moves static asset serving off FastAPI workers.
6. **No paid sponsor flow / Stripe billing.** Phase 11.
7. **No snowbird-return panel.** Phase 7 per prereq §3.j.
8. **No itinerary builder / bookings / reservations.** All V1.5.
9. **No frontend framework swap.** Stays on Jinja2 + vanilla JS per prereq §4.5.
10. **No regression on Phase 2-5 surfaces.** Magic-link auth, photo upload, /api/search, /provider/<slug> all preserve existing behavior unless Phase 6 explicitly extends them.

---

## §5 Risk register

12 entries:

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | Unified Hava card grammar locks at 6.1 but later sub-phases need new states | M | M | Phase 6.1 ships extension points (named Jinja slots); 6.2+ adds without re-locking |
| 2 | Mobile bottom-sheet pattern doesn't translate to Android Chrome | M | M | 6.5 explicit Android testing; Phase 10 catches anything missed |
| 3 | Map view performance bad with 740 markers at zoom-out | L | M | Marker clustering plugin; test with 500-marker fixture in 6.4 |
| 4 | Boat-mode toggle confuses non-boater users | L | M | Header toggle opt-in; default-off; cookie persistence |
| 5 | Time-aware ranking shifts unpredictably hour-to-hour | L | M | Heat bias threshold at >100°F; sort-stable within rank buckets |
| 6 | District paragraph NULL state looks like a bug | L | L | Render district as chip only per prereq §3.d lock |
| 7 | Phase 5 data is too thin when Phase 6 ships | H | L | Empty-state copy per §3.2 ("more coming soon"); Phase 6 ships against schema not data |
| 8 | Conditions stub microcopy looks like a TODO | L | M | "Conditions data coming soon" is intentional UX, not a TODO ribbon; Phase 8 fills cleanly |
| 9 | Phase 5 + Phase 6 Cursor sessions overlap files (gotcha #18) | M | M | Strict scope-disjoint: Phase 5 = app/contrib/* + scripts/*; Phase 6 = app/templates/* + app/static/* + app/providers/view_models.py + new routes |
| 10 | Editorial copy authoring blocks sub-phase ship | M | L | Defer editorial copy to operator-on-Phase-6-close OR Phase 10; sub-phases ship with placeholder operator text |
| 11 | Map view tile rate-limit hits production | L | M | OSM free tier is fine for ~5k/day per prereq §4.1; verify pre-launch via Phase 10 perf pass |
| 12 | Operator review backs up between sub-phase HALT boundaries | M | M | Cap at 1 design-review per week (~30-60 min); sub-phases ship serially not in parallel |

---

## §6 Phase 6 close-out criteria

Phase 6 SHIPS when:

1. All 6 Tier 1 category landing pages render at `/category/<slug>` (even if data is thin per Phase 5 progress)
2. Unified Hava card grammar locked at `app/templates/components/hava_card.html` + works across all render contexts
3. Map view + boat-mode toggle + themed group landing pages all ship
4. Homepage rebuilt with hero + Ask Hava + conditions stub + 8 themed tiles
5. Provider profile extended with "What's on at this venue" region
6. Mobile QA passes on operator's test devices
7. Pytest green (+50-100 net-new across 5 sub-phases — final count ~1850-1900 by close-out depending on Phase 5 + 6 parallel cadence)
8. Ruff clean across all touched paths
9. master plan §4 Phase 6 marked SHIPPED + STATE.md refreshed
10. No regression on Phase 2-5 surfaces

**After Phase 6 ships:**
- Phase 7 (Tier 2 UI + chat integration) dispatches in a fresh Cursor session (or fresh Cowork chat if multi-week)
- Phase 5 continues if not yet closed (Phase 5 takes 4-8 weeks; Phase 6 takes 4-6 weeks; Phase 5 finishes after Phase 6 in most scenarios)
- Operator decides on Railway redeploy cadence — Phase 6 changes are UI-only + don't gate on a fresh deploy beyond cache-bust + asset upload

---

## §7 Operator daily/weekly rhythm (parallel with Phase 5)

Phase 6 is engineering-driven so operator load is light:

| Day type | Activity | Time |
|---|---|---|
| Sub-phase boundary | Design review with Cowork primary (sub-phase §13 walkthrough + accept/reject deviations + commit decision) | ~30-60 min, 5x per Phase 6 lane = ~2.5-5h total |
| Sub-phase mid-flight | Cowork stays quiet; Cursor works | 0h operator |
| Phase 5 day | Operator runs Phase 5 work in the OTHER Cowork chat | ~9-15h/week |
| Total | Combined Phase 5 + Phase 6 | ~11-19h/week for 4-6 weeks; then Phase 5 solo for 2-3 weeks |

Suggested cadence:
- **Monday:** Phase 6 design-review (if a sub-phase just closed); Phase 5 morning scrape run
- **Tuesday:** Phase 5 field entry (~2h)
- **Wednesday:** Phase 5 ambiguous-queue triage + Layer 5 manual recovery (~2h)
- **Thursday:** Phase 5 field entry (~2h)
- **Friday:** Phase 5 QA spot-check + Phase 6 mid-flight check-in (if applicable)
- **Weekend:** Phase 5 field-trip pass OR rest

---

## §8 First operator action when Phase 6 chat opens

1. **Verify baseline** with `git log --oneline -10` + `python -m pytest -q --collect-only | tail -3` + `python -m alembic heads`
2. **Confirm or revise the §2 locked decisions** — most are pre-locked per prereq §3 recommendations; operator may want to revisit any of them before §3.1 dispatches
3. **Dispatch Phase 6.1** in a fresh Cursor session against `outputs/cursor_dispatch_prompt_phase_6_1.md` (TBD — Cowork primary authors during sub-phase planning OR in the new Phase 6 chat as the first opening task)
4. **HALT and review at §3.1 close-out**; operator commits + pushes Cursor's 6.1 work; §3.2 dispatches in next fresh Cursor session

Phase 6 begins.

---

*Authored at session-23-extension-3 (2026-05-13) alongside `outputs/phase6_prereq_checklist.md` and the Phase 6 Cowork-chat kickoff prompt. Lives at `outputs/cursor_brief_phase_6_tier_1_ui.md`. Parallel-lane brief with Phase 5; both phases finish in ~7-9 weeks calendar from when both start.*
