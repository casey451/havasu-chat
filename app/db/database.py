from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

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
    if insp.has_table("alembic_version"):
        command.upgrade(cfg, "head")
        return
    if insp.has_table("events"):
        # Pre-Alembic SQLite with full schema from metadata.create_all — align version table only.
        command.stamp(cfg, "head")
        return
    command.upgrade(cfg, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
