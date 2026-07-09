"""OPS-1: /health must report 503 when the database is unreachable.

Railway's ``healthcheckPath`` gates deploys on this endpoint — a process that
cannot reach Postgres must fail the probe, not serve a 200 with
``db_connected: false`` and let a dead deploy go live.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


def test_health_200_when_db_ok() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db_connected"] is True
    # Build SHA present so the cold-cache canary can match it against each page's
    # <meta name="build-sha"> ("dev" locally where the deploy env var is unset).
    assert "build_sha" in body and body["build_sha"]
    # DB-identity fingerprint present (values are null on the SQLite test DB — the
    # Postgres-only probes fail gracefully — but the contract/shape is asserted).
    assert "db_identity" in body
    assert set(body["db_identity"]) == {
        "system_identifier", "database", "server_port", "server_version"
    }


def test_health_503_when_db_query_fails() -> None:
    class _BrokenSession:
        def query(self, *args: object, **kwargs: object):
            raise RuntimeError("db down")

    def _broken_db():
        yield _BrokenSession()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _broken_db
    try:
        with TestClient(app) as client:
            r = client.get("/health")
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
    assert r.status_code == 503
    body = r.json()
    assert body["db_connected"] is False
    assert body["status"] == "error"
