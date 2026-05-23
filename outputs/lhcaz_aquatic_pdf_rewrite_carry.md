# lhcaz_aquatic — PDF-parser rewrite carry

> **Status:** ✅ **CLOSED** via commit `24f4aa1` 2026-05-22 ~03:14Z. Live PDF
> fetcher + parser shipped; aquatic source re-enabled in
> `scripts/run_scrapes.py::SOURCES`; loader else-branch restored; 16 parser
> tests pass against committed PDF fixtures. Re-enable checklist below is
> fully ticked. The next scheduled `parks-rec-scrapes` cron run at
> 2026-05-22T07:15Z is the live prod-side validation of the PDF fetcher
> working end-to-end. This carry doc is preserved as historical record;
> the session-handoff supersedes it for next-session context.
>
> Originally authored 2026-05-22 during the resume-from-v5 session as
> companion to the ship (`59ae1f2`) that disabled the `lhcaz_aquatic`
> source in `scripts/run_scrapes.py` SOURCES + silenced the loader's
> `"no snapshot found"` path for it.

## Why this carry exists

The Lake Havasu City parks-and-rec site reorganized sometime between
2026-05-07 and 2026-05-21. The old HTML schedule URL
`https://www.lhcaz.gov/parks-recreation/open-swim-schedule` now
redirects (HTTP 200 after follow) to
`https://www.lhcaz.gov/329/Aquatic-Center`, a tabbed landing page that
contains **zero** `.sch-day-wrp` blocks. The
`app.contrib.lhcaz_aquatic.parse_schedule_html` parser silently returns
`[]` because the CSS class names no longer exist on the page.

Evidence captured during diagnosis:

- Last working snapshot: `data/scrapes/lhcaz_aquatic/20260507T*.json`
  (136 records).
