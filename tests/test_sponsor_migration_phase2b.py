"""Phase 2B migration 2a3b4c5d6e7f — upgrade/downgrade on SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "phase2b_sponsors.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_phase2b_sponsor_migration_round_trip(alembic_cfg: Config) -> None:
    """Legacy sponsor row survives upgrade defaults and downgrade is clean."""
    url = alembic_cfg.get_main_option("sqlalchemy.url")
    eng = create_engine(url, connect_args={"check_same_thread": False})

    command.upgrade(alembic_cfg, "1a2b3c4d5e6f")
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sponsors (
                    id, name, cta_label, cta_url, active, weight,
                    created_at, updated_at
                ) VALUES (
                    'legacy-1', 'Legacy Banner', 'Visit', 'https://example.com',
                    1, 0, datetime('now'), datetime('now')
                )
                """
            )
        )

    command.upgrade(alembic_cfg, "2a3b4c5d6e7f")
    with eng.connect() as conn:
        row = conn.execute(text("SELECT slot, status FROM sponsors WHERE id = 'legacy-1'")).one()
        assert row.slot == "marquee"
        assert row.status == "approved"
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(sponsors)")).fetchall()}
        assert "headline" in cols and "business_id" in cols

    command.downgrade(alembic_cfg, "1a2b3c4d5e6f")
    with eng.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(sponsors)")).fetchall()}
        assert "slot" not in cols and "status" not in cols
        name = conn.execute(text("SELECT name FROM sponsors WHERE id = 'legacy-1'")).scalar_one()
        assert name == "Legacy Banner"

    command.upgrade(alembic_cfg, "2a3b4c5d6e7f")
    eng.dispose()
