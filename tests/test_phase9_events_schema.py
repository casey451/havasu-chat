"""Phase 9a — events schema migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.db.models import Event


def test_migration_upgrade_downgrade_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "phase9.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    expected_head = ScriptDirectory.from_config(cfg).get_current_head()
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_revision(expected_head)
    assert head_rev is not None
    assert head_rev.down_revision == "d8e9f0a1b2c3"

    eng = create_engine(url, connect_args={"check_same_thread": False})
    try:
        with eng.connect() as conn:
            ver = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert ver == expected_head
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(events)")).fetchall()
            }
            for name in (
                "rrule",
                "rdate",
                "exdate",
                "scraped_at",
                "cancellation_reason",
                "operator_override",
                "capacity",
                "capacity_source",
            ):
                assert name in cols
            indexes = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA index_list(events)")
                ).fetchall()
            }
            assert "ix_events_status_date" in indexes
            assert "ix_events_is_recurring_date" in indexes
            assert "ix_events_provider_id_date" in indexes
            assert "ix_events_scraped_at" in indexes
    finally:
        eng.dispose()

    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_events_status_check_rejects_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "phase9_check.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    eng = create_engine(url, connect_args={"check_same_thread": False})
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (id, entity_type, name, slug, is_active, created_at, updated_at) "
                "VALUES ('ent-chk', 'event', 'E', 'ent-chk', 1, datetime('now'), datetime('now'))"
            )
        )
        with pytest.raises(Exception):
            conn.execute(
                text(
                    "INSERT INTO events (id, title, normalized_title, date, start_time, "
                    "location_name, location_normalized, description, status, source, "
                    "entity_id, is_recurring, operator_override) "
                    "VALUES ('ev-bad', 'T', 't', '2026-06-01', '10:00:00', 'L', 'l', "
                    "'d', 'not_a_status', 'admin', 'ent-chk', 0, 0)"
                )
            )


def test_event_orm_has_phase9_columns() -> None:
    from app.db.database import engine

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("events")}
    assert "rrule" in cols
    assert "operator_override" in cols
    mapper = inspect(Event)
    assert "rrule" in mapper.columns
