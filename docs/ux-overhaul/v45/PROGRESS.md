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
| 0 punchlist  | feat/v45-00-punchlist       | ✅ merged | pytest 12516✅ ruff✅ mypy✅ | merge 02ceafcf | gas footer literal dropped; /news date → Phoenix via router `news_updated_label` |
| 1 events-ui  | feat/v45-01-events-ui       | ✅ merged | pytest 12515✅ ruff✅ mypy✅ live-QA✅ | merge 978cf71e | /events-ui → v4 shell, emoji pill → places |
| 2 gas-shell  | feat/v45-02-gas-shell       | ✅ merged | pytest 12515✅ ruff✅ mypy✅ live-QA✅ | merge 6e2e5f32 | /gas → base_redesign |
| 3 movies     | feat/v45-03-movies          | ✅ merged | pytest 12516✅ ruff✅ mypy✅ live-QA✅ | merge 991876ea | /movies → v4 shell, posters/tpills kept, rating→.tg, no head-art |
| 4 directory  | feat/v45-04-directory       | ✅ merged | pytest 12517✅ ruff✅ mypy✅ live-QA✅ | merge f2dab10d | /categories index+dept+trade+leaf+faceted → v4; card v4 + SVG star (no ★); cond+gas via _chrome_context |
| 5 remaining  | feat/v45-05-remaining-pages | ✅ merged | pytest 12520✅ ruff✅ mypy✅ live-QA✅ | merge f8e8094e | 12 pages → v4 (about/help/contact/privacy/terms/seniors/login/sponsor/portal/family/night/provider/chat); SVG star+heart; provider fixes already present |
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

## PR-3 scouting (done)
- `/movies` = `app/movies/router.py` → `movies_lake.html` (11 lines: extends base_lake, loads
  desert_movies.css, `{% block content %}` includes `movies_body.html`). The real markup +
  poster/showtime/rating structure is in `movies_body.html` (mv-* classes, desert_movies.css).
  PR-3: NEW `movies_redesign.html` extends base_redesign (block main), v4 body (serif Fraunces
  heads, v4 day cards, KEEP real posters + time-pill buttons, rating badges PG-13 → `.tg` chips);
  route renders it. Add v4 movie CSS to lake_redesign.css. Read movies_body.html first for the
  poster/rating/showtime data shape. Update movies tests that assert mv-* / base_lake markers.

