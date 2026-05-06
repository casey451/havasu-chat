# database

`app/db/database.py` (~79 lines)

## Purpose

Single module for **SQLAlchemy engine**, **`SessionLocal` factory**, **`DeclarativeBase` subclass (`Base`)**, **database URL resolution**, FastAPI **`get_db`** dependency, and **`init_db`** bootstrap that reconciles Alembic vs legacy SQLite layouts. Imported early by models (`from app.db.database import Base`) and by `app/main.py` at startup.

## Public surface

**`get_database_url() -> str`** — Reads **`DATABASE_URL`** env (stripped). If unset/empty, returns default **`sqlite:///…/data/events.db`** (path under repo `data/`, directory created at import).

**`DATABASE_URL`** — Module-level string cached at import via `get_database_url()`.

**`DB_PATH`**, **`_DEFAULT_SQLITE_URL`** — Dev defaults; tests often override env before import per `tests/conftest.py`.

**`engine`** — `create_engine(DATABASE_URL, **_engine_kwargs(url))`.

**`SessionLocal`** — `sessionmaker(bind=engine, autoflush=False, autocommit=False)`.

**`class Base(DeclarativeBase)`** — Empty declarative base; all ORM models inherit from it in `app/db/models.py`.

**`init_db() -> None`** — Runtime migration orchestration:

1. Build Alembic `Config` from repo-root `alembic.ini`, set `sqlalchemy.url` from **`get_database_url()`** (not the stale ini default).
2. **`inspect(engine)`** — if `alembic_version` exists **and** has rows → **`command.upgrade(cfg, "head")`**.
3. If `alembic_version` is empty/missing but **`events`** table exists → **`command.stamp(cfg, "head")`** (legacy DB that predates version table population — avoids re-running initial CREATE on existing data).
4. Else → **`command.upgrade(cfg, "head")`** (fresh DB).

**`get_db()`** — Generator dependency: `SessionLocal()` yield, **`finally: close()`**.

## Inputs and outputs

**`get_db`** yields one session per request; no return value to callers beyond dependency injection semantics.

**`init_db`** returns `None`; raises from Alembic if migrations fail.

## Internal structure

**`_engine_kwargs(url)`** — SQLite URLs get `connect_args={"check_same_thread": False}` for FastAPI multi-threaded dev servers; non-SQLite URLs use `pool_pre_ping=True`.

**Import-time side effects:**

- `ensure_dotenv_loaded()` from `app.bootstrap_env` so `.env` is visible before URL resolution.
- **`_DATA_DIR.mkdir(exist_ok=True)`** when using default SQLite path.

## Conventions

**`get_database_url()` at init_db time.** Alembic config URL is refreshed inside `init_db` so tests that patch env before calling `init_db` see the correct database.

**Sessions closed in `get_db`.** Prefer FastAPI `Depends(get_db)` over bare `SessionLocal()` in HTTP handlers; scripts and background tasks open sessions explicitly.

**Models import `Base` from here.** Keeps metadata binding consistent — do not declare a second `DeclarativeBase` elsewhere.

## Known limitations and design notes

**SQLite default is dev-oriented.** Production (Railway) must set **`DATABASE_URL`** to Postgres; local file lives under **`data/events.db`** (Slice 48 moved from repo root — see Backlog #28).

**Stamp-vs-upgrade branch.** Operators upgrading very old copies should understand `stamp head` behavior when `events` exists without version rows — equivalent to “assume schema matches migration head.”

**No async engine.** Entire stack uses sync SQLAlchemy sessions.

## Configuration

- **`DATABASE_URL`** — optional; when set, used verbatim for SQLAlchemy URL.
- **`alembic.ini`** — file location only; URL overridden in code for `init_db`.

## Related

**Direct callers:**

- `app/main.py` — `init_db()` on startup; `get_db` / `SessionLocal` used broadly (user asked Slice 64 not to edit `main.py`; callers remain accurate).
- Most routers and scripts that need DB — pattern `Depends(get_db)` or `with SessionLocal() as db`.

**Direct dependencies:**

- `sqlalchemy.create_engine`, `inspect`, `text`
- `sqlalchemy.orm.sessionmaker`, `DeclarativeBase`
- `alembic.config.Config`, `alembic.command`
- `app.bootstrap_env.ensure_dotenv_loaded`

**Cross-references:**

- `docs/components/models.md` — ORM tables bound to `Base`.
- `alembic/env.py` — offline/online migration context (sibling to `versions/`).
- `docs/maintainability/railway_layout.md` — production `DATABASE_URL` posture.
