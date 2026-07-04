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
| 0 polish     | feat/v46-00-polish     | ✅ merged | pytest 12535✅ ruff✅ mypy✅ live-QA✅ | merge e462715a | water flag default-ON; provider About factual line + .pautonote footnote; /movies .tpill anchors (text-decoration:none) |
| 1 last-pages | feat/v46-01-last-pages  | ✅ merged | pytest 12537✅ ruff✅ mypy✅ live-QA✅ | merge 2e0ad068 | ALL 27 live base_lake pages → v4 shell; base_plain.html created; only lake_styleguide left (→PR-2 delete) |
| 2 one-shell  | feat/v46-02-one-shell   | 🔨 building | — | — | delete base_lake.html + lake_styleguide + site_chrome.css + orphaned CSS; guard test |
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

## PR-1 implementation (done, gating)
BUILD_PLAN framed "seven surfaces" but PR-2's "delete base_lake" requires ZERO extenders,
so ALL 27 live base_lake pages were migrated (the 7 named ones are logical groups of these).
Mechanism: routes resolve `foo.html`→`foo_lake.html` via per-router helpers; migration = flip
each template's `extends` + `block content`→`block main` + drop its bespoke CSS link, wrap in a
v4 scope, and port that CSS into lake_redesign.css retokenized (v4 palette). Groups:
- **NEW `base_plain.html`** — v4 tokens + shared six-link header + footer, NO cond strip, NO
  gas JS. For error pages + admin (Pre-answered 2/3). Also added overridable og_type/og_title/
  og_description blocks to base_plain AND base_redesign (backward-compatible defaults) so the
  event permalink keeps og:type=event.
- **Errors** (not_found, event_not_found) → base_plain; serif "Can't find that" + search box
  (→/categories) + Today link; status codes preserved; `.errx` CSS.
- **/today** → base_redesign + live cond strip (today.py gains a guarded `_chrome()` passing
  cond_tiles+gas); `.todayx` CSS; honest-omit intact.
- **Account/auth/claim** (account, account_favorites, account_alerts, login_check_email,
  login_expired, claim_form, claim_status, claim_submitted, merchant_upgrade_form) → base_redesign;
  `.acctx` (signed-in hub/lists/alerts) + `.authx` (narrow column) scopes; every form action/field/
  checkbox name preserved.
- **Portal** (portal_claim, portal_placements, portal_placement_new, portal_creatives) →
  base_redesign; `.portx` scope (claim autocomplete JS + all placement/creative field names kept).
- **/feedback** → base_redesign `.artx` (editorial) + form controls; page_url JS kept.
- **Landings** (collection_landing, event_permalink) → base_redesign; `.coll-wrap`/`.evd` scopes;
  **event permalink's drawn sun/ridge scene-art removed** (§0 guardrail 3 — no image → no block).
- **/search** → base_redesign `.srch`; **/map** → base_plain full-page (`body.map-page .rd-shell{
  max-width:none}` un-constrains the centered shell; map_view.css + Leaflet + all map JS verbatim);
  **/group** (themed_group_landing) → base_redesign `.grpx` (directory chrome ported; search_bar/
  category_filters/map/boat_mode hooks verbatim; decorative `.ridge` dropped).
- **Admin** (6 `.d-admin` templates) → base_plain; dropped the dead desert_portal.css link (its
  desert.css tokens were deleted 2026-06-24); the AdminLakeSkinMiddleware still injects the
  self-contained lake_admin.css (`--la-*` tokens) for every /admin path, so styling is preserved.
- Test shell-assert repoints: test_site_redesign (rewritten — no base_lake sentinel left),
  test_lake_conditions/errors/portal/group/map/search/map_view (css link → lake_redesign.css).
  NEW test_v46_last_pages.py (only styleguide extends base_lake; public pages on v4 shell; 404
  = base_plain + errx + Today link).

## Judgment calls (decision 15 log)
- **PR-1 scope = ALL 27 live base_lake pages, not just the 7 named.** PR-2's guard test
  (base_lake absent) can't pass with any extender left, so the "seven surfaces" had to expand to
  every live page. lake_styleguide (a Phase-0 gallery of the lake.css component library being
  deleted) is intentionally NOT migrated — migrating it would demo classes PR-2 removes; it's
  deleted in PR-2 with base_lake + lake.css. So after PR-1 exactly one template extends base_lake.
- **/map on base_plain, not base_redesign.** The map is a full-viewport Leaflet app; base_redesign/
  base_plain wrap content in `.rd-shell{max-width:1180}`, which would clamp the full-bleed map. A
  scoped `body.map-page .rd-shell{max-width:none;margin:0}` un-constrains it. base_plain (no cond
  strip, no gas JS) is the right floor; map_view.css keeps owning the load-bearing layout.
