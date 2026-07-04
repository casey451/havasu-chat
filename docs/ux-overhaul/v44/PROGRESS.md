# v4.4 build — PROGRESS (external memory; resume from here)

**How to resume cold:** read this file top-to-bottom, then re-read README/BUILD_PLAN/
DESIGN_SPEC/DATA_CONTRACTS, then continue from **NEXT ACTION** at the bottom. Trust the
gate results recorded here; do not redo a row marked ✅ merged.

## Fixed facts
- Integration branch: `v44-integration`, based off `origin/main` @ `20dfeeec`.
- Work items on `feat/v44-NN-slug` off `v44-integration`; gate (pytest+ruff+refs) →
  merge into `v44-integration` → log here → next. Order is strict PR-1..PR-9.
- Gate command: `.venv\Scripts\python.exe -m pytest -q` green AND `ruff check .` clean.
  After code changes: `graphify update .`.
- Local `main` is stale + worktree-locked (havasu-chat-vpsfix). Never touch it; base
  everything on `origin/main`. Final PR = `v44-integration → main` under the autonomy
  grant, only after ALL gates pass; then post-deploy smoke; revert path on smoke fail.
- Uncommitted noise carried in the tree: `docs/scraper/SCHEDULE_HUNT_PLAN.md`,
  `docs/scraper/schedule_hunt_candidates.csv` — pre-existing, NEVER stage them
  (breaks schedule_drift_check). Always stage explicit paths, never `git add -A`.
- Confirmed real files (no spec naming drift): `app/templates/home_redesign.html`,
  `app/templates/base_redesign.html`, `app/static/styles/lake_redesign.css`,
  `app/templates/components/redesign_icons.html`, `app/templates/_partials/*`.

## Baseline
- ✅ `20dfeeec`: pytest **12463 passed, 13 skipped** (255s); ruff clean.
- Full suite ≈4m15s → use targeted `pytest tests/test_X.py` during dev, full suite before each merge.
- Gate cmds: `.venv\Scripts\python.exe -m pytest -q` ; `.venv\Scripts\python.exe -m ruff check .`
  (bare `ruff` is not on PATH — must go through the venv module).

## Work log (one line per item)
| PR | branch | status | gate | merge sha | notes |
|----|--------|--------|------|-----------|-------|
| 1 gas-truth      | feat/v44-01-gas-truth        | ✅ merged | pytest 12477✅ ruff✅ mypy✅ | commit 2a59edcd → merge e8663045 | GasService single source |
| 2 date-keys      | feat/v44-02-date-keys        | ✅ merged | pytest 12482✅ ruff✅ | commit 20001edb → merge 41d4614b | rollover regression + no-cache pin (tests only) |
| 3 count-parity   | feat/v44-03-count-parity     | ✅ merged | pytest 12485✅ ruff✅ mypy✅ | commit → merge 172d6d07 | day_counts one base (summary headers); cells keep audit display |
| 4 conditions     | feat/v44-04-conditions       | ✅ merged | pytest 12489✅ ruff✅ mypy✅ live✅ | merge 2a54d850 | water+sunset, retire clouds |
| 5 ads-rail       | feat/v44-05-ads-rail         | ✅ merged | pytest 12494✅ ruff✅ mypy✅ smoke✅ | merge 15d2a77f | one paid unit + working rail |
| 6 gas-ui         | feat/v44-06-gas-ui           | ✅ merged | pytest 12499✅ ruff✅ mypy✅ smoke✅ | merge fa4c76aa | grade switch + /gas page |
| 7 schedule       | feat/v44-07-schedule-niceties| ⏳ | — | — | previews/tpills/pills/dots |
| 8 shell          | feat/v44-08-shell            | ⏳ | — | — | 6-link shell + footer/email |
| 9 dead-code      | feat/v44-09-dead-code        | ⏳ | — | — | sweep old UX |
| final            | v44-integration → main       | ⏳ | — | — | grant merge + smoke |

## Judgment calls (decision 15 log)
- **PR-1 cheapest derivation:** the board's `cheapest(grade)` derives from
  `stations` (contract §1.1), not the pull's precomputed `cheapest` list — needed
  because PR-6's grade switch requires mid/prem/dsl cheapest the pull never
  precomputes. For real data these are identical (the pull's `cheapest` IS
  stations-with-regular sorted). Rewrote `test_home_gas_parity` to assert the true
  invariant (all surfaces agree, by construction) + an honest-filter guard.
