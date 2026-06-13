from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Project root (parent of alembic/)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import Base, get_database_url  # noqa: E402, F401, I001
import app.db.models  # noqa: E402, F401, I001

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: by default fileConfig DISABLES every logger
    # not named in alembic.ini. Migrations run in-process (app startup lifespan
    # via init_db, and the test session), so a default-True call silently turns
    # off already-imported app loggers (e.g. app.admin.v1_overview) for the rest
    # of the process -- which made admin-sync log assertions intermittently see
    # zero records depending on test order. Keep our loggers alive.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
