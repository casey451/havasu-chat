"""Phase 8a — migration + ORM columns for conditions cache circuit breaker."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_migration_upgrade_downgrade_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "phase8.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    phase8_rev = "d8e9f0a1b2c3"
    command.upgrade(cfg, phase8_rev)
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_revision(phase8_rev)
    assert head_rev is not None
    assert head_rev.down_revision == "c9d0e1f2a3b4"
    expected_head = phase8_rev

    eng = create_engine(url, connect_args={"check_same_thread": False})
    try:
        with eng.connect() as conn:
            ver = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert ver == expected_head
            cols = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(external_conditions_cache)")
                ).fetchall()
            }
            assert "last_attempt_at" in cols
            assert "next_attempt_after" in cols
    finally:
        eng.dispose()

    command.downgrade(cfg, "-1")
    command.upgrade(cfg, phase8_rev)


def test_external_conditions_cache_orm_has_phase8_columns() -> None:
    from app.db.database import engine

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("external_conditions_cache")}
    assert "last_attempt_at" in cols
    assert "next_attempt_after" in cols
