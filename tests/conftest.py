"""
Pytest configuration: isolated SQLite DB for the whole test session.

Do not import app.* at module load time — pytest_configure must run before
app.db.database is first imported so DATABASE_URL is applied to the engine.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Populated in pytest_configure when using the temp DB; used for teardown cleanup.
_TEST_SQLITE_FILE: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    """
    Set DATABASE_URL to a fresh temp SQLite file before test collection imports
    app modules (so sqlalchemy create_engine sees the test URL).

    Escape hatch: HAVASU_USE_DEV_DB_FOR_TESTS=1 uses repo-root events.db (or
    whatever DATABASE_URL was already set). **For rare local debugging only** —
    never set this in CI, Railway, or production automation; it defeats isolation
    and mutates the developer database.
    """
    global _TEST_SQLITE_FILE  # noqa: PLW0603 — module state for teardown
    if os.environ.get("HAVASU_USE_DEV_DB_FOR_TESTS") == "1":
        return
    fd, path = tempfile.mkstemp(suffix=".sqlite", prefix="havasu_pytest_")
    os.close(fd)
    _TEST_SQLITE_FILE = path
    abs_path = Path(path).resolve().as_posix()
    os.environ["DATABASE_URL"] = f"sqlite:///{abs_path}"


@pytest.fixture(scope="session", autouse=True)
def _init_test_database() -> None:
    """Run Alembic migrations once per session against the session test database."""
    from app.db.database import init_db

    init_db()
    yield
    if os.environ.get("HAVASU_USE_DEV_DB_FOR_TESTS") == "1":
        return
    path = _TEST_SQLITE_FILE
    if path and os.path.isfile(path):
        try:
            os.unlink(path)
        except OSError:
            pass
