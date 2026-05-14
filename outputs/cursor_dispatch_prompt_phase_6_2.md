# Cursor Dispatch Prompt — Phase 6.2 (first category landing page + Eat & Drink proof)

> Paste-into-Cursor prompt for the second Phase 6 sub-phase per master plan §4 Phase 6 + brief §3.2 — the FIRST category landing page template that the remaining 5 Tier 1 category pages will inherit, plus the Eat & Drink page as the proof. Phase 6.2 composes the Phase 6.1 unified Hava card grammar into a page-level shell (sub-hero + 3-row chip filter + sort dropdown + sponsor slot + organic stream + map view toggle stub + editorial footer). The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_6_tier_1_ui.md` (read end-to-end, especially §0 + §3.2 + §2 + §4 + §5).
>
> **Gating dependency:** Phase 6.1 SHIPPED on origin at `fd16e7a` (cleanup commit chain pre-6.1 closes at `0331102`). Phase 4 + Phase 5 prep on origin chain unchanged from 6.1 dispatch (`ac94b6c` + `62ab3b7` + `08bca69`). **Phase 6.2 consumes 6.1's `app/templates/components/hava_card.html` partial** as the per-card renderer inside the new category landing template; the deviation Cursor reported in 6.1 §13 (e.g., view-model placement, freshness anchor) is locked-as-shipped by the time 6.2 dispatches.
>
> **Parallel-with-Phase-5 caveat:** if a Phase 5 Cowork chat + Phase 5 Cursor session are running concurrently, the file-scope disjointness rule (gotcha #18) applies. Phase 6.2 touches `app/templates/category_landing.html` (new) + `app/api/routes/category_pages.py` (new) + `app/static/styles/category_landing.css` (new) + `app/static/js/category_filters.js` (new) + `tests/test_phase6_category_landing.py` (new) + possibly small `app/providers/queries.py` additions (chip-driven category-page query helpers). Phase 5 sessions touch `app/contrib/` + `scripts/` + `app/db/`. Zero overlap if both lanes hold scope.
>
> **No operator prereq for Phase 6.2.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure template + CSS + view-model + route + tests authoring on top of the 6.1 Hava card grammar.
>
> **Operator decision-lock status:** the 10 prereq §3 decisions are locked at recommendation in brief §2 (read brief §2 entries 6 "Sort defaults per category" + entry 7 "District paragraph rendering" + entry 11 "Time-aware ranking" — all directly applicable to 6.2). If anything required operator confirmation during 6.1 implementation, brief §2 has been refreshed by Cowork primary review post-6.1 ship.
>
> **Author note:** authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution — saves the 2-3h re-author cycle between 6.1 close-out and 6.2 dispatch. SHA-patch slot at `fd16e7a` — fill once 6.1 commit lands on origin.
>
> **Clipboard pipeline** (after SHA patch; primes operator clipboard with prompt body only — skips the 22-line preamble + 34-line post-dispatch footer; verified offsets per fence positions at lines 22 + 277):
> ```powershell
> Get-Content outputs\cursor_dispatch_prompt_phase_6_2.md | Select-Object -Skip 22 | Select-Object -SkipLast 34 | Set-Clipboard
> ```

---

```
Read outputs/cursor_brief_phase_6_tier_1_ui.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3.2 (Phase 6.2
deliverable list -- first category landing template + Eat & Drink
proof), §2 (locked decisions; entries 6 + 7 + 11 + 8 + 12 are
6.2-relevant), §4 (what NOT to do), §5 (risk register).

Phase 6.1 SHIPPED on origin at `fd16e7a`
(unified Hava card grammar -- the per-card renderer 6.2 composes
into the page shell). Phase 4 SHIPPED chain unchanged
(`ac94b6c` Phase 4.4 close-out). Phase 5 prep chain unchanged
(`62ab3b7` types-mapping + `08bca69` prereq+brief). Pytest
baseline going in is **1813-1818** tests (1803 floor + 10-15
net-new from 6.1; verify per `python -m pytest --collect-only -q
| tail -3`). Alembic head is **0a1b2c3d4e5f** (Phase 4.1 outbox;
unchanged through Phase 5 prep + Phase 6.1; Phase 6 ships no
migration).

