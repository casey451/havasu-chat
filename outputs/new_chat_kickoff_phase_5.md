# New Cowork Chat — Phase 5 Kickoff Prompt

> Paste the block below into a fresh Cowork chat when you're ready to start Phase 5 work. Pre-positioned at session-23-extension-3 (2026-05-13) after Phase 4 SHIPPED on origin.

---

```
You are Cowork primary continuing the havasu-chat build plan in a fresh chat dedicated to PHASE 5 (Tier 1 data gathering). Phase 6 (Tier 1 UI build) is running in PARALLEL in a separate Cowork chat at outputs/new_chat_kickoff_phase_6.md. Coordinate via origin commits — both chats pull origin/main at session start; both chats only edit files in their declared scope (gotcha #18 reminder). Phase 5 chat touches app/contrib/* + scripts/* + app/db/*; Phase 6 chat touches app/templates/* + app/static/* + app/providers/view_models.py + app/providers/queries.py + new app/api/routes/* + new tests/test_phase6_*.py. Strict-disjoint at file level.

## State of the world (as of paste time — verify with `git log --oneline -10`)

**Phase 4 of the master build plan COMPLETE on origin** (all 4 sub-phases shipped 2026-05-13):
- Phase 4.1 (background-jobs scaffold + Outbox must-not-lose surface): `91cd37b` feat + `f5b3953` ruff autofix + `a75cfe8` docs ship-line
- Phase 4.2 (layered-scrape client interface + Google Places refactor): `aaac4db` chore dispatch prompt + `86eeaf8` feat + `2ab5f07` chore + `997cdc3` docs ship-line
- Phase 4.3 (OSM Overpass Layer-2 client + cross-layer reconciler): `2f87211` feat + `2eb2759` docs ship-line
- Phase 4.4 (close-out: runbook + scrape-logs template + with_retry wrappers + master plan SHIPPED): `ac94b6c` feat

**Phase 5 forward-positioning COMPLETE on origin** (4 artifacts):
- `08bca69` chore(outputs) — Phase 5 prereq checklist + Tier 1 brief
- `62ab3b7` feat(phase5-prep) — google_types_mapping expansion (Tier 1 types coverage) + beauty-skip lock + places_discovery docstring fix
- Phase 5 lead-up docs back-filled at session-23-extension-3 (commit pending):
  - `docs/operations/boat_access_rubric.md` (new file, ~250 lines) — per-venue-type JSON shapes for the boat_access Phase 3.1 column; locks the rubric Phase 5 §3.2 on-the-water needs and Phase 6 boat-mode toggle consumes
  - `docs/maintainability/manual_recovery_checklist.md` (back-fill, ~250 lines added) — §1-§6 body items back-filled with field-work prompts (where to look, what to record, expected counts, per-entry patterns); §7 field-trip planner extended with 6 concrete geographic route clusters + sequencing recommendation

**Production deploy status:** Phase 4 + Phase 5 prep all on origin/main; **production Railway not yet redeployed.** Production alembic head still at `e1f2a3b4c5d6` (Phase 3.2 from session-22 deploy); origin alembic head at `0a1b2c3d4e5f` (Phase 4.1 outbox table). Phase 4 redeploy is the operator's first concrete pre-Phase-5 action.

**Pytest baseline:** 1803 collected (1801 passed + 2 skipped + 30 subtests). All Phase 4 + Phase 5 prep tests green. Ruff clean.

## Reading order for this chat's first session

1. `docs/STATE.md` end-to-end — production state, recently shipped, session lessons absorbed (gotcha #18 in particular: Cursor reverts Cowork-parallel edits to its scope; only safe to edit files outside Cursor's session-current scope during parallel work)
2. `outputs/phase5_prereq_checklist.md` end-to-end (~330 lines) — operator decisions + external verifications + workload audit + Phase 4 dependency check
3. `outputs/cursor_brief_phase_5_tier_1_data.md` end-to-end (~640 lines) — per-category playbooks + tooling-touchup queue + operator daily/weekly rhythm + close-out criteria
4. `docs/operations/boat_access_rubric.md` (~250 lines) — JSON shapes for the boat_access field (relevant when Phase 5 §3.2 on-the-water dispatches)
5. `docs/maintainability/manual_recovery_checklist.md` (~600 lines after back-fill) — Layer 5 field-work prompts per category (relevant when each Phase 5 category Layer 5 step runs)
6. `docs/maintainability/master_build_plan.md` §4 Phase 5 + Phase 6 (briefly — for context on the parallel UI lane)

## Phase 5 lead-up tasks remaining (operator + Cowork primary)

Per `outputs/phase5_prereq_checklist.md` §9 timeline:

**Lead-up week 1 (operator-driven; ~3-4h spread):**
- [§4 external verifications] 10 data-source checks: AZ ROC, LHC Parks & Rec, LHC business licenses, Mohave County GIS, NPI registry, USAPickleball, PDGA, Google Places billing posture, OSM Overpass rate posture, parks-rec-scrapes workflow health
- [Railway redeploy] Deploy Phase 4 changes to production; alembic walks one migration (`e1f2a3b4c5d6 → 0a1b2c3d4e5f` outbox table); the `with_retry` wrappers go live

**Lead-up week 2 (operator + Cowork primary; ~3-4h):**
- [§3 operator decisions] Lock 11 decisions: §3.1.a beauty_personal_care (recommendation: skip in Phase 5 — already codified in `google_types_mapping.py:127-129`); §3.1.b RV-park-vs-lodging-vacation-rentals (recommendation: lodging-vacation-rentals — already locked in mapping); §3.2.d-f sequencing decisions; §3.3.g-i field-entry rubrics (boat_access rubric already authored — operator reviews; heat_exposure priority-30 list operator brainstorms; crowd_notes long-form scope locks)
- [Brief §2] Fill Phase 5 brief section §2 with locked decisions once operator closes them (currently placeholder)
- [Phase 5 first scrape] Eat & Drink warm-up category per brief §9 sequencing once lead-up closes

## Phase 5 execution lanes (operator chooses pace)

After lead-up closes, the brief's §3.1-§3.6 per-category playbooks dispatch one category at a time over the 4-8 week execution window. Recommended start: §3.1 Eat & Drink (warm-up, single-layer Google scrape, no Layer 3/4).

Tooling-touchup tasks (§4 stubs) author as Phase 5 surfaces real-data needs:
- §4.b AZ ROC license cross-reference script (~4-6h Cursor dispatch — author after §4.1 verification confirms endpoint shape)
- §4.c NPI cross-reference wrapper (~2-4h — author when §3.4 health-wellness-care dispatches)
- §4.d OSM JSONL → DB load path script (~3-5h — author when §3.2 on-the-water dispatches)
- §4.f Phase 5 admin form shim (~8-12h — only if Phase 6 admin form lags + operator finds direct-DB entry too slow)
- §4.g reconciler GEO_PROXIMITY_THRESHOLD_M tuning (~30 min — only if first per-category scrape produces >50 ambiguous geo-within-50m hits)

## What today's first session should do

Pick one of these as the opening task (or propose alternative):

**A. Commit the Phase 5 lead-up docs that landed in the prior chat** (`docs/operations/boat_access_rubric.md` + `docs/maintainability/manual_recovery_checklist.md` back-fill). `git status` should show these two files as modified/new. Single chore-docs commit + push. ~10 min.

**B. Knock out §4 external verifications** (operator browser work; ~3-4h spread across sessions). Cowork primary can stay quiet during the operator's verification time; surface back at end of each batch with what was found / blocked.

**C. Author the Phase 5 §3.1.c expanded types-mapping items the operator wants to defer or extend** — if the operator looks at the §3.1 Eat & Drink types coverage and wants to add more (e.g., `food_court`, `juice_bar`, `donut_shop`), Cowork primary adds them to `google_types_mapping.py` per the same pattern as `62ab3b7`.

**D. Lock the §3 operator decisions** by having Cowork primary surface each one as an AskUserQuestion and updating Phase 5 brief §2 with the locked answer. ~30-60 min.

**E. Operator does Railway redeploy** (no Cowork work; operator-only). Surface back when deployed for verification check.

## Constraints + reminders

- Phase 5 is operator-driven, multi-week. No single Cursor dispatch closes Phase 5.
- HALT etiquette: each per-category run + each tooling-touchup is its own natural HALT boundary. No sub-phase chain like Phase 4.
- Gotcha #18 lesson: when running parallel work alongside a Cursor session, ONLY edit files outside Cursor's session-current scope. New files in `outputs/` are always safe. Existing files Cursor's brief references are at risk of Cursor reverting them as out-of-scope.
- Pytest must stay green throughout. Run `python -m pytest -q` after any code change.
- Ruff must stay clean. Run `python -m ruff check <paths>` after any code change.
- No git add / commit / push / amend by Cowork primary. Operator commits per Rule 2 + 12.
- Commit message reminder (gotcha #16): no embedded double-quotes inside `-m '...'` bodies on PowerShell. Use hyphens, em-dashes, or rephrase.

## First operator action when you paste this

After confirming the state above with `git log --oneline -10` + `python -m pytest -q --collect-only | tail -3` + `python -m alembic heads`, decide between options A-E above (or propose alternative). I'll execute the chosen lane in this chat.
```

