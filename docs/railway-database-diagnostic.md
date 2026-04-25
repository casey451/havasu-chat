# Railway database diagnostic — Havasu chat vs Postgres vs `railway run`

**Purpose:** Handoff for review (e.g. Claude). Documents how the app resolves the DB URL, what Railway CLI shows for each service, and why `railway run` can hit SQLite while production hits Postgres.

**Scope:** Code inspection and `railway variable` / `railway variables` only. No population scripts were run; no Railway or code changes were made as part of this investigation.

**Security:** Variable values below are **redacted** where sensitive. Do not paste raw `railway variable list -k --service Postgres` output into shared channels; it includes live credentials.

---

## 1. Havasu chat service — variable list (redacted)

From `railway variables` (linked **Havasu chat** service):

| Name | Value (redacted) |
|------|------------------|
| `ADMIN_PASSWORD` | `<redacted — see Railway dashboard>` |
| `OPENAI_API_KEY` | `<redacted — see Railway dashboard>` |
| `RAILWAY_ENVIRONMENT` | `production` |
| `RAILWAY_ENVIRONMENT_ID` | `272f465f-806d-4f0a-9c30-2b97dec352cb` |
| `RAILWAY_ENVIRONMENT_NAME` | `production` |
| `RAILWAY_PRIVATE_DOMAIN` | `havasu-chat.railway.internal` |
| `RAILWAY_PROJECT_ID` | `f94c4651-cc90-4041-b445-057167938b20` |
| `RAILWAY_PROJECT_NAME` | `Havasu chat` |
| `RAILWAY_SERVICE_ID` | `43cd280e-5dbd-48a6-9d33-fd5f7b7e60a4` |
| `RAILWAY_SERVICE_NAME` | ` Havasu chat` (leading space in CLI output) |
| `SECRET_KEY` | `<redacted — see Railway dashboard>` |
| `SENTRY_DSN` | `<redacted — see Railway dashboard>` |

**Not present** in this list: `DATABASE_URL`, `DATABASE_PUBLIC_URL`, or any `PG*` / `POSTGRES_*` variables.

**Related check:** `railway run .\.venv\Scripts\python.exe -c "import os; ..."` showed `DATABASE_URL` **not set** in the subprocess, consistent with the app service variable list.

---

## 2. Postgres service — exposed variables

**Command:** `railway variable list -k --service "Postgres"`

**Variables (names and role; values not reproduced here — CLI printed live credentials):**

| Variable | Role |
|----------|------|
| `DATABASE_URL` | Internal Postgres URL (`postgres.railway.internal`, port `5432`, database `railway`). |
| `DATABASE_PUBLIC_URL` | Public TCP proxy URL (proxy host + port). |
| `PGDATA` | Data directory under `/var/lib/postgresql/data/...`. |
| `PGDATABASE` | `railway` |
| `PGHOST` | `postgres.railway.internal` |
| `PGPASSWORD` | Postgres password (matches URL credential material). |
| `PGPORT` | `5432` |
| `PGUSER` | `postgres` |
| `POSTGRES_DB` | `railway` |
| `POSTGRES_PASSWORD` | Same secret family as `PGPASSWORD` / URLs. |
| `POSTGRES_USER` | `postgres` |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | `60` |
| `RAILWAY_ENVIRONMENT` | `production` |
| `RAILWAY_ENVIRONMENT_ID` | Same environment id as app. |
| `RAILWAY_ENVIRONMENT_NAME` | `production` |
| `RAILWAY_PRIVATE_DOMAIN` | `postgres.railway.internal` |
| `RAILWAY_PROJECT_ID` / `RAILWAY_PROJECT_NAME` | Same project as app. |
| `RAILWAY_SERVICE_ID` | Postgres service id. |
| `RAILWAY_SERVICE_NAME` | `Postgres` |
| `RAILWAY_TCP_APPLICATION_PORT` | `5432` |
| `RAILWAY_TCP_PROXY_DOMAIN` | Public proxy hostname. |
| `RAILWAY_TCP_PROXY_PORT` | Public proxy port. |
| `RAILWAY_VOLUME_ID` / `RAILWAY_VOLUME_MOUNT_PATH` / `RAILWAY_VOLUME_NAME` | Volume metadata. |
| `SSL_CERT_DAYS` | `820` |

**Takeaway:** `DATABASE_URL` is defined on the **Postgres** service. The **Havasu chat** service’s CLI-visible variable table does **not** include `DATABASE_URL`.

---

## 3. `app/db/database.py` — URL resolution and engine

**Read path:** only `DATABASE_URL` from the environment (after `ensure_dotenv_loaded()` at import time in this module).