- **Bespoke page CSS ported into lake_redesign.css, not kept.** Those sheets used lake.css tokens
  (--brass-deep/--ink-2/--hair-2/--muted…) that are undefined over the v4 shell, so they had to be
  retokenized (--brass-ink/--ink2/--hair2/--ink3…) and scoped. PR-2 deletes the originals.
- **/contribute left as-is.** BUILD_PLAN named it a PR-1 utility page, but `/contribute` is NOT a
  base_lake template — it's a standalone inline-HTML page (contribute.py `_render_contribute_page`)
  with its own self-contained `contribute.css` (Fraunces/Inter, eyebrow/lede/form-card, own topbar).
  It links neither base_lake, site_chrome.css, nor lake.css, so PR-2's deletions don't touch it, and
  it already reads in the v4 language. Rewriting its multi-field intake form + JS + prefill/error
  states into a base_redesign Jinja template is a large rewrite with real regression risk for
  cosmetic parity, off the base_lake-deletion critical path → smallest-diff (decision 15): leave it;
  smoke verifies 200 + zero-emoji.

- **PR-0.2 footnote class = `.pautonote`, not `.gasnote`.** BUILD_PLAN said "a small
  `.gasnote`-style footnote". But `.gasnote` (no hyphen) has NO CSS rule in the repo (the
  /gas page uses `gas-note` with a hyphen, and its styling is scoped under `.gaswrap`). Reusing
  a class with no global rule rendered the footnote at default 16px/ink (not small/muted).
  Delivered the SPEC intent — a small muted footnote — via a dedicated `.pautonote`
  (11px, `--ink3`) so it's correct on the provider page (no `.gaswrap` ancestor). Smallest diff.
- **v4.6 refs — live-QA instead of committed PNGs (inherits v4.4/v4.5 decision 15).** The
  capture_refs mock isn't in the repo; verifying each change via the havasu-local preview +
  unit/template tests instead, logged per PR.

## PR-2 plan (deletion recon — grep-proven, do before deleting each per verify_dead_code_before_deleting)
After PR-1, base_lake.html has exactly ONE extender left: `lake_styleguide.html` (a Phase-0 gallery
of the lake.css component library). PR-2 deletes:
- **Templates:** `base_lake.html`, `lake_styleguide.html`.
- **Route + reg:** `app/home/lake_preview.py` + its `include_router` in `app/main.py`.
- **CSS (all orphaned after PR-1 — 0 template refs each, verified):** `site_chrome.css`, `lake.css`,
  `lake-components.css`, `lake_redesign_site.css`, `lake_conditions.css`, `lake_account.css`,
  `lake_editorial.css`, `lake_landing.css`, `lake_portal.css`, `lake_error.css`, `lake_search.css`,
  `lake_map.css`, `lake_group.css`, `desert_portal.css`. (Re-grep app+tests+scripts before each.)
- **Comment-only refs to fix (not delete):** `_partials/site_header.html` + `_partials/site_footer.html`
  (mention site_chrome.css in doc comments), `lake_redesign.css` header comment, and the base_lake
  mentions in `app/movies/router.py` / `app/feedback/routes.py` / `app/admin/shell.py` / `app/core/theme.py`
  docstrings — audit each; they may just be prose.
- **Tests to repoint/remove (assert deleted files):** `test_static_cache.py` + `test_static_url_fingerprint.py`
  (fetch/fingerprint `lake.css` → point at `lake_redesign.css`), `test_lake_contrast.py` (reads
  lake-components.css → repoint to lake_redesign.css or drop), `test_lake_theme.py` (base_lake), the
  styleguide test, `test_ada_compliance.py` base_lake comment.
- **Guard test:** extend/keep the sweep guard — `base_lake.html` absent, `site_chrome.css` absent, zero
  `extends "base_lake"` and zero links to the deleted sheets across app templates.
Acceptance: guard tests + full gates + every public route still 200 (smoke list).

## NEXT ACTION
PR-1 gating: authoritative full suite running (bg bntkopksm). If green → stage the PR-1 files
(explicit paths, NOT the schedule_hunt noise; include base_plain.html + all migrated templates +
lake_redesign.css + today.py + base_redesign.html + the repointed tests + PROGRESS), commit
`feat/v46-01-last-pages`, merge into `v46-integration`, mark PR-1 ✅ here. Then START PR-2
(`feat/v46-02-one-shell`) per the "PR-2 plan" above. Gate → merge → FINAL PR.
