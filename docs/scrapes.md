# Parks & Rec scrapes

Source-of-truth pulls for Lake Havasu City parks-and-rec activity data,
plus the schedule and snapshot pattern they share.

## Sources

| Source          | URL                                                        | Shape                                 | Status        |
|-----------------|------------------------------------------------------------|---------------------------------------|---------------|
| `webtrac`       | `register.lhcaz.gov/webtrac/web/search.html?module=AR`     | Programs → sections (registered)      | Implemented   |
| `lhcaz_aquatic` | `lhcaz.gov/parks-recreation/open-swim-schedule`            | Per-day class slots (concrete dates)  | Implemented   |

WebTrac (Vermont Systems 3.1.x) returns server-rendered HTML; sections
are inline in the document, so a single GET per category yields the full
payload. The aquatic schedule is static HTML on the city website.

## Snapshot pattern

```
data/
└── scrapes/
    ├── manifest.json               # latest run summary per source + history
    ├── webtrac/
    │   ├── 20260507T210000Z.json
    │   └── 20260508T060000Z.json
    └── lhcaz_aquatic/
        └── 20260507T210000Z.json
```

Each snapshot is a JSON document `{ source, captured_at, records }`. The
manifest records the latest successful run per source plus a rolling
history of the last 100 runs.

Snapshots are immutable. The catalog loader (`app/contrib/parks_rec_loader.py`)
reads the *latest* snapshot for a source, dedupes against rows already in
`contributions` / `events`, and routes new records through the existing
approval flow:

* WebTrac single-day section          → Contribution(entity_type="event")    → Event
* WebTrac multi-day or weekly         → Contribution(entity_type="program")  → Program
* Aquatic Center class slot           → Contribution(entity_type="event")    → Event

Only publicly bookable rows are loaded into the catalog (WebTrac
`available_for_signup`, aquatic `is_public`). Pool-closed, private
practice, and unavailable / full sections remain in the snapshot file
on disk but never enter the catalog. The chat layer reads the snapshot
directly when answering direct-ask carve-outs (e.g. "is the basketball
league full?").

The loader is intentionally separate from the scraper layer so DB
schema changes don't churn the scrapers and vice versa.

## Running

Two-step pipeline: scrape, then load.

```
# Step 1 — refresh snapshots (writes data/scrapes/<source>/<ts>.json):
python scripts/run_scrapes.py

# Step 2 — load the latest snapshots into the catalog:
python scripts/parks_rec_load.py            # full live load
python scripts/parks_rec_load.py --dry-run  # count without writing
```

`run_scrapes.py` and `parks_rec_load.py` both exit non-zero on any
failure — wire that into your scheduler for paging. Either step is
idempotent: re-running the loader against an unchanged snapshot
imports zero rows because every source URL is already in the catalog.

## Scheduling

Pick the option that matches your hosting:

### Heroku Scheduler / Render Cron

Configured externally; point a 6h job at the entry above. No worker
process needed inside the app. Recommended cadence: every 6h, with a
nightly full re-pull at 02:00 local time.

### Procfile worker (in-process scheduler)

If you want the scheduler living next to the web process, add to
`Procfile`:

```
worker: while true; do python scripts/run_scrapes.py || true; sleep 21600; done
```

That's a sleep-loop, not a real cron. Fine for a single-instance
deployment, brittle if you scale dynos. Prefer external scheduling.

### GitHub Actions

`.github/workflows/scrapes.yml`:

```yaml
name: scrapes
on:
  schedule:
    - cron: "15 */6 * * *"
  workflow_dispatch: {}
jobs:
  pull:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/run_scrapes.py
      - run: python scripts/parks_rec_load.py
      - uses: actions/upload-artifact@v4
        with:
          name: scrapes-${{ github.run_id }}
          path: data/scrapes/
```

### Local cron (development)

```
15 */6 * * * cd /path/to/havasu-chat && /usr/bin/env python scripts/run_scrapes.py && /usr/bin/env python scripts/parks_rec_load.py >> data/scrapes/cron.log 2>&1
```

## Failure modes and observability

* The runner is fail-soft: one source failing does not abort the others.
  Failures are recorded in `manifest.json` under `sources.<src>.error`
  and the run exits non-zero so the scheduler can alert.
* WebTrac will rotate session and CSRF tokens between runs; the fetcher
  bootstraps a fresh session each invocation, so this is fine.
* If WebTrac introduces real pagination (today: all results in one
  document), adjust `app.contrib.webtrac.fetch_search_html` to follow
  the `Showing results X-Y of Z` paginator.

## Adding a new source

1. Implement a module under `app/contrib/<source>.py` exposing
   `pull_snapshot() -> list[dict]`.
2. Register it in `SOURCES` in `scripts/run_scrapes.py`.
3. Add a fixture under `tests/fixtures/<source>/` and a parser test.
4. Document the source above and the chat-layer carve-outs (e.g.
   "Unavailable sections hidden by default") in
   `docs/components/dedupe.md`.
