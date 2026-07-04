# v4.5 build — PROGRESS (external memory; resume from here)

**Resume cold:** read this top-to-bottom, then re-read v45/README + v45/BUILD_PLAN +
v44/DESIGN_SPEC + v44/DATA_CONTRACTS, then continue from **NEXT ACTION**. Trust the
gates recorded here; never redo a ✅ row.

## Fixed facts
- Integration branch `v45-integration` off `origin/main` @ `50d3ae90` (the deployed v4.4).
- Items on `feat/v45-NN-slug` off `v45-integration`; gate → merge into `v45-integration`
  yourself → log here → next. STRICT order PR-0 → PR-7.
- Gates: `.venv\Scripts\python.exe -m pytest -q` green AND `.venv\Scripts\python.exe -m
  ruff check .` clean AND `.venv\Scripts\python.exe -m mypy app` clean. `graphify update .`
  after code. (bare `ruff`/`mypy` not on PATH — go through the venv module.)
- Local `main` worktree-locked → base on `origin/main`. Final = ONE `v45-integration →
  main` PR under the kickoff grant after all gates + post-deploy smoke; revert path on fail.
- NEVER stage `docs/scraper/SCHEDULE_HUNT_PLAN.md` / `schedule_hunt_candidates.csv`
  (pre-existing noise). Explicit paths only, never `git add -A`.
- The v4 language lives in `base_redesign.html` + `lake_redesign.css` +
  `components/redesign_icons.html`; when in doubt a component looks like home does.
- Full suite ≈3–4 min → targeted tests during dev, full suite before each merge.
- Reusable: `scripts/run_local_preview.py` (havasu-local launch profile = throwaway
  SQLite, never prod) for live QA; §Refs = capture from LOCAL live render.

## Baseline
- ✅ `50d3ae90`: pytest **12514 passed, 13 skipped** (234s); ruff clean.

## Work log (one line per item)
| PR | branch | status | gate | merge sha | notes |
|----|--------|--------|------|-----------|-------|
| 0 punchlist  | feat/v45-00-punchlist       | 🔨 gating | 2✅ ruff✅ mypy✅; full suite next | — | gas footer literal dropped; /news date → Phoenix via router `news_updated_label` |
| 1 events-ui  | feat/v45-01-events-ui       | ⏳ | — | — | /events-ui → v4 shell, emoji pill → places |
| 2 gas-shell  | feat/v45-02-gas-shell       | ⏳ | — | — | /gas → base_redesign (rewrite ~20 tests) |
| 3 movies     | feat/v45-03-movies          | ⏳ | — | — | /movies body v4 (keep posters/tpills) |
| 4 directory  | feat/v45-04-directory       | ⏳ | — | — | /categories + listing pages v4 |
| 5 remaining  | feat/v45-05-remaining-pages | ⏳ | — | — | family/seniors/provider/legal + provider fixes |
| 6 water-temp | feat/v45-06-water-temp      | ⏳ | — | — | dependable gauge + retry + WATER_TEMP_STALE |
| 7 dead-shell | feat/v45-07-dead-shell      | ⏳ | — | — | delete base_lake + old ribbon/cards |
| final        | v45-integration → main      | ⏳ | — | — | grant merge + smoke |

## PR-1 scouting (done)
- `serve_events_ui` (home/router.py:378) renders `events_lake.html` (303 lines, extends
  base_lake; 4 modes: today/day/week/month). Context: `mode`, `groups` (==
  calendar_day_view_model sections, SAME as home feed), `week_rows`, `calendar`,
  `swipe_weeks`, `day_label`, `family_qs`, `_h1`. Emoji pill: `events_lake.html:136`
  `<span aria-hidden="true">🧒</span> For kids` → replace with `.cpill.places` + `kid` icon.
- Home's row/section macros (`ev_row`, `sub_tree`, `sec_preview`) live INLINE in
  home_redesign.html. Plan says reuse not fork → EXTRACT to a shared partial
  (`components/feed_macros.html`), import in home_redesign + new `events_redesign.html`.
- PR-1 = new `events_redesign.html` extends base_redesign (cond strip via cond_tiles+gas —
  serve_events_ui must ALSO pass cond_tiles+gas_panel_data like home/calendar do), serif
  heads, `.cpill` view toggle, section accordions via the shared macros, v4 week/month.
  Keep URLs/params/counts (parity tests: test_home_calendar_parity, test_events_ui_views).

## Judgment calls (decision 15 log)
- (none yet)

## NEXT ACTION
Baseline gate on `50d3ae90` (pytest+ruff+mypy). Then PR-0 (`feat/v45-00-punchlist`):
(1) gas panel footer in `base_redesign.html` prepends literal "updated" before
`gas.staleness_label` (which already starts "Updated") → "updated Updated today…";
drop the literal so it reads "All {n} stations · {label} →". (2) /news "Updated {date}."
uses a UTC date → use `now_lake_havasu()` Phoenix date. Add tests for both.
