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
| 1 gas-truth      | feat/v44-01-gas-truth        | 🔨 gating | targeted 43✅, ruff✅, mypy✅; full suite running | — | GasService single source |
| 2 date-keys      | feat/v44-02-date-keys        | ⏳ | — | — | date-keyed cache |
| 3 count-parity   | feat/v44-03-count-parity     | ⏳ | — | — | day_counts one base |
| 4 conditions     | feat/v44-04-conditions       | ⏳ | — | — | water+sunset, retire clouds |
| 5 ads-rail       | feat/v44-05-ads-rail         | ⏳ | — | — | one paid unit + working rail |
| 6 gas-ui         | feat/v44-06-gas-ui           | ⏳ | — | — | grade switch + /gas page |
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

## NEXT ACTION
PR-1 gating: full suite running (bg bnyqw7lon). If green → commit `feat/v44-01-gas-truth`,
merge into `v44-integration`, mark PR-1 ✅, then start PR-2.

**PR-2 scouting (done):** HTML responses already carry `Cache-Control: no-cache`
(`app/main.py:480`), so the stale-page bug is NOT browser/CDN — it's an in-process
data-layer cache keyed WITHOUT the resolved date (DATA_CONTRACTS §4: "never cache a
bare-'today' key"). Candidates to inspect: in-process caches in `app/home/collections.py`
(`reset_cache`), `app/home/queries_c.py` (`reset_cache`), and any `lru_cache`/TTLCache
that memoizes a "today"/"this month" computed value. PR-2 = resolve today/month
(America/Phoenix) BEFORE the cache lookup and include it in the key for /home,
/events-ui, /calendar. Regression test: freeze date D, warm cache, advance to D+1,
assert response reflects D+1.
