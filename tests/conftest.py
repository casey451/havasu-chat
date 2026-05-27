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
    # PR D6 (2026-05-26) flipped HOME_REDESIGN to ON by default in prod.
    # Pin tests to HOME_REDESIGN=0 so the large pre-D-series test surface
    # (Phase 3/6/7/8/9 etc.) keeps hitting the legacy home.html template
    # without per-test refactors. Direction C / D-series tests opt back in
    # explicitly via ``?redesign=1`` query param or
    # ``monkeypatch.setenv("HOME_REDESIGN", "1")``. The feature-flag and
    # direction-C test modules ``monkeypatch.delenv`` to test the prod
    # default directly.
    os.environ.setdefault("HOME_REDESIGN", "0")
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
    from app.db.models import Entity, EntityCategory, Program, Provider

    sources = (
        "test-p7",
        "test-p7-boat",
        "test-p7-heat",
        "test",
        "test-p7-sb",
        "test-tier2-pivot",
        # Added 2026-05-21 per Cursor diagnostic of
        # tests/test_gap_template_contribute_link.py::test_date_lookup_gap_includes_contribute:
        # `test_program_category_ref_relationship` was committing a Program with
        # provider_name="City Events" and source="test-directory-schema", which
        # the entity matcher then indexed (Program.provider_name path), poisoning
        # the near-match scoring for later tests in the same pytest session.
        "test-directory-schema",
    )
    with SessionLocal() as db:
        for src in sources:
            for prov in db.scalars(select(Provider).where(Provider.source == src)).all():
                db.delete(prov)
            # Programs are entity-matcher inputs via Program.provider_name; clean
            # them up alongside Providers so test pollution doesn't leak into the
            # near-match scoring path on subsequent tests.
            for prog in db.scalars(select(Program).where(Program.source == src)).all():
                db.delete(prog)
            for ent in db.scalars(select(Entity).where(Entity.source == src)).all():
                db.execute(
                    delete(EntityCategory).where(EntityCategory.entity_id == ent.id)
                )
                db.delete(ent)
        db.commit()


@pytest.fixture(autouse=True)
def _phase7_test_row_cleanup() -> None:
    """Remove Phase 7 seed rows after every test so tier2 catalog tests stay isolated.

    Also resets the entity-matcher module-level catalog cache (added 2026-05-27,
    v45 session) so the 5-minute TTL on ``_rows_loaded_at`` doesn't carry stale
    catalog state across tests within the same pytest process. See
    ``outputs/entity_matcher_cache_deferral_2026-05-27_v41.md`` for the failure
    mode this prevents (``test_post_api_chat_tier1_phone_lookup_path`` returning
    ``tier_used == "gap_template"`` instead of ``"1"`` because a prior test's
    catalog warm masked the freshly-seeded providers).
    """
    yield
    _cleanup_phase7_seed_sources()
    from app.chat.entity_matcher import reset_entity_matcher

    reset_entity_matcher()
