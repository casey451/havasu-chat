# river_scene

`app/contrib/river_scene.py` (parser/fetcher, ~460 lines)
`app/contrib/river_scene_pull.py` (orchestration, ~215 lines)

## Purpose

The River Scene ingestion lane is the **sole live source** of catalog events as of the 2026-04-30 RS-only cleanup. It crawls RiverScene Magazine's WordPress sitemap, fetches each event detail page, parses the HTML into a normalized `RiverSceneEvent` dataclass, and inserts a `Contribution` row (or dry-runs). Approved contributions become live `Event` rows via `approval_service.approve_contribution_as_event`. The pipeline is operator-triggered (CLI script `scripts/river_scene_pull.py` over `run_pull`), not request-time; production catalog refresh is a deliberate human action.

The two modules split cleanly: `river_scene.py` is HTTP+parsing (no DB writes), `river_scene_pull.py` is orchestration (sitemap discovery → dedupe-before-fetch → HTML fetch → parse → contribution insert + optional auto-approval).

## Public surface

### `river_scene.py`

**`RiverSceneEvent` (dataclass)** — Normalized event parsed from one detail page. Fields: `title`, `url`, `start_date`, `end_date`, `start_time`, `end_time`, `description_html`, `venue_name`, `venue_address`, `organizer`, `category_slugs`, `raw`. The `raw` dict carries verbatim labels from the WordPress event-details table for downstream rescue passes.

**`fetch_sitemap_urls(*, client: httpx.Client | None = None) -> list[str]`** — Loads `wp-sitemap.xml`, follows `wp-sitemap-posts-events-*.xml` children, and returns every `<url><loc>` value (no filtering, including past events). Caller is responsible for dedupe and date filtering.

**`fetch_and_parse_event(url, *, client=None, today=None) -> RiverSceneEvent | None`** — Fetches one event page, parses the WordPress event-details table, applies a description-rescue pass for missing fields, and returns the normalized dataclass. Returns `None` on unparseable HTML (no event-details table found) or when the event's `start_date` is in the past (per `today` cutoff). Past-event filtering happens here; callers don't need to recheck.

