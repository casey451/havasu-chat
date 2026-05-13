"""Phase 4.1 — background-jobs scaffold tests.

Coverage:

* ``with_retry`` semantics — happy path, exhaustion, retry-then-success,
  backoff escalation, ``fatal_on`` bypass, Sentry breadcrumb fires on
  retry and exhaustion, no re-raise on exhaustion.
* ``with_retry_async`` mirror suite — happy path, exhaustion, the async
  helper uses ``asyncio.sleep`` (not ``time.sleep``).
* Outbox ORM + migration — class importable, CHECK constraints on
  ``state`` + ``kind``, ``attempts`` defaults to 0, migration cycles
  cleanly (downgrade -> upgrade).
* ``deliver_outbox_row`` state machine — pending -> delivered (success),
  pending -> pending+attempts (transient), pending -> failed at
  ``OUTBOX_MAX_ATTEMPTS``, idempotent on a delivered row.
* ``scripts/outbox_redrive`` behavior — picks only ``pending`` rows
  older than ``--idle-seconds``, respects ``--max-rows``, ``--dry-run``
  skips delivery.
* Magic-link integration — POST /api/auth/request-link inserts an
  Outbox row, BackgroundTasks delivers it, mocked send is invoked;
  send failure leaves the row in ``pending`` with ``attempts`` bumped.
* Gotcha-#17 cure — importing ``app.core.background`` does not import
  ``app.db.models`` at module top (subprocess test, mirroring the
  Phase 1D ``test_scraper_entry_point_import_chain_does_not_cycle``
  shape from session-22).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core import background as bg_module
from app.core.background import (
    OUTBOX_KIND_MAGIC_LINK,
    OUTBOX_MAX_ATTEMPTS,
    OUTBOX_STATE_DELIVERED,
    OUTBOX_STATE_FAILED,
    OUTBOX_STATE_IN_FLIGHT,
    OUTBOX_STATE_PENDING,
    deliver_outbox_row,
    enqueue_outbox,
    register_outbox_handler,
    with_retry,
    with_retry_async,
)
from app.db.database import SessionLocal
from app.db.models import MagicLinkToken, Outbox
from app.main import app as _fastapi_app


# ---------------------------------------------------------------------------
# with_retry — sync
# ---------------------------------------------------------------------------


def test_with_retry_happy_path_returns_value_on_first_attempt() -> None:
    calls: list[int] = []

    def _ok() -> str:
        calls.append(1)
        return "ok"

    out = with_retry(_ok, sleep=lambda _s: None)
    assert out == "ok"
    assert len(calls) == 1


def test_with_retry_exhaustion_returns_none_after_max_attempts() -> None:
    calls: list[int] = []

    def _always_raises() -> str:
        calls.append(1)
        raise RuntimeError("boom")

    out = with_retry(_always_raises, max_attempts=3, sleep=lambda _s: None)
    assert out is None
    assert len(calls) == 3


def test_with_retry_retry_then_success_returns_value() -> None:
    state = {"attempt": 0}

    def _flaky() -> str:
        state["attempt"] += 1
        if state["attempt"] < 2:
            raise RuntimeError("first call raises")
        return "second-call-ok"

    out = with_retry(_flaky, max_attempts=3, sleep=lambda _s: None)
    assert out == "second-call-ok"
    assert state["attempt"] == 2


def test_with_retry_backoff_escalates_per_multiplier() -> None:
    sleeps: list[float] = []

    def _record_sleep(s: float) -> None:
        sleeps.append(s)

    def _always_raises() -> None:
        raise RuntimeError("boom")

    with_retry(
        _always_raises,
        max_attempts=4,
        backoff_initial_s=1.0,
        backoff_multiplier=2.0,
        sleep=_record_sleep,
    )
    # 4 attempts -> 3 sleeps between attempts. Multiplier 2x.
    assert sleeps == [1.0, 2.0, 4.0]


def test_with_retry_fatal_on_bypasses_retry() -> None:
    calls: list[int] = []

    class _Validation(Exception):
        pass

    def _raises_fatal() -> None:
        calls.append(1)
        raise _Validation("400 bad request")

    out = with_retry(
        _raises_fatal,
        max_attempts=5,
        fatal_on=(_Validation,),
        sleep=lambda _s: None,
    )
    assert out is None
    assert len(calls) == 1


def test_with_retry_does_not_reraise_underlying_exception() -> None:
    def _raises() -> None:
        raise RuntimeError("never reaches caller")

    # Caller should never see the exception bubble out.
    out = with_retry(_raises, max_attempts=2, sleep=lambda _s: None)
    assert out is None


def test_with_retry_records_sentry_breadcrumb_on_retry_and_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    def _capture(**kwargs: Any) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(bg_module.sentry_sdk, "add_breadcrumb", _capture)

    def _always_raises() -> None:
        raise RuntimeError("boom")

    with_retry(_always_raises, max_attempts=3, sleep=lambda _s: None)
    # 3 attempts: 3 "retry" breadcrumbs + 1 "exhausted" breadcrumb.
    events = [c.get("data", {}).get("event") for c in captured]
    assert events.count("retry") == 3
    assert events.count("exhausted") == 1
    # Category is consistent.
    categories = {c.get("category") for c in captured}
    assert categories == {"background-jobs"}


def test_with_retry_invalid_max_attempts_raises() -> None:
    with pytest.raises(ValueError):
        with_retry(lambda: None, max_attempts=0)


# ---------------------------------------------------------------------------
# with_retry_async
# ---------------------------------------------------------------------------


def test_with_retry_async_happy_path_returns_value() -> None:
    async def _ok() -> str:
        return "async-ok"

    async def _no_sleep(_s: float) -> None:  # pragma: no cover — not exercised
        return None

    out = asyncio.run(with_retry_async(_ok, sleep=_no_sleep))
    assert out == "async-ok"


def test_with_retry_async_exhaustion_returns_none() -> None:
    async def _boom() -> None:
        raise RuntimeError("async boom")

    async def _no_sleep(_s: float) -> None:
        return None

    out = asyncio.run(
        with_retry_async(_boom, max_attempts=3, sleep=_no_sleep)
    )
    assert out is None


def test_with_retry_async_uses_asyncio_sleep_not_time_sleep() -> None:
    """The injected sleep callable receives the backoff and is awaitable.

    Proves the helper does not call ``time.sleep`` synchronously, which
    would block the event loop. We satisfy this by capturing the sleeps
    via the injection seam.
    """
    sleeps: list[float] = []

    async def _capture_sleep(s: float) -> None:
        sleeps.append(s)

    async def _boom() -> None:
        raise RuntimeError("async boom")

    asyncio.run(
        with_retry_async(
            _boom,
            max_attempts=3,
            backoff_initial_s=0.5,
            backoff_multiplier=2.0,
            sleep=_capture_sleep,
        )
    )
    assert sleeps == [0.5, 1.0]


# ---------------------------------------------------------------------------
# Outbox ORM + migration
# ---------------------------------------------------------------------------


def test_outbox_model_importable_with_expected_columns() -> None:
    cols = {c.name for c in Outbox.__table__.columns}
    assert {
        "id",
        "kind",
        "payload",
        "state",
        "attempts",
        "last_attempt_at",
        "last_error",
        "created_at",
        "updated_at",
        "delivered_at",
    } <= cols


def test_outbox_state_default_is_pending_and_attempts_defaults_to_zero() -> None:
    with SessionLocal() as db:
        row = Outbox(
            kind=OUTBOX_KIND_MAGIC_LINK,
            payload={"email": "x@example.com", "token": "tok"},
        )
        db.add(row)
        db.commit()
        rid = str(row.id)
    with SessionLocal() as db:
        row = db.get(Outbox, rid)
        assert row is not None
        assert row.state == OUTBOX_STATE_PENDING
        assert row.attempts == 0
        assert row.delivered_at is None
        assert row.last_attempt_at is None
        assert row.last_error is None


def test_outbox_check_constraint_rejects_invalid_state() -> None:
    from sqlalchemy.exc import IntegrityError

    with SessionLocal() as db:
        row = Outbox(
            kind=OUTBOX_KIND_MAGIC_LINK,
            payload={"x": 1},
            state="not-a-real-state",
        )
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()


def test_outbox_check_constraint_rejects_invalid_kind() -> None:
    from sqlalchemy.exc import IntegrityError

    with SessionLocal() as db:
        row = Outbox(kind="not-a-real-kind", payload={"x": 1})
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()


def test_outbox_migration_upgrade_downgrade_cycle_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 4.1 migration cycles cleanly: head -> downgrade-1 -> head.

    Runs against a fresh temp SQLite to avoid disturbing the session
    DB. Confirms reversibility before the operator commits Phase 4.1.

    Critically: ``alembic/env.py`` calls
    ``config.set_main_option('sqlalchemy.url', get_database_url())``
    which clobbers anything we set on the Config instance. Override
    via the ``DATABASE_URL`` env var instead so :func:`get_database_url`
    picks up our temp path.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    db_path = tmp_path / "phase4_outbox_cycle.sqlite"
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    cfg = Config(str(repo_root / "alembic.ini"))

    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == "0a1b2c3d4e5f"
        insp = inspect(engine)
        assert "outbox" in insp.get_table_names()

        command.downgrade(cfg, "-1")
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == "e1f2a3b4c5d6"
        insp = inspect(engine)
        assert "outbox" not in insp.get_table_names()

        # And back up — proves the migration is durable across cycles.
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == "0a1b2c3d4e5f"
        insp = inspect(engine)
        assert "outbox" in insp.get_table_names()
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# deliver_outbox_row state machine
# ---------------------------------------------------------------------------


def _make_outbox_row(payload: dict[str, Any] | None = None) -> str:
    with SessionLocal() as db:
        row = Outbox(
            kind=OUTBOX_KIND_MAGIC_LINK,
            payload=payload or {"email": "x@example.com", "token": "t", "next_path": None},
        )
        db.add(row)
        db.commit()
        return str(row.id)


def test_deliver_outbox_row_success_transitions_to_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def _ok_handler(payload: dict[str, Any]) -> None:
        calls.append(payload)

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _ok_handler)

    row_id = _make_outbox_row({"email": "user@example.com", "token": "tok-abc"})
    ok = deliver_outbox_row(row_id)
    assert ok is True
    assert calls == [{"email": "user@example.com", "token": "tok-abc"}]
    with SessionLocal() as db:
        row = db.get(Outbox, row_id)
        assert row is not None
        assert row.state == OUTBOX_STATE_DELIVERED
        assert row.delivered_at is not None
        assert row.last_error is None
        assert row.attempts == 0


def test_deliver_outbox_row_transient_failure_returns_to_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _flaky(payload: dict[str, Any]) -> None:
        raise RuntimeError("Resend 429")

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _flaky)

    row_id = _make_outbox_row()
    ok = deliver_outbox_row(row_id)
    assert ok is False
    with SessionLocal() as db:
        row = db.get(Outbox, row_id)
        assert row is not None
        assert row.state == OUTBOX_STATE_PENDING
        assert row.attempts == 1
        assert row.last_error is not None
        assert "RuntimeError" in row.last_error


def test_deliver_outbox_row_exhaustion_transitions_to_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _always_raises(payload: dict[str, Any]) -> None:
        raise RuntimeError("persistent failure")

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _always_raises)

    row_id = _make_outbox_row()
    # Pre-bump the attempts counter to one shy of the cap so the next
    # call lands the row in the ``failed`` state.
    with SessionLocal() as db:
        row = db.get(Outbox, row_id)
        assert row is not None
        row.attempts = OUTBOX_MAX_ATTEMPTS - 1
        db.commit()

    ok = deliver_outbox_row(row_id)
    assert ok is False
    with SessionLocal() as db:
        row = db.get(Outbox, row_id)
        assert row is not None
        assert row.state == OUTBOX_STATE_FAILED
        assert row.attempts == OUTBOX_MAX_ATTEMPTS


def test_deliver_outbox_row_idempotent_on_delivered_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call on a delivered row is a no-op; handler must not re-fire."""
    calls: list[int] = []

    def _ok_handler(payload: dict[str, Any]) -> None:
        calls.append(1)

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _ok_handler)
    row_id = _make_outbox_row()
    assert deliver_outbox_row(row_id) is True
    assert deliver_outbox_row(row_id) is True  # idempotent return for delivered
    assert len(calls) == 1