- **PR-1 >7d on /gas:** per-station hide uses `posted_time` when present; whole-board
  >7d sets `unavailable` (strip tile/panel show "prices unavailable"). /gas renders
  `board.stations` (empty when board >7d). Bumped 3 `test_gas_prices_page` fixtures
  off month-old fixed dates → recent relative dates (they predated this rule).
- **PR-1 honest label is gas-specific:** added `_gas_label` in the service; left the
  shared `staleness_label` untouched (all other conditions tiles + its tests use it).

- **PR-3 cells keep the audit display (decision 15).** §2.1 base is class-dominated
  (real July days: total 48–100, of which 70+ are recurring class sessions). Wiring
  the month cell "+N more = base − chips" would render "+90 more" in every cell —
  reversing the 2026-07-01 audit that moved classes to a "N classes" badge to kill
  that flood, and breaking the glanceable-calendar guardrail. So PR-3 unifies the
  SUMMARY HEADERS users compare (home headline `feed.total` == agenda "N events &
  classes" == `day_counts(d).total`) and fixes the F6 agenda divergence (was
  `len(rows)`, e.g. 42 vs base 48); the glanceable month cell keeps its two honest
  numbers. `day_counts` is exposed for PR-7 dots. Files: NEW `app/home/day_counts.py`;
  `redesign.feed_view_model` + `_agenda` route through it (reusing the vm, no double
  build). Test: `tests/test_count_parity.py`.

- **PR-2 = tests + no-cache pin, no app cache change (decision 15).** Investigated
  exhaustively: routes (/home, /calendar, /events-ui) already resolve today/month
  via `now_lake_havasu()` fresh per request; HTML ships `no-cache, max-age=0,
  must-revalidate` (middleware); the only in-process caches are request-scoped
  (`_LIVE_EVENTS_MEMO` keyed by Session), static-file (`lru_cache`), or short-TTL
  data (conditions 300s, pullquote 1h) — NONE date-blind. Empirical probe confirms
  /home + /calendar + /events-ui roll over correctly. So there is no app render
  cache to date-key; the 6-day prod staleness was edge/CDN caching of bare URLs
  (infra, out of scope per "no railway"). BUILD_PLAN says "TTLs unchanged... do
  not add new perf infra" — so PR-2 correctly ADDS the rollover regression tests
  (the acceptance criterion) + a test pinning `no-cache` on the date-scoped routes
  (the edge-cache guard), and changes no app code. New: `tests/test_date_keyed_pages.py`.

- **PR-4 visual refs NOT regenerable here (decision 15 / missing source).** The
  committed `tests/visual/refs/*.png` are captured by `capture_refs.py` from the
  MOCK `design-exploration/ask-hava-premium-v4.html` — which is NOT in the repo
  (README: mock not required; not committed). So refs can't be regenerated. This
  does NOT block: the visual test self-baselines against a gitignored per-env
  baseline and is skipped in default CI (`RUN_VISUAL != 1`). Verified instead via
  live render (havasu-local preview): the conditions strip shows the computed
  Sunset tile ("7:54" + "pm"), no Clouds, honest-omit working; unit tests pin
  order + water marking + sunset split + clouds removed. Same applies to PR-5/6/7/8
  visual deltas — rely on live preview + unit/template tests, note refs can't be
  mock-regenerated.

**PR-4 scouting (done):** cond strip = `redesign.conditions_tiles` (builds
temp/wind/uv/**clouds**/water_temp/gas) → rendered by `base_redesign.html` cond loop
(home + calendar pass `cond_tiles`). The `_utility_chips` strip (other pages) already
excludes clouds. Sunset infra EXISTS: `app/conditions/sun.py::sunset_utc` (NOAA) +
`api_payload` already exposes `payload["sunset_local"]` ("7:42 PM") and
`payload["water_temp_f"]`/`water_temp_is_stale` — REUSE these, don't reimplement the
DATA_CONTRACTS §3.2 formula. PR-4 = in `conditions_tiles`: drop the clouds block, add a
sunset tile (value = `sunset_local` split → "7:42" + unit "pm", icon `sunset`), mark
water tile `is_water:True` (label "Water", icon `wave`, teal tint), reorder to
Temp·Water·Wind·UV·Sunset·Gas; template: add `water` class + render new tiles; CSS
`.cond .c.water` tint (DESIGN_SPEC §1); add `wave`+`sunset` monoline icons to
`redesign_icons.html` (§8); honest-omit water when absent; update visual refs. Clouds
plumbing residue swept in PR-9.

