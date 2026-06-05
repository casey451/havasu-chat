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
    os.environ.setdefault("R2_ENDPOINT_URL", "https://test.r2.cloudflarestorage.com")
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


# Module-scoped seed source in tests/test_ask_mode.py (``_phase34_seed``); its
# rows must survive across the module's tests, so the per-test sweep below
# exempts it. The module tears its own rows down.
_MODULE_SEED_SOURCE = "phase34-test"


def _cleanup_test_source_rows() -> None:
    """Delete Event/Entity/Program/Provider rows created under a test source.

    History: this started as a curated list of phase-7 seed sources, but the
    curated list kept missing newcomers — under ``pytest -n`` the worker-local
    interleaving changes, and Events/Entities/Programs from one test module
    leak into another's window/cap/catalog assertions (e.g.
    ``test_tier2_db_query``'s June 2026 ``tier2-test`` events landing inside
    ``test_oneoffs_fill_before_recurring_under_cap``'s this-week window). All
    test-created rows in this suite use a ``source`` that either starts with
    ``test`` (``test``, ``test-*``, ``test_*``) or ends with ``-test``
    (``tier2-test``, ``x21-test``, ...), so a two-pattern sweep is both
    broader and cheaper than the per-source loop it replaces.

    Deliberately NOT swept:

    * ``phase34-test`` (:data:`_MODULE_SEED_SOURCE`) — module-scoped seed in
      ``tests/test_ask_mode.py``, cleaned by that module's own teardown.
    * Non-test sources (``google_places``, ``osm``, ``seed``, ...) — tests
      using those clean up after themselves with explicit deletes, and the
      alembic seed rows (categories) carry no source at all.

    Entity children (EntityCategory) are bulk-deleted first because the
    SQLite test engine runs with foreign_keys OFF, so ``passive_deletes``
    cascades never fire.
    """
    from sqlalchemy import ColumnElement, and_, delete, or_, select
    from sqlalchemy.orm import InstrumentedAttribute

    from app.db.database import SessionLocal
    from app.db.models import Entity, EntityCategory, Event, Program, Provider

    def _is_test_source(col: InstrumentedAttribute[str]) -> ColumnElement[bool]:
        return and_(
            or_(col.like("test%"), col.like("%-test")),
            col != _MODULE_SEED_SOURCE,
        )

    with SessionLocal() as db:
        ent_ids = list(db.scalars(select(Entity.id).where(_is_test_source(Entity.source))).all())
        if ent_ids:
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(ent_ids)))
            db.execute(delete(Entity).where(Entity.id.in_(ent_ids)))
        db.execute(delete(Event).where(_is_test_source(Event.source)))
        db.execute(delete(Program).where(_is_test_source(Program.source)))
        db.execute(delete(Provider).where(_is_test_source(Provider.source)))
        db.commit()


@pytest.fixture(autouse=True)
def _test_source_row_cleanup() -> None:
    """Remove ``test*``-sourced rows after every test so catalog/window tests stay isolated.

    Also resets the entity-matcher module-level catalog cache (added 2026-05-27,
    v45 session) so the 5-minute TTL on ``_rows_loaded_at`` doesn't carry stale
    catalog state across tests within the same pytest process. See
    ``outputs/entity_matcher_cache_deferral_2026-05-27_v41.md`` for the failure
    mode this prevents (``test_post_api_chat_tier1_phone_lookup_path`` returning
    ``tier_used == "gap_template"`` instead of ``"1"`` because a prior test's
    catalog warm masked the freshly-seeded providers).
    """
    yield
    _cleanup_test_source_rows()
    from app.chat.entity_matcher import reset_entity_matcher

    reset_entity_matcher()
