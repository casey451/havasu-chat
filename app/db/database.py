from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = _DATA_DIR / "events.db"
_DEFAULT_SQLITE_URL = f"sqlite:///{DB_PATH.as_posix()}"


def get_database_url() -> str:
    """Resolve DB URL from env, or the project SQLite file when DATABASE_URL is unset.

    Fail-closed in production (OPS-2, same pattern as the auth secrets): when
    ``RAILWAY_ENVIRONMENT`` is set, a missing/blank ``DATABASE_URL`` raises at
    import instead of silently booting an empty local SQLite app that would
    pass a naive healthcheck. Local/test keeps the SQLite fallback.
    """
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        if (os.getenv("RAILWAY_ENVIRONMENT") or "").strip():
            raise RuntimeError(
                "DATABASE_URL must be set in production (RAILWAY_ENVIRONMENT is "
                "set); refusing to fall back to a local SQLite file."
            )
        return _DEFAULT_SQLITE_URL
    return raw


DATABASE_URL = get_database_url()


def _int_env(name: str, default: int) -> int:
    """Optional integer tuning knob: unset/blank/garbage falls back to the default.

    Deliberately NOT fail-closed (unlike DATABASE_URL above): these are optional
    pool-tuning overrides, and refusing to boot prod over a typo'd knob would be
    worse than running with the documented default.
    """
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # postgresql://, postgres://, etc. — explicit pool sizing (PERF-1, audit
    # AUDIT_SECURITY_PERF_OPS_2026-06-10.md:70-77). SQLAlchemy's defaults
    # (5 + 10 = 15 connections, 30s pool_timeout) exhaust under ~15 concurrent
    # Tier-3-bound chats while each request's session is parked across an LLM
    # round-trip; request 16 then waits 30s and errors. Defaults below give
    # 10 persistent + 20 burst per process and fail fast (10s) when truly
    # saturated. Env knobs allow Railway-side tuning without a deploy.
    return {
        "pool_pre_ping": True,
        "pool_size": _int_env("DB_POOL_SIZE", 10),
        "max_overflow": _int_env("DB_MAX_OVERFLOW", 20),
        "pool_timeout": _int_env("DB_POOL_TIMEOUT", 10),
        "pool_recycle": _int_env("DB_POOL_RECYCLE", 1800),
    }


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Bring the database schema to head via Alembic (or stamp legacy SQLite created with create_all)."""
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", get_database_url())

    insp = inspect(engine)
    has_av = insp.has_table("alembic_version")
    has_events = insp.has_table("events")
    if has_av:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
        if n:
            command.upgrade(cfg, "head")
            return
        # Empty alembic_version table: treat like missing so we don't re-run initial CREATE on existing events.
    if has_events:
        command.stamp(cfg, "head")
        return
    command.upgrade(cfg, "head")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def connection_released(db: Session) -> Iterator[None]:
    """Hand ``db``'s pooled connection back for the duration of a slow non-DB call.

    PERF-1 (audit :70-77): the chat request's session otherwise stays checked out
    through 1-3s (worst-case 45s, ``LLM_CLIENT_READ_TIMEOUT_SEC``) OpenAI round-trips.
    ``rollback()`` ends the session's implicit read transaction, returning the
    connection to the pool; the session stays fully usable and lazily re-acquires
    a connection on its next query.

    Two caveats for adopters (chat hot path — ``unified_router``):

    - Refuses to run with pending uncommitted writes (raises ``RuntimeError``)
      rather than silently discarding them. Commit first.
    - ``rollback()`` expires loaded ORM instances; attribute access on objects
      loaded *before* the block triggers a refresh SELECT *after* it. Consume
      query results into plain values before wrapping (the tier-3 prompt-build
      path already does).

    Usage::

        with connection_released(db):
            hints = extract_hints(query)   # no DB work inside
    """
    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "connection_released() called with pending uncommitted writes; "
            "commit or roll back explicitly before releasing the connection."
        )
    db.rollback()
    yield


# Phase 1D dual-write hook registration lives in ``app/db/__init__.py`` — see
# the module docstring there for the full why. Short version: both ``models``
# and ``entity_dual_write`` need to be fully loaded before the registration
# can succeed, and they reference each other, so registration must happen
# from a third location that drives the load order. The package ``__init__.py``
# runs before any submodule attribute lookup, which makes it the right home.
#
# Earlier sessions called ``_register_orm_listeners()`` here at module-top,
# which broke when ``scripts/parks_rec_load.py`` reached ``contribution_store
# -> models -> database`` before ``models`` finished initializing
# (``ImportError: cannot import name 'ContactPoint'``). Session-22 fix.