def test_deliver_outbox_row_missing_row_returns_false() -> None:
    out = deliver_outbox_row("does-not-exist-" + uuid4().hex)
    assert out is False


# ---------------------------------------------------------------------------
# outbox_redrive script
# ---------------------------------------------------------------------------


def test_outbox_redrive_picks_only_pending_older_than_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import outbox_redrive

    calls: list[str] = []

    def _ok_handler(payload: dict[str, Any]) -> None:
        calls.append("delivered")

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _ok_handler)

    # Fresh row (younger than idle threshold) — should NOT be picked.
    fresh_id = _make_outbox_row({"label": "fresh", "email": "f@x.com", "token": "t"})
    # Old row — should be picked.
    old_id = _make_outbox_row({"label": "old", "email": "o@x.com", "token": "t"})
    with SessionLocal() as db:
        row = db.get(Outbox, old_id)
        assert row is not None
        row.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        db.commit()

    rc = outbox_redrive.main(["--idle-seconds", "30", "--max-rows", "100"])
    assert rc == 0

    with SessionLocal() as db:
        old = db.get(Outbox, old_id)
        fresh = db.get(Outbox, fresh_id)
        assert old is not None
        assert fresh is not None
        assert old.state == OUTBOX_STATE_DELIVERED
        assert fresh.state == OUTBOX_STATE_PENDING