**PR-7 scouting (done) — depends PR-3 ✅ (day_counts):**
- Date-strip dots: `sandstone.week_strip` (sandstone.py:398) builds the 7 day cards; add an
  `act` field per card from `day_counts(d).total` thresholds (§2.3: 1–19→1 dot, 20–49→2,
  ≥50→3, 0→none) + brass spark for HEADLINER_DATES. Render `<span class="act">` per card in
  the week-strip template (find it — home_redesign uses `week`). CSS §6.4 `.dcard .act`.
- Movies rows: `home_redesign.html` ~l.196-204 — currently `.evt`+`.et`+`.em`+times. §6.1:
  title-first (drop `.evt`), theater `.em`, `.tpill` showtimes; `.tpill` CSS §6.1.
- Counts row: l.174-178 — append `For Kids`/`For Seniors` as `.cpill.places` (brass, no
  count) → /family, /seniors. Icons `kid`(head+shoulders), `people`(two figures) → add to
  redesign_icons.html (§6.3/§8).
- Closed-section `.sp` previews (§6.2): server macro `sec_preview(s)` from section's first 3
  rows (needs `preview_rows`/`time_short` on sections — check what day_groups sections carry;
  may need to add preview_rows). Placed in `.sechd` between `.sc` and `.cv`; hidden when open
  + mobile (CSS §6.2). This is the fiddliest bit — sections need preview data.
- `HEADLINER_DATES` config dict (§8): NEW, seed `{"2026-07-04": "4th of July Fireworks at
  the Beach · 9 PM"}`. No DB. Put in day_counts.py or a config module.

**PR-6 implementation (done, gating):** Home panel grade switch — `redesign.gas_panel_data`
(per-grade top-5 via board.cheapest(grade), drop-off, echo strings, single_grade,
station_count); home + calendar routes pass it; `base_redesign.html` gaspanel gains `.gseg`
segment (aria-pressed) + `#gasList` aria-live + `.gpall` footer + `.gl` tile-echo span +
embedded `gasByGrade`/`gasEcho` JSON (guarded for non-panel gas shapes); `lake_redesign.js`
grade switch (list swap + tile echo + revert-on-close, stateless). `/gas` page: `.gseg.lg`
segment + brass `Cheapest` chip + row data-attrs + inline sort/drop-off JS + honest footnote;
CSS in lake_conditions.css (its own token set). Tests `test_gas_grade_switch_v44.py`.
- **Decision 15 — /gas kept on base_lake, not migrated to base_redesign (v4 shell).**
  DESIGN_SPEC §5.3 says "v4 shell", but /gas already wears the lake shell (nav + conditions
  ribbon) and a full base_lake→base_redesign migration would rewrite ~20 gas-page tests for
  cosmetic chrome — high risk, low user value. Delivered the §5.3 SUBSTANCE (grade segment +
  per-grade sort/drop-off + Cheapest chip + honest clock + footnote + a11y) on the existing
  shell. Full shell migration left for a later polish pass if Casey wants it.
- Gas new visual refs can't be mock-regenerated (mock absent) — same as PR-4/5.

**PR-6 scouting (done) — LARGEST remaining PR (depends PR-1 ✅):**
- Gas panel toggle JS: `app/static/js/lake_redesign.js` l.23-30 (simple open toggle) —
  extend for grade switching (delegated, aria-pressed, aria-live, ~2KB).
- Panel markup: `base_redesign.html` gaspanel (l.70-83), renders `gas.cheapest` (regular).
- `/gas` page: `gas_prices_lake.html` extends `base_lake.html` (OLD shell) — §5.3 wants the
  v4 shell (`base_redesign.html`). Significant rebuild: `.gseg.lg` segment, sorted table,
  brass `Cheapest` tag row 1, stations w/o grade drop off, footnote.
