# Cursor Dispatch Prompt — Phase 6.3 (remaining 5 category pages + district context + time-aware ranking + seasonal hours)

> Paste-into-Cursor prompt for the third Phase 6 sub-phase per master plan §4 Phase 6 + brief §3.3 — applies 6.2's `category_landing.html` template to the remaining 5 Tier 1 categories (On the Water, Home & Property Services, Health & Wellness, Auto/RV/Fuel, Shopping & Essentials), adds district-context chip rendering on profile pages, ships time-aware + heat-aware default ranking logic, and wires seasonal hours rendering on profile pages. Phase 6.3 is the **breadth pass** for Tier 1 categories — 6.2 proves the template with Eat & Drink; 6.3 makes all 6 categories live. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_6_tier_1_ui.md` (read end-to-end, especially §0 + §3.3 + §2 + §4 + §5).
>
> **Gating dependencies:** Phase 6.1 SHIPPED on origin at `<<<PATCH_PHASE_6_1_SHA_HERE>>>` (unified Hava card grammar). Phase 6.2 SHIPPED on origin at `<<<PATCH_PHASE_6_2_SHA_HERE>>>` (first category landing template + Eat & Drink proof). Phase 4 + Phase 5 prep on origin chain unchanged (`ac94b6c` + `62ab3b7` + `08bca69`). **Phase 6.3 consumes 6.2's `app/templates/category_landing.html` template** + the `app/api/routes/category_pages.py` route module — extends both without rewriting. Any deviations Cursor reported in 6.2 §13 are locked-as-shipped by the time 6.3 dispatches.
>
> **Parallel-with-Phase-5 caveat:** if a Phase 5 Cowork chat + Phase 5 Cursor session are running concurrently, the file-scope disjointness rule (gotcha #18) applies. Phase 6.3 touches: `app/templates/category_landing.html` (anchored edit — adds per-category chip sets), `app/templates/provider_profile.html` (anchored edit — district context chip insertion + seasonal hours region), `app/api/routes/category_pages.py` (anchored edit — adds chip dispatcher for remaining 5 slugs), new `app/core/ranking.py` (heat-bias + time-aware ranking helper), anchored edit on `app/providers/queries.py` (seasonal hours fallback logic), `app/providers/view_models.py` (anchored edit — appends seasonal-hours fields to ProviderProfileVM), new `tests/test_phase6_ranking.py`, new `tests/test_phase6_seasonal_hours.py`, anchored edit on `tests/test_phase6_category_landing.py` (adds per-category coverage). Phase 5 sessions touch `app/contrib/` + `scripts/` + `app/db/`. Zero overlap if both lanes hold scope.
>
> **No operator prereq for Phase 6.3.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure template + route + helper + tests authoring on top of 6.1 + 6.2.
>
> **Operator decision-lock status:** the 10 prereq §3 decisions are locked at recommendation in brief §2. Most-relevant to 6.3: entry 6 "Sort defaults per category" (prereq §3.c — per-category locked), entry 7 "District paragraph rendering" (prereq §3.d — chip-only graceful fallback), entry 11 "Time-aware ranking" (prereq §3.h — heat-bias at 100°F + 20% indoor / 10% shaded). Brief §2 should already reflect any 6.1/6.2 §13 deviation patches.
>
> **Author note:** authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution — saves the 2-3h re-author cycle between 6.2 close-out and 6.3 dispatch. Two SHA-patch slots: `<<<PATCH_PHASE_6_1_SHA_HERE>>>` + `<<<PATCH_PHASE_6_2_SHA_HERE>>>`. Fill both before paste; each appears in 3 sites (preamble, dispatch body, pre-dispatch checklist).
>
> **Clipboard pipeline** (after both SHAs patched; primes operator clipboard with prompt body only — skips the 22-line preamble + 37-line post-dispatch footer; verified offsets per fence positions at lines 22 + 318):
> ```powershell
> Get-Content outputs\cursor_dispatch_prompt_phase_6_3.md | Select-Object -Skip 22 | Select-Object -SkipLast 37 | Set-Clipboard
> ```

---

```
Read outputs/cursor_brief_phase_6_tier_1_ui.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3.3 (Phase 6.3
deliverable list -- remaining 5 categories + district + ranking
+ seasonal hours), §2 (locked decisions; entries 3 + 6 + 7 + 11
are 6.3-relevant), §4 (what NOT to do), §5 (risk register).

Phase 6.1 SHIPPED on origin at `<<<PATCH_PHASE_6_1_SHA_HERE>>>`
(unified Hava card grammar). Phase 6.2 SHIPPED on origin at
`<<<PATCH_PHASE_6_2_SHA_HERE>>>` (first category landing template
+ Eat & Drink proof). Phase 4 SHIPPED chain unchanged
(`ac94b6c` Phase 4.4 close-out). Phase 5 prep chain unchanged
(`62ab3b7` types-mapping + `08bca69` prereq+brief). Pytest
baseline going in is **~1823-1838** tests (1803 floor + 10-15
from 6.1 + 10-15 from 6.2; verify per `python -m pytest
--collect-only -q | tail -3`). Alembic head is **0a1b2c3d4e5f**
(Phase 4.1 outbox; unchanged through Phase 5 prep + Phase 6.1
+ Phase 6.2; Phase 6 ships no migration).

Ship Phase 6.3 ONLY per brief §3.3 -- (a) apply 6.2's
category_landing.html template to the remaining 5 Tier 1 slugs
(on-the-water, home-property-services, health-wellness-care,
auto-rv-fuel, shopping-essentials) with per-category chip
customizations; (b) wire district context chip rendering on
provider_profile.html (single SQL join entities → districts;
graceful chip-only display per prereq §3.d -- no paragraph 
placeholder, no TODO ribbon); (c) ship time-aware + heat-aware
default ranking logic in new app/core/ranking.py
(compute_card_rank helper); (d) wire seasonal hours rendering 
on profile pages (reads entities.seasonal_hours JSON; falls 
back to Provider.hours for venues without seasonal hours; 
tested across 4 calendar-window scenarios). **No map view, no
boat-mode toggle, no themed group landing pages, no homepage
rebuild, no profile extension for events region** -- all of
that is 6.4-6.5.

NO OPERATOR DECISION-LOCK BLOCKER for 6.3. Most-relevant brief
§2 locks for 6.3:
- Sort defaults per category (brief §2 entry 6 / prereq §3.c):
  - on-the-water: "Closest + boat-access populated"
  - home-property-services: "Verified first" (AZ ROC matters)
  - health-wellness-care: "Closest + NPI-verified first"
  - auto-rv-fuel: "Closest + mobile-service variant"
  - shopping-essentials: "Closest + open-now"
- District chip rendering (brief §2 entry 7 / prereq §3.d) --
  chip-only graceful fallback. NO placeholder paragraph copy.
  NO TODO ribbon. If District.paragraph IS NULL (always in V1
  per path-b lock), render district as breadcrumb chip on
  profile pages -- nothing more.
- Time-aware ranking (brief §2 entry 11 / prereq §3.h):
  - Server clock (America/Phoenix via existing 
    LAKE_HAVASU_TZ in app/core/timezone.py)
  - Heat bias kicks in at >100°F (tunable constant
    HEAT_BIAS_THRESHOLD_F)
  - +20% rank boost for heat_exposure='indoor'
    (HEAT_BIAS_INDOOR_WEIGHT)
  - +10% rank boost for heat_exposure='shaded'
    (HEAT_BIAS_SHADED_WEIGHT)
  - Sort-stable within rank buckets (ties break on alphabetical
    name)
- Conditions data source (brief §2 entry 13 -- DO NOT WIRE):
  heat-bias kicks in based on a STUB temperature constant
  ("current temperature is hardcoded to 105°F for testing the
  bias path") because real conditions data is Phase 8. The
  ranking math is fully testable; the upstream temperature
  source is the stub.

ORDER MATTERS WITHIN PHASE 6.3:
1. First: read the docs + source files in brief §0 step 6+7,
   PLUS 6.1 + 6.2 ship surfaces. Critical reads: brief §3.3
   end-to-end (the scope spec); brief §3.2 close-out (to know
   what 6.2 actually shipped -- specifically the chip dispatcher
   shape + the route's organic_stream construction pattern);
   docs/maintainability/master_build_plan.md §4 Phase 6
   (Tier 1 category page deliverables); 
   app/templates/category_landing.html (6.2 template to extend);
   app/api/routes/category_pages.py (6.2 route to extend);
   app/templates/provider_profile.html (profile page to extend
   with district chip + seasonal hours region; ~existing line
   count check via wc -l for anchored-edit safety);
   app/providers/view_models.py (existing ProviderProfileVM 
   shape; 6.3 appends seasonal_hours fields);
   app/providers/queries.py (existing helpers including 
   effective_hours_structured + is_open_now; 6.3 adds 
   seasonal hours fallback);
   app/db/models.py (Entity.seasonal_hours JSON column shape +
   District relationship + Phase 1A SeasonalHours extension 
   table relationship `seasonal_hour_rows` -- both coexist 
   per Phase 3.1 documented deviation; reads default to JSON 
   for V1);
   app/core/timezone.py (LAKE_HAVASU_TZ + now_lake_havasu);
   docs/operations/boat_access_rubric.md (informs the boat-
   access JSON shape but 6.3 does NOT consume this -- 6.4 
   does; reading just to know what shape NOT to break).
2. Then: new app/core/ranking.py. ~80-150 lines.
   compute_card_rank(entity_or_provider, *, now=None, 
   temperature_f=None) -> float helper. Base rank from 
   Haversine distance (lower distance = higher rank);
   heat bias if temperature_f > HEAT_BIAS_THRESHOLD_F 
   (default 100.0): +HEAT_BIAS_INDOOR_WEIGHT (0.20) for
   heat_exposure='indoor', +HEAT_BIAS_SHADED_WEIGHT (0.10) 
   for heat_exposure='shaded', 0 otherwise; verified-first 
   boost for entities with verified=True (configurable
   per-category via call-site weight); open-now boost for 
   entities currently within hours (call-site weight). 
   Returns float ranking score; caller sorts descending. 
   Pure-function -- NO DB reads inline, NO ORM imports at 
   module top (gotcha-#17 discipline).
3. Then: anchored edit on app/api/routes/category_pages.py.
   Imports compute_card_rank from app.core.ranking; wires
   into the organic_stream construction so the per-category 
   default sort uses heat-bias ranking when sort=closest_now
   (the Eat & Drink default; other categories use their 
   per-category default per brief §2 entry 6 -- table above).
   Per-category chip-set dispatcher: dict mapping slug -> 
   {sub_trade_chips, district_chips, operational_chips, 
   sort_default, sort_options}. For Cursor's reference, the
   chip sets to ship in 6.3:
   - on-the-water: sub-trade ["Marinas", "Boat rentals", 
     "Lake tours", "Watersports", "Fishing charters", 
     "Beaches", "Launches"]; operational ["Open now", 
     "Boat-friendly", "Family-friendly", "Free", "Paid"]
   - home-property-services: sub-trade ["Plumber", 
     "Electrician", "HVAC", "Handyman", "Landscaper",
     "Pool service", "Cleaning", "Pest control", 
     "Roofer", "Garage door"]; operational ["Open now",
     "Verified", "Mobile-service", "Emergency 24h"]
   - health-wellness-care: sub-trade ["Doctor", "Dentist",
     "Urgent care", "Pharmacy", "Vet", "Gym", "Yoga", 
     "Massage", "Chiropractor", "Mental health"]; 
     operational ["Open now", "NPI-verified", "Accepting
     new patients", "Insurance accepted"]
   - auto-rv-fuel: sub-trade ["Auto repair", "Tire shop",
     "RV repair", "RV park", "Gas station", "Car wash",
     "Detailing", "Mobile mechanic"]; operational 
     ["Open now", "Mobile-service", "Tow available", 
     "RV-friendly"]
   - shopping-essentials: sub-trade ["Grocery", "Pharmacy",
     "Hardware", "Sporting goods", "Pet supplies", 
     "Clothing", "Department store", "Liquor", "Bakery", 
     "Specialty"]; operational ["Open now", "Open past 
     9pm", "Drive-through", "Curbside pickup"]
   (Brief §3.3 acknowledges Phase 10 may lock chip 
   source-of-truth elsewhere; 6.3 ships hardcoded per 
   category.)
4. Then: anchored edit on app/templates/provider_profile.html.
   Add district context chip rendering -- single chip 
   showing district.name when entity.district_id IS NOT 
   NULL; chip is ALSO a link to /district/<slug> in 
   anticipation of Phase 7 (Phase 7 ships the district 
   landing page -- 6.3 just makes the chip a link; the 
   target route will 404 until Phase 7, that's OK -- the
   master plan acknowledges this hook). Add seasonal hours
   region: when entity.seasonal_hours JSON is non-null, 
   render the active season's hours by current date (using 
   the JSON shape per existing seed data + brief §3.3 
   acceptance gate #5 "render correctly across calendar
   windows"); falls back to existing Provider.hours_freetext 
   when seasonal_hours is null. **CRITICAL: anchored edit -- 
   add the chip + region; do NOT rewrite the rest of the 
   template.** Verify line count delta is reasonable 
   (~30-60 lines added; existing template ~XXX lines).
5. Then: anchored edit on app/providers/view_models.py.
   Append to ProviderProfileVM fields: 
   district_chip_url (Optional[str]) + 
   seasonal_hours_active_season (Optional[str]) + 
   seasonal_hours_active_rows (list[dict] or None) + 
   season_status_copy (Optional[str] -- e.g., "Winter hours
   (Nov 1 - Apr 30)"). build() function populates these 
   from entity.seasonal_hours JSON + entity.district 
   relationship.
6. Then: anchored edit on app/providers/queries.py. Append
   new helper effective_seasonal_hours(entity, now=None) 
   -> tuple[active_season_name | None, active_rows | None, 
   season_status_copy | None]. Logic: if entity.seasonal_hours
   JSON is null OR not a dict, return (None, None, None) -- 
   caller falls back to effective_hours_structured + hours
   freetext; if active season matches current date, return 
   (season_name, season_rows, season_status_copy). 4 calendar-
   window scenarios per brief §3.3 acceptance gate #5:
   summer (Jun 1 - Sep 30), fall (Oct 1 - Oct 31), winter 
   (Nov 1 - Apr 30), spring (May 1 - May 31). Pure-function
   -- exact season boundary thresholds tunable as module 
   constants.
7. Then: new tests across THREE files:
   - tests/test_phase6_ranking.py (8-12 tests):
     compute_card_rank base distance ranking; heat-bias 
     fires at temperature_f > 100; +20% indoor; +10% shaded;
     no bias for outdoor/water_adjacent/null heat_exposure; 
     sort-stable within rank buckets (alphabetical fallback);
     heat-bias does NOT fire at temperature_f = 100 (strict 
     >); verified-first boost integrates cleanly; open-now 
     boost integrates cleanly; ranking math reproducible 
     (same input → same output)
   - tests/test_phase6_seasonal_hours.py (6-10 tests):
     effective_seasonal_hours returns (None, None, None) 
     for null seasonal_hours JSON; same for non-dict shape;
     winter season active 2026-01-15 returns winter rows + 
     "Winter hours" copy; summer season active 2026-07-15;
     fall season active 2026-10-15; spring season active 
     2026-05-15 (edge of winter→spring transition); 
     seasonal hours fallback to Provider.hours_freetext 
     verified in ProviderProfileVM.build()
   - anchored edit on tests/test_phase6_category_landing.py
     (+5-8 tests): GET /category/on-the-water 200 OK with
     fixture; same for home-property-services, 
     health-wellness-care, auto-rv-fuel, shopping-essentials; 
     each category's chip dispatcher produces correct 
     sub_trade_chips list; sort_default per category matches
     brief §2 entry 6 lock; district chip on profile page 
     renders when entity.district_id IS NOT NULL; district 
     chip omits cleanly when district_id IS NULL
8. After all of the above: confirm full pytest stays green 
   (1823-1838 floor + 19-30 net-new = 1842-1868), ruff
   clean. Manual smoke deferred-to-operator:
   - `python -m fastapi run app.main:app` + browse to 
     /category/on-the-water, /category/home-property-services,
     /category/health-wellness-care, /category/auto-rv-fuel, 
     /category/shopping-essentials -- verify each renders
   - Browse to /provider/<slug-with-district> -- verify
     district chip appears
   - Browse to /provider/<slug-with-seasonal-hours> -- 
     verify active-season rendering matches current date

POSTGRES COMPATIBILITY (carry-forward from brief §0):
- NO migration in Phase 6.3.
- Alembic head stays at 0a1b2c3d4e5f.
- entity.seasonal_hours JSON column already exists from 
  Phase 3.1; no schema change needed.

DEVIATION INVITATIONS (per brief §3.3):
- Heat-bias threshold: brief locks 100°F; if local data 
  suggests 95°F is the practical threshold for shoulder-month 
  discomfort, flag in §13.
- Heat-bias weights: brief locks +20% indoor / +10% shaded;
  if testing reveals these need tuning, flag in §13.
- Ranking math placement: brief locks app/core/ranking.py;
  alternative app/search/ranking.py extension acceptable
  (existing search ranking lives there).
- Seasonal hours fallback shape: brief assumes 
  "if seasonal_hours empty/null then Provider.hours"; if
  you want a separate fallback config (e.g., entity attribute
  override), flag in §13.
- Season boundary dates: brief uses Jun-Sep summer / Oct 
  fall / Nov-Apr winter / May spring per Lake Havasu seasonal
  reality; if data suggests different boundaries, flag.
- District chip → /district/<slug> link: brief specifies link
  even though Phase 7 ships the target; if you'd rather omit
  the link and just render as static chip until Phase 7, flag.
- Time-of-day default sort math: brief assumes 
  Haversine + time-decay; if more sophisticated ranking reads
  cleaner, flag.

WHAT NOT TO DO (per brief §4 + §5):
- Don't ship map view in 6.3. Phase 6.4.
- Don't ship boat-mode toggle in 6.3. Phase 6.4.
- Don't ship themed group landing pages in 6.3. Phase 6.4.
- Don't ship homepage rebuild in 6.3. Phase 6.5.
- Don't ship "What's on at this venue" region on profile. 
  Phase 6.5.
- Don't ship district paragraph rendering. V1.5.
- Don't ship real conditions data for heat-bias. Phase 8 
  wires AirNow + NWS + USGS. 6.3 uses a STUB temperature
  constant for testing.
- Don't add new schema migrations. None needed.
- Don't change /api/search response shape.
- Don't break /provider/<slug> existing test coverage.
- Don't add new Python dependencies.
- Don't add frontend framework. Vanilla JS + Jinja2 per 
  prereq §4.5.
- Don't dispatch Phase 6.4 in the same Cursor session. 
  HALT at the §3 Phase 6.3 boundary.

HALT at the §3 Phase 6.3 boundary. After 6.3 ships + commits 
+ pushes, halt for operator re-dispatch in a fresh session 
for Phase 6.4 (map view + boat-mode + themed groups).

Same constraints as Phase 6.1 + 6.2:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for 6.3

Pre-dispatch checklist (verify before paste):
- Phase 6.1 SHIPPED on origin (`<<<PATCH_PHASE_6_1_SHA_HERE>>>`)
- Phase 6.2 SHIPPED on origin (`<<<PATCH_PHASE_6_2_SHA_HERE>>>`)
- Phase 4 SHIPPED chain (`ac94b6c`)
- Phase 5 prep chain (`62ab3b7` + `08bca69`)
- 0a1b2c3d4e5f is the current single alembic head on origin
- Pytest baseline going in is ~1823-1838 (or matches reality 
  per `python -m pytest --collect-only -q | tail -3`)
- Brief §2 reflects any 6.1 + 6.2 §13 deviations (Cowork 
  primary patched after ships if needed)
- Phase 5 chat (if running) is in a sub-phase that doesn't 
  touch app/templates/ or app/api/routes/ or app/core/ranking.py
  or app/providers/ -- verify per gotcha #18
```

---

## After Cursor returns with the §12 report

Same rhythm as 6.1 + 6.2: paste back to Cowork primary chat, primary reviews against §3.3 acceptance gates + brief §4 design rails, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:
- 1 new `app/core/ranking.py` (~80-150 lines)
- 1 modified `app/api/routes/category_pages.py` (anchored edit; +~80-120 lines for chip dispatcher + ranking integration)
- 1 modified `app/templates/provider_profile.html` (anchored edit; +~30-60 lines for district chip + seasonal hours region)
- 1 modified `app/providers/view_models.py` (anchored edit; +~20-40 lines for new VM fields)
- 1 modified `app/providers/queries.py` (anchored edit; +~30-50 lines for effective_seasonal_hours helper)
- 1 new `tests/test_phase6_ranking.py` (~8-12 tests)
- 1 new `tests/test_phase6_seasonal_hours.py` (~6-10 tests)
- 1 modified `tests/test_phase6_category_landing.py` (anchored edit; +~5-8 tests)
- 0 changes to `app/main.py` (no new route mounts in 6.3 — `category_pages_router` already mounted in 6.2)

Expected pytest delta: +19-30 net-new tests. Pre-existing Phase 6.1 + 6.2 + Phase 5 prep tests must remain green.

Expected effort: 5-8 days dispatch per brief §3.3; two to three Cursor sessions realistically (one for ranking + category chips; one for district chip + seasonal hours + view-model wiring; possibly third for test expansion).

Expected pragmatic deviations:
1. Heat-bias threshold (100°F vs 95°F)
2. Heat-bias weights (20%/10% tuning)
3. Ranking math placement (app/core/ranking.py vs app/search/ranking.py extension)
4. Seasonal hours fallback shape
5. Season boundary dates (4-season Lake Havasu calendar)
6. District chip → /district/<slug> link vs static chip until Phase 7
7. Time-of-day sort math sophistication

## After Phase 6.3 ships

Update master plan §4 Phase 6 — append Phase 6.3 entry under "Shipped (incremental)" subsection (Cowork primary appends below the 6.2 entry). Update STATE.md Production block + Recently shipped §1 prepend with the 6.3 close-out narrative.

Phase 6.4 dispatch prompt to be authored after 6.3 ships — chains off whatever 6.3's HEAD SHA is; alembic head stays at `0a1b2c3d4e5f`. 6.4 dispatch is gated on 6.3 close-out + operator design-review of all 6 Tier 1 category pages rendering + profile pages with district chip + seasonal hours.

---

*Authored at session-23-extension-3 (2026-05-13) pre-positioned during Phase 6.1 in-flight execution. Lives at `outputs/cursor_dispatch_prompt_phase_6_3.md`. Two SHA-patch slots: `<<<PATCH_PHASE_6_1_SHA_HERE>>>` + `<<<PATCH_PHASE_6_2_SHA_HERE>>>` — fill both before paste.*
