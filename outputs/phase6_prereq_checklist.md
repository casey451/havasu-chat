# Phase 6 Operator Prereq Checklist — Tier 1 UI Build

> Pre-positioned at session-23-extension-3 (2026-05-13) alongside Phase 5 forward-positioning. Phase 6 dispatches **in parallel with Phase 5** per master plan §4 Phase 5 + §4 Phase 6 ("runs in parallel with Phase 5 data gathering"). Phase 6 builds against the SCHEMA (Phase 1+3, already shipped on origin); Phase 5 fills against the schema. Empty-state copy on Phase 6 pages renders until Phase 5 data lands.
>
> Authored alongside `outputs/cursor_brief_phase_6_tier_1_ui.md` for the parallel-execution lane. Phase 6 has its own Cowork chat (separate from Phase 5's chat) to keep operator decisions + Cursor dispatches scope-disjoint. Gotcha #18 caveat: when Phase 5 + Phase 6 Cursor sessions run, file scopes must stay disjoint or one will revert the other.

## §1 What Phase 6 is

Per master plan §4 Phase 6: **Tier 1 UI build — the user-facing pages residents look at.** Six category landing pages, the unified Hava card grammar that renders place + event + commercial entries with the same shell, the map view, the boat-access mode toggle, the time-aware + heat-aware default ranking, district context paragraphs on profiles, seasonal hours rendering, homepage with hero + Ask Hava + Today in Havasu strip + 8 themed group tiles.

Phase 6 is **engineering-driven** (unlike Phase 5 which is operator-driven). Cursor sessions ship per-sub-phase; the operator reviews at design-milestone boundaries (~4-6 reviews across the lane) rather than running daily field-work.

**Texture rule** (carried forward from every prior phase brief): zero regression on existing surfaces. The `/home`, `/api/search`, `/provider/<slug>`, photo upload, magic-link auth, and chat-route response shapes are all touched in Phase 6 (new homepage replaces existing one, search bar moves, etc.) — but each change preserves the underlying API/data semantics. Existing routes that don't get UI updates render unchanged. Pre-Phase-6 photo uploads + magic-link emails + chat responses keep working identically.

## §2 Tier 1 categories Phase 6 renders

Same 6 as Phase 5; the pages are built per the brief §3 playbooks:

| Category slug | Phase 5 entry target | Phase 6 default sort | Boat-mode visible |
|---|---|---|---|
| `eat-drink` | 90-140 | "Closest now" (time-aware + heat-aware bias) | Shoreline-commercial subset |
| `on-the-water` | 40-90 | "Closest" + boat-access JSON populated | Always visible (this is the boat-mode category) |
| `home-property-services` | 120-220 | "Verified first" (AZ ROC cross-reference matters) | Hidden |
| `health-wellness-care` | 30-70 | "Closest" + NPI-verified-first | Hidden |
| `auto-rv-fuel` | 50-100 | "Closest" + is_mobile_service variant ("comes to you") | Hidden |
| `shopping-essentials` | 60-120 | "Closest" + open-now filter | Hidden |

## §3 Operator decisions to lock BEFORE Phase 6 dispatches

10 decisions. Most are design choices the operator owns; a few are technical defaults Cowork primary can recommend if operator wants.

**a. Mobile breakpoint strategy.** At what viewport width does the bottom-sheet pattern kick in (vs desktop sidebar/inline)? Standard mobile-first is 768px / 1024px / 1280px breakpoints. **Recommendation: 768px** (tablet portrait = breakpoint between mobile bottom-sheet and desktop side panel).

**b. Sponsor slot styling.** What visual differentiation between paid sponsor and organic results? Per Opus design but operator may want to revisit. Default: subtle "Sponsored" pill + slightly different border treatment + same Hava card shell (texture rule — paid doesn't get fancier rendering). **Recommendation: subtle pill + same shell**; sponsor-vs-organic differentiation lives in the disclosure renderer, not the card.

**c. Sort dropdown default per category.** Each Tier 1 category gets a default sort. Options: closest-now / alphabetical / top-rated / editorial-pick / verified-first. Recommendation per category in §2 table above; operator confirms or revises.

**d. District context paragraph rendering.** V1 has `District.paragraph = NULL` per session-21 path (b) lock — paragraph landing pages deferred to V1.5. Phase 6 renders: (a) just district name on profile pages, falling back gracefully when paragraph is NULL; OR (b) reserves the paragraph slot with placeholder UX ("District context coming soon") for the V1.5 cutover. **Recommendation: (a) graceful fallback** — render district as a chip / breadcrumb only; the placeholder text feels like a TODO ribbon.

**e. Search bar placement.** Where does the search bar live? Options: homepage hero center / hero corner / sub-hero / mobile-first sticky bottom. **Recommendation: hero center on desktop + sticky-top on mobile** (matches the Phase 2B.3 search bar shape that already shipped at `8338505`); category page headers get a sub-hero compact variant.

**f. Map view default state per category.** Does the map open expanded by default, collapsed by default, or hidden behind a toggle? Per-category override (on-the-water naturally wants expanded; eat-drink wants collapsed). **Recommendation: collapsed default everywhere except on-the-water + outdoors-parks-trails** (Tier 2 category but worth treating same way) where it opens expanded.

**g. Boat-access mode persistence.** Phase 2A.1 already shipped `User.preferred_mode` column with values `default / boat`. Phase 6 boat-mode toggle reads + writes from this. For anonymous users, persistence options: URL param only (no persistence across visits) vs localStorage vs Cookie. **Recommendation: URL param + localStorage** (anonymous users get cross-visit persistence without auth); logged-in users get `User.preferred_mode` write on toggle so the preference roams across devices.

**h. Time-aware default ranking weights.** "Now" is defined as server clock (since clients in different time zones would be confusing for a Lake Havasu directory). Heat-aware bias kicks in when current temperature >100°F: shifts ranking toward `heat_exposure IN ('indoor', 'shaded')` venues by some weight. **Recommendation: heat bias starts at 100°F (Lake Havasu summer baseline)**, applies as +20% rank boost for indoor + +10% for shaded venues; tunable constant in code.

**i. Honest freshness band thresholds.** Per Opus design §6.3: colored dot/band on cards + profiles. Green / amber / red thresholds. Master plan §4 Phase 9 implies `green <7 days / amber 7-21 / red >21 days` for **events** specifically. For Phase 6 (Tier 1 places + commercial), the freshness anchor is `entities.updated_at` from the dual-write hook. **Recommendation: green <30 days / amber 30-90 days / red >90 days** for Phase 6 places (longer thresholds; commercial info changes slower than event schedules); the Phase 9 events spec is per-vertical.

**j. Snowbird-return view trigger.** Master plan §4 Phase 7 mentions "snowbird-return view on homepage (logged-in users active October-April see 'what's reopened' panel)" — Phase 6 may or may not ship this. **Recommendation: defer to Phase 7** (snowbird logic is small but needs the "what counts as reopened" data ingestion + seasonal_hours density; Phase 7 has the parallel-phase context). Phase 6 ships the homepage hero + 8 themed group tiles + Ask Hava box + Today in Havasu strip stub WITHOUT the snowbird panel.

## §4 External / technical verifications

**1. Leaflet + OSM tile usage.** Verify the OSM tile server rate limits + attribution requirements work for production scale. Production estimated traffic: ~100-500 page-views/day pre-launch ramp, ~1k-5k/day post-launch. OSM is fine for this volume. Operator decision: attribution placement on map view (corner overlay vs map footer). ~15 min.

**2. CDN cache header tuning.** Phase 2B.1 shipped R2 with `Cache-Control: public, max-age=31536000, immutable` per image. Verify this works against Cloudflare CDN edge in production. Phase 10 is the formal performance pass; Phase 6 just needs to confirm headers aren't blocking image loads. ~15 min.

**3. Mobile testing matrix.** Which devices does operator want tested? Standard set: iPhone 12+ Safari, iPhone SE (small), Android Chrome (Samsung), iPad portrait + landscape. Plus the operator's primary devices. **Recommendation: operator's iPhone + one Android friend's phone + iPad if available**; deferred professional QA to Phase 10. ~15 min lock.

**4. Cloudflare Pages decision.** Phase 10 master plan mentions "static asset serving moved off FastAPI workers (CDN edge)." Phase 6 doesn't gate on this — static assets continue serving from FastAPI through Phase 6; Phase 10 migrates. Decision: confirm "Phase 10 moves to CDN, Phase 6 doesn't worry about it." ~5 min.

**5. Jinja2 vs Svelte vs React.** Phase 1+ shipped with Jinja2 server-side rendering. Operator decision: stick with Jinja2 for Phase 6 (matches Phase 2B.3 / Phase 4.4 surfaces) OR introduce a frontend framework. **Recommendation: stick with Jinja2 + vanilla JS for sprinkled interactivity** (same shape as Phase 2B.3 search.js); frontend framework is V2/V3 territory. ~5 min lock.

**6. Opus design handoff 8 open questions.** Master plan §4 Phase 10 mentions "8 open design questions from Opus handoff resolved + folded into final templates" as a Phase 10 deliverable. Phase 6 may surface some of these — operator resolves them inline as Phase 6 sub-phases dispatch, OR defers all 8 to Phase 10 polish pass. **Recommendation: resolve in Phase 6** if the question blocks a specific sub-phase; otherwise defer to Phase 10. ~variable.

## §5 Workload estimate

Master plan §4 Phase 6 estimate: **L+ (15-25 days dispatch) over 4-6 weeks calendar**. Sub-phase decomposition (per §1 of brief):

| Sub-phase | Days dispatch | Calendar weeks |
|---|---|---|
| 6.1 — Unified Hava card grammar | 4-7 | 1 |
| 6.2 — First category page template (Eat & Drink) | 4-6 | 1 |
| 6.3 — Remaining 5 category pages + district + ranking + seasonal hours | 5-8 | 1-2 |
| 6.4 — Map view + boat-mode + themed groups | 5-7 | 1-2 |
| 6.5 — Homepage + profile extension + mobile polish + close-out | 4-6 | 1 |
| **Total** | **22-34** | **5-8 (overlap reduces calendar)** |

Engineering effort is mostly Cursor-side; operator review at sub-phase boundaries (~30-60 min each, 5 boundaries = ~2.5-5h total). Parallel with Phase 5's ~80-190h operator time, that's still operator-dominated overall.

**Concurrent total operator load with Phase 5 running:**
- Phase 5: ~9-15h/week (per Phase 5 prereq §5)
- Phase 6: ~2-4h/week (design review + sub-phase QA spot-checks)
- **Combined: ~11-19h/week for 4-6 weeks**, then Phase 5 continues solo for 2-3 more weeks

## §6 Risk register

12 entries per the brief-shape pattern:

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| 1 | Operator burns out under combined Phase 5 + Phase 6 load | M | H | Structure weeks: scrape-days (Phase 5 morning), entry-days (Phase 5 afternoon), design-review-days (Phase 6 1x/week); cap total at 15h/week |
| 2 | Phase 6 design decisions feel rushed under parallel pressure | M | M | §3 above pre-locks 10 most-likely decisions; operator confirms in lead-up not under-pressure |
| 3 | File-scope overlap between Phase 5 + Phase 6 Cursor sessions (gotcha #18) | M | M | Strict scope-disjoint dispatch: Phase 5 touches `app/contrib/*` + `scripts/*`; Phase 6 touches `app/templates/*` + `app/static/*` + `app/providers/view_models.py` + new routes |
| 4 | Phase 6 ships empty pages before Phase 5 fills data | H | L | Empty-state copy is part of brief §3; "more coming soon" with category-specific framing |
| 5 | Unified Hava card grammar locked at 6.1 but later sub-phases need new states | M | M | Phase 6.1 ships card with extension points (slot patterns); 6.2+ extends without re-locking the grammar |
| 6 | Mobile bottom-sheet pattern doesn't translate to Android Chrome | M | M | 6.5 mobile polish sub-phase explicitly tests Android + iOS; Phase 10 catches anything 6.5 missed |
| 7 | Map view performance bad with 740 markers at zoom-out | L | M | Marker clustering via Leaflet plugin (recommended); test with 500-marker fixture before launch |
| 8 | Boat-access mode toggle confuses non-boater users | L | M | Header toggle is opt-in; default-off; cookie persistence so it doesn't surprise repeat visitors |
| 9 | Time-aware ranking degrades trust if rankings shift wildly hour-over-hour | L | M | Heat bias only kicks in at >100°F threshold; sort stability is preserved within rank buckets |
| 10 | District context paragraph NULL state looks like a bug | L | L | §3.d recommendation: render district as chip only, no placeholder ribbon — looks intentional |
| 11 | Search bar placement A/B feedback comes too late | L | L | Operator reviews search bar at Phase 6.5 (after enough categories live to test); pre-launch QA in Phase 10 |
| 12 | "Today in Havasu" strip stub looks broken without conditions data | L | M | Phase 6 ships the stub with placeholder ("Conditions data coming soon" microcopy); Phase 8 wires real data; the slot itself doesn't render until Phase 8 unless operator wants visible-promise UX |

## §7 Phase 1-5 deliverables Phase 6 depends on

**Blockers (Phase 6 cannot dispatch without these):**
1. ✅ Phase 1 ENTITY schema (Provider + Event + Program + Entity unified table; SHIPPED)
2. ✅ Phase 2 photos + R2 (hero / thumbnail / medium / gallery rendering; SHIPPED + DEPLOYED)
3. ✅ Phase 2 account-lite (User table + magic-link auth + favorites; SHIPPED + DEPLOYED — Phase 6 boat-mode + favorites read from this)
4. ✅ Phase 2 Postgres FTS + /api/search (search bar consumes this; SHIPPED + DEPLOYED)
5. ✅ Phase 3 operator-curated fields (heat_exposure + crowd_notes + boat_access + seasonal_hours + district_id + featured; SHIPPED + DEPLOYED)
6. ✅ Phase 3 districts table (district chip + future paragraph rendering; SHIPPED + DEPLOYED)

**Nice-to-haves (Phase 6 dispatches with or without; Phase 5 + 7 fill these in):**
1. Phase 5 Tier 1 data populated (Phase 6 renders empty without; brief §3 empty-state copy handles)
2. Phase 6 admin form for operator-curated field entry (if Phase 6 sub-phases ship an admin form, Phase 5 operator entry gets faster; otherwise direct DB SQL per Phase 5 brief §3 acceptance gates)

All blockers are SHIPPED on origin. Phase 6 is **structurally unblocked** the moment the operator opens the second Cowork chat.

## §8 What Phase 6 explicitly does NOT do

Per master plan §4 Phase 6 + brief §7 design rails:

1. **No new schema migrations.** Phase 3 + 4 shipped every column Phase 6 reads.
2. **No Tier 2/Tier 3 category pages.** Outdoors / Parks / Trails + Lodging + Pets are Phase 7. Events + Classes/Sports/Rec are Phase 9.
3. **No real conditions data on "Today in Havasu" strip.** Phase 8 wires this; Phase 6 ships the slot stub.
4. **No alert subscription UI.** Phase 8 ships `/account/alerts` page.
5. **No frontend framework swap.** Stays on Jinja2 + vanilla JS per §4.5 lock.
6. **No CDN migration.** Phase 10 polish pass moves static asset serving off FastAPI workers.
7. **No paid sponsor flow / billing.** Phase 11. Phase 6 renders the slot with no paying sponsors.
8. **No admin form for operator-review queue.** Phase 5 uses direct DB SQL; admin form is Phase 6 LATE sub-phase OR V1.5.
9. **No itinerary builder / bookings / reservations.** All V1.5.
10. **No snowbird-return panel.** Defer to Phase 7 per §3.j lock.

## §9 Lead-up timeline

Suggested before opening Phase 6 chat:

**Day 1-2** (operator + Cowork primary):
- Lock the 10 §3 decisions (~1-2h with AskUserQuestion in this chat or a quick session)
- Fill Phase 6 brief §2 placeholder with locked decisions

**Day 3-7** (operator-driven):
- Run §4 technical verifications (~1h total spread across days)
- Decide §3.j snowbird panel inclusion (defer to Phase 7 recommended)
- Schedule Phase 6 design-review cadence (1x/week recommended)

**Day 7-14** (Cowork primary):
- Author Phase 6.1 dispatch prompt for the unified Hava card grammar sub-phase (~3-4h)
- (If operator wants the Phase 6 chat to start sooner, Cowork in the new chat authors 6.1 dispatch prompt as opening task; this saves 3-4h here)

**Day 14+:**
- Open Phase 6 Cowork chat with `outputs/new_chat_kickoff_phase_6.md` kickoff
- Phase 6.1 dispatches in fresh Cursor session
- Phase 5 continues in parallel in its own Cowork chat

## §10 Next concrete action

1. **Lock the 10 §3 decisions.** Either via AskUserQuestion in this chat (~1-2h) OR via a written response from operator (~30 min). Cowork primary fills brief §2 with locked answers.
2. **Run the technical verifications in §4.** ~1h spread; not blocking decision-locks.
3. **Open Phase 6 Cowork chat** using the kickoff prompt at `outputs/new_chat_kickoff_phase_6.md` (authored alongside this checklist).

Phase 6 dispatches in parallel with Phase 5. Combined timeline: both finish in ~7-9 weeks calendar from when both start.

---

*Authored at session-23-extension-3 (2026-05-13) alongside the Phase 6 brief + Phase 6.1 dispatch prompt + Phase 6 kickoff prompt. Lives at `outputs/phase6_prereq_checklist.md`. Phase 6 chat reads this + the brief end-to-end on first session.*