```python
# app/db/database.py (excerpt)

DB_PATH = Path(__file__).resolve().parents[2] / "events.db"
_DEFAULT_SQLITE_URL = f"sqlite:///{DB_PATH.as_posix()}"


def get_database_url() -> str:
    """Resolve DB URL from env, or the project SQLite file when DATABASE_URL is unset."""
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        return _DEFAULT_SQLITE_URL
    return raw


DATABASE_URL = get_database_url()


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # postgresql://, postgres://, etc.
    return {"pool_pre_ping": True}


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

**Fallback:** If `DATABASE_URL` is missing or whitespace-only, the app uses repo-local SQLite at `events.db` (path derived from package layout).

**Other env names:** None in this file — no `PGHOST`, `DATABASE_PUBLIC_URL`, or Railway-specific URL construction.

**Alembic:** `init_db()` sets `cfg.set_main_option("sqlalchemy.url", get_database_url())` so migrations follow the same resolver.

---

## 4. Repo `.env` and dotenv behavior

**Found:** `projects/havasu-chat/.env` only (no `.env.local`, `.env.example`, `.env.sample` in repo search under project root).

```env
# .env (representative — no DATABASE_URL)

OPENAI_API_KEY=

ADMIN_PASSWORD=changeme
```

```python
# app/bootstrap_env.py (excerpt)

def ensure_dotenv_loaded() -> None:
    """Parse `.env` if present. Existing ``os.environ`` keys are never overwritten."""
    global _LOADED
    if _LOADED:
        return
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    _LOADED = True
```

Platform-injected `DATABASE_URL` is never overwritten by `.env`. The repo `.env` does not supply Postgres.

---

## 5. Python search — Postgres / DB URL usage

- Case-insensitive `postgres` in `*.py`: only a comment in `database.py` (`# postgresql://, postgres://, etc.`).
- `DATABASE_URL` / related usage:
  - `app/db/database.py` — primary resolver.
  - `alembic/env.py` — uses `get_database_url()` from `database.py`.
  - `tests/conftest.py` — sets `DATABASE_URL` to temp SQLite for tests.
  - `scripts/activate_scraped_programs.py` — comment about `railway run` and `DATABASE_URL`.
  - `app/admin/router.py` — imports `DATABASE_URL`; branches on `startswith("sqlite")` for admin behavior, not for building Postgres URLs.

No code path constructs Postgres from `PGHOST` / `POSTGRES_*` alone.

---

## 6. Railway-specific logic in `main.py` / `database.py`

**`database.py`:** No `RAILWAY_ENVIRONMENT` or Railway-specific DB logic.

**`main.py`:** `RAILWAY_ENVIRONMENT` is used for Sentry environment naming and for `run_seed_if_empty` on startup — **not** for database URL selection.

```python
# app/main.py (excerpt) — Sentry

environment = "production" if os.getenv("RAILWAY_ENVIRONMENT") else "development"
sentry_sdk.init(dsn=dsn, environment=environment, ...)
```

```python
# app/main.py (excerpt) — lifespan

async def lifespan(_: FastAPI):
    logger.info("ADMIN_PASSWORD loaded: %s", bool(os.getenv("ADMIN_PASSWORD")))
    init_db()
    if os.getenv("RAILWAY_ENVIRONMENT"):
        await asyncio.to_thread(run_seed_if_empty)
```

---

## 7. Prior conclusion (Script 1 / seed_providers)

Because `railway run` did not inject `DATABASE_URL` and `database.py` falls back to SQLite when it is unset, a provider seed run under that subprocess would write to **ephemeral container-local SQLite** (`events.db`), not production Postgres. A summary like “providers updated: 25” in that context is **not** evidence of production Postgres writes.

---

## 8. Synthesis

| Context | `DATABASE_URL` in process env? | App behavior (per code) |
|---------|-------------------------------|-------------------------|
| **Deployed Havasu chat** (observed: DB works in prod) | Likely set by Railway at deploy/runtime (service linking / referenced variables), possibly not shown on `railway variables` for the app service | Postgres when URL is `postgresql://` / `postgres://` |
| **`railway run` (app-linked directory, as tested)** | Not set in subprocess | SQLite `events.db` |
| **Postgres service** (`variable list -s Postgres`) | Yes — `DATABASE_URL`, `DATABASE_PUBLIC_URL`, `PG*` | N/A (different service) |

**Implication:** The application **only** honors **`DATABASE_URL`**. There is no alternate code path from Postgres’s `PG*` variables. Aligning `railway run` with production requires the **same** `DATABASE_URL` (or equivalent explicit export) in the subprocess environment — via Railway app service variables, CLI behavior, or a deliberate local export (operational choice; not prescribed here).

---

## 9. Suggested review questions for Claude

1. Should `DATABASE_URL` be added explicitly to the **Havasu chat** service (e.g. `${{ Postgres.DATABASE_URL }}`) so `railway run` and deployments share one obvious source of truth in CLI output?
2. Is there any Railway-documented difference between **injected** linked variables at runtime vs **`railway variable list`** for the web service?
3. Should seed/maintenance scripts print the resolved DB backend (e.g. SQLite vs Postgres) at startup to prevent silent mis-targeting?

---

*File: `docs/railway-database-diagnostic.md`*
