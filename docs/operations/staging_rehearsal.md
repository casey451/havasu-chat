# Migration rehearsal on VPS staging

> Implements HANDOFF #6 of the VPS rollout (`outputs/vps-rollout/CLAUDE_CODE_HANDOFF.md`).
> Operator-side step. **CI is not changed** — this runs by hand before you merge.

## Why

`main` auto-deploys to Railway, and the deploy runs `alembic upgrade head` on
**production** Postgres (`CLAUDE.md`). There is no rehearsal target, so a bad
migration is discovered *in prod*. This procedure replays last night's prod
backup onto the VPS's staging Postgres (which has pgvector, enabling HANDOFF #2)
and runs the migration there first. Green on staging → safe to merge.

This is the safety net the whole rollout exists for: *a bad migration can no
longer take down prod untested.*

## One-time setup (Casey)

The staging Postgres is already defined in `outputs/vps-rollout/docker-compose.yml`
(`pgvector/pgvector:pg16`, bound to `127.0.0.1:5433`, db `havasu_staging`). After
`docker compose up -d`, add the connection string to `/opt/hava/.env.vps`:

```
STAGING_DATABASE_URL=postgresql://hava:<pgpass>@127.0.0.1:5433/havasu_staging
```

Never commit it. The nightly `backup_prod_db.sh` already drops dumps in
`/opt/hava/backups/`.

## The one command

```bash
cd /opt/hava/havasu-chat
git fetch && git checkout <the-branch-with-the-migration>
scripts/rehearse_migration.sh
```

That wrapper:

1. **Resets + restores** — drops the staging `public` schema and restores the
   newest `/opt/hava/backups/hava_prod_*.sql.gz` (or `--backup=PATH`).
2. **`alembic upgrade head`** against staging — the actual rehearsal. A failure
   here is the failure you wanted to catch before prod.
3. Prints **REHEARSAL OK** only if every step succeeded (`set -euo pipefail`).

### Useful flags

| Flag | Effect |
|---|---|
| `--check-downgrade` | After `upgrade head`, run `downgrade -1` then `upgrade head` again — proves the new migration is reversible (we've shipped a merge-node tip that broke `downgrade -1` before). |
| `--smoke` | Boot uvicorn against staging and run `scripts/smoke_concurrent_chat.py` (p50/p95, 5xx check); the server is always torn down on exit. |
| `--backup=PATH` | Restore a specific dump instead of the newest. |

Env overrides: `ENV_FILE`, `BACKUP_DIR`, `ALEMBIC_BIN`, `PYTHON_BIN`, `SMOKE_PORT`,
`SMOKE_SECONDS`. On the VPS venv, set `ALEMBIC_BIN=/opt/hava/venv/bin/alembic` and
`PYTHON_BIN=/opt/hava/venv/bin/python`.

## The safety fence

The wrapper **drops and recreates the target schema**, so it hard-refuses any
`STAGING_DATABASE_URL` whose value does not contain `staging`. Prod is database
`railway`; staging is `havasu_staging`. If the guard ever trips, *stop* — do not
"work around" it; it means the URL is pointed somewhere it shouldn't be. This is
the line that keeps a rehearsal from ever becoming a prod write.

## Manual fallback

If you'd rather run it by hand (equivalent to the wrapper, minus the guard —
so double-check the URL yourself):

```bash
LATEST=$(ls -1t /opt/hava/backups/hava_prod_*.sql.gz | head -n1)
psql "$STAGING_DATABASE_URL" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
gunzip -c "$LATEST" | psql "$STAGING_DATABASE_URL"
DATABASE_URL="$STAGING_DATABASE_URL" alembic upgrade head
```

## After a green rehearsal

Merge the branch to `main` per `CLAUDE.md` (Casey's gate). The Railway deploy
then runs the same `alembic upgrade head` you just rehearsed.

## Related

- `outputs/vps-rollout/docker-compose.yml` — the staging container.
- `outputs/vps-rollout/backup_prod_db.sh` — produces the dumps restored here.
- `docs/operations/vps_readonly_db_role.md` — the read-only role the backup uses.
- HANDOFF #2 (pgvector cache) is the first migration that should go through this.
