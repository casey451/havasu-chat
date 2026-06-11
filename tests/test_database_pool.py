"""PERF-1: explicit pool sizing + connection_released() release helper.

Audit: docs/AUDIT_SECURITY_PERF_OPS_2026-06-10.md:70-77.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import QueuePool

from app.db.database import _engine_kwargs, connection_released


class _Base(DeclarativeBase):
    pass


class _Thing(_Base):
    __tablename__ = "perf1_release_probe"

    id: Mapped[int] = mapped_column(primary_key=True)


@pytest.fixture()
def pooled_session(tmp_path):
    """Throwaway file-SQLite engine on an explicit QueuePool (so checkedout() is meaningful)."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'pool_probe.db').as_posix()}",
        poolclass=QueuePool,
        connect_args={"check_same_thread": False},
    )
    _Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    yield engine, db
    db.close()
    engine.dispose()


def test_engine_kwargs_sqlite_has_no_pool_sizing():
    kwargs = _engine_kwargs("sqlite:///./x.db")
    assert kwargs == {"connect_args": {"check_same_thread": False}}


def test_engine_kwargs_postgres_defaults():
    kwargs = _engine_kwargs("postgresql://u:p@h/db")
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20
    assert kwargs["pool_timeout"] == 10
    assert kwargs["pool_recycle"] == 1800


def test_engine_kwargs_env_overrides(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "3")
    kwargs = _engine_kwargs("postgresql://u:p@h/db")
    assert kwargs["pool_size"] == 4
    assert kwargs["max_overflow"] == 0
    assert kwargs["pool_timeout"] == 3
    assert kwargs["pool_recycle"] == 1800  # untouched knob keeps its default


def test_engine_kwargs_garbage_env_falls_back(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "banana")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "  ")
    kwargs = _engine_kwargs("postgresql://u:p@h/db")
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20


def test_connection_released_returns_connection_to_pool(pooled_session):
    engine, db = pooled_session
    db.execute(text("SELECT 1"))
    assert engine.pool.checkedout() == 1  # read transaction pins a connection

    with connection_released(db):
        assert engine.pool.checkedout() == 0  # released for the slow call

    db.execute(text("SELECT 1"))  # session still usable, lazily re-acquires
    assert engine.pool.checkedout() == 1


def test_connection_released_refuses_pending_writes(pooled_session):
    engine, db = pooled_session
    db.add(_Thing())
    with pytest.raises(RuntimeError, match="pending uncommitted writes"):
        with connection_released(db):
            pass  # pragma: no cover
    db.rollback()


def test_connection_released_allows_committed_state(pooled_session):
    engine, db = pooled_session
    db.add(_Thing())
    db.commit()
    with connection_released(db):
        assert engine.pool.checkedout() == 0
    assert db.query(_Thing).count() == 1
