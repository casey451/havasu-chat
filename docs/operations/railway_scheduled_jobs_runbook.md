# Railway scheduled jobs — operator runbook

Spinning up a new Railway scheduled-job service for a scrape or background task. Sized for a solo-operator workflow.

## When to use

Per [background_job_infrastructure_decision.md](../maintainability/background_job_infrastructure_decision.md) §6.1, **Railway scheduled jobs** handle the cron-like surface (scrape sweeps, aged-row refresh, weekly re-verification passes, outbox redrive). For **event-triggered** work (magic-link email, image processing), the app uses FastAPI `BackgroundTasks` (wired in Phase 4.1 + 4.4).

## Pre-checks

1. Confirm the script is operator-runnable end-to-end from your local venv, for example:

   ```powershell
   python -m scripts.places_discovery --category eat-drink --dry-run
   ```

   Or for a no-API-key smoke path:

   ```powershell
   python -m scripts.outbox_redrive --dry-run --max-rows 1
   ```

2. Confirm env vars are in `.env.example` and in **Railway → Variables** for that service (e.g. `DATABASE_URL`, `GOOGLE_PLACES_API_KEY` when using Places).

3. Confirm the script is **idempotent** — re-running must not create duplicate catalog rows. Layer-1 dedupe on Google Place ID plus `app.contrib.ingest_reconciler.reconcile_hit` on load paths covers most cases.

## Steps

1. Railway dashboard → **New service** in the same project as the main app.
2. **Source:** connect the same GitHub repo as the main app (same branch you deploy from, usually `main`).
3. **Settings → Deploy → Start command**, for example:

   ```text
   python -m scripts.places_discovery --category eat-drink
   ```

   Or parameterize with a Railway variable:

   ```text
   python -m scripts.places_discovery --category $PLACES_CATEGORY
   ```

4. **Settings → Cron schedule:** e.g. `15 */6 * * *` (every 6 hours at :15 — matches the parks-rec precedent in `.github/workflows/parks-rec-scrapes.yml`). Use [crontab.guru](https://crontab.guru) to validate.
5. **Variables:** set service-specific vars; you can **reference** variables from the web service instead of duplicating secrets where Railway supports it.
6. **Deploy** and wait for the first scheduled run (or trigger a one-off deploy/run from the dashboard).
7. Open **Logs** and confirm no tracebacks; confirm rate limits and API quotas are acceptable.
8. **Verify effects** (production Postgres): use Railway’s Postgres plugin / Query tab, for example count new or updated rows by `source` and time window. On SQLite dev, use your usual local inspection tools instead.

## Monitoring

- **Sentry:** breadcrumbs from `app.core.background.with_retry` use category `background-jobs` (Phase 4.1).
- **Per-run summary:** copy [scrape_logs_template.md](scrape_logs_template.md) into `docs/scrape_logs/<source>_YYYY-MM-DD.md` after significant runs (optional but recommended).
- **Failure signal:** if a run discovers zero new rows when you expected growth, or error rate is high, inspect logs and Sentry before the next cron tick.

## Cost

Scheduled services bill as normal Railway services. **N categories → N services → N bill lines.** Alternatively, one service with `$JOB_NAME` or similar env switching reduces bill lines but concentrates failure blast radius.

## Rollback

1. **Pause cron:** Service → Settings → Cron schedule → clear the expression (stops future runs; service can stay).
2. Or **Suspend** the service.
3. Fix on `main`, redeploy, re-enable cron when verified.

## Reference

- [background_job_infrastructure_decision.md](../maintainability/background_job_infrastructure_decision.md) (Option A)
- [layered_scrape_strategy.md](../maintainability/layered_scrape_strategy.md) (per-layer cadences)
- [app/core/background.py](../../app/core/background.py) (`with_retry`, Outbox delivery)
- [.github/workflows/parks-rec-scrapes.yml](../../.github/workflows/parks-rec-scrapes.yml) (GitHub Actions cron precedent)
