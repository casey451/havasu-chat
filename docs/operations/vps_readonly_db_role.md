# Read-only Postgres role for VPS scripts

> Implements HANDOFF #7 of the VPS rollout (`outputs/vps-rollout/CLAUDE_CODE_HANDOFF.md`).
> **This is a production DB DDL change.** Per `CLAUDE.md` it must not be applied
> without Casey's explicit approval. This document is the spec; Casey runs the SQL.

## Why

The VPS ops scripts that touch prod Postgres are both **read-only**:

| Script | Access pattern | Privilege actually needed |
|---|---|---|
| `backup_prod_db.sh` | `pg_dump` (full logical dump) | `SELECT` on all tables **and sequences** |
| `check_health_and_fallback.py` | one `SELECT` on `chat_logs` (24h window) | `SELECT` on `chat_logs` |

Today both read `PROD_DATABASE_URL` from `/opt/hava/.env.vps`, which is the
**full-privilege** Railway credential. That means a leaked or compromised VPS
(`.env.vps` on a second machine, behind only SSH) hands an attacker the ability
to **drop, truncate, or mutate production data** — far beyond what these scripts
need.

A dedicated `hava_readonly` LOGIN role removes that blast radius: a leaked VPS
credential could still *read* prod (see "What this does and does not protect"
below), but it cannot write, delete, alter schema, or drop anything.

## What to run (against Railway Postgres)

Run as the role that **owns the objects** — i.e. the user in the current
`DATABASE_URL` (Railway's provisioned admin user, typically `postgres`). The
`ALTER DEFAULT PRIVILEGES` lines only apply to objects created by the role that
executes them, so running as the migration/owner role is what makes future
tables (from `alembic upgrade head`) automatically readable.

Replace `<strong-password>` with a freshly generated strong password, and
`railway` with the actual database name if different (check with `\conninfo` or
the `DATABASE_URL` path component).

```sql
-- 1. Create the login role.
CREATE ROLE hava_readonly LOGIN PASSWORD '<strong-password>';

-- 2. Let it connect and see the schema.
GRANT CONNECT ON DATABASE railway TO hava_readonly;
GRANT USAGE ON SCHEMA public TO hava_readonly;

-- 3. Read existing tables AND sequences.
--    pg_dump reads each sequence's last_value, so SELECT on sequences is
--    required for a clean backup — omit it and pg_dump fails "permission denied".
GRANT SELECT ON ALL TABLES IN SCHEMA public TO hava_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO hava_readonly;

-- 4. Read tables/sequences created *later* (e.g. by future migrations),
--    without having to re-run step 3 after each deploy.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO hava_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO hava_readonly;

-- 5. (Optional hardening) cap any single query so a buggy watchdog can't pin
--    the prod DB. The watchdog query is a sub-second aggregate; 30s is generous.
ALTER ROLE hava_readonly SET statement_timeout = '30s';
```

> **Multiple schemas:** the app uses only `public`. If that ever changes, repeat
> steps 2–4 per schema. `ALTER DEFAULT PRIVILEGES` is per-schema, not global.

## Wire it into the VPS

1. Build the read-only connection string (same host/port/db as
   `PROD_DATABASE_URL`, swap user + password):

   ```
   postgresql://hava_readonly:<strong-password>@<host>:<port>/railway?sslmode=require
   ```

   Keep `sslmode=require` (Railway requires TLS).

2. In `/opt/hava/.env.vps`, point `PROD_DATABASE_URL` at the read-only string.
   Both `backup_prod_db.sh` and `check_health_and_fallback.py` read that one
   variable, so no script changes are needed. The full-privilege credential
   should **not** live on the VPS at all after this.

3. Restart / let cron pick up the next run.

## Verify it worked (and is genuinely read-only)

From the VPS (or any psql with the read-only URL):

```bash
# Reads succeed:
psql "$PROD_DATABASE_URL" -c "SELECT count(*) FROM chat_logs;"

# Writes are refused — this MUST error with "permission denied for table ...":
psql "$PROD_DATABASE_URL" -c "INSERT INTO chat_logs (role) VALUES ('x');"

# Backup smoke (writes only to local disk, reads prod):
pg_dump --no-owner --no-privileges "$PROD_DATABASE_URL" | head -c 200
```

If the `INSERT` succeeds, the grants are wrong — stop and recheck; the role is
not actually read-only.

## What this does and does not protect

- **Does:** removes write/delete/DDL capability from the credential stored on the
  VPS. A leaked `.env.vps` can no longer mutate or destroy prod data, change
  schema, or drop tables.
- **Does not:** prevent *reading* prod data. `chat_logs` and sponsor tables
  contain user content / business data; the read-only role can still SELECT it.
  Read-only ≠ confidential. Keep `.env.vps` `chmod 600`, owned by the `hava`
  user, and off any backup that leaves the box.

## Rotation / teardown

- **Rotate password:** `ALTER ROLE hava_readonly PASSWORD '<new>';` then update
  `.env.vps`. No grant changes needed.
- **Revoke entirely:**

  ```sql
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hava_readonly;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM hava_readonly;
  REVOKE ALL ON SCHEMA public FROM hava_readonly;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM hava_readonly;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON SEQUENCES FROM hava_readonly;
  REVOKE CONNECT ON DATABASE railway FROM hava_readonly;
  DROP ROLE hava_readonly;
  ```