- Data: `gas_top5` returns regular-only. Need per-grade cheapest. Plan: extend the board
  usage — expose `grades_available` + per-grade top-5 (or embed each station's 4 grade
  prices as data for client re-sort). Board already has `cheapest(grade)` + `grades_available`.
- Progressive enhancement: server renders Regular; JS re-sorts. If `len(grades_available)==1`
  → render NO segment anywhere (BUILD_PLAN dec.3). Tile echo while panel open (label gains
  " · Diesel", value swaps; revert on close, stateless).
- Tests: per-grade sort + drop-off; tile echo string; a11y (aria-pressed, aria-live).
  New gas visual refs can't be mock-regenerated (note it).

**PR-5 implementation (done, gating):** NEW `redesign.directory_launcher(db)` (8-cat
map → cached `_get_index_payload` counts, total floor-rounded "2,400+"); route passes
`directory`; template rail rebuilt (launcher card + news card, in-feed + rail ad_placeholders
+ promoted sponsor_slot removed; ad_placeholder/sponsor_slot macros left defined but
uncalled → PR-9 sweeps); 8 dept icons added to redesign_icons.html; CSS §4 railcard/
dirgrid/newsit + responsive (mobile: rail below sections, newscard hidden, ticker shown;
desktop: ticker hidden, newscard shown). Tests: `test_ads_rail_v44.py` (1 marquee/0 slots,
launcher mapping+counts, honest omission). Render smoke vs prod DB: 8 tiles + newscard.
Note: launcher is DB-count-dependent (empty in the test DB → mapping tested via mocked index).

**PR-5 scouting (done):** `home_redesign.html` — macros `ad_placeholder(infeed)`
(l.78), `sponsor_slot(s)` (l.86), `feature-marquee sold` (l.103) / unsold (l.113);
in-feed ad at l.213 (`loop.index % 2 == 0 ... ad_placeholder(infeed=True)`); rail
`<aside class="rail">` l.218–222 = `{% if promoted %}sponsor_slot{% endif %}` + 2×
`ad_placeholder()`. Route (`home/router.py serve_home`) already passes `marquee`
(serve_homepage_placement or sponsor_store.active_marquee), `promoted`, and
`news = news_store.ticker_view(db)`. PR-5 = DELETE the 2 rail ad_placeholders + the
in-feed one + the rail's promoted `sponsor_slot` (§3: promoted never renders on home,
keep it plumbed for category pages); marquee stays the ONLY ad unit (keep macro for
sponsor/portal); rail becomes launcher (§4.1: `directory_total` + 8 category counts,
mini-search → /categories) + news card (§4.2: 3 most recent stored items). Ticker
mobile-only, news card desktop-only. Need: directory count helper (DATA_CONTRACTS §5,
per-category count as /categories uses, cached ≤24h, total floor-rounded hundreds) +
`news_store` recent-3 accessor. CSS from DESIGN_SPEC §4 (.railcard/.dirgrid/.newsit),
marquee keyline §2, add `search`/`arrow` icons if missing.

## PR-1 implementation (files touched)
- NEW `app/gas/__init__.py`, `app/gas/service.py` — `GasStation`/`GasBoard`,
  `board_from_cache` (pure transform = single call site), `load_gas_board`,
  `_gas_label` (§1.3 tiers, no `>Nh` ceiling), `to_legacy_station_dict`,
  GAS_PULL_STALE warn (§1.4, 1/hr throttle).
- `app/home/redesign.py::gas_top5`, `app/home/router.py::_gas_snapshot`,
  `app/api/routes/gas.py` (`_read_board`, `gas_page`, `gas_api`) → all build the
  board from their own `read_source` seam (preserves existing test patches).
- Removed dead `redesign._maps_url` + orphaned imports (dead-code-as-you-go).
- Tests: rewrote `test_home_gas_parity.py`; new `test_gas_service.py` (label tiers,
  >7d hide, cheapest/grades, key normalization); 3 fixture dates in
  `test_gas_prices_page.py`.

