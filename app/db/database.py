from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

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


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Bring the database schema to head via Alembic (or stamp legacy SQLite created with create_all)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