## PR-2 implementation (done, gating)
- gas_prices_lake.html now extends base_redesign (block main, `.gaswrap`, serif heads, v4 crumbs);
  removed lake_conditions.css link. base_redesign gains `cond_gas_plain` → the /gas gas cond-tile
  renders as a plain span (no #gasTile button/#gasPanel). gas.py `_shell_context` now returns
  cond_tiles+today_label+cond_gas_plain+active_tab (no `gas`, so no panel). Kept all PR-6 substance
  (grade segment, all-grade matrix table, Cheapest chip, honest clock, sort JS). Ported the gas-body
  CSS to lake_redesign.css (v4 tokens: brass-deep→brass, ink-2→ink2, muted→ink3, etc.), scoped under
  `.gaswrap`; `.gseg.lg` already existed; added `.chp`. lake_conditions.css stays for /today (untouched).
- Only 4 shell-coupled tests needed rewriting (not ~20 — the rest are substance): test_gas_prices_page
  (2: v4 css + plain gas tile), test_lake_conditions (1: lake_redesign.css). Substance tests
  (city avg, cheapest, table, sort, honest clock, no-station>7d) all still green.
- Live QA (havasu-local, seeded gas): full body renders (avg $3.55, 3 cards, Cheapest chip, 4-grade
  segment, 3 rows); no mobile overflow; the wide table scrolls inside .gas-table-wrap.

## PR-2 scouting (done)
- `/gas` = `app/api/routes/gas.py::gas_page` → `gas_prices_lake.html` (extends base_lake).
  PR-2: make it extend `base_redesign.html`. Pass `cond_tiles`+`today_label` (+ `active_tab`).
  §5.3: the gas cond-tile on THIS page is a PLAIN SPAN (no caret/panel) — add a base_redesign
  flag `cond_gas_plain` so the cond loop renders the gas tile as `<span>` (showing the price)
  and DON'T pass `gas` (so the `{% if gas and gas.cheapest %}` panel is skipped). Keep PR-6
  substance: `.gseg.lg` grade segment + all-grade matrix table + Cheapest chip + honest clock
  + inline sort JS. Move the .gseg.lg/.chp/.gsegwrap CSS from lake_conditions.css → lake_redesign.css.
  REWRITE the ~20 test_gas_prices_page.py tests (shell-coupled: base_lake markers, .crumbs,
  lake_conditions.css) to the base_redesign shell (sanctioned, §Pre-answered 4).

## PR-1 implementation (done, gating)
- NEW `components/feed_macros.html` (tags/ev_row/sub_tree/sec_preview/section) — extracted
  from home_redesign so /events-ui reuses them (not forked). home_redesign imports + uses
  `section()`. NEW `events_redesign.html` (extends base_redesign; today/day via section(),
  week = v4 `.ev` day-list `wklist`, month = v4 `.calgrid/.calmonth` grid; cpill Today/Week/
  Month toggle; `.cpill.places` For Kids/For Seniors — emoji 🧒 GONE; breadcrumb+ItemList
  JSON-LD ported for SEO). serve_events_ui passes cond_tiles+gas_panel_data+today_label+
  month_label, renders events_redesign. CSS: `.evx/.crumbs/.evnav/.wklist/.calwd/.calnote`.
- ev_row now renders a pageless row (no url) as a `<div>`, never `href="#"` (fixed a latent
  dead-link the extracted macro would have introduced on /events-ui).
- Tests updated to v4 markup (data-group→data-k, ev-acc→sec, ev-week→wklist, ev-daynav→evnav,
  mcal→calmonth, lake_events.css→lake_redesign.css): test_events_ui_views, test_wp3_events_
  surfaces, test_lake_events, test_movies_in_events_ui, test_movies_lake_parity,
  test_class_row_links, test_posters_calendar_fixes. New PR-1 acceptance (v4 shell + zero emoji).

## Judgment calls (decision 15 log)
- **PR-1 swipe carousel dropped.** Old /events-ui had a mobile swipe-carousel + a simplified
  Day/Full-calendar toggle. v4 uses ONE language: the Today/Week/Month cpill toggle (horizontally
  scrollable on mobile) + the month grid with dots on mobile — exactly what /calendar does. So
  the swipe carousel + `ev-seg-m` toggle are gone; `swipe_weeks` context is now unused (drop in
  PR-7). Rewrote the 2 posters_calendar_fixes tests to the v4 grid/list. Live QA: no mobile overflow.
- **v4.5 refs (§Refs) — live-QA instead of committed PNGs (decision 15).** §Refs wants refs
  captured from the local render via capture_refs.py, but capture_refs.py reads the absent mock
  and repointing it per-page is heavy; the visual test is self-baselining + CI-optional. Verifying
  each migrated page via the havasu-local preview (structure + mobile-fit) instead, logged per PR.

## PR-4 implementation (done, merged f2dab10d)
- 4 templates (categories_index_lake / category_department_lake / category_trade_lake /
  category_sandstone_lake) now `extends base_redesign`, `{% block main %}`, `.dirx` wrapper,
  drop lake_directory.css. Router: `_chrome_context(db, now)` gained cond_tiles+gas (both
  `_safe`-guarded) → spread into all 5 render points incl. the index.
- lake_biz_card.html → v4: serif name, `.tg` Sponsored chip, teal Open-now, `.btn-ghost`
  View/Call, real photo OR **no image block** (old `ph--art` monogram dropped, §0 guardrail 3).
- Rating star = new inline SVG `star` icon in redesign_icons.html (NOT `★` U+2605), so the
  directory carries zero emoji codepoints. `.dirx .pagehead h1` / `h2.also-sec` give Fraunces
  via CSS so page headings keep bare `<h1>`/`<h2 class="also-sec">` markers (SEO/test-stable).
- Directory CSS ported into lake_redesign.css (v4 palette; --brass-deep→--brass, --muted→--ink3,
  --raised→--surface, --sh-1→--sh-sm, etc.). Responsive: exgrid/leafgrid auto-fill, scrollable
  toolbar/dates, bizcard wraps <560px.
- GOTCHA logged: attribute-adjacency — a `class="x serif"` breaks `assert 'class="x"' in body`;
  headings keep a single class and get Fraunces from scoped CSS. 7 leaf/trade/wp5 h1/also-sec/
  cat-empty exact-match tests were fixed this way (not by loosening asserts).
- The 404 page (hit when a leaf slug doesn't resolve in an empty DB) is still base_lake — it's a
  utility/error template, out of PR-4 scope (belongs to PR-5/PR-7 sweep). Directory listing pages
  themselves are v4 (verified via prod-DB TestClient render: dirx/listcard/extile/leaftile,
  zero emoji, base_redesign shell on index+dept+trade+leaf).

## PR-5 implementation (done, merged f8e8094e)
- Editorial/legal (about/help/contact/privacy/terms/seniors): base_lake→base_redesign, block
  content→main, `.wrap`→`.artx` prose scope, dropped lake_editorial.css. Auth/landing:
  login→`.authx`, sponsor→`.sponx`, portal→`.portx`; btn-primary = v4 teal pill.
- Family/Night: mode_sandstone.html (desert + emoji tiles + data-mode dark) → NEW
  mode_redesign.html (v4 tiles, no emoji, cond strip replaces hero mini-conditions). Desert
  4-mode switch + data-mode retired (decision-15: v4 6-link header is the nav; one lake theme).
  _serve_mode_landing renders mode_redesign + passes cond_tiles+gas.
- Provider (SEO-critical): rebuilt in `.prof-wrap` v4; preserved ALL favorites/owner JS hooks
  (.fav-save/.favorite-heart + body data-* via a NEW `{% block body_attrs %}` in base_redesign),
  LocalBusiness+Breadcrumb JSON-LD, Website button, own-description (the "provider fixes" the
  prompt asked for were ALREADY present — verified). ★rating/★Featured/♥save → SVG star/heart
  icons (zero emoji). No-photo → NO image block (monogram retired). hava_card.css kept (self-
  contained BEM component for the venue-events strip).
- Chat (/chat + /ask): →base_redesign; desert_chat.css retired (ported to lake_redesign.css);
  chat_cards.css KEPT (B-01 clamps); every JS id/hook + `ll-page ll-chat` body class preserved.
- redesign_icons gained star/heart/phone. Live-QA (havasu-local preview): /about /portal /chat
  render clean v4, no console errors.
- Test repointing GOTCHAs: /today is now the base_lake-reskin sentinel (test_site_redesign);
  /portal/claim & account pages stay base_lake (didn't over-swap their css asserts); the empty
  test DB 404s unseeded provider/leaf slugs → base_lake 404 (out of scope, PR-7).

## NEXT ACTION
PR-5 ✅ merged (f8e8094e). START PR-6 (`feat/v45-06-water-temp`) — water-temp reliability.
Verify the USGS gauge actually returns param 00010 (real fetch; record the site ID in PROGRESS),
add retry-once, a WATER_TEMP_STALE log token (≤1/hr), keep the 6h window + honest-omit. If no
gauge returns a live value, document it and leave the honest-omit. Scout app/conditions water-temp
source first. Gate → merge → PR-7.

## (older) NEXT ACTION
PR-1 ✅ merged (978cf71e). START PR-2 (`feat/v45-02-gas-shell`) — see "PR-2 scouting":
gas_prices_lake.html extends base_redesign; pass cond_tiles+today_label+cond_gas_plain (gas
tile = plain span, no panel); keep PR-6 grade segment/matrix/Cheapest chip/JS; move .gseg.lg/
.chp CSS to lake_redesign.css; rewrite the ~20 test_gas_prices_page tests to the v4 shell. Gate → merge → PR-3.

## (done) NEXT ACTION
PR-0 ✅ merged (02ceafcf). START PR-1 (`feat/v45-01-events-ui`) — see "PR-1 scouting".
Extract home's feed macros to `components/feed_macros.html`; new `events_redesign.html`
extends base_redesign; serve_events_ui passes cond_tiles+gas_panel_data+active_tab; swap
emoji For-kids pill → `.cpill.places`+kid icon; keep counts/URLs (parity tests). Capture
local refs. Gate → merge → PR-2.

## (done) NEXT ACTION
Baseline gate on `50d3ae90` (pytest+ruff+mypy). Then PR-0 (`feat/v45-00-punchlist`):
(1) gas panel footer in `base_redesign.html` prepends literal "updated" before
`gas.staleness_label` (which already starts "Updated") → "updated Updated today…";
drop the literal so it reads "All {n} stations · {label} →". (2) /news "Updated {date}."
uses a UTC date → use `now_lake_havasu()` Phoenix date. Add tests for both.