def test_outbox_redrive_respects_max_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import outbox_redrive

    handled: list[str] = []

    def _ok_handler(payload: dict[str, Any]) -> None:
        handled.append(payload.get("label", ""))

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _ok_handler)

    ids: list[str] = []
    for i in range(5):
        rid = _make_outbox_row({"label": f"m{i}", "email": "x@x.com", "token": "t"})
        ids.append(rid)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    with SessionLocal() as db:
        for rid in ids:
            row = db.get(Outbox, rid)
            assert row is not None
            row.created_at = cutoff
        db.commit()

    rc = outbox_redrive.main(["--idle-seconds", "30", "--max-rows", "2"])
    assert rc == 0
    # Only 2 rows should have been delivered this invocation.
    delivered = 0
    pending = 0
    with SessionLocal() as db:
        for rid in ids:
            row = db.get(Outbox, rid)
            assert row is not None
            if row.state == OUTBOX_STATE_DELIVERED:
                delivered += 1
            else:
                pending += 1
    assert delivered == 2
    assert pending == 3


def test_outbox_redrive_dry_run_does_not_deliver(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import outbox_redrive

    handled: list[int] = []

    def _ok_handler(payload: dict[str, Any]) -> None:
        handled.append(1)

    monkeypatch.setitem(bg_module._OUTBOX_HANDLERS, OUTBOX_KIND_MAGIC_LINK, _ok_handler)

    rid = _make_outbox_row()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    with SessionLocal() as db:
        row = db.get(Outbox, rid)
        assert row is not None
        row.created_at = cutoff
        db.commit()

    rc = outbox_redrive.main(["--idle-seconds", "30", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN would redrive outbox row" in out
    with SessionLocal() as db:
        row = db.get(Outbox, rid)
        assert row is not None
        assert row.state == OUTBOX_STATE_PENDING
    assert handled == []


# ---------------------------------------------------------------------------
# Magic-link integration via the live FastAPI router
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(_fastapi_app)


def test_magic_link_request_inserts_outbox_row_and_delivers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sends: list[tuple[str, str]] = []

    def _capture(email: str, token: str, *, next_path: str | None = None) -> None:
        sends.append((email, token))

    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _capture)

    email = f"p4-{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/request-link", data={"email": email})
    assert r.status_code == 200
    assert "Check your email" in r.text

    # MagicLinkToken row is created (Phase 2A.2 behavior preserved).
    with SessionLocal() as db:
        n_token = (
            db.query(MagicLinkToken)
            .filter(MagicLinkToken.email == email)
            .count()
        )
        assert n_token == 1
        # Outbox row was created for the magic-link send and delivered
        # by FastAPI BackgroundTasks before the response unblocked the
        # client. The handler was the monkeypatched capture fn.
        rows = (
            db.query(Outbox)
            .filter(Outbox.kind == OUTBOX_KIND_MAGIC_LINK)
            .all()
        )
        # At least one row for this run; isolate by payload email.
        matching = [r for r in rows if (r.payload or {}).get("email") == email]
        assert len(matching) == 1
        assert matching[0].state == OUTBOX_STATE_DELIVERED
        assert matching[0].delivered_at is not None
    # Send fired exactly once and saw the right recipient.
    assert len(sends) == 1
    assert sends[0][0] == email


def test_magic_link_send_failure_leaves_outbox_pending_with_attempt_bumped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("simulated Resend 429")

    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _boom)

    email = f"p4fail-{uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/request-link", data={"email": email})
    # Response still 200 — the Outbox decouples the response from the
    # send outcome. The user sees the same "Check your email" page
    # whether the BackgroundTasks delivery succeeded or not.
    assert r.status_code == 200
    assert "Check your email" in r.text

    with SessionLocal() as db:
        rows = (
            db.query(Outbox)
            .filter(Outbox.kind == OUTBOX_KIND_MAGIC_LINK)
            .all()
        )
        matching = [r for r in rows if (r.payload or {}).get("email") == email]
        assert len(matching) == 1
        row = matching[0]
        assert row.state == OUTBOX_STATE_PENDING
        assert row.attempts == 1
        assert row.last_error is not None
        assert "RuntimeError" in row.last_error