## NEXT ACTION (current)
PR-6 ✅ merged (fa4c76aa). START PR-7 (schedule-niceties) on `feat/v44-07-schedule-niceties`
— see "PR-7 scouting". Order: (1) date-strip dots via day_counts in week_strip, (2) movies
title-first + tpills, (3) Kids/Seniors places pills + kid/people icons, (4) closed-section
.sp previews (fiddliest — sections may need preview_rows). Gate → merge → PR-8.

## (prev) NEXT ACTION
PR-4 ✅ merged (2a54d850). START PR-5 (ads-rail) on `feat/v44-05-ads-rail` — see
"PR-5 scouting" below. Delete the 2 rail + 1 in-feed `ad_placeholder()` and the
rail's promoted `sponsor_slot`; build the Find-any-business launcher (directory
counts helper, DATA_CONTRACTS §5) + Local-news card (news_store recent 3); ticker
mobile-only. Marquee stays the only ad unit. CSS DESIGN_SPEC §2/§4. Gate → merge → PR-6.

## (older) NEXT ACTION
PR-3 ✅ merged (172d6d07). START PR-4 (conditions) on `feat/v44-04-conditions`:
per the PR-4 scouting below — in `app/home/redesign.py::conditions_tiles` drop the
clouds block, add a sunset tile (value from `payload["sunset_local"]` split into
"7:42" + unit "pm", icon `sunset`), mark the water tile `is_water:True` (icon `wave`),
reorder Temp·Water·Wind·UV·Sunset·Gas; add `.cond .c.water` tint CSS to
`lake_redesign.css`; add `wave`+`sunset` monoline icons to `redesign_icons.html`;
render new tiles/class in `base_redesign.html` cond loop; honest-omit water when
absent; sunset util already tested (`app/conditions/sun.py`) — add a tile-level test;
update visual refs. Gate (pytest+ruff+mypy) → merge → PR-5.

## (prior) NEXT ACTION
PR-2 gating: run full suite. If green → commit `feat/v44-02-date-keys` (tests only:
`tests/test_date_keyed_pages.py` + PROGRESS), merge into `v44-integration`, mark
PR-2 ✅. Then START PR-3 (count-parity): build one `day_counts(date) -> DayCount`
(DATA_CONTRACTS §2) whose `.total` == what the home feed renders for that date
(events + class sessions + venue-hours rows + movie titles, after redesign._enrich
filters). Wire it to home headline/pills (already F6-pinned — reuse), calendar
month cells (`+N more` = total − chips), agenda header, and expose for PR-7 dots.
Start by reading `redesign.feed_view_model` + `_enrich` (how home computes total
today) and `sandstone.calendar_month` cell counts to unify their base.

**PR-3 scouting (done):**
- Home/agenda base = `events_views.calendar_day_view_model(db, day=d)["total"]`
  = `sum(section counts)` over `day_groups(events_only=False)` + movies section.
  Includes events + classes + venue-hours rows + movies + civic. This IS §2.1's
  base (F6 already pinned home headline/pills to it via `feed_view_model.total`).
- Calendar cells (`sandstone.calendar_month`, sandstone.py:698) count DIFFERENTLY:
  one-off events only for the cell `count`/pills; recurring → separate `class_count`
  badge; venue-hours rows (`_is_venue_hours_row`) and civic meetings EXCLUDED
  (2026-07-01 month audit). That mismatch is the F6 cross-surface bug (home 54 vs
  cell 87 vs agenda 17).
- PR-3 = one `day_counts(db, d, now) -> DayCount` with `.total` == the home base;
  wire home headline/pills (reuse), calendar cell `+N more` (= total − chips
  shown), agenda header, and expose for PR-7 dots. TENSION to resolve per contract
  (§2.1 wins): the month audit deliberately excluded venue-hours/civic from cells;
  unifying to the home base re-includes them in the cell TOTAL (pills stay one-off;
  only the count/"+N more" changes). PERF: month grid needs ~35 per-day totals —
  day_counts must compute the total WITHOUT building the full render tree (share
  day_groups' occurrence/dedup logic), or the 42× full-build is too slow. Parity
  test `tests/test_home_calendar_parity.py` already guards (section,count) tuples —
  keep it green.
