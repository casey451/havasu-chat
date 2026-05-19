# Cursor Dispatch Prompt — Phase 7 (chat ENTITY wiring + boat-mode + conditions awareness + HALT 3 close-out + cross-entity + snowbird-return view)

> Paste-into-Cursor prompt for Phase 7 per master plan §4 Phase 7 (refreshed 2026-05-19 at `c1d9ed2`) + `outputs/phase7_handoff_note.md` (refreshed 2026-05-19) — ships (a) chat tier 2 / tier 3 wired to query the ENTITY table (replacing pre-pivot River Scene events catalog query at `app/chat/tier2_db_query.py:33+`), (b) chat awareness of boat-access mode (queries filter by `boat_access IS NOT NULL` when active; tier 3 LLM prompt gets a "user is in boat mode" preamble), (c) chat awareness of conditions (heat-bias toward indoor venues per Opus #2; reuses Phase 6.3's `STUB_CURRENT_TEMPERATURE_F` from `app/core/ranking.py` until Phase 8 wires real AirNow + NWS data), (d) HALT 3 close-out — confabulation guardrails ship + `FEATURE_FLAG_DISCLOSURE_RENDERER` flip gated by eval-set pass (N-case held-out chat test cases + 0 confabulation on missing-data + 100% disclosure-pipeline coverage on cited responses), (e) cross-entity chat queries (e.g., "where can I take my dog for breakfast?" returns dog-friendly restaurants AND dog parks interleaved), (f) snowbird-return view on homepage (logged-in users active October–April see a "what's reopened" panel). Phase 7 is the **chat-integration + HALT 3 lane** that runs after Phase 5 (data) + 6.3 (UI breadth pass) land; the original 2026-05-14 framing of "Tier 2 UI + data gathering" was absorbed by Phase 5 + 6.3. The heavy-prescriptive operating doc is the master plan §4 Phase 7 + the refreshed `outputs/phase7_handoff_note.md`.
>
> **Gating dependencies:** Phase 1 (ENTITY schema) SHIPPED 2026-05-14. Phase 4 (background jobs + scrapers + reconciler) SHIPPED 2026-05-13. Phase 5 (Tier 1 data, all 13 categories populated) SHIPPED 2026-05-17 at Phase 5.11 close (`dcf3dd4`); STATE.md ledger landed at `3a2d895` 2026-05-19. Phase 6.1 SHIPPED `fd16e7a` 2026-05-14 (unified Hava card grammar). Phase 6.2 SHIPPED `3948add` 2026-05-15 (category landing template + Eat & Drink proof). Phase 6.3 SHIPPED `5ebee46` 2026-05-19 (breadth pass + district chip + `app/core/ranking.py` + seasonal hours). parks-rec-scrapes sidecar `f6a7b8c9d0e1` SHIPPED at `532d48b`. Phase 7 docs refresh at `c1d9ed2` (master plan + handoff note both align to current scope). **Phase 7 consumes** the ENTITY catalog (1,314 active entities; 12 active Tier-1 slugs + cat-13 thin) + `app/providers/queries.py` shared helpers (`is_open_now`, `effective_hours_structured`, `effective_seasonal_hours`, district eager-load) + `app/core/ranking.py` (`compute_card_rank` + heat-bias + `STUB_CURRENT_TEMPERATURE_F`) + operator-curated `heat_exposure` / `boat_access` / `seasonal_hours` JSON fields. **Phase 8 is NOT required** — Phase 7 uses the same stub temperature constant 6.3 uses until Phase 8 swaps in live AirNow + NWS + USGS data; the chat-conditions wiring is testable behind the stub.
>
> **Parallel-with-Phase-6.4 caveat:** Phase 6.4 (map view + boat-mode toggle + themed groups + search bar) is parallel-eligible with Phase 7 per gotcha #18 file-scope disjointness. **One shared file: `app/templates/home.html`.** Phase 6.4 adds a search bar in the hero block (anchored at the hero region); Phase 7 adds a snowbird panel `{% include %}` line (anchored at a structurally separate region — below hero, above footer). Both wrappers use distinct anchor comments (`<!-- search-bar-include -->` for 6.4; `<!-- snowbird-panel-include -->` for 7) to enable parallel edits without textual collision. **If a true-parallel run hits a merge conflict on home.html, recommend sequencing 6.4 first then 7** (operator decision per close-out cadence). Other Phase 7 file scope: anchored edits on `app/chat/tier2_db_query.py`, `app/chat/tier2_handler.py`, `app/chat/tier3_handler.py`, `app/chat/tier3_postprocess.py`, `app/chat/disclosure_render.py`, `app/chat/context_builder.py`, `app/api/routes/chat.py`; new files `app/chat/halt3_eval_set.yaml` (or .py), `app/chat/halt3_validator.py`, `app/templates/components/snowbird_panel.html`, `app/api/routes/snowbird.py` (if separate route needed); new tests `tests/test_phase7_chat_entity_wiring.py`, `tests/test_phase7_chat_boat_mode.py`, `tests/test_phase7_chat_conditions.py`, `tests/test_phase7_halt3_validation.py`, `tests/test_phase7_cross_entity.py`, `tests/test_phase7_snowbird.py`. Phase 6.4 file scope: `app/templates/category_landing.html` + `provider_profile.html` + `home.html` (hero block only) + `app/static/` + `app/api/routes/category_pages.py` + new `themed_groups.py` + new `map_data.py` + `app/main.py`. **Zero overlap outside home.html if both lanes hold scope.**
>
> **No operator prereq for Phase 7.** No new env vars BEYOND a possible `FEATURE_FLAG_DISCLOSURE_RENDERER=true` flip post-validation (operator does that flip out-of-band after eval set passes; the wrapper does NOT instruct Cursor to flip the env var). No Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure chat + template authoring on top of 6.3.
>
> **Operator decision-lock status:** the 4 Phase 7-relevant decisions are locked at this session (2026-05-20):
> - **Snowbird-return view: IN Phase 7** (per operator lock 2026-05-20). Homepage panel for logged-in users with `last_active_at` in the Oct–Apr seasonal window; shows entities with seasonal_hours indicating they've reopened in the current calendar window (vs. were closed in the prior window).
> - **HALT 3 validation criteria: eval-set pass** (N-case held-out chat test cases + confabulation rate threshold). Define an eval set of 20–30 chat queries covering: cited responses, "I don't know" paths, missing-data fallbacks, conditions-aware ranking. Renderer pipeline must route correctly on each. Pass criteria = 100% disclosure-pipeline coverage on cited responses + 0 confabulation on missing-data cases. Eval set is CI-runnable; operator reviews flagged responses pre-flip. Master plan §7 risk register #7 mitigation.
> - **Stub-temperature approach: reuse Phase 6.3's `STUB_CURRENT_TEMPERATURE_F`** from `app/core/ranking.py` (per `phase7_handoff_note.md` §1). Single source of truth; Phase 8 swap-in is a one-constant change.
> - **Cross-entity queries:** chat returns interleaved results across categories when intent surfaces multi-domain need ("dog-friendly breakfast" → cat-1 dog-friendly restaurants + cat-7 dog parks + cat-11 pet-friendly services). Interleaving is rank-based (`compute_card_rank`); operator-tunable per-domain weights deferred to V1.5.
>
> **Author note:** authored at the post-Lanes-A+B+C Cowork primary session (2026-05-20) post-`23b3a70` against the post-Phase-5.11 + post-6.3 + post-sidecar tip. Five SHA-patch slots: `fd16e7a` + `3948add` + `5ebee46` + `f6a7b8c9d0e1` + `c1d9ed2`. All five are already filled below; verify against `python -m alembic current` + `.git/refs/heads/main` before paste in case origin/main has advanced.
>
> **Clipboard pipeline** (primes operator clipboard with prompt body only — skips the preamble + post-prompt footer; PowerShell 5.1 truncates large multi-line clipboard payloads per session-2026-05-19 lesson #3, so this pipeline writes to a temp file + uses Notepad as a synchronous clipboard router):
> ```powershell
> Get-Content outputs\cursor_dispatch_prompt_phase_7.md | Select-Object -Skip 34 | Select-Object -SkipLast 71 | Out-File -FilePath $env:TEMP\phase_7_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_7_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-2026-05-19 lesson #2 — do NOT use `Get-Clipboard` directly):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~22000–28000 bytes. Anything under ~1000 bytes is a truncation signal — re-do the Notepad route.

---

````
Read docs/maintainability/master_build_plan.md §4 Phase 7 (refreshed
2026-05-19 at `c1d9ed2`) + outputs/phase7_handoff_note.md (refreshed
2026-05-19) end-to-end. Also read docs/maintainability/master_build_
plan.md §7 risk register entry #7 (HALT 3 close-out scoping) + §8 OQ
#11 (search vs Ask Hava -- explains why two separate affordances) + §8
OQ #4 (vacation-rental permits to lodging records -- adjacent surface,
NOT in Phase 7 scope per current master plan but referenced for
context).

Phase 1 (ENTITY) SHIPPED. Phase 4 SHIPPED. Phase 5 multi-phase data-
population COMPLETE at 5.11 close (1,314 active entities across 12
active Tier-1 slugs; cat-13 thin at 4 entries). Phase 6.1 SHIPPED at
`fd16e7a` (unified Hava card grammar). Phase 6.2 SHIPPED at `3948add`
(first category landing template + Eat & Drink proof). Phase 6.3
SHIPPED at `5ebee46` (breadth pass to all 11 remaining Tier-1 slugs
+ district chip on profiles + time/heat-aware ranking via
app/core/ranking.py + seasonal hours rendering). parks-rec-scrapes
sidecar migration `f6a7b8c9d0e1` SHIPPED at `532d48b` (ON DELETE SET
NULL on contributions.created_event_id FK; cron workflow_dispatch +
scheduled runs verified green from 2026-05-19 onward).

Pytest baseline going in is **2060 collected** (2058 passed + 2 skipped
per post-Phase-6.3 + sidecar state on origin/main tip `23b3a70`). Verify
per `python -m pytest --collect-only -q | tail -3` BEFORE starting work.
Alembic head is **f6a7b8c9d0e1** (Phase 6 sidecar; chains from
`0a1b2c3d4e5f` Phase 4.1 outbox). Verify per `python -m alembic current`
BEFORE starting work and REPORT THE OBSERVED VALUE (do NOT copy the
dispatch-body-claimed value -- session-2026-05-19 lesson #6).

Ship Phase 7 ONLY per master plan §4 Phase 7 -- (a) chat tier 2 / tier
3 wired to query the ENTITY table (replaces pre-pivot River Scene events
catalog query at app/chat/tier2_db_query.py:33+); (b) chat awareness of
boat-access mode (when active, queries filter by `boat_access IS NOT
NULL`; tier 3 LLM prompt gets a "user is in boat mode" preamble); (c)
chat awareness of conditions (when stub temperature > HEAT_BIAS_THRESHOLD_F
i.e. 100°F, ranking shifts toward indoor venues per Phase 6.3's
compute_card_rank; reuses STUB_CURRENT_TEMPERATURE_F from
app/core/ranking.py); (d) HALT 3 close-out -- confabulation guardrails
ship + eval-set validator runs against 20-30 held-out chat queries;
FEATURE_FLAG_DISCLOSURE_RENDERER flip is OPERATOR-MANUAL post-validation,
NOT in this dispatch's scope; (e) cross-entity chat queries -- "where
can I take my dog for breakfast?" returns dog-friendly restaurants AND
dog parks AND pet-friendly cafes interleaved by compute_card_rank; (f)
snowbird-return view on homepage -- logged-in users with last_active_at
in the Oct-Apr seasonal window see a panel listing entities whose
seasonal_hours indicate they're now open (reopened post-snowbird-season).
**No new category landing pages** -- Phase 6.2 + 6.3 already shipped all
12 active Tier-1 category pages. **No map view, no boat-mode UI toggle,
no themed group landing pages, no search bar** -- those are Phase 6.4
(parallel-eligible lane). **No real conditions data** -- Phase 8.
**No district paragraph rendering** -- V1.5 per path-b lock.
**No sponsor logic** -- Phase 11.

OPERATOR DECISION-LOCK STATUS for Phase 7 (locked at
session-2026-05-20):

- Snowbird-return view: **IN Phase 7**. Homepage panel for
  logged-in users with last_active_at in Oct-Apr window.
  Renders nothing for anonymous users; renders nothing in
  May-Sep window (off-season). Implementation: new partial
  `app/templates/components/snowbird_panel.html` + new helper
  `app/chat/snowbird_query.py` (or reuse queries.py) returning
  the entity list. Anchored edit on `app/templates/home.html`
  adds a single `{% include 'components/snowbird_panel.html' %}`
  line at anchor `<!-- snowbird-panel-include -->` (Phase 6.4
  wrapper reserves the `<!-- search-bar-include -->` anchor in
  the hero block; gotcha #18 coordination).
- HALT 3 validation criteria: **eval-set pass**. Define a
  held-out eval set of 20-30 chat queries (in YAML or Python
  config at `app/chat/halt3_eval_set.yaml`). Each query has:
  query text, expected disclosure pipeline path (cited /
  uncited / I-don't-know), expected confabulation rate (0
  for missing-data cases), expected response shape (tier 1
  / tier 2 / tier 3). Validator at `app/chat/halt3_validator.py`
  runs the eval set + reports per-query pass/fail. Pass
  criteria for the flag flip: 100% disclosure-pipeline
  coverage on cited responses + 0 confabulation on
  missing-data cases. The validator is CI-runnable; operator
  reviews flagged responses pre-flip. FEATURE_FLAG_
  DISCLOSURE_RENDERER env var flip is OPERATOR-MANUAL after
  eval set passes -- this dispatch does NOT flip the env var.
- Stub-temperature approach: **reuse Phase 6.3's
  STUB_CURRENT_TEMPERATURE_F** from app/core/ranking.py.
  Chat conditions-awareness imports the same constant. When
  Phase 8 swaps in live data, both ranking + chat paths
  update with one constant change.
- Cross-entity queries: chat returns interleaved results
  across categories when intent surfaces multi-domain need.
  Interleaving = rank-based via compute_card_rank. Operator-
  tunable per-domain weights deferred to V1.5.
- Snowbird-window dates: brief assumes Oct 1 - Apr 30 (Lake
  Havasu snowbird season per local convention); if a
  different window reads cleaner from operator-side data,
  flag in §13.

ORDER MATTERS WITHIN PHASE 7:

1. First: read the source files in the chat module. Critical
   reads:
   - app/chat/tier2_db_query.py (the file with the pre-pivot
     River Scene events catalog query at line 33+ that Phase 7
     replaces with ENTITY query)
   - app/chat/tier2_handler.py (tier 2 dispatch surface)
   - app/chat/tier2_formatter.py + tier2_components.py +
     tier2_catalog_render.py (tier 2 rendering surface; the
     unified Hava card grammar from 6.1 should be reused
     where possible)
   - app/chat/tier3_handler.py + tier3_postprocess.py (tier 3
     LLM surface; LLM prompt construction lives here)
   - app/chat/disclosure_render.py (already exists with
     FEATURE_FLAG_DISCLOSURE_RENDERER env var at line ~52 +
     `is_disclosure_renderer_enabled` at line ~218; Phase 7
     wires this into the response pipeline, NOT the flag flip)
   - app/chat/context_builder.py + audience_signal.py (chat
     context surfaces -- boat-mode + conditions awareness
     hook here OR upstream in unified_router.py)
   - app/chat/unified_router.py (top-level chat dispatcher
     that routes tier 1 / 2 / 3)
   - app/chat/entity_matcher.py (entity matching; ENTITY-table
     awareness flows through here)
   - app/api/routes/chat.py (HTTP surface; receives user
     request, dispatches to chat module, returns response)
   - app/core/ranking.py (Phase 6.3's compute_card_rank +
     STUB_CURRENT_TEMPERATURE_F + HEAT_BIAS_THRESHOLD_F +
     HEAT_BIAS_INDOOR_WEIGHT + HEAT_BIAS_SHADED_WEIGHT;
     Phase 7 imports + reuses these)
   - app/providers/queries.py (shared helpers; is_open_now,
     effective_hours_structured, effective_seasonal_hours,
     district eager-load -- Phase 7 chat surfaces consume
     these)
   - app/db/models.py (Entity model -- boat_access,
     heat_exposure, seasonal_hours, district_id columns;
     User model -- last_active_at for snowbird window
     detection; verify last_active_at exists or add anchored
     edit if it doesn't)
   - app/templates/home.html (verify the
     `<!-- snowbird-panel-include -->` anchor location; if
     the anchor comment doesn't exist yet, add it as part
     of Phase 7's home.html edit -- single comment + single
     include line at the same anchor; coordinate with Phase
     6.4's `<!-- search-bar-include -->` anchor which should
     be in the hero block)
   - docs/maintainability/disclosure_renderer_spec.md (HALT 3
     spec; informs the eval set design)

2. Then: chat ENTITY wiring (deliverable a). Anchored edit on
   app/chat/tier2_db_query.py replacing the pre-pivot River
   Scene events catalog query at line ~33+. New query reads
   from the entities table via SQLAlchemy ORM, filters by
   `Entity.is_active=True` joined through `EntityCategory`
   (the strict-join filter pattern 6.2 ships in
   app/api/routes/category_pages.py:274-275), applies intent
   filters from the tier 2 parser (cuisine / sub-trade /
   district / operational), applies compute_card_rank for
   ordering, returns top N results. Anchored edits on
   tier2_handler.py + tier2_formatter.py to consume the new
   query shape (entities not pre-pivot River Scene events).
   Anchored edits on tier3_handler.py + tier3_postprocess.py
   so tier 3 LLM responses cite ENTITY records (with
   profile_url linking to /provider/<slug> for commercial OR
   place/program permalink for non-commercial). Test in new
   tests/test_phase7_chat_entity_wiring.py (8-12 tests).

3. Then: chat boat-mode awareness (deliverable b). Anchored
   edit on app/chat/context_builder.py adding boat_mode flag
   to the chat context (read from request -- query param
   `?boat=1` OR header `X-Boat-Mode: 1` OR session-state
   if Phase 6.4 ships a session/cookie surface for it). When
   boat_mode is true: tier 2 db_query filters by
   `Entity.boat_access IS NOT NULL`; tier 3 LLM prompt
   construction in tier3_handler.py prepends a preamble
   string ("The user is in boat-access mode. Prefer
   waterfront / dock-accessible entities. Mention boat-access
   details when relevant."). Test in new
   tests/test_phase7_chat_boat_mode.py (8-14 tests).

4. Then: chat conditions awareness (deliverable c). Anchored
   edit on app/chat/tier2_db_query.py (and/or
   tier2_formatter.py if rank application happens there) to
   import compute_card_rank from app.core.ranking and apply
   heat-bias weighting when STUB_CURRENT_TEMPERATURE_F >
   HEAT_BIAS_THRESHOLD_F (default 100°F per Phase 6.3 lock).
   Anchored edit on app/chat/tier3_handler.py: when heat-bias
   active, tier 3 LLM prompt gets a "current temperature is
   105°F; user comfort favors indoor venues" preamble.
   IMPORTANT: do NOT introduce a separate STUB constant in
   app/chat/; reuse app/core/ranking's. Test in new
   tests/test_phase7_chat_conditions.py (8-12 tests).

5. Then: HALT 3 close-out (deliverable d). Author the eval
   set at app/chat/halt3_eval_set.yaml (or .py; YAML is
   recommended for operator-readability). Shape per query:
   ```yaml
   - id: q01
     query: "Where can I get coffee right now?"
     expected_tier: tier2
     expected_disclosure_path: cited
     expected_confabulation_rate: 0.0
     notes: "Standard intent; tier 2 should hit eat-drink with
       operational filter open-now."
   ```
   Aim for 20-30 queries covering:
   - 5-7 cited-response cases (standard intent; data exists)
   - 5-7 "I don't know" cases (intent surface but missing
     data; e.g., "What's the wait at Heat Hotel right now?"
     -- we don't have live wait times)
   - 5-7 missing-data cases (entity not in catalog; verify
     0 confabulation -- response is "I don't have data on
     <entity>" NOT a fabricated description)
   - 3-5 conditions-aware cases (heat / boat-mode toggled;
     verify ranking shifts)
   - 2-3 cross-entity cases (multi-domain intent)

   Author the validator at app/chat/halt3_validator.py.
   `validate_eval_set(eval_set_path, *, stub_temperature_f=
   None, boat_mode=False) -> EvalSetReport`. Runs each query
   through unified_router, captures: disclosure path taken,
   confabulation rate (computed via entity-match check;
   confabulation = response contains entity name NOT in
   catalog), tier hit. EvalSetReport has per-query results +
   aggregate pass/fail per criterion (100% disclosure-pipeline
   on cited; 0 confabulation on missing-data).

   Author tests/test_phase7_halt3_validation.py (8-14 tests):
   eval set loads correctly; validator runs each query; cited
   cases hit disclosure_render.is_disclosure_renderer_enabled
   correctly; missing-data cases produce "I don't know"
   response with 0 confabulation; full eval set passes
   acceptance criteria (this is the gate test).

   Do NOT flip FEATURE_FLAG_DISCLOSURE_RENDERER. The operator
   does that out-of-band after reviewing the eval set report.

6. Then: cross-entity queries (deliverable e). Anchored edit
   on app/chat/intent_classifier.py (or the closest current
   surface in the chat module that classifies intent) adding
   detection for multi-domain intents (the heuristics: query
   contains 2+ category-suggestive nouns -- "dog" + "breakfast"
   -- or contains a connector phrase like "and" / "with" /
   "where I can also"). Anchored edit on tier2_db_query.py:
   when intent is multi-domain, the query runs against
   multiple EntityCategory filters interleaved by
   compute_card_rank rather than category-locked. Test in
   new tests/test_phase7_cross_entity.py (8-14 tests):
   "dog-friendly breakfast" returns mix of cat-1 + cat-7 +
   cat-11 entities ranked together; query "groceries and
   coffee" returns cat-8 + cat-1 interleaved; single-domain
   queries continue to category-lock (regression guard).

7. Then: snowbird-return view (deliverable f). New file
   app/templates/components/snowbird_panel.html (~60-100
   lines): Jinja partial rendering a list of entities whose
   seasonal_hours indicate they've reopened in the current
   calendar window (current month is in their "open" window
   but prior month was NOT). New helper in
   app/chat/snowbird_query.py (or wherever queries.py reads
   cleanest -- flag in §13 if you prefer queries.py): function
   `get_snowbird_reopened_entities(now=None) -> list[Entity]`.
   Reads entities with seasonal_hours JSON; returns those
   where current date is in the active season but the prior
   month was in an inactive season. Limit N=20.

   Anchored edit on app/templates/home.html: insert single
   `{% include 'components/snowbird_panel.html' %}` line at
   anchor `<!-- snowbird-panel-include -->`. If the anchor
   comment doesn't exist in home.html yet, add it as part
   of the same edit -- single comment line + the include line
   directly below. Anchor location: structurally separate
   from the hero block (Phase 6.4 reserves the hero block
   for its search bar via `<!-- search-bar-include -->`).
   Suggested location: between the existing hero block and
   the existing category-tiles block (or wherever home.html's
   current shape has a natural seam below the hero). Verify
   the anchor location doesn't collide with Phase 6.4's edit
   per gotcha #18.

   Snowbird panel renders ONLY when (a) user is logged-in
   (verify via session middleware / current_user dependency)
   AND (b) current date is in Oct 1 - Apr 30 window AND (c)
   user has last_active_at indicating snowbird-pattern
   activity (last_active_at within last 90 days OR
   last_active_at falls in a prior Oct-Apr window). Else
   render nothing (no placeholder, no copy).

   Test in new tests/test_phase7_snowbird.py (8-14 tests):
   panel renders for logged-in user in Oct window; panel
   absent for anonymous user; panel absent in May-Sep window;
   panel absent for logged-in user with last_active_at >
   365 days ago; get_snowbird_reopened_entities returns
   correct entities given seeded seasonal_hours fixtures;
   anchor coordination -- 6.4's `<!-- search-bar-include -->`
   and 7's `<!-- snowbird-panel-include -->` both present
   without conflict in home.html (assumes 6.4 ships first OR
   both wrappers land their anchors via independent commits).

8. After all of the above: confirm full pytest stays green
   (2060 floor + 50-80 net-new = 2110-2140), ruff clean.
   Manual smoke deferred-to-operator:
   - `python -m fastapi run app.main:app` + chat surface
     query "where can I get coffee" verify tier 2 returns
     ENTITY records (not pre-pivot River Scene events)
   - Chat query "dog-friendly breakfast" verify cross-entity
     interleaving across cat-1 + cat-7 + cat-11
   - Toggle boat-mode (when 6.4 lands) verify chat queries
     filter by boat_access IS NOT NULL
   - Login + browse to / in Oct-Apr window verify snowbird
     panel renders
   - Run `python -m app.chat.halt3_validator app/chat/
     halt3_eval_set.yaml` verify eval set passes; review
     per-query report; if all green operator flips
     FEATURE_FLAG_DISCLOSURE_RENDERER=true out-of-band

POSTGRES COMPATIBILITY (carry-forward from brief §0 + Phase 1A
lesson):

- Phase 7 ships ZERO alembic migrations IF User.last_active_at
  already exists. Verify at step 1 read. If User.last_active_at
  does NOT exist, ship ONE alembic migration adding it
  (DateTime nullable=True; no server_default; chain from
  `f6a7b8c9d0e1`; use `sa.DateTime(timezone=True)` per Phase
  2A.1 + 2A.3 precedent). Test migration cycle with dynamic
  head capture (NEVER hardcode head literals -- session-2026-
  05-19 lesson #4).
- Alembic head after Phase 7 ships is either `f6a7b8c9d0e1`
  (unchanged; if no migration needed) or the new migration's
  revision SHA.

DEVIATION INVITATIONS (per master plan §4 Phase 7 + handoff
note):

- HALT 3 eval set size: brief assumes 20-30 queries; if 15
  is sufficient or 40 reads cleaner, flag in §13. The
  acceptance criteria stay the same.
- HALT 3 eval set location: brief assumes YAML at
  app/chat/halt3_eval_set.yaml; if Python config reads cleaner
  for type-checking purposes, flag.
- Cross-entity intent detection heuristics: brief assumes
  "2+ category-suggestive nouns OR connector phrase";
  alternative LLM-based intent classification acceptable (but
  do NOT introduce a new LLM call -- reuse the existing
  intent_classifier.py path).
- Snowbird-window dates: brief assumes Oct 1 - Apr 30; if
  Lake Havasu seasonal data argues different, flag.
- Snowbird query helper location: brief assumes new
  app/chat/snowbird_query.py; if queries.py reads cleaner,
  flag.
- Snowbird "last_active_at indicates snowbird pattern"
  heuristic: brief assumes last_active_at within 90 days OR
  prior Oct-Apr window; if a different heuristic reads
  cleaner, flag.
- Chat conditions-awareness LLM preamble shape: brief
  assumes a static preamble string when heat-bias active;
  if a more nuanced preamble per tier reads better, flag.
- HALT 3 validator output format: brief assumes structured
  EvalSetReport object; if a markdown report reads better
  for operator review, flag.
- Boat-mode preamble in tier 3: brief assumes "user is in
  boat-access mode" string; if a richer preamble works
  better, flag.

WHAT NOT TO DO (per master plan §4 Phase 7):

- Don't ship map view. Phase 6.4 (parallel-eligible lane).
- Don't ship boat-mode UI toggle in header. Phase 6.4.
- Don't ship themed group landing pages. Phase 6.4.
- Don't ship search bar. Phase 6.4.
- Don't ship new category landing pages. Phase 6.2 + 6.3
  already shipped all 12 active Tier-1 category pages.
- Don't ship real conditions data. Phase 8.
- Don't flip FEATURE_FLAG_DISCLOSURE_RENDERER. Operator
  does this out-of-band post-validation.
- Don't ship district paragraph rendering. V1.5.
- Don't ship sponsor logic. Phase 11.
- Don't ship native review system. V1.5.
- Don't add new Python dependencies beyond what the chat
  module + LLM router already use.
- Don't introduce a new LLM call for intent classification
  -- reuse intent_classifier.py path.
- Don't introduce a new STUB constant for current
  temperature. Reuse STUB_CURRENT_TEMPERATURE_F from
  app/core/ranking.py.
- Don't bash heredoc commit messages. PowerShell-safe
  multiple `-m "..."` flags or here-string `@'...'@ |
  Out-File ... | git commit -F <file>` per session-2026-
  05-19 lesson #1.
- Don't hardcode alembic head literals in test code
  (session-2026-05-19 lesson #4). Use
  `script.get_current_head()` + dynamic capture.
- Don't dispatch Phase 8 or Phase 6.4 in the same Cursor
  session. HALT at the §3 Phase 7 boundary.
- Don't edit app/templates/home.html outside the
  `<!-- snowbird-panel-include -->` anchor region. Phase
  6.4 (if parallel) owns the `<!-- search-bar-include -->`
  anchor in the hero block. Two distinct anchor regions;
  do NOT touch each other's region.

HALT at the §3 Phase 7 boundary. After Phase 7 ships +
commits + pushes, halt for operator re-dispatch in a fresh
session for Phase 8 (conditions data + trust layer + alerts)
OR Phase 6.5 (homepage rebuild + 8 themed group tiles +
"What's on at this venue" region hook).

Same constraints as Phase 6.1 + 6.2 + 6.3:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for
  Phase 7
- Re-verify `python -m alembic current` and report the
  observed value (do NOT copy the dispatch-body-claimed
  value -- session-2026-05-19 lesson #6). If observed head
  differs from `f6a7b8c9d0e1`, HALT and ask operator before
  proceeding.

Pre-dispatch checklist (verify before paste):
- Phase 6.1 SHIPPED on origin (`fd16e7a`)
- Phase 6.2 SHIPPED on origin (`3948add`)
- Phase 6.3 SHIPPED on origin (`5ebee46`)
- Sidecar migration SHIPPED on origin (`532d48b`; alembic head
  `f6a7b8c9d0e1`)
- Phase 5 ledger SHIPPED on origin (`3a2d895`)
- Phase 7 docs refresh SHIPPED on origin (`c1d9ed2`)
- `f6a7b8c9d0e1` is the current single alembic head on origin
- Pytest baseline going in is 2060 (or matches reality per
  `python -m pytest --collect-only -q | tail -3`)
- master_build_plan.md §4 Phase 7 + phase7_handoff_note.md
  reflect current scope (both refreshed at `c1d9ed2`)
- Phase 6.4 lane (if running concurrently) is in a sub-phase
  that doesn't touch app/chat/ or app/api/routes/chat.py or
  the `<!-- snowbird-panel-include -->` anchor in
  app/templates/home.html -- verify per gotcha #18
- The 4 operator decisions are locked: snowbird IN Phase 7,
  HALT 3 eval-set criteria, reuse STUB_CURRENT_TEMPERATURE_F,
  cross-entity interleaving via compute_card_rank
````

---

## After Cursor returns with the §12 report

Same rhythm as 6.1 + 6.2 + 6.3 + 6.4: paste back to Cowork primary chat, primary reviews against master plan §4 Phase 7 + handoff note acceptance gates, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 0 OR 1 new alembic migration (User.last_active_at if column doesn't exist; verify at step 1 read)
- 1 new `app/chat/snowbird_query.py` (~40-80 lines)
- 1 new `app/chat/halt3_eval_set.yaml` (~150-250 lines; 20-30 queries with metadata)
- 1 new `app/chat/halt3_validator.py` (~100-180 lines)
- 1 new `app/templates/components/snowbird_panel.html` (~60-100 lines)
- 0 OR 1 new `app/api/routes/snowbird.py` (only if a separate route is needed for panel data; otherwise snowbird query happens in home route handler)
- 1 modified `app/chat/tier2_db_query.py` (anchored edit; +~80-150 lines for ENTITY query replacing pre-pivot River Scene + cross-entity interleaving)
- 1 modified `app/chat/tier2_handler.py` (anchored edit; +~30-60 lines for new query shape consumption)
- 1 modified `app/chat/tier2_formatter.py` (anchored edit; +~20-40 lines for unified Hava card grammar reuse)
- 1 modified `app/chat/tier3_handler.py` (anchored edit; +~40-80 lines for boat-mode preamble + conditions preamble + ENTITY citation)
- 1 modified `app/chat/tier3_postprocess.py` (anchored edit; +~20-40 lines for ENTITY citation cleanup)
- 1 modified `app/chat/context_builder.py` (anchored edit; +~20-40 lines for boat-mode flag in context)
- 1 modified `app/chat/intent_classifier.py` (anchored edit; +~30-60 lines for multi-domain intent detection)
- 1 modified `app/api/routes/chat.py` (anchored edit; +~15-30 lines for boat-mode + conditions request parsing)
- 1 modified `app/templates/home.html` (anchored edit; +~3 lines for snowbird include + anchor comment)
- 6 new test files:
  - `tests/test_phase7_chat_entity_wiring.py` (~8-12 tests)
  - `tests/test_phase7_chat_boat_mode.py` (~8-14 tests)
  - `tests/test_phase7_chat_conditions.py` (~8-12 tests)
  - `tests/test_phase7_halt3_validation.py` (~8-14 tests)
  - `tests/test_phase7_cross_entity.py` (~8-14 tests)
  - `tests/test_phase7_snowbird.py` (~8-14 tests)

Expected pytest delta: +50-80 net-new tests. Pre-existing Phase 6.1 + 6.2 + 6.3 + Phase 5 prep tests must remain green.

Expected effort: 5-8 days dispatch per master plan §4 Phase 7 + session close-out §3 Lane E. Reduced from M-L (10-14 days) per Lane C 2026-05-19 docs refresh (Tier 2 UI + data strands were absorbed by Phase 5 + 6.3).

CURSOR MAY SPLIT INTO TWO SUB-SESSIONS if it estimates the full scope as >6 days:
- Phase 7a: chat ENTITY wiring + boat-mode + conditions + cross-entity (~3-5 days; file scope = app/chat/tier2_db_query.py + tier2_handler.py + tier2_formatter.py + tier3_handler.py + tier3_postprocess.py + context_builder.py + intent_classifier.py + app/api/routes/chat.py + tests/test_phase7_chat_entity_wiring.py + tests/test_phase7_chat_boat_mode.py + tests/test_phase7_chat_conditions.py + tests/test_phase7_cross_entity.py)
- Phase 7b: HALT 3 close-out + snowbird-return view (~2-3 days; file scope = app/chat/halt3_eval_set.yaml + app/chat/halt3_validator.py + app/chat/snowbird_query.py + app/templates/components/snowbird_panel.html + anchored edit on app/templates/home.html + tests/test_phase7_halt3_validation.py + tests/test_phase7_snowbird.py)

HALT between 7a and 7b is at the natural §3 work-unit boundary; operator commits + pushes 7a; 7b dispatches fresh against 7a's HEAD SHA.

For monolithic Phase 7 execution (single session, all 6 deliverables), the dispatch body applies directly.

Expected pragmatic deviations:

1. HALT 3 eval set size (20-30 vs 15 vs 40)
2. HALT 3 eval set location (YAML vs Python config)
3. Cross-entity intent detection heuristics (regex vs LLM-based; reuse existing intent_classifier.py)
4. Snowbird-window dates (Oct 1 - Apr 30 vs different)
5. Snowbird query helper location (new app/chat/snowbird_query.py vs queries.py extension)
6. Snowbird "last_active_at indicates snowbird pattern" heuristic
7. Chat conditions-awareness LLM preamble shape
8. HALT 3 validator output format (structured object vs markdown report)
9. Boat-mode preamble in tier 3 string content
10. Standalone snowbird route vs home route handler

## After Phase 7 ships

Update master plan §4 Phase 7 — append SHIPPED line under the existing scope section (Cowork primary appends). Update STATE.md Production block + Recently shipped §1 prepend with Phase 7 close-out narrative. Update alembic head reference if the User.last_active_at migration shipped.

After eval set passes, operator flips `FEATURE_FLAG_DISCLOSURE_RENDERER=true` env var out-of-band (Railway production environment) + verifies post-flip chat surface behavior. STATE.md "Recently shipped" entry should note both the Phase 7 ship + the flag flip date.

Phase 8 dispatch prompt to be authored after Phase 7 ships — chains off Phase 7's HEAD SHA + alembic head. Phase 8 = trust layer (cat-13 expansion) + conditions panel + alerts; lands real AirNow + NWS + USGS data that swaps in for the STUB_CURRENT_TEMPERATURE_F constant Phase 6.3 + 7 both currently read.

Phase 6.4 (map view + boat-mode toggle + themed groups + search bar) is parallel-eligible with Phase 7. The Phase 6.4 wrapper at `outputs/cursor_dispatch_prompt_phase_6_4.md` (authored at this same session 2026-05-20) is the parallel-dispatch artifact. Per gotcha #18, file scopes are mostly disjoint; the one shared file is `app/templates/home.html` (6.4 = hero block search bar at `<!-- search-bar-include -->` anchor; 7 = snowbird include at `<!-- snowbird-panel-include -->` anchor, structurally separate region).

---

*Authored by Cowork primary at the post-Lanes-A+B+C session (2026-05-20) against origin/main tip `23b3a70`. Lives at `outputs/cursor_dispatch_prompt_phase_7.md`. Five SHA-patch slots: `fd16e7a` + `3948add` + `5ebee46` + `f6a7b8c9d0e1` + `c1d9ed2` — all five filled at authoring time; verify against `python -m alembic current` + `.git/refs/heads/main` before paste in case origin/main has advanced. The Phase 6.4 wrapper at `outputs/cursor_dispatch_prompt_phase_6_4.md` is the parallel-dispatch artifact per gotcha #18.*