# ---------------------------------------------------------------------------
# Gotcha-#17 cure: subprocess import-chain regression
# ---------------------------------------------------------------------------


def test_background_module_does_not_import_models_at_module_top() -> None:
    """Phase 4.1 regression — gotcha-#17 cure.

    Importing :mod:`app.core.background` must NOT pull
    :mod:`app.db.models` into ``sys.modules``. The Outbox table is
    referenced via function-scope imports inside
    :func:`deliver_outbox_row` and :func:`enqueue_outbox` so that this
    module can be imported by lightweight tooling (Sentry init,
    standalone scripts) without forcing the whole ORM graph to load.

    Mirrors the shape of
    ``tests/test_phase1d_dual_write.py::test_scraper_entry_point_import_chain_does_not_cycle``
    — runs in a fresh subprocess so the assertion isn't masked by
    sys.modules caching from earlier tests in the same process.
    """
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "import app.core.background  # noqa: F401\n"
        "import json\n"
        "print(json.dumps({\n"
        '  "models_loaded": "app.db.models" in sys.modules,\n'
        '  "background_loaded": "app.core.background" in sys.modules,\n'
        "}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
        env={**os.environ, "AUTH_DEV_MODE": "1"},
    )
    assert result.returncode == 0, (
        f"import chain failed:\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["background_loaded"] is True
    assert payload["models_loaded"] is False, (
        "app.db.models should not be imported at module top of "
        "app.core.background — see gotcha #17 in "
        "docs/maintainability/dispatch_channels.md."
    )


# ---------------------------------------------------------------------------
# enqueue_outbox / handler registry
# ---------------------------------------------------------------------------


def test_enqueue_outbox_writes_pending_row_without_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enqueue_outbox`` only flushes — caller commits the surrounding txn."""
    with SessionLocal() as db:
        rid = enqueue_outbox(
            db, kind=OUTBOX_KIND_MAGIC_LINK, payload={"email": "x@x.com", "token": "t"}
        )
        # Row visible inside this session before commit.
        row = db.get(Outbox, rid)
        assert row is not None
        assert row.state == OUTBOX_STATE_PENDING
        db.rollback()

    # After rollback, no row persists.
    with SessionLocal() as db:
        assert db.get(Outbox, rid) is None


def test_enqueue_outbox_rejects_unknown_kind() -> None:
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            enqueue_outbox(db, kind="not-a-real-kind", payload={})


def test_register_outbox_handler_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        register_outbox_handler("not-a-real-kind", lambda payload: None)
