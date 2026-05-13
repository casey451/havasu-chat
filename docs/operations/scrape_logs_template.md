# Scrape run log template

Copy this file to `docs/scrape_logs/<source>_YYYY-MM-DD.md` after each meaningful scrape or scheduled job run.

## Run identification

- **Source:** `<google_places | osm | lhc_open_data | az_roc | outbox_redrive | ...>`
- **Run timestamp (UTC):** `<ISO 8601>`
- **Triggered by:** `<cron schedule | manual operator | workflow_dispatch | Railway one-off>`
- **Script:** `<e.g. python -m scripts.places_discovery --category eat-drink>`

## Counts

- **Total queries issued:** `<N>`
- **Total rows discovered:** `<N>`
- **Total rows new (inserted):** `<N>`
- **Total rows updated (reconciler matched existing):** `<N>`
- **Total rows skipped (dedupe within same run):** `<N>`
- **Total errors:** `<N>`
- **Sample errors (first 3):**
  - `<error 1>`
  - `<error 2>`
  - `<error 3>`

## Duration

- **Run elapsed time:** `<HH:MM:SS>`

## Notes

`<Free-form operator notes: anomalies, rate limits, API messages, follow-ups.>`
