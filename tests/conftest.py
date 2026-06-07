"""
Pytest configuration: isolated SQLite DB for the whole test session.

Do not import app.* at module load time — pytest_configure must run before
app.db.database is first imported so DATABASE_URL is applied to the engine.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
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
def _init_test_database() -> Generator[None, None, None]:
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


def _snapshot_row_ids() -> dict[str, set[str]]:
    """Snapshot existing Provider/Program/Entity/Event ids before a test runs."""
    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import Entity, Event, Program, Provider

    with SessionLocal() as db:
        return {
            "provider": set(db.scalars(select(Provider.id)).all()),
            "program": set(db.scalars(select(Program.id)).all()),
            "entity": set(db.scalars(select(Entity.id)).all()),
            "event": set(db.scalars(select(Event.id)).all()),
        }


def _cleanup_new_rows(before: dict[str, set[str]]) -> None:
    """Delete Provider/Program/Entity/Event rows the finished test created.

    History: this started as a curated list of phase-7 seed sources, then a
    ``source LIKE 'test%' / '%-test'`` pattern sweep — but both kept missing
    newcomers. Under ``pytest -n`` the worker-local interleaving changes, and
    rows from one test module leak into another's window/cap/catalog/matcher
    assertions. The pattern sweep missed every test that seeds production-like
    sources: ``test_unified_router`` (Providers with ``source="seed"``),
    ``test_tier2_routing`` / ``test_phase38_gap_and_hours`` (same), the entity
    dual-write paths (Entities with ``source="google_places"``), etc. — e.g.
    ``test_unified_router``'s leftover "Altitude Trampoline Park — Lake Havasu
    City" Provider made ``test_explicit_bmx_hours_query_still_matches`` match
    the wrong entity once shuffled into the same worker (T2.4).

    A snapshot diff is source-agnostic: ids present before the test stay, ids
    created during the test are swept (regardless of what ``source`` the test
    chose), so no curated list can rot. Inductively the DB then only carries
    alembic seed rows plus deliberately module-scoped seeds between tests.

    Deliberately NOT swept:

    * ``phase34-test`` (:data:`_MODULE_SEED_SOURCE`) — module-scoped seed in
      ``tests/test_ask_mode.py``: it is created inside the FIRST test's setup
      phase (module fixture), so the diff would otherwise reap it after that
      first test. The module's own teardown removes it.
    * Other tables (ChatLog, Contribution, ...) — no observed cross-test
      assertion couples through them; extend the snapshot if one appears.

    Entity children (EntityCategory) are bulk-deleted first because the
    SQLite test engine runs with foreign_keys OFF, so ``passive_deletes``
    cascades never fire; Event/Program/Provider go before Entity so the sweep
    also works on a pooled connection where a prior test left PRAGMA
    foreign_keys=ON.
    """
    from sqlalchemy import and_, delete, select

    from app.db.database import SessionLocal
    from app.db.models import Entity, EntityCategory, Event, Program, Provider

    with SessionLocal() as db:
        for model, key in ((Event, "event"), (Program, "program"), (Provider, "provider")):
            new_ids = set(db.scalars(select(model.id)).all()) - before[key]
            if new_ids:
                db.execute(
                    delete(model).where(
                        and_(model.id.in_(new_ids), model.source != _MODULE_SEED_SOURCE)
                    )
                )
        new_ent_ids = list(
            db.scalars(
                select(Entity.id).where(
                    and_(
                        Entity.id.not_in(before["entity"]),
                        Entity.source != _MODULE_SEED_SOURCE,
                    )
                )
            ).all()
        )
        if new_ent_ids:
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(new_ent_ids)))
            db.execute(delete(Entity).where(Entity.id.in_(new_ent_ids)))
        db.commit()


class _NoNetworkOpenAI:
    """Autouse stand-in for every module-level ``OpenAI`` constructor seam.

    Several modules build their own ``OpenAI`` client straight from the
    ``openai`` package (NOT via ``app.core.llm_messages``, which LLM-mocking
    tests patch): ``app.core.embeddings`` (query + ingest embeddings),
    ``app.chat.hint_extractor`` (age/location hints), ``app.core.extraction`` (tagging), and ``app.core.llm_messages`` (tier-3
    completions). Any test that drives those
    paths with ``OPENAI_API_KEY`` set fired REAL requests to api.openai.com —
    tests/test_ask_mode.py alone made 75 live TLS connections per run (T2.4
    socket audit), each costing seconds and failing only as slowly as the
    network allows. Raising on construction keeps every caller's documented
    best-effort contract (they catch, log, and degrade to ``None``/empty)
    with zero sockets. Tests that exercise a specific seam re-patch it
    locally (e.g. ``patch.object(llm_cache, "OpenAI", ...)`` in
    tests/test_llm_cache.py), which overrides this autouse default.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("test suite: real OpenAI client construction blocked")


@pytest.fixture(autouse=True)
def _block_module_openai_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.chat.hint_extractor as hint_extractor
    import app.core.embeddings as embeddings
    import app.core.extraction as extraction
    import app.core.llm_messages as llm_messages

    # NOTE: app.v1.contrib_extraction imports OpenAI lazily inside the
    # function body, so there is no module attribute to patch; no test
    # currently drives that path with an API key set.
    # app.chat.llm_cache no longer constructs OpenAI directly — query embeddings
    # route through app.core.embeddings (HANDOFF #3), which is the seam now.
    for mod in (embeddings, hint_extractor, llm_messages, extraction):
        monkeypatch.setattr(mod, "OpenAI", _NoNetworkOpenAI)


@pytest.fixture(autouse=True)
def _test_source_row_cleanup() -> Generator[None, None, None]:
    """Remove rows the test created so catalog/window/matcher tests stay isolated.

    Also resets the entity-matcher module-level catalog cache (added 2026-05-27,
    v45 session) so the 5-minute TTL on ``_rows_loaded_at`` doesn't carry stale
    catalog state across tests within the same pytest process. See
    ``outputs/entity_matcher_cache_deferral_2026-05-27_v41.md`` for the failure
    mode this prevents (``test_post_api_chat_tier1_phone_lookup_path`` returning
    ``tier_used == "gap_template"`` instead of ``"1"`` because a prior test's
    catalog warm masked the freshly-seeded providers).
    """
    before = _snapshot_row_ids()
    yield
    _cleanup_new_rows(before)
    from app.chat.entity_matcher import reset_entity_matcher

    reset_entity_matcher()
