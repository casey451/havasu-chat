# Cursor Dispatch Prompt — Phase 8b (cat-13 Public & Civic Resources expansion micro-dispatch)

> **SHA-PATCH APPLIED 2026-05-22 — DISPATCH-READY.** Both SHA slots are now filled with concrete values from the post-Phase-8a + post-lhcaz-rewrite state: the Phase-8a HEAD-SHA placeholder is filled with **`8a905c6`** (Phase 8a SHIPPED at Railway v1.3.0 — conditions + alerts subsystem); the Phase-8a alembic-head placeholder is filled with **`d8e9f0a1b2c3`** (Phase 8a additive migration extended `external_conditions_cache` + `alerts_dispatched` enum). Current origin/main HEAD is `6070726` (well past Phase 8a); pytest baseline at HEAD is ~2290 + 3 skipped. No multi-head state. Wrapper is paste-ready in a fresh Cursor chat. Historical SHA-patch-pending framing preserved in the next paragraph for audit.
>
> Paste-into-Cursor prompt for Phase 8b per master plan §4 Phase 8 (lines 401-419) + `outputs/phase_8_architecture_design.md` §10 (Lane C cat-13 expansion via Layer 3 + Layer 5). Phase 8b ships the **content-density closure** for cat-13 — the slug that Phase 5.11 close-out flagged as "intentionally light at 4 entries" (`outputs/phase5_11_session_closeout.md` §5 + §7). The category page itself has rendered since Phase 6.3 (chip dispatcher SHIPPED for all 12 active slugs); Phase 8b just expands the entity catalog to a useful population threshold (~15-25 entities per design doc §10.2).
>
> **SHA-patch slots — fill post-Phase-8a-ship.** Phase 8a dispatches FIRST and ships the conditions + alerts subsystem. Phase 8b chains off Phase 8a's HEAD SHA. Two slots in this wrapper: `8a905c6` (Phase 8a SHIPPED commit) + `d8e9f0a1b2c3` (alembic head post-Phase-8a; either `c9d0e1f2a3b4` if Phase 8a shipped no migration, OR the new revision SHA if Phase 8a shipped the `external_conditions_cache` additive migration per design doc §2.1).
>
> **Gating dependencies:** Phase 8a SHIPPED at `8a905c6`; Phase 7.5 SHIPPED (HALT 3 validator 22/22 PASS; operator flag-flip pending out-of-band); Phase 7 SHIPPED at `0a305e0`; Phase 6.5 SHIPPED (homepage chrome + conditions-strip-anchor); Phase 6.4 SHIPPED at `96c915d`; Phase 6.3 SHIPPED at `5ebee46` (chip dispatcher renders `/category/public-civic-resources` for cat-13 already); Phase 5 multi-phase data-population COMPLETE at `dcf3dd4` (1,314 active entities, **cat-13 thin at 4 entries** per Phase 5.11 close-out §5 table — that's the gap Phase 8b closes). Phase 6 lane COMPLETE. **Phase 8b consumes:** existing `entities` table (Phase 3.1 schema; no schema work); existing `categories` table (cat-13 row already present from Phase 3.1); existing `/category/public-civic-resources` route (Phase 6.3 chip dispatcher); existing `app/admin/contributions_html.py` admin form (Layer 5 manual-entry surface).
>
> **Operator prereq status — CONFIRM BEFORE PASTE.** Phase 8b's only operator-side prereq is **Layer 3 source-URL confirmation**. Operator-decide before dispatch:
>
> 1. **LHC open data portal — does it exist?** Phase 8 prereq research found CivicPlus serves the city-meeting calendar but NOT general civic-resource content (`outputs/phase_8_operator_prereq_checklist.md`). Likely outcome: no structured JSON feed; Phase 8b's Layer 3 scraper targets HTML pages on `lhcaz.gov` directly. Operator confirms before paste.
> 2. **City of LHC GIS feeds — any?** Mohave County publishes some parcel + zoning GIS; the city itself is sparser. Operator-decide: in-scope (only if structured + scrape-cheap) or skip-to-Layer-5 (most likely path).
> 3. **Library hours source.** Mohave County Library (https://www.mohavecountylibrary.us) — operator confirms whether the LHC branch hours render in scrape-friendly HTML. If yes: Layer 3. If JS-rendered or PDF-only: Layer 5 operator-typed.
> 4. **Transit + airport — confirmed Layer 5 only.** Per design doc §10.2: Havasu Hopper bus has no API; KHII airport info is federal AirNav (scrape-feasible but low-yield). Both default to Layer 5 manual entry.
>
> If any of the 4 confirmations is unresolved at paste time, Cursor halts at step 2 + operator decides before resumption.
>
> **Operator decision-lock status:** the 4 Phase 8b-relevant decisions are locked per architectural design §10:
>
> 1. **Sub-categories within cat-13.** Per master plan §4 Phase 8: library / transit / visitor info / utilities / airport / senior resources / payment+licensing links / civic orgs. **Phase 8b ships ALL 8 sub-categories** but with a population skew (libraries + utilities + civic orgs dense; transit + airport sparse since there's only 1 of each in LHC). Cat-13 filter chips on the category page (per design doc §10.3) optional in Phase 8b — operator decides at step 5 below; default omit (chips can ship in V1.5 if useful).
> 2. **Entity-shape decisions for civic surfaces.** Per Phase 1 schema canon (`app/db/models.py:1177` — "V1 only accepts entity_type IN ('commercial', 'place')"): library + utility offices + senior center + visitor bureau + airport are `place` (public services + civic facilities); civic orgs split — for-profit (Chamber of Commerce often is a 501(c)(6) but operates like a business) trend `place`; pure-volunteer nonprofits (Rotary, Kiwanis) trend `place`. **Default all 8 sub-categories to `entity_type='place'`** unless a sub-category specifically operates as a commercial provider with paid services (none in cat-13 do). Lock: `place` across the board.
> 3. **Layer 3 scope.** Per design doc §10.3 — ~6 entities populated via Layer 3 scraper (`scripts/ingest/lhc_civic_scrape.py`) targeting library hours + Havasu Hopper schedule + airport info. Rest (~14-19 entities) is Layer 5 operator-typed via existing `app/admin/contributions_html.py` flow OR a Phase 8b-specific seed script. **Lock: Layer 3 scraper ships in Phase 8b**; Layer 5 manual entries documented as operator follow-up surface (Cursor doesn't type them — operator does via admin form post-ship).
> 4. **Population threshold for "shipped."** Per design doc §13.3 L1: "Cat-13 category page populated with at least 15 entities." Phase 8b's engineering ship-line is: Layer 3 scraper lands ~6 entities + seed-script-or-fixture-data lands ~10-12 more starter entries (Chamber, Visitor Bureau, Senior Center, Meals on Wheels, Republic trash, UniSource electric, Mohave Electric, water/sewer dept, KHII airport, court records portal, business license portal, utility bill pay portal). Operator post-ship tops up to ~20-25 via admin form for the remaining sub-categories. **Lock: Phase 8b ships ≥15 cat-13 entities; ≥20 is stretch.**
>
> **Author note:** authored 2026-05-20 by Cowork primary at the post-Phase-7.5-ship session. Phase 8a dispatches first; this wrapper is pre-positioned for the subsequent Phase 8b micro-dispatch. Architecture design at `outputs/phase_8_architecture_design.md` §10 (~80 lines specific to cat-13) is the authoritative scope spec for Lane C. Master plan §4 Phase 8 + Phase 5.11 close-out §5 (cat-13 thin-at-4-entries baseline) are the upstream context. Reference wrapper: `outputs/cursor_dispatch_prompt_phase_8.md` (Phase 8a; ~457 lines; structural mirror) + `outputs/cursor_dispatch_prompt_phase_7_5.md` (Phase 7.5; ~211 lines; micro-dispatch shape mirror).
>
> **Clipboard pipeline** (PowerShell 5.1 truncates large payloads; uses Notepad as synchronous router per session-2026-05-19 lesson #3; offsets need recomputation post-SHA-patch since authoring may have shifted line counts):
> ```powershell
> # Verify offsets after SHA-patch by counting fence positions:
> # python3 -c "import sys; lines = open('outputs/cursor_dispatch_prompt_phase_8b.md').readlines(); fences = [i+1 for i, ln in enumerate(lines) if ln.strip() in ('```', '````')]; print('Fences at lines:', fences, 'Total:', len(lines))"
> Get-Content outputs\cursor_dispatch_prompt_phase_8b.md | Select-Object -Skip 44 | Select-Object -SkipLast 52 | Out-File -FilePath $env:TEMP\phase_8b_clip.txt -Encoding utf8
> notepad $env:TEMP\phase_8b_clip.txt
> # In Notepad: Ctrl+A then Ctrl+C. Then close Notepad. Clipboard now contains the prompt body.
> ```
>
> Verify clipboard size via temp-file Length (per session-2026-05-19 lesson #2):
> ```powershell
> Get-Clipboard | Out-File -FilePath $env:TEMP\clip_check.tmp -Encoding utf8; (Get-Item $env:TEMP\clip_check.tmp).Length; Remove-Item $env:TEMP\clip_check.tmp
> ```
> Expected size: ~9000-12000 bytes (Phase 8b is a micro-dispatch closer in size to Phase 7.5 than Phase 8a). <500 bytes = truncation; redo Notepad.

---

````
PHASE 8b — CAT-13 PUBLIC & CIVIC RESOURCES EXPANSION (MICRO-DISPATCH)

You are a focused content-density Cursor session. Phase 8a SHIPPED at
8a905c6 (conditions + alerts subsystem). Phase 7.5 SHIPPED
(HALT 3 validator 22/22 PASS). Phase 6.5 SHIPPED (homepage chrome). Phase 6
lane COMPLETE through 6.4. Phase 5 multi-phase data-population COMPLETE at
dcf3dd4 (1,314 active entities); cat-13 public-civic-resources is the
single thin slug at 4 entries (per outputs/phase5_11_session_closeout.md
sec5). Your job is to expand cat-13 to >=15 entities via Layer 3 scraper
+ Layer 5 seed-script combination per outputs/phase_8_architecture_design.md
sec10 (Lane C scope).

Read these first (in order):

1. outputs/phase_8_architecture_design.md sec10 ("Cat-13 Public & Civic
   Resources expansion") -- the authoritative scope spec. ~80 lines:
   sec10.1 scope, sec10.2 what LHC publishes (entity-type inventory table),
   sec10.3 implementation shape (Layer 3 scraper + ~20 Layer 5 entries +
   optional filter chips), sec10.4 why-split-from-8a.
2. docs/maintainability/master_build_plan.md sec4 Phase 8 (lines 401-419)
   -- the 8 sub-categories: library / transit / visitor info / utilities /
   airport / senior resources / payment+licensing links / civic orgs.
3. outputs/phase5_11_session_closeout.md sec5 (current cat-13 baseline =
   4 entries; sec7 hand-off documents this as the cat-13 light-population
   carry) + sec7 (Phase 7 + Phase 8 hand-off context).
4. Critical reads in the codebase:
   - app/db/models.py (Entity model; lines 627-700ish; verify
     entity_type IN ('commercial', 'place') V1 constraint per
     app/db/models.py:1177 + sec1241; cat-13 entries all use
     entity_type='place' per locked decision sec2 above)
   - app/admin/contributions_html.py (existing Layer 5 admin form;
     Phase 8b does NOT modify; documents as operator follow-up surface)
   - app/api/routes/category.py (Phase 6.2 + 6.3 category landing
     template + chip dispatcher; verify /category/public-civic-resources
     route renders without modification once entities are populated)
   - scripts/ingest/ingest_enrichment_csv.py + validate_enrichment_csv.py
     (existing Phase 5 ingest pattern; Phase 8b's Layer 3 scraper mirrors
     this shape)
   - docs/data/category_population_briefs/cat_13_public_civic_resources.md
     (operator category brief; if exists, the canonical population guide)
5. outputs/cursor_dispatch_prompt_phase_8.md (Phase 8a wrapper; structural
   reference -- Phase 8b mirrors the shape at smaller scale).

Verify baseline at session start:

- python -m pytest --collect-only -q | tail -3
  (expected: post-Phase-8a baseline, likely 2220-2330)
- python -m alembic current
  (expected: d8e9f0a1b2c3; either c9d0e1f2a3b4 if Phase 8a
  shipped no migration, OR the new revision SHA if Phase 8a shipped the
  external_conditions_cache additive migration)
- python -m alembic heads
  (expected: d8e9f0a1b2c3 SINGLE head; no multi-head)
- Cat-13 baseline count:
  python -c "from app.db.session import SessionLocal; from app.db.models import Entity, EntityCategory, Category; s = SessionLocal(); cat = s.query(Category).filter_by(slug='public-civic-resources').one(); n = s.query(EntityCategory).join(Entity).filter(EntityCategory.category_id == cat.id, Entity.is_active == True).count(); print(f'cat-13 baseline: {n} active entities')"
  (expected: 4 per Phase 5.11 close-out)

REPORT THE OBSERVED VALUES (do NOT copy dispatch-body-claimed values --
session-2026-05-19 lesson #6).

CRITICAL -- RUN BOTH:
- python -m alembic current   (returns SINGLE head)
- python -m alembic heads     (returns ALL heads; should be EXACTLY ONE)
If python -m alembic heads returns MULTIPLE heads, you have a multi-head
state. HALT immediately and report. This is the alembic-collision pattern
from the 2026-05-20 Phase 6.4/Phase 7 parallel-session collision -- see
outputs/dispatch_channels_alembic_collision_gotcha_draft.md for context.
Phase 8b ships ZERO migrations; multi-head at session start signals
upstream contamination that must be resolved before content work.

Ship Phase 8b ONLY per outputs/phase_8_architecture_design.md sec10
(Lane C; Lane A + Lane B = Phase 8a already shipped):

(a) Layer 3 scraper -- scripts/ingest/lhc_civic_scrape.py. Scrapes:
    - Mohave County Library LHC branch hours (https://www.mohavecountylibrary.us)
      -- IF operator confirmed Layer 3 feasible per prereq #3 above; ELSE
      falls back to placeholder + flag for Layer 5
    - Havasu Hopper transit info (https://www.lhcaz.gov/transit) -- likely
      Layer 5 per design doc sec10.2; scraper attempts + falls back
    - Lake Havasu City Airport KHII info (city airport page + federal
      AirNav fallback) -- Layer 3 / Layer 5 mix
    Target: ~6 entities populated via scraper.

(b) Layer 5 seed script -- scripts/seed_cat13_civic.py. Seeds ~10-12
    high-trust starter entities for the remaining sub-categories:
    - Lake Havasu Area Chamber of Commerce (civic org; entity_type='place')
    - Lake Havasu Visitor Bureau / Tourism CVB (civic org; place)
    - LHC Senior Center (senior resources; place)
    - Meals on Wheels LHC chapter (senior resources; place)
    - Republic Services LHC (utility, trash; place)
    - UniSource Energy Services / Mohave Electric (utility, electric; place)
    - City of LHC Water + Sewer Dept (utility; place)
    - Mohave County Court records portal (payment/licensing; place +
      website attribute carrying the portal URL)
    - LHC business license portal (payment/licensing; place + URL attr)
    - LHC utility bill pay portal (payment/licensing; place + URL attr)
    Mirrors the pattern of existing Phase 5 seed scripts; idempotent
    upserts on (name, address) match.

(c) Category page filter chips -- OPTIONAL per design doc sec10.3 + locked
    decision sec1 above. Default OMIT in Phase 8b (chips ship in V1.5 if
    useful). If operator wants chips at dispatch time, anchored edit on
    app/templates/category_landing.html adds Government services / Civic
    groups / Utilities / Transit chips. Skip otherwise.

(d) Tests -- 2-4 new test files:
    - tests/test_phase8b_civic_scraper.py (~6-10 tests; mocks HTML fetches
      + asserts parsed entity dicts match expected shape)
    - tests/test_phase8b_seed_script.py (~4-8 tests; asserts idempotent
      upsert + verifies seed-script entities present post-run)
    - tests/test_phase8b_cat13_population.py (~3-5 tests; asserts cat-13
      count >=15 active entities post-seed; asserts category page renders
      without 500 against populated DB)
    - tests/test_phase8b_civic_entity_shapes.py (~3-5 tests; asserts all
      cat-13 entities use entity_type='place' per locked decision; asserts
      sub-categories represented per master plan sec4 Phase 8 list)

LOCKED DECISIONS (resolved 2026-05-20):
- Sub-categories: library + transit + visitor info + utilities + airport +
  senior resources + payment+licensing + civic orgs (8 sub-categories per
  master plan sec4 Phase 8)
- Entity type: ALL cat-13 entities use entity_type='place' per Phase 1
  schema V1 constraint (entity_type IN ('commercial', 'place'); 'place'
  covers public services + civic facilities + nonprofits per app/db/
  models.py:1177)
- Layer split: Layer 3 scraper for ~6 entities (library / transit / airport
  if Layer 3 feasible) + Layer 5 seed script for ~10-12 starter entries +
  operator post-ship admin-form follow-up for remaining ~3-7 entries to
  hit ~20-25 total
- Population threshold: SHIP ship-line is >=15 cat-13 active entities;
  >=20 is stretch
- Filter chips: OMIT in Phase 8b unless operator requests at dispatch
- NO new alembic migration (cat-13 row + Entity table already exist from
  Phase 3.1)
- NO chat module changes (entity catalog reads automatically include
  cat-13 once entities populated; Phase 7's tier2_db_query.py +
  entity_catalog_query.py already handle all 12 active slugs)

ORDER MATTERS WITHIN PHASE 8b:

1. First: read the design doc sec10 end-to-end + master plan sec4 Phase 8
   + Phase 5.11 close-out sec5 (current baseline) + the codebase reads
   listed above. Confirm the 4 operator prereq decisions are resolved
   (Layer 3 source-URL feasibility for library + transit + airport +
   GIS-feed-exists question). If any of the 4 is unresolved, HALT at this
   step + report to operator before resuming.

2. Then: verify schema + baseline. Confirm:
   - python -m alembic current returns d8e9f0a1b2c3
   - python -m alembic heads returns SINGLE head
   - cat-13 baseline = 4 active entities (per Phase 5.11 close-out)
   - Category row for slug='public-civic-resources' exists in categories
     table (from Phase 3.1)
   If any of the above is off, HALT and report.

3. Then: Layer 3 scraper. New scripts/ingest/lhc_civic_scrape.py:
   - Mirrors scripts/ingest/ingest_enrichment_csv.py argparse + logging
     shape; reuse Phase 5 ingest patterns
   - HTTP fetches via httpx (already in deps); User-Agent header convention
   - Parses HTML via BeautifulSoup (verify if already in deps; if not,
     ADD to requirements.txt -- this is the only new Python dep
     Phase 8b should need)
   - Per-source try/except + idempotent upsert (UPSERT on name+address
     match, not blind insert)
   - --dry-run + --source flags for testing
   - Sources: library / transit / airport per prereq feasibility decision

4. Then: Layer 5 seed script. New scripts/seed_cat13_civic.py:
   - Pure-Python dict of ~10-12 starter entities (Chamber, Visitor Bureau,
     Senior Center, Meals on Wheels, Republic, UniSource, water/sewer,
     court portal, business license portal, utility bill pay portal)
   - Each entry: name + address + entity_type='place' + website + hours
     (where known) + category_id mapping to cat-13
   - Idempotent upserts on (name, address) match; never blind-insert
     duplicates
   - --dry-run flag prints planned inserts without committing
   - --commit flag commits the batch (default dry-run for safety)

5. Then: optional category page filter chips. ONLY if operator requested
   at dispatch time. Anchored edit on app/templates/category_landing.html
   adding Government services / Civic groups / Utilities / Transit chips
   that filter cat-13's entity list by a tags-or-attribute match. SKIP
   otherwise (V1.5 carry).

6. Then: test files. Write the 2-4 test files listed in sec(d) above.
   Pytest stay green throughout. Pytest collect delta expected +10-20
   net-new.

7. Then: run scripts end-to-end manually -- python -m scripts.ingest.lhc_
   civic_scrape --dry-run + python -m scripts.seed_cat13_civic --dry-run
   first; review planned inserts; then --commit. Verify final cat-13
   count >=15 via the count snippet from baseline verification.

8. After all of the above: confirm full pytest stays green (post-Phase-8a
   baseline + 10-20 net-new), ruff clean, alembic head UNCHANGED at
   d8e9f0a1b2c3 (no migration shipped). Document Layer 5
   operator-follow-up surface (entities for remaining sub-categories that
   Cursor didn't auto-seed; operator types via admin form post-ship to
   top up to 20-25 entities). Manual smoke deferred-to-operator:
   - python -m fastapi run app.main:app + browse to /category/public-
     civic-resources verify >=15 entity cards render
   - Verify each sub-category has at least 1 representative entity (8
     sub-categories per master plan; some may be Layer 5 follow-up)
   - Verify chat returns library / Chamber / Visitor Bureau on relevant
     queries (e.g. "where's the library?" -- works because Phase 7's
     entity_catalog_query.py handles all 12 active slugs)

POSTGRES COMPATIBILITY (carry-forward from brief sec0 + Phase 1A lesson):
- Phase 8b ships ZERO new migrations. cat-13 row + Entity table already
  exist from Phase 3.1; categories table already has the slug row;
  EntityCategory join table already supports many-to-many. Seed script
  inserts ENTITY rows + ENTITY_CATEGORY join rows via SQLAlchemy ORM;
  no DDL changes.
- python -m alembic heads MUST return SINGLE head at start AND at end
  of dispatch. If multi-head detected mid-flight, HALT and report.
- Re-verify python -m alembic current returns d8e9f0a1b2c3
  at end of session (unchanged from start; no migration shipped).

DEVIATION INVITATIONS (per design doc sec10 + master plan sec4 Phase 8):

- Layer 3 scraper scope: design locks ~6 entities (library + transit +
  airport). If operator's prereq research found additional structured
  feeds (e.g. Mohave County GIS open data with civic facility records),
  flag for expansion. If library hours are JS-rendered or PDF-only,
  scraper falls back to placeholder + flag for Layer 5 follow-up.
- Layer 5 seed-script entity list: design locks ~10-12 starter entries.
  If operator wants different prioritization (e.g. ship Republic Services
  but defer UniSource since rates change frequently), flag.
- Population threshold: design locks >=15 entities ship-line + >=20
  stretch. If operator wants higher bar (e.g. >=25 = all 8 sub-categories
  represented with 3+ entities each), flag and extend Layer 5 seed script.
- Filter chips: design locks OMIT in Phase 8b. If operator wants chips
  now (vs V1.5 deferral), flag + ship chip dispatcher addition.
- Entity-type defaults: design locks 'place' for all cat-13 sub-
  categories. If a specific entity operates as a commercial provider
  with paid services (e.g. private senior-care concierge), 'commercial'
  is the right type -- flag and adjust per entity.
- Sub-category tagging: cat-13 entities may benefit from a sub-category
  tag (e.g. entity.tags='senior_resource' / 'utility' / 'civic_org') for
  the optional V1.5 filter chips. If you add tags now, document the
  taxonomy in docs/data/category_population_briefs/cat_13_*.md.

WHAT NOT TO DO (per design doc sec10 + master plan sec4 Phase 8):

- Don't ship any Phase 8a Lane A or Lane B work (conditions / alerts /
  external_conditions_cache / /api/conditions / /account/alerts). That's
  shipped already at 8a905c6.
- Don't ship Phase 9 events scraper subsystem.
- Don't ship Phase 11 sponsor logic / monetization.
- Don't modify the chat module (app/chat/*). Cat-13 expansion is purely
  data-population; the catalog reads handle the new entities automatically
  once they're in the DB.
- Don't modify the admin form (app/admin/contributions_html.py).
  Layer 5 manual-entry follow-up is OPERATOR follow-up post-ship; Cursor
  doesn't type the remaining ~3-7 entries.
- Don't ship a new alembic migration. cat-13 already exists in the
  categories table from Phase 3.1.
- Don't proceed if python -m alembic heads returns multiple heads. HALT.
- Don't add Python dependencies beyond BeautifulSoup IF needed for HTML
  parsing (and only if not already present). httpx already in deps; no
  RSS / OGC / GIS deps needed.
- Don't bash heredoc commit messages. PowerShell-safe multi-line `-m`
  flags or here-string per session-2026-05-19 lesson #1.
- Don't hardcode alembic head literals in test code (session-2026-05-19
  lesson #4). Phase 8b tests don't touch alembic at all; ignore.
- Don't dispatch Phase 9 or any subsequent lane in the same Cursor
  session. HALT at the sec3 Phase 8b boundary.

HALT at the sec3 Phase 8b boundary. After Phase 8b ships + commits +
pushes, halt for operator re-dispatch in a fresh session for Phase 9
(events scraper + Classes/Sports schedule UX + Things to Do themed group
+ RRULE recurrence) -- architectural design pre-positioned at
outputs/phase_9_architecture_design.md (1620 lines).

Same constraints as Phase 6.1 + 6.2 + 6.3 + 6.4 + Phase 7 + Phase 8a:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 sec12 final report format adapted for Phase 8b
- Re-verify python -m alembic current AND python -m alembic heads and
  report the observed values
- If alembic heads returns multiple heads, HALT and report

Pre-dispatch checklist (verify before paste):

- Phase 8a SHIPPED on origin (8a905c6) -- SHA-patch slot
  must be resolved before paste
- Phase 7.5 SHIPPED on origin (HALT 3 validator 22/22 PASS)
- Phase 7 SHIPPED on origin (0a305e0)
- Phase 6.5 SHIPPED on origin
- Phase 6.4 SHIPPED on origin (96c915d)
- Phase 6.3 SHIPPED on origin (5ebee46) -- /category/public-civic-resources
  route renders
- Phase 5 ledger SHIPPED on origin (3a2d895); cat-13 baseline 4 entries
- d8e9f0a1b2c3 is the current SINGLE alembic head on
  origin (verify via `python -m alembic current` AND `python -m alembic
  heads`)
- Pytest baseline going in matches reality per `python -m pytest
  --collect-only -q | tail -3` (likely 2220-2330)
- The 4 operator prereq decisions are RESOLVED: Layer 3 feasibility for
  library + transit + airport sources; GIS-feed in/out-of-scope
- The 4 operator decisions are LOCKED at design-doc-defaults: 8 sub-
  categories, entity_type='place' across the board, Layer 3+Layer 5
  split (~6 + ~10-12 + operator-follow-up), >=15 ship-line, chips
  OMITTED unless operator-requested
- Master plan sec4 Phase 8 reviewed + acceptance gate L1/L2/L3 noted
  (per design doc sec13.3)
- Phase 9 is NOT in scope (deferred)
- No Phase 8a Lane A / Lane B surface touched (file scope disjoint)
- No chat module changes (file scope disjoint)
````

---

## After Cursor returns with the §12 report

Same rhythm as prior sub-phase ships: paste back to Cowork primary chat, primary reviews against design doc §13.3 success criteria (L1: cat-13 >=15 entities; L2: library hours + Havasu Hopper info present; L3: cat-13 entities appear in chat results) + master plan §4 Phase 8 acceptance gates, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:

- 0 new alembic migrations
- 1 new `scripts/ingest/lhc_civic_scrape.py` (~150-250 lines; Layer 3 HTTP fetches + BeautifulSoup parsing + idempotent upserts; mirrors `scripts/ingest/ingest_enrichment_csv.py` pattern)
- 1 new `scripts/seed_cat13_civic.py` (~100-200 lines; pure-Python starter-entity dict + idempotent upsert helper)
- 0-1 modified `app/templates/category_landing.html` (anchored edit; ONLY if operator-requested filter chips)
- 0-1 modified `requirements.txt` (anchored edit; ONLY if BeautifulSoup not already present)
- 2-4 new test files (per dispatch body §(d)):
  - `tests/test_phase8b_civic_scraper.py` (~6-10 tests)
  - `tests/test_phase8b_seed_script.py` (~4-8 tests)
  - `tests/test_phase8b_cat13_population.py` (~3-5 tests)
  - `tests/test_phase8b_civic_entity_shapes.py` (~3-5 tests)
- 0-1 new `docs/data/category_population_briefs/cat_13_public_civic_resources.md` patch (optional; documents Layer 5 follow-up surface for operator)

Expected pytest delta: +10-20 net-new tests. Pre-existing tests must remain green.

Expected effort: S-M (2-4 days dispatch) per master plan §4 Phase 8 + design doc §14.2 (Phase 8b engineering = 2 days dispatch; this wrapper estimates 2-4 days with buffer for prereq-research-not-yet-fully-done eventualities). Could compress to 1-2 days if Layer 3 scraper has clean targets (library hours scrape-friendly + transit/airport feasibility confirmed) and seed-script entries are well-defined. Could stretch to 4-5 days if Layer 3 fallback paths multiply (library JS-rendered, transit PDF-only, airport federal-only) — Cursor falls back to Layer-5-heavy + a near-empty Layer 3 scraper.

Expected pragmatic deviations:

1. Layer 3 scraper falls back to placeholder for sub-sources operator-research showed are not Layer-3-feasible (library JS-rendered? transit PDF-only? airport federal-only?). Deviation: ship a smaller scraper than design doc §10.3's "~6 entities" target; expand Layer 5 seed script to cover the gap.
2. Entity-type edge case: a specific civic org operates commercially (e.g. paid concierge senior-care). Deviation: `entity_type='commercial'` for that one entity; document.
3. Sub-category tagging taxonomy: if you tag entities with sub-category tags for the future V1.5 filter chips, document the taxonomy (`senior_resource` / `utility` / `civic_org` / etc.) in `docs/data/category_population_briefs/cat_13_*.md`.
4. Filter chips: if operator requests at dispatch time, ship chip dispatcher addition; otherwise OMIT.
5. Population stretch: if Layer 3 + Layer 5 yield >25 entities organically, flag as overshoot (good problem; document the surplus for operator's category-curation review post-ship).

## After Phase 8b ships

Update master plan §4 Phase 8 — append "Phase 8b SHIPPED" line under the existing Phase 8a SHIPPED entry. Update STATE.md "Recently shipped" prepend with Phase 8b close-out narrative (cat-13 expansion from 4 → ≥15 entities; Layer 3 scraper + Layer 5 seed script shipped; operator follow-up surface documented for ~3-7 remaining manual entries).

After Phase 8b is durable, **operator post-ship action**: type the remaining ~3-7 Layer 5 entries via `app/admin/contributions_html.py` admin form to top up cat-13 to 20-25 entities (the full V1 target). This is operator data-entry work, ~30-60 min, not a Cursor dispatch. Documents as the only operator-side carry from Phase 8b.

Phase 9 (events scraper + Classes/Sports schedule UX + Things to Do themed group + RRULE recurrence) dispatch wrapper authored after Phase 8b ships — chains off Phase 8b HEAD SHA. Architectural design pre-positioned at `outputs/phase_9_architecture_design.md` (1620 lines, Plan-agent ADR-level design).

The Phase 8 lane (8a + 8b) is the trust + retention layer plus the cat-13 content-density closure. After both ship, V1 has:
- Real conditions data driving homepage + chat (8a)
- Alert dispatch subsystem with venue-context texture-moat (8a)
- All 13 Tier 1 categories populated to ≥15 entities (8b closes the lone thin slug)

The post-Phase-8 V1 surface area is complete for trust + density; Phase 9 ships events + the Things-to-Do narrative layer; Phase 10+ continue with monetization / V1 acceptance gates.

---

*Authored by Cowork primary at the post-Phase-7.5-ship session (2026-05-20). Lives at `outputs/cursor_dispatch_prompt_phase_8b.md`. SHA-patch slots `8a905c6` + `d8e9f0a1b2c3` need filling post-Phase-8a-ship. Phase 8b is a micro-dispatch (S-M effort; 2-4 days) closing the cat-13 content-density gap from Phase 5.11 (4 entries → ≥15). Companion docs: `outputs/phase_8_architecture_design.md` §10 (authoritative scope spec for Lane C), `outputs/cursor_dispatch_prompt_phase_8.md` (Phase 8a wrapper; structural reference), `outputs/cursor_dispatch_prompt_phase_7_5.md` (micro-dispatch shape mirror), `outputs/phase5_11_session_closeout.md` §5 (current cat-13 baseline). No parallel-lane risk since Phase 8b file scope is disjoint from any other in-flight lane (Layer 3 scraper + Layer 5 seed script + cat-13 entity rows; no chat / no templates beyond optional chips / no migrations).*