---

## After Cowork primary returns

Same rhythm as Phase 4 sessions: paste responses back, primary reviews, operator commits + pushes per Rule 8 batching. Phase 5 sessions tend to be shorter than Phase 4 sessions because most work is operator-driven (verifications, decisions, field-work) with brief Cowork glue.

## File inventory for the new chat

**On origin (committed as of `62ab3b7`):**
- `outputs/phase5_prereq_checklist.md`
- `outputs/cursor_brief_phase_5_tier_1_data.md`
- `outputs/cursor_dispatch_prompt_phase_4_1.md` through `phase_4_4.md` (historical reference)
- `outputs/cursor_brief_phase_4_background_jobs_scrape.md` (historical reference)

**On origin (committed as of Phase 4.4 `ac94b6c`):**
- `docs/operations/railway_scheduled_jobs_runbook.md`
- `docs/operations/scrape_logs_template.md`

**In working tree, awaiting commit (this session's lead-up authoring):**
- `docs/operations/boat_access_rubric.md` (new file, ~250 lines)
- `docs/maintainability/manual_recovery_checklist.md` (modified, ~250 lines added via §1-§6 back-fill + §7 route-cluster extension)

Single chore-docs commit covers the new-and-modified pair:

```powershell
git add docs/operations/boat_access_rubric.md docs/maintainability/manual_recovery_checklist.md

git commit -m 'chore(docs): Phase 5 lead-up doc back-fill -- boat_access rubric + manual_recovery_checklist content' `
           -m 'New docs/operations/boat_access_rubric.md (~250 lines): per-venue-type JSON shapes for the entities.boat_access Phase 3.1 column. Four canonical shapes: marina (ramps/slips/fuel/haul_out/pump_out/transient_dock/fee), public_ramp (trailer_ramp/kayak_launch/dock_walk_m/parking_spaces/trailer_parking_spaces/fee/restroom/lighted), beach (trailer_ramp/kayak_launch/swimming_marked/lifeguard/shade_structures/parking_spaces/fee/motorized_boats_ok), shoreline_commercial (dockable/ramp_walkable_m/guest_dock/guest_dock_slips/guest_dock_time_limit_min/fuel). Plus NULL-vs-empty-vs-populated semantic locks, 4 illustrative LHC examples, operator entry tips, Phase 6 consumer reference. Locks the rubric Phase 5 section-3.2 on-the-water playbook and Phase 6 boat-mode toggle both consume. Authored per Phase 5 prereq checklist section-3.3.i lead-up task.' `
           -m 'Modified docs/maintainability/manual_recovery_checklist.md (~250 lines added): back-fill of section-1 through section-6 body items per Phase 5 prereq section-3.4.j. Sections covered: section-1 Community recreation facilities (dog parks / Little League / pickleball / tennis / soccer / basketball / skate park / disc golf / playgrounds); section-2 Public infrastructure / outdoor places (boat ramps / beaches / fishing / overlooks / hiking / OHV / restrooms / picnic); section-3 Hobbyist clubs (RC / model railroad / shooting / skating / bowling / arcade / climbing / car / boating / aviation); section-4 Ephemeral / seasonal / recurring (farmers markets / food trucks / weekly meet-ups / seasonal events / music nights); section-5 Non-business places (historical markers / civic / public art / London Bridge POIs / Lake Havasu lighthouses); section-6 Tier-2 manual recovery (mom-and-pop home services / specialty shops / word-of-mouth trades). Each section has "where to look" prompts + expected count ranges + per-entry pattern + operator notes. Section-7 field-trip planner extended with 6 concrete geographic route clusters (north-side / downtown / English Village / Lakefront / 95 corridor / off-island) plus sequencing recommendation (Lakefront first for boat-mode-critical density, English Village second, etc.).' `
           -m 'Both docs are field-work prompts -- where to look, what to record, expected counts -- NOT a populated venue inventory. Operator generates specific entries during Phase 5 Layer-5 passes per category over the 4-8 week execution window.' `
           -m 'No code changes. No migration. No pytest delta. Phase 5 lead-up artifacts now complete on origin; first scrape (eat-drink warm-up per brief section-9 sequencing) dispatchable after operator closes section-3 decisions + section-4 verifications.'

git push origin main
```

After that commit lands, **the new-chat kickoff prompt above is fully aligned** with origin state. Paste it into the fresh chat whenever ready.