Ship Phase 6.2 ONLY per brief §3.2 -- new
app/templates/category_landing.html base template + new
app/api/routes/category_pages.py route module (GET
/category/<slug>) + new app/static/styles/category_landing.css
+ new app/static/js/category_filters.js (vanilla JS chip-filter
interactivity per prereq §4.5 Jinja2 + vanilla JS lock) + Eat &
Drink page as the proof + 10-15 new tests in
tests/test_phase6_category_landing.py. **No other category
pages, no map view, no boat-mode toggle, no homepage rebuild,
no profile extension, no district context paragraph wiring** --
all of that is 6.3-6.5.

NO OPERATOR DECISION-LOCK BLOCKER for 6.2. Most-relevant brief
§2 locks for 6.2:
- Sort defaults per category (brief §2 entry 6 / prereq §3.c) --
  Eat & Drink default sort: "Closest now" (Haversine from user
  location or city center for anonymous; heat-bias if >100°F)
- District chip rendering (brief §2 entry 7 / prereq §3.d) --
  district name as chip only, no placeholder paragraph
- Time-aware ranking (brief §2 entry 11 / prereq §3.h) --
  heat-bias threshold 100°F, +20% indoor / +10% shaded;
  implementation may defer to 6.3 (per brief §3.3 ranking
  scope), 6.2 ships the sort-dropdown UI but ranking math
  can land in 6.3 -- flag in §13 if 6.2 ships ranking math too
- Sponsor slot rendering (brief §2 entry 5 / prereq §3.b) --
  subtle pill + same shell; sponsor slot renders empty in 6.2
  (no paying sponsors; Phase 11 wires sponsor flow)
- Conditions strip stub (brief §2 entry 13) -- Phase 6.2 does
  NOT render the conditions strip on category pages; it's a
  homepage-only element per 6.5

ORDER MATTERS WITHIN PHASE 6.2:
1. First: read the docs + source files in brief §0 step 6+7,
   PLUS the 6.1 ship surface. Critical reads: brief §3.2
   end-to-end (the scope spec); brief §3.1 close-out (to know
   what 6.1 actually shipped + deviations Cursor flagged in
   §13); docs/maintainability/master_build_plan.md §4 Phase 6
   (Tier 1 category page deliverables + Eat & Drink chip set);
   app/templates/components/hava_card.html (6.1 partial 6.2
   includes per-card); app/providers/view_models.py (6.1
   HavaCardViewModel dataclass 6.2 consumes); 
   app/providers/queries.py (6.1 build_card_view_model helper
   6.2 calls in bulk for the result stream); app/search/routes.py
   (Phase 2B.3 /api/search; 6.2 reads from this internally via
   the category=<slug> filter); app/templates/home.html
   (existing homepage; the topbar + directory-search wrap are
   reused on category pages; sub-hero compact variant patterns
   live in home.css); app/static/js/search.js (Phase 2B.3 vanilla
   JS pattern for the directory-search; 6.2 mirrors this pattern
   for chip-filter interactivity).
