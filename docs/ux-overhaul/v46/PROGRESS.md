# v4.6 build — PROGRESS (external memory; resume from here)

**Resume cold:** read this top-to-bottom, then re-read v46/README + v46/BUILD_PLAN +
v44/DESIGN_SPEC (§0 guardrails) + v44/BUILD_PLAN decision 15, then continue from
**NEXT ACTION**. Trust the gates recorded here; never redo a ✅ row.

## Fixed facts
- Integration branch `v46-integration` off `origin/main` @ `b82078b1` (the deployed v4.5).
- Items on `feat/v46-NN-slug` off `v46-integration`; gate → merge into `v46-integration`
  yourself → log here → next. STRICT order PR-0 → PR-2.
- Gates: `.venv\Scripts\python.exe -m pytest -q` green AND `.venv\Scripts\python.exe -m
  ruff check .` clean AND `.venv\Scripts\python.exe -m mypy app` clean. `graphify update .`
  after code. (bare `ruff`/`mypy` not on PATH — go through the venv module.)
  NOTE: do NOT pass `.html` files to ruff — it parses them as Python and errors. `ruff check .`
  already skips templates.
- Local `main` worktree-locked → base on `origin/main`. Final = ONE `v46-integration →
  main` PR under the kickoff grant after all gates + post-deploy smoke; revert path on fail.
- NEVER stage `docs/scraper/SCHEDULE_HUNT_PLAN.md` / `schedule_hunt_candidates.csv`
  (pre-existing noise). Explicit paths only, never `git add -A`.
- Live QA harness: `havasu-local` launch profile (throwaway SQLite, never prod). It seeds a
  provider `/provider/havasu-preview-lanes` (no description → exercises the PR-0.2 About change).
  No movies showtimes seeded → verify /movies tpills via the TestClient test, not the preview.
- Full suite ≈3.5 min → targeted tests during dev, full suite before each merge.

## Baseline
- ✅ `b82078b1`: pytest **12526 passed, 13 skipped** (202s); ruff clean; mypy clean.

## Work log (one line per item)
| PR | branch | status | gate | merge sha | notes |
|----|--------|--------|------|-----------|-------|
| 0 polish     | feat/v46-00-polish     | 🔨 gating | pytest (running) ruff✅ mypy✅ live-QA✅ | — | water flag default-ON; provider About factual line + .pautonote footnote; /movies .tpill anchors (text-decoration:none) |
| 1 last-pages | feat/v46-01-last-pages  | ⬜ todo | — | — | /today /account /contribute /feedback /portal/claim + 404 + admin off base_lake |
| 2 one-shell  | feat/v46-02-one-shell   | ⬜ todo | — | — | delete base_lake.html + site_chrome.css + orphaned CSS; guard test |
| final        | v46-integration → main  | ⬜ todo | — | — | grant-merge after CI + smoke |

## PR-0 implementation (done, gating)
Three polish fixes from the 2026-07-04 live QA sweep:
1. **Water tile default-ON.** Flag `FEATURE_FLAG_WATER_TEMP_RISE_6127` in
   `app/conditions/rise_water_temp.py::feature_enabled` — flipped the code default from
   `"false"` → `"true"`. RISE item 6127 (Parker Dam) is the dependable main-lake gauge and
   the v4.5 Accept-header fix is deployed, so it now fetches without operator action; an
   explicit falsy env var still disables it (honest-omit protects the UI when there's no
   reading). Updated the "default OFF" comments in rise_water_temp.py + fetcher.py +
   constants.py. Tests: rewrote `test_conditions_extras.py::test_rise_flag_off_no_http` →
   `test_rise_flag_default_on_when_env_absent` (default ON, no env var) +
   `test_rise_flag_explicit_falsy_disables` (explicit false/0/no/off/"" → no HTTP, empty).
   **CASEY:** if the water tile is still omitted 24h after this deploys, the env var is
   explicitly set false in Railway — that single check is yours.
2. **Provider About copy.** `provider_profile_lake.html` — when a provider has no
   description, the About body is now the short factual line (`name · category · address`,
   or `· Serving <area>` for service-area-only), NEVER the auto-built disclaimer as the
   lead. The "auto-built from trusted public data — suggest an edit" sentence moved to a
   small muted `.pautonote` footnote by the suggest-an-edit control (only rendered when
   auto-built). New CSS `.pautonote` (11px/ink3) next to `.psuggest`. NOTE: the /gas page's
   footnote class is `gas-note` (hyphen) and `.gasnote` (no hyphen) has NO global rule — so
   I used a dedicated `.pautonote`, not `gasnote`. Tests added to `test_lake_profile.py`
   (factual-line lead, no auto-built footnote when a description exists, service-area fallback).
   Live-QA: `/provider/havasu-preview-lanes` About = "Havasu Preview Lanes · Bowling",
   `.pautonote` present.
3. **Movies tpills.** ROOT CAUSE: `movies_redesign.html` already used `<a class="tpill">`
   anchors, but `.tpill` had no `text-decoration:none`, so as anchors they inherited the
   global underline → "underlined text links" (home's tpills are `<span>`, so unaffected).
   Fix: added `text-decoration:none;transition:.15s` to `.tpill` + `a.tpill:hover` chrome in
   lake_redesign.css. Booking hrefs unchanged (real ticketing links). Test in
   `test_movies_lake_parity.py::test_movies_showtimes_are_tpill_anchors`.

## Judgment calls (decision 15 log)
- **PR-0.2 footnote class = `.pautonote`, not `.gasnote`.** BUILD_PLAN said "a small
  `.gasnote`-style footnote". But `.gasnote` (no hyphen) has NO CSS rule in the repo (the
  /gas page uses `gas-note` with a hyphen, and its styling is scoped under `.gaswrap`). Reusing
  a class with no global rule rendered the footnote at default 16px/ink (not small/muted).
  Delivered the SPEC intent — a small muted footnote — via a dedicated `.pautonote`
  (11px, `--ink3`) so it's correct on the provider page (no `.gaswrap` ancestor). Smallest diff.
- **v4.6 refs — live-QA instead of committed PNGs (inherits v4.4/v4.5 decision 15).** The
  capture_refs mock isn't in the repo; verifying each change via the havasu-local preview +
  unit/template tests instead, logged per PR.

## NEXT ACTION
PR-0 gating: authoritative full suite running (bg brmxvqpf5). If green → stage the PR-0 files
(explicit paths, NOT the schedule_hunt noise), commit `feat/v46-00-polish`, merge into
`v46-integration`, mark PR-0 ✅ here. Then START PR-1 (`feat/v46-01-last-pages`): migrate
/today, /account, /contribute, /feedback, /portal/claim, admin pages, and the 404/error page
off `base_lake.html`. Create `base_plain.html` (v4 tokens, six-link header, footer, no cond
strip, no JS) per Pre-answered 2/3; point error handlers at a serif "Can't find that" page with
a search box + Today link (status codes correct). /today = full v4 shell + cond strip (honest-omit
water). Utility pages = v4 shell + footer, no cond strip; restyle forms like /login (v4.5 PR-5
authx pattern); preserve EVERY form action/field/method/JS hook. Read v45 PROGRESS on the
/portal/claim sed over-reach before editing it. Gate → merge → PR-2.