- First visible workflow failure: `parks-rec-scrapes #57` at
  2026-05-21T01:19Z (commit `fd695d2`). Five consecutive scheduled
  failures (#57–#61) preceded the diagnosis.
- The webtrac source is unaffected — same workflow run #57 imported 8
  webtrac programs cleanly. The disable is isolated to lhcaz_aquatic.

## Where the data went

The new `/329/Aquatic-Center` page surfaces the schedule as two PDF
downloads inside its rich-text body:

| Path | Description |
| --- | --- |
| `/DocumentCenter/View/7325/Exercise-Class-Schedule-PDF` | Exercise classes (Fit & Flex, Aqua Aerobics, etc.) |
| `/DocumentCenter/View/7326/Lap-and-Open-Swim-Schedule-PDF` | Lap swim + open swim slots |

(Pool-Use-Permit PDF at `/DocumentCenter/View/494` is unrelated — keep
out of scope.)

These PDFs are the canonical schedule artifact going forward. Plan on
fetching both each cron tick — the page links to them by absolute path
on `lhcaz.gov`, so a hardcoded list of URLs is the simplest stable
contract until / unless the city moves them again. (A discovery-mode
pass that re-extracts the PDF hrefs from `/329/Aquatic-Center` would
be more robust but adds an extra fetch + selector dependency. Defer
unless / until the URLs prove unstable.)

## Proposed rewrite approach

1. **New module:** `app.contrib.lhcaz_aquatic_pdf` (sibling to the
   existing `lhcaz_aquatic`, which stays in place for parser-reuse if
   the city ever flips back). New module exposes
   `pull_snapshot() -> list[dict]` with the same return shape as today's
   `app.contrib.lhcaz_aquatic.pull_snapshot()`.
2. **PDF text extraction:** Start with `pdfplumber` (already an
   acceptable dep in this repo per scripts that handle PDFs elsewhere —
   verify before committing). Fallback to `pdftotext` shell-out if
   pdfplumber gives noisy layout. Avoid OCR-route deps unless the PDFs
   turn out to be raster scans (they shouldn't — these are city-published
   layouts, almost certainly Word/Sitefinity exports).
3. **Layout parsing:** Each PDF is a week-grid table. Extract row-by-row
   into the existing `AquaticSlot` shape (`slot_date`, `day_name`,
   `class_type`, `title`, `start_time`, `end_time`, `duration_minutes`,
   `all_day`, `is_public`). Reuse `CLASS_TYPE_BY_CODE` and
   `PUBLIC_CLASS_TYPES` from the existing module. Year-inference logic
   from `_infer_year()` should port unchanged.
4. **Test fixtures:** Save a sample PDF of each schedule into
   `tests/fixtures/lhcaz_aquatic_pdf/` and add parser tests that assert
   record counts + a couple of representative `AquaticSlot` values.
   Without committed fixtures the parser becomes an HTTP-live test
   only, which is the same gap the original HTML scraper had.
5. **Re-enable:** Uncomment `lhcaz_aquatic` in
   `scripts/run_scrapes.py::SOURCES` (or add `lhcaz_aquatic_pdf` as a
   second entry). Restore the else-branch in
   `app.contrib.parks_rec_loader.load_latest_snapshots` to either error
   on missing snapshot OR omit silently — operator's choice based on
   how confident the new fetcher is.
6. **Optional polish:** Add a smoke test that fetches the PDFs in CI
   weekly (separate workflow, low-frequency) to catch URL drift early
   instead of waiting for the every-6h parks-rec-scrapes run to fail.

## Loader changes that landed in the disable ship

- `scripts/run_scrapes.py` SOURCES dict — `lhcaz_aquatic` commented out
  with DISABLED comment block linking here.
- `app.contrib.parks_rec_loader.load_latest_snapshots` — aquatic
  else-branch (the `"no snapshot found"` error path) replaced with a
  comment-only block. When no aquatic snapshot exists on disk, the
  source is silently omitted from `results`. Webtrac path is unchanged
  and still surfaces its own `"no snapshot found"` error if its
  snapshot is missing.
- No test changes shipped with the disable — the rewrite should be the
  carrier of the new test suite for `load_latest_snapshots`. The
  natural verification of the disable ship is the next scheduled
  `parks-rec-scrapes` cron run going green.

## Risk if left uncarried

- **Catalog has stale aquatic event rows.** Existing aquatic Event rows
  in production live in the catalog dating from the last successful
  scrape (before 2026-05-21). They will age out via
  `scripts/parks_rec_prune.py`'s 7-day grace window, but that means the
  catalog reflects no aquatic-center programming until the rewrite
  ships. Workaround: the city's own page is still authoritative for
  end-users; the chat layer can deflect to a link.
- **Manual operator runs of `scripts/parks_rec_load.py` still work**
  for webtrac. The disable does not affect webtrac.
- **The prune step (`scripts/parks_rec_prune.py`) still runs** every
  cron tick — it removes Event rows whose `source_url` matches the
  aquatic substring AND whose date is in the past. Safe to leave on;
  it'll just match fewer and fewer rows over time.

## Re-enable checklist (for the future ship)

- [ ] New `app.contrib.lhcaz_aquatic_pdf` module landed with
      `pull_snapshot()`.
- [ ] Test fixtures + tests added at
      `tests/test_lhcaz_aquatic_pdf_parser.py`.
- [ ] Re-add an entry to `scripts/run_scrapes.py::SOURCES`.
- [ ] Restore the else-branch in
      `app.contrib.parks_rec_loader.load_latest_snapshots` (or replace
      with the new flow's contract).
- [ ] Manual `workflow_dispatch` of the parks-rec-scrapes workflow to
      verify green on first run before the next scheduled fire.
- [ ] Smoke prod a chat query that surfaces aquatic-center
      programming after the next cron tick lands.

---

*Authored 2026-05-22 by Cowork primary during the resume-from-v5
session. Companion to the disable ship — same commit, or the commit
immediately preceding the disable ship.*
