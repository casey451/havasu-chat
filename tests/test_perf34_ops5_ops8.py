"""PERF-3/PERF-4 (sync work off the event loop), OPS-5 (verify-only prod startup),
OPS-8 (single dictConfig + no silent admin-sync swallows).

Audit: docs/AUDIT_SECURITY_PERF_OPS_2026-06-10.md:87-99, :195-198, :218-221.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import app.admin.v1_overview as v1_overview
import app.auth.session as auth_session
import app.v1.routes.contribute as contribute_mod
from app.auth.session import COOKIE_NAME, sign_session_cookie
from app.db.database import _assert_schema_at_head, init_db
from app.main import _configure_logging, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _assert_off_event_loop() -> None:
    """Raises if called on a thread that runs an asyncio event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # worker thread — exactly where sync work belongs
    raise AssertionError("sync work ran on the event loop thread")


# --- PERF-3: contribute route's LLM/PIL work off the loop -----------------


def test_contribute_route_is_still_async():
    assert inspect.iscoroutinefunction(contribute_mod.post_contribute_start)


def test_contribute_text_extraction_runs_off_loop(client: TestClient, monkeypatch):
    calls: list[str] = []

    def fake_extract(text: str) -> dict:
        _assert_off_event_loop()
        calls.append(text)
        return {}

    monkeypatch.setattr(contribute_mod, "extract_from_text", fake_extract)
    r = client.post(
        "/api/contribute",
        json={"session_id": "perf3-session", "text": "taco stand flyer"},
    )
    assert r.status_code == 200
    assert calls == ["taco stand flyer"]


# --- PERF-4: session middleware DB work off the loop -----------------------


def test_session_middleware_lookup_runs_off_loop(client: TestClient, monkeypatch):
    seen: list[str] = []

    def fake_load(session_id: str):
        _assert_off_event_loop()
        seen.append(session_id)
        return None, None, False

    monkeypatch.setattr(auth_session, "_load_session_user", fake_load)
    client.cookies.set(COOKIE_NAME, sign_session_cookie("perf4-session-id"))
    r = client.get("/health")
    assert r.status_code == 200
    assert seen == ["perf4-session-id"]


def test_session_middleware_helper_clears_on_unknown_session():
    user, sess, clear = auth_session._load_session_user("no-such-session-id")
    assert user is None
    assert sess is None
    assert clear is True


# --- OPS-5: prod startup verifies, never migrates ---------------------------


def test_init_db_prod_gate_verifies_without_migrating(monkeypatch):
    """Main test DB is at head (conftest migrated it): the prod gate must pass
    WITHOUT invoking alembic's upgrade/stamp."""
    import alembic.command

    def _boom(*a, **k):  # pragma: no cover - failure path
        raise AssertionError("alembic migration invoked during prod startup (OPS-5)")

    monkeypatch.setattr(alembic.command, "upgrade", _boom)
    monkeypatch.setattr(alembic.command, "stamp", _boom)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    init_db()  # must verify and return quietly


def test_assert_schema_at_head_raises_on_unmigrated_db(tmp_path):
    from pathlib import Path

    from alembic.config import Config

    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    bind = create_engine(url, connect_args={"check_same_thread": False})
    try:
        with pytest.raises(RuntimeError, match="preDeploy owns migrations"):
            _assert_schema_at_head(cfg, bind=bind)
    finally:
        bind.dispose()


# --- OPS-8: logging config + no silent admin-sync swallows ------------------


def test_configure_logging_idempotent_single_root_handler(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    _configure_logging()
    _configure_logging()  # re-run must replace, not stack
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.INFO


def test_configure_logging_env_level_and_garbage_fallback(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    _configure_logging()
    assert logging.getLogger().level == logging.DEBUG
    monkeypatch.setenv("LOG_LEVEL", "verbose-nonsense")
    _configure_logging()
    assert logging.getLogger().level == logging.INFO
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    _configure_logging()


def test_admin_sync_logs_pull_failures_instead_of_silence(client: TestClient, monkeypatch, caplog):
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = client.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303

    def _boom(*a, **k):
        raise RuntimeError("pull exploded")

    monkeypatch.setattr(v1_overview, "run_pull", _boom)
    monkeypatch.setattr(v1_overview, "river_scene_pull", _boom)
    monkeypatch.setattr(v1_overview, "golake_pull", _boom)
    with caplog.at_level(logging.ERROR, logger="app.admin.v1_overview"):
        r = client.post("/admin/overview/sync", follow_redirects=False)
    assert r.status_code == 303  # best-effort behavior preserved
    msgs = [rec.message for rec in caplog.records]
    assert sum("pull failed" in m for m in msgs) == 3
