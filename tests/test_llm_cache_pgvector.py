"""HANDOFF #2: pgvector similarity path for the LLM response cache.

The real pgvector query path is validated by the staging rehearsal
(scripts/rehearse_migration.sh) -- pgvector cannot run on SQLite, so these
tests cover the *selection logic* (which path runs where), the literal
serialization, the threshold/time-sensitivity filtering on returned rows,
and the dimension guards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.chat import llm_cache
from app.chat.llm_cache import (
    EMBEDDING_DIM,
    SIMILARITY_THRESHOLD,
    _pgvector_available,
    _similarity_scan_pgvector,
    _similarity_scan_with_embedding,
    _store_pg_vector,
    _vector_literal,
)


def _clear_probe_cache():
    llm_cache._PGVECTOR_AVAILABLE.clear()


# ---------------------------------------------------------------------------
# _vector_literal
# ---------------------------------------------------------------------------


def test_vector_literal_format():
    assert _vector_literal([0.5, -1.0, 2.0]) == "[0.5,-1.0,2.0]"


def test_vector_literal_roundtrip_precision():
    import json

    vec = [0.123456789012345, -0.000001]
    parsed = json.loads(_vector_literal(vec))
    assert parsed == vec


# ---------------------------------------------------------------------------
# _pgvector_available: dialect + probe gating
# ---------------------------------------------------------------------------


def _db_with_dialect(name):
    db = MagicMock()
    db.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name=name), url=f"{name}://test"
    )
    return db


def test_pgvector_unavailable_on_sqlite():
    _clear_probe_cache()
    db = _db_with_dialect("sqlite")
    assert _pgvector_available(db) is False
    db.execute.assert_not_called()


def test_pgvector_available_on_postgres_with_ext_and_column():
    _clear_probe_cache()
    db = _db_with_dialect("postgresql")
    db.execute.return_value.scalar.return_value = 1
    assert _pgvector_available(db) is True
    # cached: second call must not re-probe
    db.execute.reset_mock()
    assert _pgvector_available(db) is True
    db.execute.assert_not_called()


def test_pgvector_probe_negative_is_cached():
    _clear_probe_cache()
    db = _db_with_dialect("postgresql")
    db.execute.return_value.scalar.return_value = None
    assert _pgvector_available(db) is False
    db.execute.reset_mock()
    assert _pgvector_available(db) is False
    db.execute.assert_not_called()


def test_pgvector_probe_exception_is_not_cached():
    _clear_probe_cache()
    db = _db_with_dialect("postgresql")
    db.execute.side_effect = RuntimeError("transient")
    assert _pgvector_available(db) is False
    # exception must NOT poison the cache -- a later healthy probe succeeds
    db.execute.side_effect = None
    db.execute.return_value.scalar.return_value = 1
    assert _pgvector_available(db) is True


# ---------------------------------------------------------------------------
# Path selection in _similarity_scan_with_embedding
# ---------------------------------------------------------------------------


def test_pg_path_selected_when_available():
    _clear_probe_cache()
    db = MagicMock()
    vec = [0.1] * EMBEDDING_DIM
    with (
        patch.object(llm_cache, "_pgvector_available", return_value=True),
        patch.object(
            llm_cache, "_similarity_scan_pgvector", return_value="pg-hit"
        ) as pg_scan,
    ):
        assert _similarity_scan_with_embedding(db, vec) == "pg-hit"
        pg_scan.assert_called_once()
    # the ORM Python scan must not have run
    db.scalars.assert_not_called()


def test_pg_clean_miss_is_final_no_python_rescan():
    db = MagicMock()
    vec = [0.1] * EMBEDDING_DIM
    with (
        patch.object(llm_cache, "_pgvector_available", return_value=True),
        patch.object(llm_cache, "_similarity_scan_pgvector", return_value=None),
    ):
        assert _similarity_scan_with_embedding(db, vec) is None
    db.scalars.assert_not_called()


def test_pg_error_falls_back_to_python_scan():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    vec = [0.1] * EMBEDDING_DIM
    with (
        patch.object(llm_cache, "_pgvector_available", return_value=True),
        patch.object(
            llm_cache, "_similarity_scan_pgvector", side_effect=RuntimeError("boom")
        ),
    ):
        assert _similarity_scan_with_embedding(db, vec) is None
    db.scalars.assert_called_once()


def test_dim_mismatch_skips_pg_path():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    vec = [0.1] * 768  # local-model dims != column dims
    with patch.object(llm_cache, "_pgvector_available", return_value=True) as avail:
        assert _similarity_scan_with_embedding(db, vec) is None
        avail.assert_not_called()  # short-circuits on dim before probing
    db.scalars.assert_called_once()


def test_python_path_on_sqlite_unchanged():
    _clear_probe_cache()
    db = _db_with_dialect("sqlite")
    db.scalars.return_value.all.return_value = []
    assert _similarity_scan_with_embedding(db, [0.1] * EMBEDDING_DIM) is None
    db.scalars.assert_called_once()


# ---------------------------------------------------------------------------
# _similarity_scan_pgvector row handling (db mocked)
# ---------------------------------------------------------------------------


def _pg_rows(db, rows):
    db.execute.return_value.fetchall.return_value = rows


def test_pgvector_scan_returns_best_above_threshold():
    db = MagicMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    _pg_rows(db, [("id-1", "answer-1", now, 0.97), ("id-2", "answer-2", now, 0.91)])
    with patch.object(llm_cache, "_bump_hit_telemetry") as bump:
        assert _similarity_scan_pgvector(db, [0.1] * EMBEDDING_DIM) == "answer-1"
        assert bump.call_args[0][1].id == "id-1"


def test_pgvector_scan_threshold_cutoff():
    db = MagicMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    _pg_rows(db, [("id-1", "answer-1", now, SIMILARITY_THRESHOLD - 0.01)])
    with patch.object(llm_cache, "_bump_hit_telemetry") as bump:
        assert _similarity_scan_pgvector(db, [0.1] * EMBEDDING_DIM) is None
        bump.assert_not_called()


def test_pgvector_scan_time_sensitive_skips_other_day():
    db = MagicMock()
    now = datetime.now(UTC).replace(tzinfo=None)
    stale = datetime(2020, 1, 1)
    _pg_rows(db, [("id-old", "stale", stale, 0.99), ("id-new", "fresh", now, 0.95)])
    with patch.object(llm_cache, "_bump_hit_telemetry"):
        out = _similarity_scan_pgvector(
            db, [0.1] * EMBEDDING_DIM, time_sensitive=True
        )
    assert out == "fresh"


# ---------------------------------------------------------------------------
# _store_pg_vector guards
# ---------------------------------------------------------------------------


def test_store_pg_vector_skips_non_1536_dim():
    db = MagicMock()
    import json

    with patch.object(llm_cache, "_pgvector_available", return_value=True):
        _store_pg_vector(db, "ck", json.dumps([0.1] * 32))
    db.execute.assert_not_called()


def test_store_pg_vector_writes_1536_dim():
    db = MagicMock()
    import json

    with patch.object(llm_cache, "_pgvector_available", return_value=True):
        _store_pg_vector(db, "ck", json.dumps([0.1] * EMBEDDING_DIM))
    db.execute.assert_called_once()
    db.commit.assert_called_once()


def test_store_pg_vector_noop_when_unavailable():
    db = MagicMock()
    import json

    with patch.object(llm_cache, "_pgvector_available", return_value=False):
        _store_pg_vector(db, "ck", json.dumps([0.1] * EMBEDDING_DIM))
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# generate_embedding: 32-dim fallback removed (extraction)
# ---------------------------------------------------------------------------


def test_generate_embedding_returns_none_on_failure():
    from app.core import extraction

    with patch.object(extraction.embeddings, "embed", return_value=None):
        assert extraction.generate_embedding("anything") is None


def test_generate_embedding_passes_through_provider_vector():
    from app.core import extraction

    with patch.object(extraction.embeddings, "embed", return_value=[0.5] * 8):
        assert extraction.generate_embedding("anything") == [0.5] * 8
