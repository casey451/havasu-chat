# Cursor Dispatch Prompt — Phase 6.4 (Leaflet+OSM map view + boat-access mode toggle + 4 themed group landing pages + search bar)

> Paste-into-Cursor prompt for the fourth Phase 6 sub-phase per master plan §4 Phase 6 + brief §3.4 — ships (a) Leaflet+OSM map view with marker clustering across category landing pages, (b) boat-access mode toggle in the header (URL param + localStorage + optional User preference; water-overlay when active; profile top-of-fold boat-access region when active), (c) 4 themed group landing pages (Eat & Drink, Health & Fitness, On the Water, Home & Auto), (d) search bar in homepage hero + category page headers (separate from Ask Hava button per master plan §8 OQ #11). Phase 6.4 is the **breadth-completion pass** for Tier 1 UI: 6.3 made all 12 active category pages live; 6.4 adds the cross-category browse + spatial + filter surfaces that complete the V1 directory experience. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_6_tier_1_ui.md` (read end-to-end, especially §0 + §3.4 + §2 + §4 + §5).
>
> **Gating dependencies:** Phase 6.1 SHIPPED on origin at `fd16e7a` (unified Hava card grammar). Phase 6.2 SHIPPED on origin at `3948add` (first category landing template + Eat & Drink proof). Phase 6.3 SHIPPED on origin at `5ebee46` (breadth pass to all 11 remaining Tier 1 slugs + district chip + time/heat-aware ranking + seasonal hours). parks-rec-scrapes cron sidecar migration `f6a7b8c9d0e1` SHIPPED at `532d48b` (ON DELETE SET NULL on `contributions.created_event_id` FK). Phase 5 multi-phase data-population COMPLETE at Phase 5.11 close (`dcf3dd4`); STATE.md ledger landed at `3a2d895`. **Phase 6.4 consumes** 6.1's Hava card grammar + 6.2's `app/templates/category_landing.html` template + 6.2's `app/api/routes/category_pages.py` route module + 6.3's `app/core/ranking.py`. Any deviations Cursor reported in 6.1/6.2/6.3 §13 are locked-as-shipped by the time 6.4 dispatches.
>
> **Parallel-with-Phase-7 caveat:** Phase 7 (chat + HALT 3 + cross-entity + snowbird-return view) is parallel-eligible with Phase 6.4 per gotcha #18 file-scope disjointness. Phase 6.4 touches: anchored edits on `app/templates/category_landing.html` + `app/templates/provider_profile.html` + `app/templates/home.html` + `app/api/routes/category_pages.py` + `app/main.py`; new files `app/templates/themed_group_landing.html` + `app/api/routes/themed_groups.py` + `app/api/routes/map_data.py` + `app/static/js/map.js` + `app/static/js/boat_mode.js` + `app/static/js/search_bar.js` + `app/static/styles/components/map.css` + `app/static/styles/components/themed_group.css` + `app/static/styles/components/search.css`; new tests `tests/test_phase6_map.py` + `tests/test_phase6_boat_mode.py` + `tests/test_phase6_themed_groups.py` + `tests/test_phase6_search_ui.py`. Phase 7 touches: `app/chat/` + `app/api/routes/chat.py` + LLM prompt surfaces + chat-specific tests. **Zero overlap** if both lanes hold scope. The Phase 7 wrapper at `outputs/cursor_dispatch_prompt_phase_7.md` is the parallel-dispatch artifact.
>
> **No operator prereq for Phase 6.4.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure template + route + helper + static-asset authoring on top of 6.1+6.2+6.3.
>
> **Operator decision-lock status:** the 4 Phase 6.4-relevant decisions are locked at this session (2026-05-20):
> - **Map library: Leaflet + OSM** (master plan §4 Phase 6 brief default; lightweight ~40KB gz, no API key, no usage cap; marker clustering via `leaflet.markercluster` plugin from same CDN).
> - **Themed group cuts: 4 groups** (Eat & Drink, Health & Fitness, On the Water, Home & Auto) per master plan §4 Phase 6 deliverables list. "Things to Do" is explicitly Phase 9 ("was deferred from Phase 6" per master plan §4 Phase 9); do NOT pull forward.
> - **Search bar UX: separate Search input + Ask Hava button** per master plan §8 OQ #11 recommendation ("collapse into single intelligent input is a V1.5 candidate after user data shows behavior"). Two distinct affordances; search hits `/api/search` (already shipped in Phase 2B.3 at `8338505`); Ask Hava routes to chat surface (Phase 7).
> - **Snowbird-return view: NOT in 6.4.** Stays in Phase 7 per operator lock 2026-05-20. Phase 6.4 wrapper explicitly excludes it.
>
> **Author note:** authored at the post-Lanes-A+B+C Cowork primary session (2026-05-20) post-`23b3a70` against the post-Phase-5.11 + post-6.3 + post-sidecar tip. Four SHA-patch slots: `fd16e7a` + `3948add` + `5ebee46` + `f6a7b8c9d0e1`. All four are already filled below; verify against `python -m alembic current` + `.git/refs/heads/main` before paste in case origin/main has advanced.
>
> **Clipboard pipeline** (primes operator clipboard with prompt body only — skips the preamble + post-prompt footer; PowerShell 5.1 truncates large multi-line clipboard payloads per session-23-2026-05-19 lesson #3, so this pipeline writes to a temp file + uses Notepad as a synchronous clipboard router):
> ```powershell
> Get-Content outputs\cursor_dispatch_prompt_phase_6_4.md | Select-Object -Skip 34 | Select-Object -SkipLast 59 | Out-File -FilePath $env:TEMP\phase_6_4_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_6_4_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-23-2026-05-19 lesson #2 — do NOT use `Get-Clipboard` directly; copying that command would overwrite the clipboard):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~18000–22000 bytes (the prompt body is dense). Anything under ~1000 bytes is a truncation signal — re-do the Notepad route.

---

```
Read outputs/cursor_brief_phase_6_tier_1_ui.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3.4 (Phase
6.4 deliverable list -- map + boat-mode + themed groups +
search), §2 (locked decisions; entries 8 + 10 + 11 are
6.4-relevant), §4 (what NOT to do), §5 (risk register).

Phase 6.1 SHIPPED on origin at `fd16e7a` (unified Hava card
grammar). Phase 6.2 SHIPPED on origin at `3948add` (first
category landing template + Eat & Drink proof). Phase 6.3
SHIPPED on origin at `5ebee46` (breadth pass to all 11
remaining Tier 1 slugs beyond Eat & Drink + district chip on
profiles + time/heat-aware ranking via app/core/ranking.py +
seasonal hours rendering). parks-rec-scrapes sidecar migration
`f6a7b8c9d0e1` SHIPPED at `532d48b` (ON DELETE SET NULL on
contributions.created_event_id FK; cron workflow_dispatch
+ scheduled runs verified green from 2026-05-19 onward). Phase
5 multi-phase data-population COMPLETE at 5.11 close (1,314
active entities across 12 active Tier-1 slugs; cat-13 thin at
4 entries).

Pytest baseline going in is **2060 collected** (2058 passed +
2 skipped per post-Phase-6.3 + sidecar state on origin/main
tip `23b3a70`). Verify per `python -m pytest --collect-only -q
| tail -3` BEFORE starting work. Alembic head is
**f6a7b8c9d0e1** (Phase 6 sidecar; chains from `0a1b2c3d4e5f`
Phase 4.1 outbox). Verify per `python -m alembic current`
BEFORE starting work and REPORT THE OBSERVED VALUE (do NOT
copy the dispatch-body-claimed value -- session-2026-05-19
lesson #6).

Ship Phase 6.4 ONLY per brief §3.4 -- (a) Leaflet+OSM map view
with marker clustering, mounted on each category landing
page as a toggle (default collapsed on desktop per master
plan §8 OQ #10 recommendation; default off on mobile to save
bandwidth) and rendering up to N=500 markers per page (paginate
or cluster aggressively above N); (b) boat-access mode toggle
in header (URL param `?boat=1`, localStorage key
`hava.boat_mode`, optional User.boat_mode_preference when
logged-in; when active, server-side category-page queries
filter by `boat_access IS NOT NULL`; map gets a water-overlay
tile layer; profile pages render a top-of-fold "Boat-access"
region showing the entity's boat_access JSON when set); (c)
4 themed group landing pages at /group/<slug> for slugs
[eat-drink-group, health-fitness-group, on-the-water-group,
home-auto-group], each rendering an interleaved stream of
unified Hava cards from the bundled categories (group-to-
category mapping below); (d) search bar in homepage hero +
category page headers, hitting /api/search (Phase 2B.3 endpoint
at `8338505`) and rendering results inline above the organic
stream; search bar is VISUALLY DISTINCT from the Ask Hava
button (two separate affordances per master plan §8 OQ #11).
**No homepage rebuild beyond adding the search bar in
hero** -- the full home.html rebuild (8 themed group tiles +
Today in Havasu conditions strip) is Phase 6.5. **No district
paragraph rendering** -- V1.5 per path-b lock. **No
snowbird-return view** -- Phase 7 (parallel-eligible lane).
**No chat integration** -- Phase 7. **No Phase 8 conditions
data wiring** -- the boat-mode water-overlay tile layer is
static (loaded from OSM-compatible tile source); does NOT
read from external_conditions_cache.

GROUP-TO-CATEGORY MAPPING (lock this as hardcoded dict in new
`app/groups/themed_groups.py` -- mirrors the 6.3 chip
dispatcher shape; brief §3.4 acknowledges Phase 10 may relocate
the source of truth):
- eat-drink-group: ["eat-drink"]  (single category; 255
  entities; the group page differentiates from the category
  page by rendering the themed-group hero copy + chip set
  per brief §3.4)
- health-fitness-group: ["health-wellness-care",
  "classes-sports-recreation"]  (cat-5 + cat-12; 272+31 = 303
  entities)
- on-the-water-group: ["on-the-water"]  (single category;
  119 entities; group page reuses cat-3's Hava cards but with
  themed-group framing + on-the-water-specific chip set)
- home-auto-group: ["home-property-services", "auto-rv-fuel"]
  (cat-4 + cat-9; 237+153 = 390 entities)

OPERATOR DECISION-LOCK STATUS for 6.4 (locked at
session-2026-05-20):

- Map library: **Leaflet + OSM** (CDN-loaded; no npm
  dependency). Use leaflet@1.9.x + leaflet.markercluster@1.5.x
  from cdnjs.cloudflare.com. Per gotcha #18 brief §4 lock --
  vanilla JS + Jinja2 only; no React/Vue/Svelte; no build step.
- Themed groups: **4 groups** (eat-drink, health-fitness,
  on-the-water, home-auto). "Things to Do" is Phase 9
  (master plan §4 Phase 9 explicitly notes "was deferred from
  Phase 6"). Do NOT add Things to Do to the 6.4 scope.
- Search bar UX: **Separate Search input + Ask Hava button**
  per master plan §8 OQ #11. Search input is a left-aligned
  text field; Ask Hava is a right-aligned pill button.
  Distinct visual treatments; search hits /api/search inline;
  Ask Hava routes to chat surface (which Phase 7 wires).
- Snowbird-return view: **NOT IN 6.4**. Phase 7 ships it.
- Boat-mode persistence layers: URL param > localStorage >
  User.boat_mode_preference (URL param takes precedence;
  localStorage persists across sessions for anonymous users;
  User column persists across devices for logged-in users).
  If User column doesn't exist yet, add it via alembic
  migration as part of 6.4 (single boolean column with
  default false on `users` table). Verify before authoring
  the migration that the column does NOT already exist.

ORDER MATTERS WITHIN PHASE 6.4:

1. First: read the docs + source files in brief §0 step 6+7,
   PLUS 6.1 + 6.2 + 6.3 ship surfaces + master plan §4 Phase
   6 deliverables list. Critical reads: brief §3.4 end-to-end
   (the scope spec); brief §3.3 close-out (to know what 6.3
   actually shipped -- specifically the chip dispatcher shape
   in app/api/routes/category_pages.py + the
   compute_card_rank helper); docs/maintainability/
   master_build_plan.md §4 Phase 6 (full deliverable list);
   docs/maintainability/master_build_plan.md §4 Phase 9
   (Things to Do group -- to confirm it's NOT in 6.4 scope);
   docs/maintainability/master_build_plan.md §8 OQ #10
   (persistent map vs toggle) and §8 OQ #11 (search vs Ask
   Hava); app/templates/category_landing.html (6.2 template;
   anchored edit adds search bar in header + map toggle);
   app/api/routes/category_pages.py (6.2 route; anchored edit
   wires boat-mode filter); app/templates/provider_profile.html
   (6.3 extended with district chip + seasonal hours;
   anchored edit adds boat-access top-of-fold region);
   app/templates/home.html (anchored edit adds search bar in
   hero only -- NO themed group tiles, NO conditions strip);
   app/db/models.py (Entity.boat_access JSON column shape +
   Entity.lat / Entity.lng for map markers; verify both
   exist; verify User.boat_mode_preference does NOT yet
   exist); app/main.py (verify category_pages_router mount
   point for adding new themed_groups_router + map_data_router
   mounts).

2. Then: alembic migration -- single new revision adding
   `users.boat_mode_preference` boolean column with default
   false + nullable=False. Migration revision SHOULD chain
   from `f6a7b8c9d0e1` (the Phase 6 sidecar head). Name the
   revision per the existing convention (8-char hex; check
   alembic/versions/ for shape). Use `sa.false()` (not
   `sa.text("0")`) for the server_default per Phase 1A
   Postgres-boolean lesson. Test the migration's upgrade +
   downgrade cycle in the new tests/test_phase6_boat_mode.py
   using `script.get_current_head()` + dynamic head capture
   (NEVER hardcode head literals -- session-2026-05-19
   lesson #4).

3. Then: new `app/groups/themed_groups.py`. ~40-80 lines.
   THEMED_GROUPS dict mapping group slug to list of category
   slugs (per GROUP-TO-CATEGORY MAPPING above). Helper
   `get_categories_for_group(group_slug) -> list[str]` +
   `get_group_for_category(category_slug) -> str | None`.
   Pure-function; no DB reads inline.

4. Then: new `app/api/routes/themed_groups.py`. Mounts
   `GET /group/<slug>`. Renders new template
   `app/templates/themed_group_landing.html` (which extends
   `category_landing.html` shape but with group-level header
   + interleaved cards from multiple categories). Query path:
   reads THEMED_GROUPS to get the underlying category slugs,
   does a single SQL join entities → categories → EntityCategory
   filtering by the group's category list, applies the same
   organic-stream + ranking logic 6.3 ships in category_pages.py,
   sorts via compute_card_rank with group-default sort. Mount
   the new router in `app/main.py` (anchored edit).

5. Then: new `app/api/routes/map_data.py`. Mounts
   `GET /api/map_data/<category_or_group_slug>` returning
   JSON {entities: [{id, name, lat, lng, category_slug,
   profile_url, status_line, hero_photo_url}]}. Filters by
   active flag + boat-mode param when set. Hard cap at 500
   markers per response; if exceeded, return the top-500
   per compute_card_rank + a `truncated_at_n: true` flag.
   Mount in `app/main.py`.

6. Then: new static assets in `app/static/`:
   - `js/map.js` (~150-300 lines): Leaflet init, marker
     clustering via leaflet.markercluster, lazy-load tiles
     from OSM tile server (use https://tile.openstreetmap.org
     directly; if CDN-load issues, fall back to a different
     OSM tile mirror -- flag in §13), click handler to
     navigate to /provider/<slug>, water-overlay tile layer
     hooked to boat-mode state.
   - `js/boat_mode.js` (~80-150 lines): toggle button event
     handler, localStorage read/write at key `hava.boat_mode`,
     URL param parse (`?boat=1` overrides localStorage), POST
     to `/api/users/me/boat_mode_preference` when logged-in
     (verify endpoint already exists from Phase 2A.3 or add
     anchored edit there if missing), DOM class toggle
     `body.boat-mode-active` for CSS targeting.
   - `js/search_bar.js` (~80-120 lines): debounced (300ms)
     fetch to /api/search?q=<query>, inline result rendering
     above the organic stream, ESC to clear, click outside
     to dismiss. SEPARATE keyboard shortcut from Ask Hava
     button.
   - `styles/components/map.css` (~60-100 lines): map
     container sizing (responsive: 400px height on mobile,
     500px on desktop), marker icon styling, cluster styling,
     toggle button styling.
   - `styles/components/themed_group.css` (~40-80 lines):
     themed group hero styling, group-specific accent colors
     per group (Eat & Drink = warm tone, Health & Fitness =
     fresh tone, On the Water = lake-blue, Home & Auto =
     neutral; pick from the existing palette in
     home.css/hava_card.css; do NOT introduce new color
     variables).
   - `styles/components/search.css` (~40-80 lines): search
     input styling, inline result-list styling.
   All four CSS files imported via `@import` at the top of
   `home.css` (matching the 6.1 pattern). All JS files loaded
   from category_landing.html / themed_group_landing.html /
   home.html via `<script src="/static/js/...">` tags --
   not inlined.

7. Then: anchored edits on templates:
   - `app/templates/category_landing.html`: add search bar
     in the page header (above the chip rows); add map
     toggle button next to existing sort dropdown; render
     a `<div id="map-container" hidden>` placeholder that
     map.js populates on toggle click. Verify the existing
     chip rows + organic stream are preserved.
   - `app/templates/provider_profile.html`: add a top-of-fold
     "Boat-access" region that renders ONLY when both (a)
     `body.boat-mode-active` class is present (JS-driven) AND
     (b) `entity.boat_access IS NOT NULL` (Jinja conditional).
     Region shows the boat_access JSON keys (dock, transient,
     fuel, etc.) per the boat_access_rubric.md shape.
   - `app/templates/home.html`: add search bar in the hero
     ONLY -- do NOT add themed group tiles (that's 6.5), do
     NOT add conditions strip (that's 6.5 + Phase 8). Other
     home.html surface preserved. **ANCHOR COORDINATION
     WITH PHASE 7 PER GOTCHA #18:** place the search bar at
     anchor comment `<!-- search-bar-include -->` inside the
     hero block. If the anchor comment doesn't exist in
     home.html yet, add it as part of this edit -- single
     comment line directly above the search bar markup.
     Phase 7's snowbird panel (if it lands first OR
     concurrently) reserves the `<!-- snowbird-panel-include -->`
     anchor in a structurally separate region (below hero,
     above category-tiles or similar seam). Do NOT touch the
     `<!-- snowbird-panel-include -->` anchor region in this
     edit; keep all 6.4-scoped home.html changes inside the
     hero block.
   - `app/api/routes/category_pages.py`: anchored edit wiring
     boat-mode query param (`?boat=1`) -> filter entities by
     `Entity.boat_access IS NOT NULL`. Reads the query param
     via FastAPI dependency. Do NOT remove or alter existing
     chip dispatcher / sort default logic from 6.3.

8. Then: new tests across FOUR files:

   - tests/test_phase6_map.py (8-12 tests): GET
     /api/map_data/<cat_slug> returns 200 + valid JSON shape;
     truncated_at_n flag fires above 500; boat-mode param
     filters correctly; lat/lng NULL entities excluded;
     marker count matches active entities; coordinate
     precision preserved; per-group map data returns
     interleaved entities; non-existent slug returns 404.

   - tests/test_phase6_boat_mode.py (8-14 tests): alembic
     migration upgrade + downgrade cycle (dynamic
     head-capture per session-2026-05-19 lesson #4);
     User.boat_mode_preference defaults to false; setting
     it via /api/users/me/boat_mode_preference persists;
     boat-mode-active class affects template rendering of
     provider_profile.html boat-access region; category
     page filters by Entity.boat_access IS NOT NULL when
     ?boat=1 query param set; localStorage-only path (no
     User) works for anonymous users via integration test;
     URL param overrides localStorage in the JS path
     (testable via a unit test of the parse helper in
     boat_mode.js IF a JS testing setup exists -- else
     defer to manual smoke).

   - tests/test_phase6_themed_groups.py (8-14 tests): GET
     /group/eat-drink-group returns 200 + renders cards;
     same for /group/health-fitness-group (interleaved cat-5
     + cat-12); /group/on-the-water-group; /group/home-auto-
     group (interleaved cat-4 + cat-9); group-to-category
     mapping returns correct lists; non-existent group slug
     returns 404; themed_group_landing.html template extends
     category_landing.html base correctly; per-group sort
     default applied.

   - tests/test_phase6_search_ui.py (6-10 tests): home.html
     hero contains search bar with correct accessible
     attributes (form role, aria-label); category_landing.html
     header contains search bar; search bar is visually
     distinct from Ask Hava button (CSS class names differ);
     /api/search endpoint still 200s with correct response
     shape from Phase 2B.3 (regression guard); search_bar.js
     loaded on home + category pages.

9. After all of the above: confirm full pytest stays green
   (2060 floor + 30-50 net-new = 2090-2110), ruff clean.
   Manual smoke deferred-to-operator:
   - `python -m fastapi run app.main:app` + browse to
     /category/eat-drink, click map toggle, verify Leaflet
     map renders with marker clusters
   - Click a marker, verify navigation to provider profile
   - Toggle boat-mode in header, verify URL updates to
     ?boat=1 + map water-overlay appears + category page
     entities reduce to boat-access-only set
   - Browse to /provider/<slug-with-boat-access>, verify
     boat-access top-of-fold region appears WHEN boat-mode
     is on; absent WHEN off
   - Browse to /group/health-fitness-group, verify
     interleaved cat-5 + cat-12 cards
   - Type in homepage search bar, verify inline results
     render distinct from Ask Hava button

POSTGRES COMPATIBILITY (carry-forward from brief §0 + Phase 1A
lesson):
- Phase 6.4 SHIPS ONE alembic migration: `users.boat_mode_
  preference` boolean column, server_default `sa.false()`,
  nullable False. Chain from `f6a7b8c9d0e1` (Phase 6 sidecar
  head). Use `sa.false()` not `sa.text("0")`; use
  `sa.func.now()` not `sa.text("CURRENT_TIMESTAMP")` for any
  timestamp defaults (no timestamps in 6.4 but the pattern
  matters).
- Alembic head after 6.4 ships becomes the new migration's
  revision SHA (Cursor names per existing convention).

DEVIATION INVITATIONS (per brief §3.4):

- Map library: brief locks Leaflet+OSM; if Leaflet's
  marker clustering blows up at N=500 (perf test before
  shipping), flag a fall-back to "no clustering, paginated
  marker subset" in §13.
- Boat-mode persistence: brief locks URL > localStorage >
  User column ordering; if the cross-device behavior gets
  weird (e.g., logged-in user toggling on one device
  affects another mid-session), flag in §13 -- may need
  WebSocket invalidation in Phase 7 or accept as V1
  limitation.
- Themed group sort defaults: brief assumes group-page
  sort = first-category's sort default; if a group-specific
  sort makes more sense (e.g., health-fitness-group might
  want "Closest + NPI-verified first" mixing cat-5's NPI
  default with cat-12's drop-in-available default), flag.
- Search bar live-results UX: brief assumes debounced
  fetch on every keystroke; if a submit-on-enter feels
  better, flag.
- Map data endpoint shape: brief assumes JSON per
  category/group; if a single /api/map_data endpoint with
  ?scope=<cat_slug|group_slug> reads cleaner, flag.
- Boat-access region styling on profile: brief assumes
  top-of-fold; if mid-page reads better, flag.
- Themed group accent colors: brief assumes 4 group colors
  pulled from existing palette; if the operator wants
  fresh accent colors, flag (V1.5 candidate).
- THEMED_GROUPS dict location: brief locks `app/groups/
  themed_groups.py`; if `app/api/routes/themed_groups.py`
  reads cleaner as the source of truth, flag.

WHAT NOT TO DO (per brief §4 + §5):
- Don't ship homepage rebuild beyond search bar in hero.
  Phase 6.5.
- Don't ship "What's on at this venue" region on profile.
  Phase 9 (event scraper subsystem).
- Don't ship Things to Do themed group. Phase 9.
- Don't ship district paragraph rendering. V1.5.
- Don't ship snowbird-return view. Phase 7.
- Don't ship chat integration. Phase 7.
- Don't ship real conditions data for boat-mode tile overlay.
  Phase 8.
- Don't add React / Vue / Svelte / build step. Vanilla JS +
  Jinja2 per prereq §4.5.
- Don't add a mapping SDK that requires an API key (Mapbox,
  Google Maps, ESRI). Leaflet+OSM is the lock.
- Don't change /api/search response shape (Phase 2B.3 lock).
- Don't break /provider/<slug> existing test coverage from
  6.1 + 6.3.
- Don't break /category/<slug> existing test coverage from
  6.2 + 6.3.
- Don't add new Python dependencies beyond the alembic
  migration's natural use of sqlalchemy primitives.
- Don't bash heredoc commit messages. PowerShell-safe
  multiple `-m "..."` flags or here-string `@'...'@ |
  Out-File ... | git commit -F <file>` per
  session-2026-05-19 lesson #1.
- Don't hardcode alembic head literals in test code
  (session-2026-05-19 lesson #4). Use
  `script.get_current_head()` + dynamic capture.
- Don't dispatch Phase 6.5 or Phase 7 in the same Cursor
  session. HALT at the §3 Phase 6.4 boundary.
- Don't edit app/templates/home.html outside the
  `<!-- search-bar-include -->` anchor region in the hero
  block. Phase 7 (if parallel) owns the
  `<!-- snowbird-panel-include -->` anchor in a structurally
  separate region. Two distinct anchor regions; do NOT touch
  each other's region.

HALT at the §3 Phase 6.4 boundary. After 6.4 ships + commits
+ pushes, halt for operator re-dispatch in a fresh session
for Phase 6.5 (homepage rebuild + 8 themed group tiles + "What's
on at this venue" region hook) OR Phase 7 (chat + HALT 3 +
cross-entity + snowbird) -- both are parallel-eligible against
6.4's HEAD SHA.

Same constraints as Phase 6.1 + 6.2 + 6.3:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for 6.4
- Re-verify `python -m alembic current` and report the
  observed value (do NOT copy the dispatch-body-claimed value
  -- session-2026-05-19 lesson #6). If observed head differs
  from `f6a7b8c9d0e1`, HALT and ask operator before proceeding.

Pre-dispatch checklist (verify before paste):
- Phase 6.1 SHIPPED on origin (`fd16e7a`)
- Phase 6.2 SHIPPED on origin (`3948add`)
- Phase 6.3 SHIPPED on origin (`5ebee46`)
- Sidecar migration SHIPPED on origin (`532d48b` for the FK
  fix; alembic head `f6a7b8c9d0e1`)
- Phase 5 ledger SHIPPED on origin (`3a2d895`)
- `f6a7b8c9d0e1` is the current single alembic head on origin
- Pytest baseline going in is 2060 (or matches reality per
  `python -m pytest --collect-only -q | tail -3`)
- Brief §2 reflects any 6.1 + 6.2 + 6.3 §13 deviations
  (Cowork primary patched after ships if needed)
- Phase 7 lane (if running concurrently) is in a sub-phase
  that doesn't touch app/templates/ or app/api/routes/
  category_pages.py / themed_groups.py / map_data.py / app/
  groups/ or app/static/ -- verify per gotcha #18
- The 4 operator decisions are locked: Leaflet+OSM, 4 themed
  groups, separate Search + Ask Hava, snowbird excluded
```

---

## After Cursor returns with the §12 report

Same rhythm as 6.1 + 6.2 + 6.3: paste back to Cowork primary chat, primary reviews against §3.4 acceptance gates + brief §4 design rails, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 1 new alembic migration (~30-50 lines) — `users.boat_mode_preference` column
- 1 new `app/groups/themed_groups.py` (~40-80 lines) — THEMED_GROUPS dict + helpers
- 1 new `app/api/routes/themed_groups.py` (~80-150 lines) — `GET /group/<slug>` route
- 1 new `app/api/routes/map_data.py` (~60-120 lines) — `GET /api/map_data/<slug>` route
- 1 new `app/templates/themed_group_landing.html` (~80-150 lines) — extends category_landing.html
- 1 new `app/static/js/map.js` (~150-300 lines)
- 1 new `app/static/js/boat_mode.js` (~80-150 lines)
- 1 new `app/static/js/search_bar.js` (~80-120 lines)
- 1 new `app/static/styles/components/map.css` (~60-100 lines)
- 1 new `app/static/styles/components/themed_group.css` (~40-80 lines)
- 1 new `app/static/styles/components/search.css` (~40-80 lines)
- 1 modified `app/templates/category_landing.html` (anchored edit; +~30-60 lines for search bar + map toggle)
- 1 modified `app/templates/provider_profile.html` (anchored edit; +~25-50 lines for boat-access region)
- 1 modified `app/templates/home.html` (anchored edit; +~15-30 lines for search bar in hero)
- 1 modified `app/api/routes/category_pages.py` (anchored edit; +~20-40 lines for boat-mode filter)
- 1 modified `app/main.py` (anchored edit; +~6-10 lines mounting 2 new routers)
- 1 modified `app/static/styles/home.css` (anchored edit; +~3 lines `@import` for 3 new component CSS files)
- 4 new test files:
  - `tests/test_phase6_map.py` (~8-12 tests)
  - `tests/test_phase6_boat_mode.py` (~8-14 tests)
  - `tests/test_phase6_themed_groups.py` (~8-14 tests)
  - `tests/test_phase6_search_ui.py` (~6-10 tests)

Expected pytest delta: +30-50 net-new tests. Pre-existing Phase 6.1 + 6.2 + 6.3 + Phase 5 prep tests must remain green.

Expected effort: 7-10 days dispatch per master plan §4 Phase 6 + session close-out §3 Lane D. CURSOR MAY SPLIT INTO TWO SUB-SESSIONS if it estimates the full scope as >8 days:
- Phase 6.4a: map + boat-mode (~4-5 days; file scope = alembic migration + 3 new JS files + 3 new CSS files + anchored edits on category_landing.html + provider_profile.html + category_pages.py + main.py + new map_data.py route + tests/test_phase6_map.py + tests/test_phase6_boat_mode.py)
- Phase 6.4b: themed groups + search bar (~3-5 days; file scope = new app/groups/themed_groups.py + new themed_groups.py route + new themed_group_landing.html + anchored edit on home.html for search bar + anchored edit on category_landing.html for search bar + new search_bar.js + new search.css + new themed_group.css + tests/test_phase6_themed_groups.py + tests/test_phase6_search_ui.py)

HALT between 6.4a and 6.4b is at the natural §3 work-unit boundary; operator commits + pushes 6.4a; 6.4b dispatches fresh against 6.4a's HEAD SHA + new alembic head.

For monolithic 6.4 execution (single session, all 4 deliverables), the dispatch body applies directly.

Expected pragmatic deviations:

1. Leaflet marker clustering perf at N=500 (may need pagination fall-back)
2. Boat-mode cross-device sync behavior (V1 limitation acceptable)
3. Themed group sort defaults (per-group vs first-category-inherits)
4. Search bar live-results vs submit-on-enter UX
5. Map data endpoint shape (per-slug vs single endpoint with scope param)
6. Boat-access region placement on profile (top-of-fold vs mid-page)
7. Themed group accent colors (existing palette vs fresh)
8. THEMED_GROUPS dict location (`app/groups/` vs `app/api/routes/`)

## After Phase 6.4 ships

Update master plan §4 Phase 6 — append Phase 6.4 entry under "Shipped (incremental)" subsection (Cowork primary appends below the 6.3 entry). Update STATE.md Production block + Recently shipped §1 prepend with the 6.4 close-out narrative. Update alembic head reference in both docs to the new migration's revision SHA.

Phase 6.5 dispatch prompt to be authored after 6.4 ships — chains off 6.4's HEAD SHA + alembic head (which will be the new boat_mode_preference migration's revision). 6.5 = homepage rebuild (8 themed group tiles + conditions strip data-hookup-deferred-to-Phase-8) + "What's on at this venue" region hook on profile (renders empty until Phase 9).

Phase 7 (chat + HALT 3 + cross-entity + snowbird) is parallel-eligible with 6.4. The Phase 7 wrapper at `outputs/cursor_dispatch_prompt_phase_7.md` (authored at this same session 2026-05-20) is the parallel-dispatch artifact. Per gotcha #18, file scopes are disjoint: 6.4 = templates/static/routes for UI; 7 = chat/api/routes/chat.py + LLM prompts.

---

*Authored by Cowork primary at the post-Lanes-A+B+C session (2026-05-20) against origin/main tip `23b3a70`. Lives at `outputs/cursor_dispatch_prompt_phase_6_4.md`. Four SHA-patch slots: `fd16e7a` + `3948add` + `5ebee46` + `f6a7b8c9d0e1` — all four filled at authoring time; verify against `python -m alembic current` + `.git/refs/heads/main` before paste in case origin/main has advanced. The Phase 7 wrapper at `outputs/cursor_dispatch_prompt_phase_7.md` is the parallel-dispatch artifact per gotcha #18.*
