# Cursor Dispatch Prompt — Phase 6.1 (unified Hava card grammar)

> Paste-into-Cursor prompt for the first Phase 6 sub-phase — the critical-first deliverable per master plan §4 Phase 6: a single Jinja partial that renders any ENTITY in any context (category page / search results / themed group landing / profile reference) with the same shell, with place vs event vs commercial differentiation via status-line color + content, NOT separate templates. The heavy-prescriptive operating doc is `outputs/cursor_brief_phase_6_tier_1_ui.md` (read end-to-end, especially §0 + §3.1 + §4 + §5). Phase 6.1 ships the foundation that 6.2-6.5 extend; nailing the grammar here means each subsequent sub-phase composes the card into pages without re-engineering the rendering surface.
>
> **Gating dependency:** Phase 4 of the master build plan COMPLETE on origin (`ac94b6c` 4.4 close-out + SHIPPED). Phase 5 prep on origin: `08bca69` prereq+brief + `62ab3b7` types-mapping expansion + Phase 5 lead-up docs (if committed pre-paste). **Phase 6 builds against the SCHEMA, not against Phase 5 DATA** — Phase 6.1 can dispatch even if Phase 5 hasn't started populating; the card grammar tests use mock fixtures that mirror the Phase 1+3 schema shape.
>
> **Parallel-with-Phase-5 caveat:** if a Phase 5 Cowork chat + Phase 5 Cursor session are running concurrently, the file-scope disjointness rule (gotcha #18) applies. Phase 6.1 touches `app/templates/` + `app/static/` + `app/providers/view_models.py` + `tests/test_phase6_hava_card.py`. Phase 5 sessions touch `app/contrib/` + `scripts/` + `app/db/` (per Phase 5 brief §3 + §4). Zero overlap if both lanes hold scope.
>
> **No operator prereq for Phase 6.1.** No new env vars, no Cloudflare changes, no R2 changes, no Resend changes, no migration. Pure template + CSS + view-model + tests authoring.
>
> **Operator decision-lock BEFORE paste:** the 10 prereq §3 decisions for Phase 6 should be locked (or accepted at recommendation). Most relevant to 6.1: mobile breakpoint 768px (prereq §3.a); sponsor pill styling (prereq §3.b); freshness band thresholds green<30/amber 30-90/red>90 (prereq §3.i). If any of these isn't yet locked, Cursor accepts recommendation defaults from prereq §3 and flags in §13 if it had to assume.
>
> **Author note:** authored at session-23-extension-3 (2026-05-13) alongside the Phase 6 brief + prereq. SHA-patch slots reference the post-Phase-5-prep state: `git log --oneline -10` top should be `62ab3b7` or later (if Phase 5 lead-up docs committed); alembic head `0a1b2c3d4e5f`; pytest baseline 1803.

---

```
Read outputs/cursor_brief_phase_6_tier_1_ui.md end-to-end,
especially §0 (baseline + reads + halt etiquette), §3.1 (Phase 6.1
deliverable list -- unified Hava card grammar), §2 (locked
decisions), §4 (what NOT to do), §5 (risk register), §6 (close-out
criteria).

Phase 4 of the master build plan COMPLETE on origin at `ac94b6c`
(SHIPPED). Phase 5 prep on origin: `62ab3b7` types-mapping
expansion + earlier prereq+brief at `08bca69`. Phase 5 lead-up
docs (boat_access_rubric + manual_recovery_checklist back-fill +
Phase 6 surface artifacts) may or may not be committed pre-paste --
check `git log --oneline -10` and report top SHAs. Pytest collect
baseline going in is **1803** tests (1801 passed + 2 skipped + 30
subtests). Alembic head is **0a1b2c3d4e5f** (Phase 4.1 outbox;
unchanged through Phase 5 prep; Phase 6 ships no migration).

Ship Phase 6.1 ONLY per brief §3.1 -- new
app/templates/components/hava_card.html Jinja partial + new
app/providers/view_models.py::HavaCardViewModel dataclass +
new app/providers/queries.py::build_card_view_model helper +
new app/static/styles/components/hava_card.css + 10-15 new
tests in tests/test_phase6_hava_card.py. **No category landing
pages, no map view, no boat-mode toggle, no homepage rebuild,
no profile extension** -- all of that is 6.2-6.5.

NO OPERATOR DECISION-LOCK BLOCKER for 6.1. Most-relevant prereq
§3 locks accept-at-recommendation if not explicitly set:
- Mobile breakpoint 768px (prereq §3.a)
- Sponsor pill styling: subtle pill + same shell (prereq §3.b)
- Freshness band thresholds: green<30 days / amber 30-90 / red>90
  for Phase 6 places (prereq §3.i)
If any of these turns out to need operator confirmation during
implementation, flag in §13 with the recommendation taken.

ORDER MATTERS WITHIN PHASE 6.1:
1. First: read the docs + source files in brief §0 step 6+7.
   Critical reads: brief §3.1 end-to-end (the scope spec); 
   docs/maintainability/master_build_plan.md §4 Phase 6 (Opus
   design context + Hava card grammar locked-as-critical-first);
   app/templates/provider_profile.html (existing profile template;
   informs what slots a profile-reference card needs);
   app/templates/home.html (existing homepage; informs sub-hero
   shape the card lives in on category pages); 
   app/providers/queries.py (`derive_hero_photo` + `derive_gallery`
   from Phase 2B.1 -- the card's hero image consumer); 
   app/providers/view_models.py (existing view model surface -- 
   informs where HavaCardViewModel fits); app/db/models.py
   (Entity columns the card reads: heat_exposure, crowd_notes,
   boat_access, seasonal_hours, district_id, featured, source,
   updated_at).
2. Then: new app/providers/view_models.py::HavaCardViewModel
   dataclass. Fields: entity_id, entity_type ("commercial" / 
   "place" / "event"), name, profile_url, hero_photo_url (via 
   derive_hero_photo), category_slug, category_label, 
   district_slug, district_name, status_line_text (the "Open 
   until 10pm" / "Tonight at 6:00pm" string -- helper computes
   from entity state + current time), status_line_color ("green"
   / "amber" / "red" / "lake-blue" -- color logic per
   entity_type + freshness band thresholds locked at prereq §3.i),
   freshness_band ("green" / "amber" / "red" based on
   updated_at delta), is_sponsored (bool; renders sponsor pill 
   when true), boat_access_badge (bool; renders when 
   boat_access IS NOT NULL), heat_exposure_pill 
   (None | "shaded" | "outdoor" | "water_adjacent" -- omits 
   when "indoor" or NULL; visible signal for the texture moat). 
   **CRITICAL: do NOT pull entity data inline; HavaCardViewModel 
   is a pure data dataclass consumed by the template.** The 
   builder helper does the DB reads.
3. Then: new app/providers/queries.py::build_card_view_model(
   db, entity_id) -> HavaCardViewModel. Joins Entity + Location
   + Photo (latest is_hero=True status='live') + Category + 
   District + Source (entity.source); applies the freshness band
   computation; applies the status-line text + color computation
   (place_open_now vs event_when vs commercial_open_now branches
   per entity_type). Function-scope ORM imports per gotcha-#17
   discipline if needed; module-top imports OK for Entity / 
   Location / Photo if they're already at module top in 
   queries.py (per existing Phase 2B.1 surface).
4. Then: new app/templates/components/hava_card.html Jinja
   partial. ~150-250 lines. Renders the card from the 
   HavaCardViewModel context object. Sections: hero image with
   sponsor pill overlay (top-left when is_sponsored=True); 
   title + status line with color-coded text (green / amber / 
   red / lake-blue per status_line_color); category chip + 
   district chip + heat_exposure pill + boat_access badge 
   (responsive overflow: stack vertically below 768px); freshness 
   band as colored dot in top-right corner (always visible);
   tap-target full-card-clickable to profile_url (mobile-friendly).
   Empty-slot graceful degradation: missing hero_photo_url renders
   a category-themed placeholder; missing district_slug omits the
   district chip cleanly; etc. **CRITICAL: do NOT use Jinja `if`
   to conditionally include the whole card if no data -- the 
   card always renders something visible. The caller decides
   whether to call this template at all.**
5. Then: new app/static/styles/components/hava_card.css. ~150
   lines of CSS. Mobile-first: base styles at <768px (stacked
   layout); media query at >=768px (horizontal layout). Color
   variables for status_line_color states + freshness_band 
   dot colors. Sponsor pill styling per prereq §3.b (subtle 
   pill, not fancy). Hover state for desktop (subtle elevation).
   Tap-area max for mobile (full card clickable; visual feedback
   on touch). Import from home.css with @import at top of 
   home.css (or operator-prefers-flat-files: just paste the 
   styles inline in home.css -- flag in §13 whichever).
6. Then: 10-15 net-new tests in tests/test_phase6_hava_card.py:
     - HavaCardViewModel dataclass: constructs with all required 
       fields; default values for optional fields
     - build_card_view_model returns HavaCardViewModel from a 
       fixture Entity + Location + Photo
     - status_line_text computes correctly for "open now" 
       (commercial currently within hours) / "closed; opens at X" 
       / "tonight at X" (event today) / "this weekend" (event 
       within 7d) / "last week" (event >7d ago)
     - status_line_color: commercial within hours -> "green"; 
       commercial outside hours -> "amber"; commercial 
       freshness >90d -> "red"; place open -> "green"; place 
       seasonal -> "amber"; event today -> "lake-blue"; etc.
     - freshness_band: <30d -> "green"; 30-90d -> "amber"; >90d 
       -> "red"
     - is_sponsored: renders sponsor pill only when True; 
       absent when False
     - heat_exposure_pill: None for indoor / null; renders 
       string label for shaded / outdoor / water_adjacent
     - boat_access_badge: renders only when boat_access IS NOT 
       NULL
     - Template render smoke: 4 render contexts (category page 
       mock / search results mock / group landing mock / profile 
       reference mock) all render with same template + different 
       view-model fixtures
     - Mobile breakpoint smoke: CSS rules apply correctly at 
       <768px (stacked) vs >=768px (horizontal) -- verify via 
       responsive HTML output OR via CSS rule introspection
     - Empty hero photo: renders category-themed placeholder
     - Empty district: omits chip without breaking layout
7. After all of the above: confirm full pytest stays green 
   (1803 floor + 10-15 net-new), ruff clean. Manual smoke 
   deferred-to-operator: render the 4 contexts in a browser; 
   verify mobile responsive at 320px / 375px / 768px via 
   DevTools.

POSTGRES COMPATIBILITY (carry-forward from brief §0):
- NO migration in Phase 6.1.
- Alembic head stays at 0a1b2c3d4e5f (Phase 4.1 outbox).

DEVIATION INVITATIONS (per brief §3.1):
- ViewModel placement: brief suggests app/providers/view_models.py;
  if app/components/view_models.py reads cleaner with the 
  components/* template directory pattern, flag in §13 with 
  rationale.
- CSS file location: brief suggests app/static/styles/components/
  hava_card.css; alternative flat-file location acceptable -- 
  flag whichever.
- Test file: brief suggests tests/test_phase6_hava_card.py; if 
  existing tests/test_provider_profile.py shape carries 
  regression coverage already, augment instead of new file.
- Freshness anchor: brief locks entities.updated_at; alternative
  entities.last_verified_at (Phase 3.1 column) acceptable if 
  signals data freshness better -- flag if switched.
- Sponsor pill rendering: brief locks "subtle pill" per prereq
  §3.b; if visual hierarchy needs adjustment for accessibility
  (color-contrast minimums) flag in §13.

WHAT NOT TO DO (per brief §4 + §5):
- Don't ship category landing pages in 6.1. Phase 6.2.
- Don't ship map view in 6.1. Phase 6.4.
- Don't ship boat-mode toggle in 6.1. Phase 6.4.
- Don't ship homepage rebuild in 6.1. Phase 6.5.
- Don't ship profile extension in 6.1. Phase 6.5.
- Don't add new schema migrations. None needed.
- Don't change /api/search response shape. Phase 6 reads via /api/
  search but doesn't extend it.
- Don't add admin form for operator-curated field entry. Phase 6.5 
  LATE or V1.5.
- Don't add frontend framework. Stays on Jinja2 + vanilla JS per 
  prereq §4.5 lock.
- Don't add new Python dependencies. The card grammar uses 
  existing Pillow / R2 derive_hero_photo + existing Jinja 
  rendering.
- Don't bypass Phase 1D dual-write. Card reads via existing 
  app/providers/queries.py helpers.
- Don't dispatch Phase 6.2 in the same Cursor session. HALT at 
  the §3 Phase 6.1 boundary.

HALT at the §3 Phase 6.1 boundary. After 6.1 ships + commits + 
pushes, halt for operator re-dispatch in a fresh session for 
Phase 6.2 (first category page template + Eat & Drink proof).

Same constraints as Phase 4 sub-phases:
- Anchored Edit on existing files; Write only for new files
- No git add / commit / push / amend (operator commits)
- Pytest must stay green throughout
- Report per Phase 4 §12 final report format adapted for 6.1

Pre-dispatch checklist (verify before paste):
- Phase 4 SHIPPED on origin (`ac94b6c`)
- Phase 5 prep on origin (`62ab3b7` + earlier `08bca69`)
- 0a1b2c3d4e5f is the current single alembic head on origin
- Pytest baseline going in is 1803 (or matches reality per
  `python -m pytest --collect-only -q | tail -3`)
- 10 prereq §3 decisions accepted at recommendation (or 
  operator-revised before paste); §2 of brief reflects the 
  final locks
- Phase 5 chat (if running) is in a sub-phase that doesn't 
  touch app/templates/ or app/static/ -- verify per gotcha #18
```

---

## After Cursor returns with the §12 report

Same rhythm as Phase 4 sub-phases: paste back to the Cowork primary chat, primary reviews against §3.1 acceptance gates + brief §4 design rails, recommends commit batch (Rule 8), operator commits + pushes.

Expected files touched:
- 1 new `app/templates/components/hava_card.html` (Jinja partial; ~150-250 lines)
- 1 new `app/static/styles/components/hava_card.css` (or appended to home.css; ~150 lines)
- 1 modified `app/providers/view_models.py` (HavaCardViewModel dataclass appended; ~30-50 lines)
- 1 modified `app/providers/queries.py` (`build_card_view_model` helper appended; ~30-50 lines)
- 1 new test file `tests/test_phase6_hava_card.py` (~10-15 tests)

Expected pytest delta: +10-15 net-new tests. Pre-existing Phase 4 + Phase 5 prep tests must remain green.

Expected effort: 4-7 days dispatch per brief §3.1; one or two Cursor sessions realistically (one session for ViewModel + template + CSS + first 5 tests; possibly second session for the remaining 5-10 tests + mobile responsive verification).

Expected pragmatic deviations:
1. ViewModel placement (view_models.py vs components/view_models.py)
2. CSS file location (components/hava_card.css vs flat-file in home.css)
3. Test file scope (new file vs augment existing test_provider_profile.py)
4. Freshness anchor (updated_at vs last_verified_at)
5. Sponsor pill accessibility tweaks if color contrast minimums force rework

## After Phase 6.1 ships

Update master plan §4 Phase 6 — add Phase 6.1 entry under "Shipped (incremental)" subsection (Cowork primary creates if first sub-phase; subsequent sub-phases append). Update STATE.md Production block + Recently shipped §1 prepend with the 6.1 close-out narrative.

Phase 6.2 dispatch prompt to be authored after 6.1 ships — chains off whatever 6.1's HEAD SHA is; alembic head stays at `0a1b2c3d4e5f` (Phase 6 ships no migrations). 6.2 dispatch is gated on 6.1 close-out + operator design-review.