2. Then: new app/api/routes/category_pages.py module. Route:
   GET /category/<slug:str>. Validates slug against the 6 Tier 1
   categories list (constant CATEGORY_SLUGS_TIER_1 = {"eat-drink",
   "on-the-water", "home-property-services", "health-wellness-care",
   "auto-rv-fuel", "shopping-essentials"} -- or wherever the
   existing canonical Tier 1 list lives; check app/db/categories.py
   or similar first; reuse, don't redefine). Returns 404 for
   unknown slugs. Reads from app/search internally OR composes a
   parallel server-rendered query (deviation-invited: pick
   whichever reads cleaner -- direct DB read may be simpler than
   round-tripping through /api/search). Page context includes:
   category_slug, category_label, sub_trade_chips (cuisine chips
   for eat-drink; trade chips for other categories), district_chips
   (10 districts from Phase 3.2 seed), operational_chips list, 
   sort_options list, sort_default ("closest_now" for eat-drink),
   organic_stream (list of HavaCardViewModel built per-entity via
   queries.build_card_view_model), editorial_footer_text (operator-
   authored short paragraph; pulled from a constant in the route
   module OR a category_editorial.json file -- deviation-invited).
3. Then: new app/templates/category_landing.html base template.
   ~200-350 lines. Renders the page shell consumed by all 6 Tier 1
   categories (6.3 reuses for the remaining 5). Sections in
   render order:
   - Topbar (reuse from home.html exact partial OR shared 
     _topbar.html include -- deviation-invited)
   - Directory search wrap (reuse from home.html as a compact 
     sub-hero variant; the sub-hero shape is search-bar + 
     category-title + brief one-line category description)
   - 3-row chip filter system:
     * Row 1: sub-trade chips (Eat & Drink: Mexican / BBQ / Pizza /
       Cafes / Bars / Bakery / Seafood / Brunch / -- pulled from
       a hardcoded list for 6.2; brief §3.2 acknowledges Phase 10
       may lock the source-of-truth for chips later)
     * Row 2: district chips (10 districts from Phase 3.2 seed)
     * Row 3: operational + time chips (Open now / Open past 9pm /
       Brunch / Dock-and-dine -- the boat_access cross-filter for
       on-the-water-adjacent eat-drink entries)
   - Sort dropdown (Closest now / Alphabetical / Top-rated /
     Editorial-pick -- default "Closest now")
   - Sponsor slot (empty render in 6.2; no paying sponsors yet)
   - Organic stream: `{% for vm in organic_stream %}{% include 
     'components/hava_card.html' with vm %}{% endfor %}`
   - Map view toggle button (stub in 6.2; map renders in 6.4)
   - Editorial footer (one-paragraph operator copy per category)
   - Empty-state copy when len(organic_stream) < 15: 
     "More <category_label> coming soon — Hava is still building
     this section. Check back this week!"
   **CRITICAL:** the template consumes ONLY the page context dict
   from the route. No DB calls inline in Jinja. No business logic 
   branching beyond simple boolean rendering.
4. Then: new app/static/styles/category_landing.css. ~150-200
   lines of CSS. Mobile-first: base styles for narrow viewports
   (chip rows scroll horizontally; sort dropdown stacks below 
   chips); media query at >=768px (chips wrap if they don't fit; 
   sort dropdown sits next to chips inline). Color variables 
   reuse from home.css palette (don't redefine). Chip styling 
   matches existing home.css `.chip` pattern with active-state
   for selected chips. Sub-hero compact variant: smaller hero 
   text + tighter directory-search padding vs home.html's hero
   version.
5. Then: new app/static/js/category_filters.js. ~100-150 lines
   of vanilla JS (NO frontend framework per prereq §4.5 lock).
   Implements: chip click toggles active state + updates URL 
   query params + re-fetches via /api/search OR triggers a 
   full-page reload to /category/<slug>?filter=<value> 
   (deviation-invited: pick whichever pattern reads cleaner with 
   existing app/static/js/search.js Phase 2B.3 shape; full-page 
   reload is simpler + works with no-JS users, but XHR + DOM 
   replace feels snappier on chip clicks). Sort dropdown change 
   triggers same flow. Boat-mode toggle from topbar (if Phase 6.2
   ships it -- defer to 6.4 per brief §3.4 scope; 6.2 leaves the
   toggle slot empty).
6. Then: 10-15 net-new tests in
   tests/test_phase6_category_landing.py:
     - GET /category/eat-drink renders 200 OK with mock entity 
       fixtures (or real Phase 5 data if available; tests should
       work either way -- use fixtures for determinism)
     - GET /category/<unknown-slug> returns 404
     - All 6 Tier 1 slugs render 200 OK with the same template
       (smoke test that the 6.3 reuse will hold)
     - Chip filter URL param parsing: /category/eat-drink?cuisine=
       mexican filters the organic_stream to mexican-tagged 
       entries
     - Sort dropdown URL param: /category/eat-drink?sort=
       alphabetical sorts the stream alphabetically
     - District chip filter: /category/eat-drink?district=
       <district_slug> filters by district_id matching the slug
     - Operational chip filter: /category/eat-drink?open=now
       filters to entries where is_open_now == True
     - Empty-state copy: when fixture has <15 entries, the
       "more coming soon" microcopy renders
     - Sponsor slot rendering: sponsor slot div renders even
       with no paying sponsors (the slot is there; just empty)
     - Editorial footer renders the category-specific paragraph
     - Mobile breakpoint smoke: CSS rules apply correctly at
       <768px (chip rows scrollable) vs >=768px (chip rows wrap)
     - Chip filter combinatorics: cuisine=mexican&district=
       <slug>&open=now applies all three filters
7. After all of the above: confirm full pytest stays green
   (1813-1818 floor + 10-15 net-new = 1823-1833), ruff clean. 
   Manual smoke deferred-to-operator: 
   `python -m fastapi run app.main:app` + browse to 
   /category/eat-drink; verify mobile responsive at 320px / 
   375px / 768px via DevTools; click chips + sort dropdown 
   to confirm interactivity.

POSTGRES COMPATIBILITY (carry-forward from brief §0):
- NO migration in Phase 6.2.
- Alembic head stays at 0a1b2c3d4e5f (Phase 4.1 outbox).
- /api/search consumption: if route reads from /api/search 
  internally, the existing FTS Postgres path applies; if route 
  composes a parallel direct-DB query, follow the existing 
  Postgres vs SQLite branching pattern in app/search/routes.py.

DEVIATION INVITATIONS (per brief §3.2):
- Server-side rendering vs hydration: brief assumes server-side 
  Jinja rendering with vanilla JS for chip interactivity; if you 
  find rendering via JSON + JS reads cleaner (chip filter 
  triggers /api/search?q=&category=eat-drink&filter=mexican then 
  re-renders), flag in §13 with rationale.
- Editorial footer text source: brief assumes hardcoded constant 
  in template; if you want a category_editorial.json 
  operator-maintainable file, flag in §13.
- Route module placement: brief suggests new 
  app/api/routes/category_pages.py; alternative extension of 
  app/home/routes.py acceptable if it groups more cohesively
  with home rendering.
- Topbar / directory-search reuse: brief assumes copy-paste from 
  home.html; alternative shared partial _topbar.html + 
  _directory_search.html include cleaner if existing patterns 
  support it.
- Chip data source: brief assumes hardcoded sub-trade lists per 
  category; alternative pull from Provider.attributes.sub_trades 
  aggregation acceptable (cleaner but adds a DB read).
- Ranking math placement: brief locks ranking math at Phase 6.3; 
  if you'd rather ship the math in 6.2 alongside the sort 
  dropdown UI, flag in §13 (still HALT at sub-phase boundary).

WHAT NOT TO DO (per brief §4 + §5):
- Don't ship remaining 5 category pages in 6.2. Phase 6.3.
- Don't ship map view in 6.2. Phase 6.4.
- Don't ship boat-mode toggle in 6.2. Phase 6.4.
- Don't ship homepage rebuild in 6.2. Phase 6.5.
- Don't ship profile extension in 6.2. Phase 6.5.
- Don't ship district context paragraph rendering in 6.2 
  (district chip on cards is OK -- that's 6.1 territory; 
  paragraph rendering on profile pages is 6.3).
- Don't ship seasonal hours rendering in 6.2. Phase 6.3.
- Don't add new schema migrations. None needed.
- Don't change /api/search response shape. Phase 6 reads via 
  /api/search but doesn't extend it.
- Don't add admin form for operator-curated field entry. Phase 
  6.5 LATE or V1.5.
- Don't add frontend framework. Stays on Jinja2 + vanilla JS per 
  prereq §4.5 lock.
- Don't add new Python dependencies. Page rendering uses 
  existing Jinja + FastAPI + SQLAlchemy.
- Don't bypass Phase 1D dual-write. Card-stream reads via 
  existing app/providers/queries.py helpers.
- Don't break 6.1 hava_card.html rendering. The {% include %}
  must work identically to 6.1's smoke tests.
- Don't dispatch Phase 6.3 in the same Cursor session. HALT at 
  the §3 Phase 6.2 boundary.

HALT at the §3 Phase 6.2 boundary. After 6.2 ships + commits + 
pushes, halt for operator re-dispatch in a fresh session for 
Phase 6.3 (remaining 5 Tier 1 category pages + district context 
paragraph rendering + time-aware ranking + seasonal hours).

Same constraints as Phase 6.1:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for 6.2

Pre-dispatch checklist (verify before paste):
- Phase 6.1 SHIPPED on origin (`fd16e7a`)
- Phase 4 SHIPPED chain (`ac94b6c`)
- Phase 5 prep chain (`62ab3b7` + `08bca69`)
- 0a1b2c3d4e5f is the current single alembic head on origin
- Pytest baseline going in is 1813-1818 (or matches reality 
  per `python -m pytest --collect-only -q | tail -3`)
- Brief §2 reflects any 6.1 §13 deviations (Cowork primary 
  patched after 6.1 ship if needed)
- Phase 5 chat (if running) is in a sub-phase that doesn't 
  touch app/templates/ or app/api/routes/ or 
  app/static/ -- verify per gotcha #18
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 6.1: paste back to the Cowork primary chat, primary reviews against §3.2 acceptance gates + brief §4 design rails, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:
- 1 new `app/api/routes/category_pages.py` (~100-150 lines)
- 1 new `app/templates/category_landing.html` (~200-350 lines)
- 1 new `app/static/styles/category_landing.css` (~150-200 lines)
- 1 new `app/static/js/category_filters.js` (~100-150 lines)
- 1 new test file `tests/test_phase6_category_landing.py` (~10-15 tests)
- Possibly small `app/providers/queries.py` additions (chip-list helpers for sub-trade aggregation; deviation-flagged)
- Possibly small `app/main.py` route mount (`app.include_router(category_pages.router)`)

Expected pytest delta: +10-15 net-new tests. Pre-existing Phase 6.1 + Phase 5 prep tests must remain green.

Expected effort: 4-6 days dispatch per brief §3.2; one or two Cursor sessions realistically.

Expected pragmatic deviations:
1. Server-side rendering vs hydration (whichever reads cleaner with existing search.js)
2. Editorial footer source (hardcoded vs JSON)
3. Route module placement (new file vs extend home/routes.py)
4. Topbar reuse pattern (copy-paste vs shared partial)
5. Chip data source (hardcoded vs aggregated from DB)
6. Ranking math placement (defer to 6.3 vs ship in 6.2)

## After Phase 6.2 ships

Update master plan §4 Phase 6 — append Phase 6.2 entry under "Shipped (incremental)" subsection (Cowork primary appends below the 6.1 entry). Update STATE.md Production block + Recently shipped §1 prepend with the 6.2 close-out narrative.

Phase 6.3 dispatch prompt to be authored after 6.2 ships — chains off whatever 6.2's HEAD SHA is; alembic head stays at `0a1b2c3d4e5f` (Phase 6 ships no migrations). 6.3 dispatch is gated on 6.2 close-out + operator design-review of the Eat & Drink page rendering (mobile + desktop).

---

*Authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution. Lives at `outputs/cursor_dispatch_prompt_phase_6_2.md`. Single SHA patch slot at `fd16e7a` — fill when 6.1 ships.*
