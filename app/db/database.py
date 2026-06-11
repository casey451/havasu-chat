from __future__ import annotations

import os
from collections.abc import Iterator
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


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # postgresql://, postgres://, etc.
    return {"pool_pre_ping": True}


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _assert_schema_at_head(cfg, *, bind=None) -> None:
    """OPS-5 (audit :195-198): verify the DB is at the migration head — never migrate.

    Raises ``RuntimeError`` on mismatch. ``bind`` defaults to the module engine;
    tests pass their own throwaway engine.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    expected = set(script.get_heads())
    with (bind or engine).connect() as conn:
        current = set(MigrationContext.configure(conn).get_current_heads())
    if current != expected:
        raise RuntimeError(
            "DB schema is not at the migration head; preDeploy owns migrations "
            f"(OPS-5). db={sorted(current) or ['<none>']} expected={sorted(expected)}"
        )


def init_db() -> None:
    r"""Bring the database schema to head via Alembic (or stamp legacy SQLite created with create_all).

    In production (``RAILWAY_ENVIRONMENT`` set — the OPS-2 gate) this VERIFIES
    instead of migrating: Railway's preDeploy step is the sole migration runner
    (OPS-5), so N workers/replicas never race N concurrent ``upgrade head`` runs.
    A mismatch fails startup fast — booting against a wrong-schema DB is worse
    than refusing. Local/test keeps the upgrade-or-stamp bootstrap below.
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", get_database_url())

    if (os.getenv("RAILWAY_ENVIRONMENT") or "").strip():
        _assert_schema_at_head(cfg)
        return

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