**`normalize_to_contribution(rse: RiverSceneEvent) -> ContributionCreate`** — Translates the parsed event into the schema used by `Contribution` insertion. Fills `submission_url`, sets `entity_type='event'`, normalizes the public URL (the event's RiverScene article URL), serializes the date/time fields per Hava's contribution schema.

**`RIVER_SCENE_DETAIL_LABELS`** — Frozen set of WordPress event-details table labels the parser knows how to consume. Adding a label here without adding a corresponding `labels.get(...)` reader is a no-op (the constant is documentation-by-convention; readers must be wired explicitly).

**Tunables exported as constants:** `SITEMAP_INDEX_URL` (the wp-sitemap.xml URL), `EVENTS_SITEMAP_PREFIX` (substring filter for events sub-sitemaps), `USER_AGENT` (HTTP UA header), `SITEMAP_HTTP_TIMEOUT` / `EVENT_PAGE_HTTP_TIMEOUT` / `REQUEST_TIMEOUT` (httpx Timeout objects).

### `river_scene_pull.py`

**`run_pull(start_date: date, *, dry_run: bool, http_client: httpx.Client | None = None) -> int`** — The orchestration entry point. Returns 0 on success, 1 on fetch error. Tallies per-run counters: `imported`, `skipped_duplicate`, `skipped_past_or_unparseable`, `flagged_seed_overlap`, `fetched_urls`, `auto_approved`, `auto_approval_failed`, `errors`. The `start_date` parameter is currently informational — the actual filter is `fetch_and_parse_event`'s `today=date.today()` past-event cutoff.

The CLI wrapper at `scripts/river_scene_pull.py` is a thin argparse layer over `run_pull`.

## Inputs and outputs

**Inputs.**
- HTTP: `wp-sitemap.xml` and the per-event detail pages on `https://riverscenemagazine.com`. Network is required; there's no offline fixture path in the production code (tests use HTTP-mock fixtures).
- DB: `Contribution`, `Event`, `Provider`, `Program` (via `SessionLocal`). Used only for dedupe checks and (on auto-approval) for `Event` insertion.
- `today` cutoff: defaults to `date.today()` in `fetch_and_parse_event`; callers can override for testing.

**Outputs.**
- `Contribution` rows inserted into the contributions queue with `status='pending'` (or `status='approved'` if auto-approval succeeds — see "Auto-approval" below).
- Optionally `Event` rows when auto-approval fires.
- `print(...)` to stderr/stdout for per-event progress and final tallies. The `run_pull` function is intentionally print-driven; callers wrap it with logging if needed.

## Internal structure

### Sitemap traversal (`fetch_sitemap_urls`)

1. GET `wp-sitemap.xml` (the sitemap-of-sitemaps).
2. Find children whose `<loc>` contains `wp-sitemap-posts-events-` (the events-only sub-sitemaps).
3. GET each child sub-sitemap.
4. Collect every `<url><loc>` value across all event sub-sitemaps.
5. Return the deduplicated list (no filtering by date — the caller dedupes against the DB and filters past events at parse time).

### Event detail parse (`fetch_and_parse_event`)

1. GET the event detail URL.
2. Locate the WordPress event-details table via `_find_event_details_table` (looks for `<table>` with class `tribe-events-event-meta` or similar fallback heuristics).
3. Build `labels` dict from the table's label/value rows.
4. Read structured fields: `Start Date`, `End Date`, `Time`, `Venue`, `Organizer`, `Website`, `Facebook`, `Event Category`.
5. Past-event cutoff: if `start_date < today`, return `None` (skip silently).
6. Description rescue pass: pull prose from `entry-content` div above the details table; strip operator scaffolding via `_strip_html_to_text`.
7. Title from `<h1>` or page title, normalized.
8. Construct `RiverSceneEvent` and return.

Failure modes return `None` rather than raising — the caller treats `None` as "skip this URL." Network errors and HTTP 4xx/5xx propagate via `_http_get_text`'s retries-then-raise pattern.

### Orchestration (`run_pull` body)

1. **Sitemap fetch.** `fetch_sitemap_urls(client=client)`. If the call fails, abort with exit code 1 (no point continuing without URLs).
2. **Per-URL loop.** For each URL:
   - **Dedupe-before-fetch:** `_duplicate_rs_article_import(db, url)` — checks if a `Contribution` with this `submission_url` already exists. If yes, increment `skipped_duplicate` and continue. Saves the per-event HTTP fetch.
   - **Fetch + parse:** `fetch_and_parse_event(url, client=client, today=date.today())`. Returns `None` for unparseable or past events; `errors += 1` on raised exceptions; otherwise an `RiverSceneEvent`.
   - **Seed overlap check:** `_find_seed_overlap(db, rse)` — looks up existing `Event` rows with title fuzzy-matching the parsed event (legacy seed event reconciliation; rare post-cleanup but kept). If matched, flag the contribution for operator review rather than auto-approve.
   - **Contribution insert:** translate via `normalize_to_contribution(rse)` and insert (or skip if `dry_run`). Increment `imported`.
   - **Auto-approval:** if not `dry_run` and not flagged for seed overlap, attempt `approval_service.approve_contribution_as_event` immediately. On success, increment `auto_approved`; on failure, increment `auto_approval_failed` (the contribution stays pending for manual review).
3. **Summary print** at the end: counts of every category. CLI wrapper inspects exit code; tally output is for the human operator.

## Conventions

**Polite HTTP.** Every successful response triggers `_sleep_polite()` (1.0 second pause) before the next request. WordPress sites have request-rate limits; this stays well under any reasonable threshold. The pause is in `_http_get_text`, not the caller — every callsite gets it for free.

**Retries on transient errors.** `_http_get_text` retries up to 3 times on `TimeoutException`/`ReadTimeout`/`ConnectTimeout` with linear backoff (0.5s, 1.0s, 1.5s), and once more on 5xx. Connect timeouts are common during a long pull; treating them as fatal would abort half-finished runs.

**Returns `None` for "skip"; raises for "stop".** `fetch_and_parse_event` returns `None` for past-date events and unparseable pages; raises only when HTTP itself fails after retries. The orchestrator's `try/except Exception` wraps the call so errors increment a counter without aborting the run.

**Past-event filtering happens at parse time, not at insert time.** This is deliberate — past-event detection requires parsed dates, which requires HTTP fetch. The dedupe-before-fetch check on `submission_url` runs first to skip already-imported URLs without HTTP cost.

**Dedupe key is the contribution's `submission_url`.** Not the event's start date or title. Re-running `run_pull` on a sitemap that hasn't changed produces zero new contributions; only newly-published RiverScene events become new contributions.

**Static labels via `frozenset`.** `RIVER_SCENE_DETAIL_LABELS` documents what the parser knows how to consume. New labels need both an entry here AND a `labels.get(...)` reader; the constant alone is documentation, not behavior.

**Tunables are module-level constants.** Timeouts (`SITEMAP_HTTP_TIMEOUT`, `EVENT_PAGE_HTTP_TIMEOUT`), the user-agent string, the URLs themselves — all top-of-module so tests can monkey-patch and operators can adjust without code-spelunking.

## Current state

What's actually deployed (refer to `STATE.md` for the current commit and recent history; SHAs are not pinned here to avoid drift):

- River Scene is the **sole live ingestion lane** as of the 2026-04-30 cleanup. Per `docs/maintainability/non_river_scene_cleanup.md`: providers/programs/llm_mentioned_entities tables empty; live events count traces to RS imports.
- `run_pull` is operator-triggered via CLI; no scheduled invocation. The `scripts/river_scene_pull.py` wrapper is the human entry point.
- Auto-approval is wired and active: events without seed-overlap flags go directly to `Event` rows via `approval_service.approve_contribution_as_event`. The flag-for-review path remains for safety.
- `prompts/`, the chat tier stack, and the unified router consume the resulting catalog rows; they don't know or care about the ingestion lane's implementation.

When updating this section, refresh the cleanup-status reference.

## Known limitations and design notes

**WordPress structural drift.** Parsing depends on RiverScene's WordPress theme rendering an event-details table with predictable labels. A theme update could break `_find_event_details_table` or change label spellings; the result would be an empty `labels` dict and `None` returns from `fetch_and_parse_event`. Tests cover the current shape; production breakage would surface as a sudden drop in `imported` counts on a re-run.

**Dedupe is URL-only.** Republishing the same event under a new URL (a moved event with a fresh slug) creates a duplicate contribution. Operator review at approval time catches this; auto-approval does not. The seed-overlap check handles the post-cleanup legacy case but isn't a general dedupe.

**Fuzzy seed-overlap match.** `_find_seed_overlap` uses `difflib`-style title comparison. A new event with a title close to an old seed-imported event flags for review. Slightly noisy but cheap.

**Past-event cutoff is `today`.** Events that started yesterday are skipped. Multi-day events that started yesterday but extend through next week are also skipped — `start_date` is the only check, not `end_date`. If multi-day past-start coverage ever matters, the cutoff needs to extend to "events whose `end_date >= today`."

**No incremental sitemap.** Every `run_pull` invocation re-traverses the full sitemap and dedupes against the DB. At RiverScene's volume this is fast (single-digit-thousand URLs). At scale a checkpoint mechanism would help.

**Print-driven, not log-driven.** `run_pull` writes progress to stdout/stderr via `print(...)`, not via `logging`. Callers (the CLI wrapper) consume the print stream. Migrating to structured logging would help if `run_pull` ever became a non-CLI caller.

**Auto-approval inverts the contribution-review default.** Most contribution sources go pending → review → approved. RS auto-approves when seed-overlap doesn't fire. This is acceptable because RS is operator-curated upstream (RiverScene editorial) and the seed-overlap check catches the high-value collision case. If a future ingestion source has lower upstream curation, copying this auto-approval pattern would be wrong.

## Related components

**Direct consumers:**

- `scripts/river_scene_pull.py` — CLI wrapper invoking `run_pull(start_date, dry_run=False)`.
- `app/contrib/approval_service.py` — `approve_contribution_as_event` is called by `run_pull` for auto-approval; it materializes a live `Event` row from the contribution.

**Direct dependencies:**

- `httpx` — HTTP client (sitemap, event pages).
- `BeautifulSoup` (bs4) — HTML parsing.
- `dateutil.parser` — flexible date string parsing for the WordPress label values.
- `app.db.contribution_store.normalize_submission_url` — URL canonicalization for dedupe matching.
- `app.schemas.contribution.ContributionCreate` — the contribution payload schema.

**Schema touched:**

- `Contribution` (insert path; status='pending' or 'approved' depending on auto-approval).
- `Event` (insert path on auto-approval, via `approval_service`).
- `Provider`, `Program` — read for seed-overlap check; not written by this lane.

**Cross-references:**

- `docs/maintainability/non_river_scene_cleanup.md` — historical context for why this is the only live lane.
- `docs/maintainability/end_to_end_creation.md` — Path 2 (River Scene auto-import) covers the full flow including approval_service materialization.
- `docs/maintainability/provider_ingestion_lane_options.md` (Slice 29) — forward-looking design for adding non-RS lanes; uses river_scene as the reference architecture.
