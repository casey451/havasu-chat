# Parks & Rec scrapes

Source-of-truth pulls for Lake Havasu City parks-and-rec activity data,
plus the schedule and snapshot pattern they share.

## Sources

| Source          | URL                                                        | Shape                                 | Status        |
|-----------------|------------------------------------------------------------|---------------------------------------|---------------|
| `webtrac`       | `register.lhcaz.gov/webtrac/web/search.html?module=AR`     | Programs → sections (registered)      | Implemented   |
| `lhcaz_aquatic` | `lhcaz.gov/parks-recreation/open-swim-schedule`            | Recurring weekly class grid           | Stubbed       |

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

Snapshots are immutable. The catalog loader reads the *latest* snapshot
for a source, diffs against existing rows, and routes adds/updates
through the contribution queue (see `app/contrib/approval_service.py`).
That loader is intentionally separate from this scraper layer so DB
schema changes don't churn the scrapers.

## Running

```
# Run every source:
python scripts/run_scrapes.py

# Run a subset (e.g. only the WebTrac side):
python scripts/run_scrapes.py --only webtrac

# JSON summary for piping into a scheduler dashboard:
python scripts/run_scrapes.py --json
```

The script exits non-zero if any source failed.

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
      - uses: actions/upload-artifact@v4
        with:
          name: scrapes-${{ github.run_id }}
          path: data/scrapes/
```

### Local cron (development)

```
15 */6 * * * cd /path/to/havasu-chat && /usr/bin/env python scripts/run_scrapes.py >> data/scrapes/cron.log 2>&1
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
