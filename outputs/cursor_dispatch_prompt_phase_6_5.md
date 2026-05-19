# Cursor Dispatch Prompt — Phase 6.5 (homepage rebuild + 8 themed group tiles + "What's on at this venue" region hook)

> Paste-into-Cursor prompt for the fifth Phase 6 sub-phase per master plan §4 Phase 6 + Phase 6.4 wrapper's "What NOT to do" exclusion list. Phase 6.5 ships (a) full homepage rebuild with hero + Ask Hava box + 8 themed group tiles for browse + "Today in Havasu" conditions strip (data hookup deferred to Phase 8 — the strip ships with stub data + honest staleness indicators wired to Phase 8's `external_conditions_cache` table that doesn't exist yet, returns empty/stub display until Phase 8), (b) "What's on at this venue" region on provider_profile pages — the Phase 9 events scraper hook; renders an empty region with placeholder copy until Phase 9 wires real event data. Phase 6.5 completes the Tier 1 UI surface for V1 launch readiness; Phase 6.6+ doesn't exist (Phase 7 chat + Phase 8 conditions + Phase 9 events are the next major lanes).
>
> **DISPATCH STATUS — READY TO PASTE (SHA-patched 2026-05-20 post-Phase-6.4-ship).** Phase 6.4 SHIPPED at `96c915d`. Post-6.4 alembic head is `f6a7b8c9d0e1` (NO new migration — 6.4 reused Phase 3.1 `users.preferred_mode`; see Phase 6.4 close-out + gotcha #18 recovery). **Phase 7 SHIPPED at `0a305e0`** — snowbird-panel coordination is LOCKED to preserve mode (see Phase 7 dependency note). Origin single alembic head as of patch time is `c9d0e1f2a3b4` (Phase 7 `users.last_active_at`; chains from `f6a7b8c9d0e1`). Phase 6.5 ships NO migration; verify `python -m alembic heads` returns ONE head before paste.
>
> **Gating dependencies:** All prior Phase 6 sub-phases SHIPPED — 6.1 (`fd16e7a`), 6.2 (`3948add`), 6.3 (`5ebee46`), 6.4 (`96c915d`). Phase 5 multi-phase data-population COMPLETE at Phase 5.11 close (`dcf3dd4`); STATE.md ledger at `3a2d895`. parks-rec-scrapes sidecar `f6a7b8c9d0e1` SHIPPED at `532d48b`. **Phase 7 SHIPPED at `0a305e0`** (chat + HALT 3 close-out + snowbird-return panel — HALT 3 flag-flip deferred to Phase 7.5). **Phase 6.5 consumes** the Hava card grammar (6.1) + category landing template (6.2) + breadth-pass categories + ranking + seasonal hours (6.3) + map view + boat-mode + 4 themed group landing pages + search bar (6.4) + snowbird panel anchor from Phase 7. Phase 6.5 is the closure of the Tier 1 UI lane.
>
> **Phase 7 dependency note (LOCKED — Phase 7 SHIPPED `0a305e0`):** Phase 7's `<!-- snowbird-panel-include -->` anchor + snowbird `{% include %}` line are already in `home.html`. 6.5's anchored extension MUST preserve both at their existing location. DO NOT touch any region inside the snowbird-panel anchor area. Read `home.html` shape before editing; verify snowbird panel intact in manual smoke + §13 report.
>
> **No operator prereq for Phase 6.5.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure template + route + helper authoring on top of 6.1+6.2+6.3+6.4. The conditions strip ships with stub data — no Phase 8 prereqs needed (AirNow / NWS / USGS wiring is Phase 8).
>
> **Operator decision-lock status:** the 4 Phase 6.5-relevant decisions to lock before paste:
>
> 1. **Conditions strip stub copy.** Phase 8 hooks AirNow + NWS + USGS to populate the strip with real data. Until Phase 8 ships, the strip needs SOMETHING to render. Three options:
>    - (a) **Honest empty:** strip renders "Conditions data coming soon" placeholder until Phase 8 (recommended; matches "no manufactured data" project principle)
>    - (b) **Static stub:** strip renders hardcoded "84°F, light breeze" stub values for the 6.5→Phase 8 gap window (NOT recommended — risks user confusion)
>    - (c) **Omit until Phase 8:** strip element doesn't render at all in 6.5; Phase 8 adds it (cleaner but means homepage looks different post-6.5 vs post-8)
>
> 2. **The 8 themed group tiles — content.** 4 are locked (Eat & Drink, Health & Fitness, On the Water, Home & Auto → /group/<slug> from 6.4). The other 4 need lock:
>    - Likely cuts: Events (/category/events), Outdoors/Parks/Trails (/category/outdoors-parks-trails), Lodging & VR (/category/lodging-vacation-rentals), Public/Civic Resources (/category/public-civic-resources)
>    - Alternative: include a "Things to Do" tile that links to a `/group/things-to-do/coming-soon` placeholder page until Phase 9 ships the actual Things to Do themed group landing
>    - Recommended (default): the 4 solo-category tiles above, no "Things to Do" placeholder
>
> 3. **"What's on at this venue" empty-state copy.** Phase 9 wires real event data into this region. Until then, recommended: render empty section with no placeholder copy at all (region simply absent when no events) OR render a single-line placeholder "Event schedule coming soon" tagline. Recommended (default): empty / absent.
>
> 4. **Homepage rebuild scope vs. 6.4's home.html anchored edit.** Phase 6.4 added a search bar at `<!-- search-bar-include -->` anchor. Phase 6.5's homepage rebuild MUST preserve this anchor + the search bar. Two patterns possible:
>    - (a) **Wholesale rewrite:** new home.html structure; explicitly re-add the search bar at the new hero location
>    - (b) **Anchored extension:** keep 6.4's home.html structure; add themed group tiles + conditions strip + (if Phase 7 already shipped) snowbird panel as additional sections below the existing hero
>    - Recommended: (b) — minimizes regression risk on 6.4's search bar wiring
>
> **Author note:** authored 2026-05-20 by Cowork primary; SHA-patched post-`96c915d` (Phase 6.4 ship) + post-`0a305e0` (Phase 7 ship). Clipboard offsets: Skip **46**, SkipLast **48** (recompute if this file changes).
>
> **Clipboard pipeline** (primes operator clipboard with prompt body only — skips preamble + post-prompt footer; offsets recomputed post-SHA-patch since authoring may have shifted line counts):
> ```powershell
> # Verify offsets after SHA-patch by counting fence positions:
> # python3 -c "import sys; lines = open('outputs/cursor_dispatch_prompt_phase_6_5.md').readlines(); fences = [i+1 for i, ln in enumerate(lines) if ln.strip() in ('```', '````')]; print('Fences at lines:', fences, 'Total:', len(lines))"
> # Then use Skip = first fence line; SkipLast = total - last fence + 1
> Get-Content outputs\cursor_dispatch_prompt_phase_6_5.md | Select-Object -Skip 46 | Select-Object -SkipLast 48 | Out-File -FilePath $env:TEMP\phase_6_5_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_6_5_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```

---

```
Read outputs/cursor_brief_phase_6_tier_1_ui.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3.5 (Phase 6.5
deliverable list -- homepage rebuild + venue events hook), §2 (locked
decisions), §4 (what NOT to do), §5 (risk register).

Phase 6.1 SHIPPED on origin at `fd16e7a` (unified Hava card grammar).
Phase 6.2 SHIPPED on origin at `3948add` (first category landing
template + Eat & Drink proof). Phase 6.3 SHIPPED on origin at
`5ebee46` (breadth pass to all 11 remaining Tier 1 slugs + district
chip + time/heat-aware ranking + seasonal hours). Phase 6.4 SHIPPED
on origin at `96c915d` (Leaflet+OSM map view + boat-
access mode + 4 themed group landing pages at /group/<slug> + search
bar in homepage hero + category page headers). Phase 5 multi-phase
data-population COMPLETE at 5.11 close. parks-rec-scrapes sidecar
shipped `532d48b`.

Pytest baseline going in is post-Phase-6.4 + post-Phase-7 -- verify
per `python -m pytest --collect-only -q | tail -3` BEFORE starting
work. Likely range 2140-2160 (~2150 at patch time). Post-6.4 alembic
head is `f6a7b8c9d0e1` (NO migration in 6.4 -- reused
`users.preferred_mode`). Origin single head as of patch is
`c9d0e1f2a3b4` (Phase 7 `users.last_active_at`, chains from
f6a7b8c9d0e1). Phase 6.5 ships NO migration. Verify per `python -m
alembic heads` (PLURAL) BEFORE starting -- must return ONE head.
REPORT THE OBSERVED VALUE (do NOT copy the dispatch-body-claimed
value -- session-2026-05-19 lesson #6). If multiple heads, HALT.

Ship Phase 6.5 ONLY per brief §3.5 -- (a) full homepage rebuild
with hero + Ask Hava box + 8 themed group tiles for browse +
"Today in Havasu" conditions strip (data hookup deferred to Phase
8 -- strip ships with empty/placeholder state until Phase 8 wires
external_conditions_cache); (b) "What's on at this venue" region
on provider_profile pages -- empty/placeholder hook that Phase 9
events scraper subsystem fills in. **No new map view, no boat-mode
UI changes** (Phase 6.4 shipped those). **No chat integration**
(Phase 7). **No real conditions data** (Phase 8). **No event
scraper or RRULE handling** (Phase 9). **No district paragraph
rendering** (V1.5).

OPERATOR DECISION-LOCK STATUS for 6.5 (recommended defaults; operator
may override at dispatch authoring time):

- Conditions strip stub state: **Honest empty placeholder**
  ("Conditions data coming soon -- Phase 8") OR Omit entirely
  until Phase 8 ships the strip. RECOMMENDED: honest empty
  placeholder, since the strip slot becomes the operator's visible
  anchor for the Phase 8 ship-line discussion.

- 8 themed group tiles content:
  - 4 themed-group tiles linking to /group/<slug> (6.4 routes):
    Eat & Drink + Health & Fitness + On the Water + Home & Auto
  - 4 solo-category tiles linking to /category/<slug>:
    Events (cat-2; /category/events)
    Outdoors/Parks/Trails (cat-7; /category/outdoors-parks-trails)
    Lodging & VR (cat-10; /category/lodging-vacation-rentals)
    Public/Civic Resources (cat-13; /category/public-civic-resources)
  - NOT included: Things to Do (Phase 9 ships this themed group
    landing page; do NOT pull forward to 6.5)
  - NOT included: Auto/RV/Fuel (rolled into Home & Auto themed group)
  - NOT included: Shopping/Essentials (no themed group; consider
    adding to Home & Auto OR keep absent from tile set; default
    absent)

- "What's on at this venue" empty state: **Region renders
  empty/absent when entity has no events tied to it**. NO
  placeholder copy. Phase 9 fills it in. RECOMMENDED.

- Homepage rebuild approach: **Anchored extension of 6.4's
  home.html** -- preserve 6.4's <!-- search-bar-include --> anchor
  + search bar in hero block; ADD themed group tiles section +
  conditions strip placeholder below the hero. Do NOT rewrite the
  hero block. RECOMMENDED.

- Phase 7 snowbird-panel coordination (LOCKED — Phase 7 SHIPPED
  `0a305e0`): PRESERVE the <!-- snowbird-panel-include --> anchor +
  the {% include %} line at their existing location in home.html.
  DO NOT touch any region inside the snowbird-panel anchor area.
  Verify by reading home.html shape before + after edit.

ORDER MATTERS WITHIN PHASE 6.5:

1. First: read the docs + source files in brief §0 step 6+7,
   PLUS 6.1 + 6.2 + 6.3 + 6.4 ship surfaces. Critical reads:
   brief §3.5 end-to-end (the scope spec); brief §3.4 close-out
   (to know what 6.4 actually shipped -- specifically the search
   bar + map toggle markup + boat-mode JS surface that 6.5 leaves
   alone); docs/maintainability/master_build_plan.md §4 Phase 6
   (full deliverable list); docs/maintainability/master_build_
   plan.md §4 Phase 9 ("What's on at this venue" hook -- Phase 9
   fills this in; 6.5 just ships the empty region); app/templates/
   home.html (current shape post-6.4; verify search bar location
   at <!-- search-bar-include --> anchor); app/templates/
   provider_profile.html (current shape post-6.3 + post-6.4 boat-
   access region; 6.5 adds events region anchored below the
   existing content); app/api/routes/category_pages.py (no
   changes needed in 6.5; reference for the chip dispatcher
   pattern); app/groups/themed_groups.py (6.4 module; 6.5 reads
   the THEMED_GROUPS dict to populate tile data).

2. Then: anchored edit on app/templates/home.html. Per the
   "anchored extension" approach: preserve 6.4's hero block +
   search bar; ADD a new "Browse" section with 8 themed group
   tiles below the hero; ADD a "Today in Havasu" conditions strip
   below the Browse section with the empty-placeholder content.
   Add <!-- conditions-strip-anchor --> + <!-- themed-tiles-
   anchor --> comments for future-phase reference (Phase 8 wires
   the conditions strip data).

3. Then: anchored edit on app/templates/provider_profile.html.
   Add a new "What's on at this venue" region below the existing
   profile content (after the boat-access region from 6.4 + the
   seasonal hours / district chip from 6.3). The region renders
   ONLY when entity.events relationship is non-empty (Phase 9
   wires this; until then, the conditional renders the region
   as absent). Anchor comment <!-- venue-events-region-anchor -->
   for Phase 9 reference.

4. Then: new template partial app/templates/components/
   themed_tile.html (~30-60 lines) reusable across the 8 tiles.
   Pure-Jinja partial; takes context vars {tile_title, tile_url,
   tile_hero_image_url, tile_subtitle, tile_count}. tile_count
   reads from app/groups/themed_groups.py helpers OR direct query
   helper (your call -- flag in §13).

5. Then: anchored edit on app/api/routes/home.py (or wherever
   the / route handler lives) to populate the 8 tile contexts.
   For the 4 themed-group tiles, count entities across the
   THEMED_GROUPS dict via app/groups/themed_groups.py helpers
   + cap displayed count for "200+ businesses" framing. For the
   4 solo-category tiles, count entities in the single category
   via EntityCategory join (same shape as 6.2 category_pages.py
   route). DO NOT change /api/search or any other route's
   response shape.

6. Then: new CSS in app/static/styles/components/themed_tile.css
   (~50-80 lines) + app/static/styles/components/conditions_
   strip.css (~30-50 lines). Mobile-first; both <768 stacked,
   >=768 grid. Import via @import at top of home.css.

7. Then: new tests across THREE files:

   - tests/test_phase6_homepage.py (8-12 tests): GET / returns
     200 + renders 8 themed group tiles in correct order;
     conditions strip placeholder renders; search bar from 6.4
     still renders at <!-- search-bar-include --> anchor;
     themed group tile counts match THEMED_GROUPS dict expansion;
     solo-category tile counts match Phase 5 entity counts;
     home page render is regression-safe vs 6.4's existing test
     coverage.

   - tests/test_phase6_venue_events_region.py (4-6 tests): GET
     /provider/<slug> renders venue-events-region-anchor comment;
     when entity has 0 events (current V1 state with no events
     scraper), the region renders absent (not visible to user);
     when entity DID have events (test fixture), region renders
     with placeholder; <!-- venue-events-region-anchor --> exists
     in template; profile page render is regression-safe vs 6.3 +
     6.4's existing test coverage.

   - anchored edit on tests/test_phase6_homepage.py OR existing
     home-page tests (whichever exists post-6.4): verify the
     post-6.5 home.html structure satisfies all prior assertions
     (search bar at hero anchor, etc).

8. After all of the above: confirm full pytest stays green
   (post-6.4 baseline + 12-18 net-new = ~2102-2128), ruff clean.
   Manual smoke deferred-to-operator:
   - `python -m fastapi run app.main:app` + browse to /
   - Verify 8 themed group tiles render in 2-col mobile / 4-col
     desktop layout
   - Click each tile, verify navigation to /group/<slug> for 4
     themed groups + /category/<slug> for 4 solo categories
   - Verify conditions strip placeholder renders below tile
     section
   - Verify search bar from 6.4 still renders in hero
   - Browse to a provider profile, verify venue-events-region
     anchor exists but renders absent (entity has 0 events)
   - If Phase 7 has shipped: verify snowbird-panel anchor +
     include line both intact

POSTGRES COMPATIBILITY (carry-forward from brief §0):

- NO migration in Phase 6.5. Do not advance alembic head. Observed
  single head may be `c9d0e1f2a3b4` (Phase 7 shipped) or
  `f6a7b8c9d0e1` (if Phase 7 not on your branch) — both OK if
  `alembic heads` returns exactly one.
- No new schema. No column additions. Pure template + route +
  static-asset authoring.

DEVIATION INVITATIONS (per brief §3.5):

- Themed tile partial shape: brief assumes single shared
  app/templates/components/themed_tile.html; if 8 separate
  templates read cleaner, flag.
- Tile count source: brief assumes app/groups/themed_groups.py
  helpers + direct EntityCategory count; if a different counting
  strategy reads cleaner, flag.
- Conditions strip placeholder copy: brief assumes "Conditions
  data coming soon -- Phase 8"; if a different copy reads better,
  flag.
- "What's on at this venue" empty state: brief assumes region
  renders absent; if rendering a single-line "Event schedule
  coming soon" tagline reads better, flag.
- Homepage section ordering: brief assumes hero (with search bar
  preserved) -> themed tiles -> conditions strip -> snowbird
  panel (if Phase 7 shipped); if a different ordering reads
  better (e.g., conditions strip directly below hero), flag.
- Tile layout: brief assumes 2-col mobile / 4-col desktop grid;
  if 1-col mobile / 2-col tablet / 4-col desktop reads cleaner,
  flag.
- Mobile vs desktop tile content shape: brief assumes same tile
  partial renders both; if mobile needs a stripped-down variant,
  flag.

WHAT NOT TO DO (per brief §4 + §5):

- Don't ship real conditions data for the strip. Phase 8.
- Don't ship event data for the "What's on at this venue"
  region. Phase 9.
- Don't ship the Things to Do themed group landing page or
  tile. Phase 9.
- Don't rebuild the existing hero block. Anchored extension
  preserves 6.4's search bar at <!-- search-bar-include -->.
- Don't touch 6.4's map view, boat-mode JS, themed group routes,
  or search bar. Phase 6.5 builds ON TOP of these surfaces,
  not modifies them.
- Don't touch Phase 7's snowbird-panel-include anchor if Phase 7
  has shipped. If Phase 7 has NOT shipped, may proactively
  reserve the anchor comment but no include line.
- Don't change /api/search response shape (Phase 2B.3 lock).
- Don't break /category/<slug> or /provider/<slug> existing
  test coverage.
- Don't break /group/<slug> existing test coverage from 6.4.
- Don't add new Python dependencies.
- Don't add a frontend framework. Vanilla JS + Jinja2 per
  prereq §4.5.
- Don't bash heredoc commit messages. PowerShell-safe multiple
  -m flags or here-string per session-2026-05-19 lesson #1.
- Don't hardcode alembic head literals in test code (session-
  2026-05-19 lesson #4). Use script.get_current_head() + dynamic
  capture.
- Don't dispatch Phase 7 or Phase 8 in the same Cursor session.
  HALT at the §3 Phase 6.5 boundary.

HALT at the §3 Phase 6.5 boundary. After 6.5 ships + commits +
pushes, halt for operator re-dispatch in a fresh session for
Phase 8 (conditions data + alerts), Phase 9 (events + Things to
Do themed group), or Phase 7.5 (HALT 3 flag-flip polish).

Same constraints as Phase 6.1 + 6.2 + 6.3 + 6.4:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for 6.5
- Re-verify `python -m alembic heads` (plural) and report the
  observed value (do NOT copy the dispatch-body-claimed value --
  session-2026-05-19 lesson #6). If multiple heads returned,
  HALT. If single head is `c9d0e1f2a3b4` or `f6a7b8c9d0e1`,
  proceed (6.5 must not author a migration).

Pre-dispatch checklist (verify before paste):

- Phase 6.1 SHIPPED on origin (`fd16e7a`)
- Phase 6.2 SHIPPED on origin (`3948add`)
- Phase 6.3 SHIPPED on origin (`5ebee46`)
- Phase 6.4 SHIPPED on origin (`96c915d`)
- Phase 7 SHIPPED on origin (`0a305e0`) — snowbird panel LOCKED
- Sidecar migration SHIPPED on origin (`532d48b`)
- Phase 5 ledger SHIPPED on origin (`3a2d895`)
- `python -m alembic heads` returns a SINGLE head (`c9d0e1f2a3b4`
  expected on origin post-Phase-7; `f6a7b8c9d0e1` if 7 not on branch)
- Pytest baseline going in matches reality per `python -m
  pytest --collect-only -q | tail -3` (likely 2140-2160)
- Brief §2 reflects any 6.1 + 6.2 + 6.3 + 6.4 §13 deviations
  (Cowork primary patched after ships if needed)
- The 4 operator decisions are locked: conditions strip stub
  state, 8 tile cuts (4 themed + 4 solo), venue-events empty
  state, homepage rebuild approach (anchored extension)
```

---

## After Cursor returns with the §12 report

Same rhythm as 6.1 + 6.2 + 6.3 + 6.4: paste back to Cowork primary chat, primary reviews against §3.5 acceptance gates + brief §4 design rails, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 0 new alembic migrations
- 1 new `app/templates/components/themed_tile.html` (~30-60 lines)
- 1 new `app/static/styles/components/themed_tile.css` (~50-80 lines)
- 1 new `app/static/styles/components/conditions_strip.css` (~30-50 lines)
- 1 modified `app/templates/home.html` (anchored extension; +~80-120 lines for tile section + conditions strip placeholder)
- 1 modified `app/templates/provider_profile.html` (anchored edit; +~15-30 lines for venue-events-region-anchor + conditional)
- 1 modified `app/api/routes/home.py` (or wherever / route lives; anchored edit; +~30-60 lines for tile context population)
- 1 modified `app/static/styles/home.css` (anchored edit; +~2 lines `@import` for 2 new CSS files)
- 2 new test files:
  - `tests/test_phase6_homepage.py` (~8-12 tests)
  - `tests/test_phase6_venue_events_region.py` (~4-6 tests)
- 1 modified `tests/test_phase6_*.py` for the existing home-page test file (anchored edit; +~3-5 regression-guard tests preserving 6.4's assertions)

Expected pytest delta: +12-18 net-new tests. Pre-existing Phase 6.1 + 6.2 + 6.3 + 6.4 + Phase 5 prep tests must remain green.

Expected effort: 3-5 days dispatch (smaller scope than 6.4 since no new alembic migration + no new routing surfaces beyond home page extensions). Single Cursor session is realistic.

Expected pragmatic deviations:

1. Themed tile partial shape (single shared vs 8 separate)
2. Tile count source (themed_groups.py helpers vs direct EntityCategory count)
3. Conditions strip placeholder copy
4. Venue events empty-state rendering shape
5. Homepage section ordering
6. Tile layout (2-col mobile / 4-col desktop vs alternatives)

## After Phase 6.5 ships

Update master plan §4 Phase 6 — append Phase 6.5 entry under "Shipped (incremental)" subsection. Update STATE.md Production block + Recently shipped §1 prepend.

Phase 6 lane COMPLETE post-6.5. Next major lanes:
- Phase 7.5 — HALT 3 validator triage + flag-flip closure (Phase 7 shipped with flag deferred)
- Phase 8 — conditions panel wires real data into the 6.5 strip placeholder + alerts subsystem + cat-13 expansion
- Phase 9 — events scraper subsystem fills in 6.5's "What's on at this venue" region + Things to Do themed group landing

---

*Authored by Cowork primary (2026-05-20). SHA-patched post-`96c915d` + post-`0a305e0`. Lives at `outputs/cursor_dispatch_prompt_phase_6_5.md`. Clipboard: Skip 46, SkipLast 48. Phase 6.4 actual ship matched wrapper except NO alembic migration (preferred_mode reuse per close-out).*
