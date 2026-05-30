# Root cause: prod schema drifts behind `main` (migrations never auto-apply)

ASCII-only. Written 2026-05-30 while diagnosing the golakehavasu-events /
river-scene-events cron failures.

## What happened
The event crons were emailing failures. Root cause turned out NOT to be the
scrapers: prod Postgres was 3 Alembic migrations behind `main`. The middle one,
`b1c2d3e4f5a6`, adds `providers.google_photo_urls`. Without it, ANY
`select(Provider)` against prod raises `UndefinedColumn`. That query runs inside
`app/events/dedup.py::resolve_venue_entity_id` -> `reconcile_event`, which is the
core of BOTH event crons. So one missing column took down both crons.

Fixed today by running `alembic upgrade head` against prod manually
(a9b0c1d2e3f4 -> c2d3e4f5a6b7). Crons should go green now.

## Why it drifted (the real bug)
Nothing applies migrations on deploy. Verified:
- `Procfile`            -> `web: uvicorn app.main:app ...`   (start only)
- `nixpacks.toml`       -> `[start] cmd = "uvicorn app.main:app ..."` (start only)
- no `railway.json` / `railway.toml` (no release phase)
- `app/db/database.py::init_db()` is `Base.metadata.create_all`, explicitly
  "dev/test convenience, NOT Alembic", and has ZERO callers in app/ or scripts/
- no `alembic upgrade` in any Procfile / config / shell / startup hook

So every deploy ships new code against whatever schema prod already had. Schema
only moves when someone runs `alembic upgrade` by hand. That is why prod fell
behind, and it WILL recur on the next migration-bearing PR -- including Task B's
backfill migration `d3e4f5a6b7c8` -- unless this is fixed.

## Recommended fix: a Railway release command
Railway runs a "release" / pre-deploy command (if configured) after build and
BEFORE the new container takes traffic. Put the migration there so schema is
always caught up before the new code serves.

Add a `railway.json` at repo root:

    {
      "$schema": "https://railway.app/railway.schema.json",
      "deploy": {
        "preDeployCommand": "alembic upgrade head"
      }
    }

(If the Railway service is configured via the dashboard rather than a file, set
the same thing under Service -> Settings -> Deploy -> "Pre-deploy Command":
`alembic upgrade head`.)

Why preDeploy (not the start command):
- Runs once per deploy, not on every container restart/scale.
- Fails the deploy if the migration fails, instead of crash-looping uvicorn.
- New code never serves against an un-migrated schema.

### Caveats to weigh
- `alembic upgrade head` must be safe to run while the OLD version is still
  serving (Railway runs preDeploy before cutover). All migrations to date are
  additive (nullable column adds, new tables), which is safe. If a future
  migration is destructive (drop/rename/NOT NULL backfill), use the standard
  expand/contract pattern: ship the additive half, deploy, backfill, then the
  contract half in a later deploy.
- preDeploy needs `DATABASE_URL` available at deploy time (it already is -- same
  service env the app uses).

## Verify after enabling
1. Make any trivial change + deploy.
2. Watch the deploy logs for `Running upgrade ... -> ...` (or "no upgrade" if
   already at head).
3. `alembic current` against prod == `alembic heads` from the code.

## Until this is enabled (manual catch-up)
Use the helper already in the repo:
    run_alembic_upgrade_prod.cmd "<prod public url>"          (preview)
    run_alembic_upgrade_prod.cmd "<prod public url>" APPLY    (apply)
Run it BEFORE/with any PR that adds a migration -- notably PR #63 (Task B), whose
backfill `d3e4f5a6b7c8` chains onto today's head `c2d3e4f5a6b7`.
