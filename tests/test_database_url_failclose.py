"""OPS-2: fail-closed DATABASE_URL resolution in production.

In production (``RAILWAY_ENVIRONMENT`` set) a missing/blank ``DATABASE_URL``
must raise instead of silently falling back to the local SQLite file — a
misconfigured prod deploy must crash at startup (and fail the healthcheck),
not boot an empty SQLite app. Locally / in tests the SQLite fallback is
unchanged. Mirrors tests/test_auth_secret_failclose.py.
"""

from __future__ import annotations

import pytest

from app.db import database as db_mod


def test_db_url_local_fallback_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.get_database_url().startswith("sqlite:///")


def test_db_url_prod_unset_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db_mod.get_database_url()


def test_db_url_prod_blank_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "   ")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db_mod.get_database_url()


def test_db_url_prod_set_returned_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host:5432/db")
    assert db_mod.get_database_url() == "postgresql://user:pw@host:5432/db"
