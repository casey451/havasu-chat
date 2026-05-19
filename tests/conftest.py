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
    # Before any test module imports ``app`` (and builds the slowapi limiter), disable
    # rate limits unless the runner explicitly left ``RATE_LIMIT_DISABLED`` unset.
    os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
    os.environ.setdefault("AUTH_DEV_MODE", "1")
    os.environ.setdefault("AUTH_MAGIC_LINK_BASE_URL", "http://testserver")
    os.environ.setdefault("R2_ACCESS_KEY_ID", "test-access-key-id")
    os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test-secret")
    os.environ.setdefault(
        "R2_ENDPOINT_URL", "https://test.r2.cloudflarestorage.com"
    )
    os.environ.setdefault("R2_BUCKET_NAME", "test-bucket")
    os.environ.setdefault("R2_PUBLIC_URL_BASE", "https://pub-test.r2.dev")
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


def _cleanup_phase7_seed_sources() -> None:
    from sqlalchemy import delete, select

    from app.db.database import SessionLocal
    from app.db.models import Entity, EntityCategory, Provider

    sources = (
        "test-p7",
        "test-p7-boat",
        "test-p7-heat",
        "test",
        "test-p7-sb",
        "test-tier2-pivot",
    )
    with SessionLocal() as db:
        for src in sources:
            for prov in db.scalars(select(Provider).where(Provider.source == src)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == src)).all():
                db.execute(
                    delete(EntityCategory).where(EntityCategory.entity_id == ent.id)
                )
                db.delete(ent)
        db.commit()


@pytest.fixture(autouse=True)
def _phase7_test_row_cleanup() -> None:
    """Remove Phase 7 seed rows after every test so tier2 catalog tests stay isolated."""
    yield
    _cleanup_phase7_seed_sources()
