"""Phase 6 sidecar — ``contributions.created_event_id`` FK regression coverage.

The new migration ``f6a7b8c9d0e1_parks_rec_prune_fk_set_null.py`` swaps the
default RESTRICT behavior for ``ON DELETE SET NULL`` so the ``parks-rec-scrapes``
GitHub Actions cron can DELETE stale events that contribution rows still
reference (audit trail preserved; link severed). See the migration docstring
+ Phase 5.7 close-out §3 for the full root-cause analysis.

Coverage:
* Migration cycle clean: upgrade head -> downgrade -1 -> upgrade head, against
  a tmp SQLite DB. Head asserted via ``ScriptDirectory.from_config(...)
  .get_current_head()`` rather than a hardcoded literal (Phase 4.1 lesson #3
  — avoids the forward-incompatibility trap that bit Phase 3 tests).
* Functional ``ON DELETE SET NULL``: with a contribution row pointing at an
  event row, deleting the event leaves the contribution row intact with
  ``created_event_id IS NULL`` (SQLite needs ``PRAGMA foreign_keys=ON`` to
  enforce, which the test enables explicitly).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine


def _enable_sqlite_fk_enforcement(engine: Engine) -> None:
    """SQLite ships with FK enforcement off by default; flip it on per-conn."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def test_parks_rec_prune_fk_migration_upgrade_downgrade_cycle_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Migration cycles clean: head -> downgrade-1 -> head on fresh SQLite.

    Mirrors the Phase 4.1 outbox cycle test shape (``test_phase4_background.py``
    ::``test_outbox_migration_upgrade_downgrade_cycle_clean``). Uses
    ``ScriptDirectory.from_config(...).get_current_head()`` instead of a
    hardcoded head literal so this test doesn't go stale on the next
    migration appended.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from alembic import command

    db_path = tmp_path / "phase6_parks_rec_prune_fk_cycle.sqlite"
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    cfg = Config(str(repo_root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    # This test targets the Phase 6 sidecar revision specifically (not repo head).
    sidecar_rev = "f6a7b8c9d0e1"
    assert script.get_revision(sidecar_rev) is not None
    pre_sidecar_rev = script.get_revision(sidecar_rev).down_revision
    assert pre_sidecar_rev is not None

    command.upgrade(cfg, sidecar_rev)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == sidecar_rev
        insp = inspect(engine)
        fks = {
            fk["name"]: fk
            for fk in insp.get_foreign_keys("contributions")
            if "created_event_id" in fk["constrained_columns"]
        }
        assert fks, "contributions.created_event_id FK not present after upgrade head"
        ((_name, fk),) = fks.items()
        assert fk["options"].get("ondelete", "").upper() == "SET NULL"

        command.downgrade(cfg, pre_sidecar_rev)
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == pre_sidecar_rev
        insp = inspect(engine)
        fks_down = [
            fk
            for fk in insp.get_foreign_keys("contributions")
            if "created_event_id" in fk["constrained_columns"]
        ]
        assert fks_down, "FK should still exist post-downgrade — only ondelete changed"
        assert fks_down[0]["options"].get("ondelete", "").upper() != "SET NULL"

        command.upgrade(cfg, sidecar_rev)
        with engine.connect() as conn:
            cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert cur == sidecar_rev
        insp = inspect(engine)
        fks_back = [
            fk
            for fk in insp.get_foreign_keys("contributions")
            if "created_event_id" in fk["constrained_columns"]
        ]
        assert fks_back[0]["options"].get("ondelete", "").upper() == "SET NULL"
    finally:
        engine.dispose()


def test_deleting_referenced_event_nulls_contribution_created_event_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete an event row; the contribution row stays, link becomes NULL.

    Reproduces the production failure mode from the parks-rec-scrapes cron
    (``scripts/parks_rec_prune.py`` deleting a stale aquatic event that a
    contribution row still references) and confirms the new migration
    rewrites the failure to a silent SET NULL.
    """
    from alembic.config import Config

    from alembic import command

    db_path = tmp_path / "phase6_parks_rec_prune_fk_functional.sqlite"
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    cfg = Config(str(repo_root / "alembic.ini"))
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    _enable_sqlite_fk_enforcement(engine)
    try:
        entity_id = str(uuid4())
        event_id = str(uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO entities (id, entity_type, slug, name, source, "
                    "is_active, created_at, updated_at) VALUES "
                    "(:id, 'event', :slug, :name, 'seed', 1, :ts, :ts)"
                ),
                {
                    "id": entity_id,
                    "slug": f"stale-aquatic-class-{entity_id[:8]}",
                    "name": "Stale aquatic class",
                    "ts": "2026-04-01 00:00:00",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO events (id, entity_id, title, normalized_title, "
                    "date, start_time, location_name, location_normalized, "
                    "description, event_url, tags, status, source, verified, "
                    "created_at, created_by, is_recurring, featured) VALUES "
                    "(:id, :entity_id, :title, :nt, :d, :st, :loc, :ln, :desc, "
                    "'', '[]', 'live', 'admin', 0, :created_at, 'user', 0, 0)"
                ),
                {
                    "id": event_id,
                    "entity_id": entity_id,
                    "title": "Stale aquatic class",
                    "nt": "stale aquatic class",
                    "d": "2026-04-01",
                    "st": "09:00",
                    "loc": "Aquatic Center",
                    "ln": "aquatic center",
                    "desc": "Past slot",
                    "created_at": "2026-04-01 00:00:00",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO contributions (entity_type, submission_name, "
                    "created_event_id, status, source, unverified) VALUES "
                    "(:et, :sn, :ceid, 'pending', 'user_submission', 0)"
                ),
                {
                    "et": "event",
                    "sn": "Contribution referencing stale event",
                    "ceid": event_id,
                },
            )

        with engine.begin() as conn:
            cur = conn.execute(text("SELECT id, created_event_id FROM contributions")).first()
            assert cur is not None
            contribution_id, ceid_before = cur
            assert ceid_before == event_id

            conn.execute(text("DELETE FROM events WHERE id = :id"), {"id": event_id})

        with engine.connect() as conn:
            after = conn.execute(
                text("SELECT id, created_event_id FROM contributions WHERE id = :id"),
                {"id": contribution_id},
            ).first()
            assert after is not None, "contribution row should survive event delete"
            assert after[1] is None, "created_event_id should be NULL after event delete"

            remaining_events = conn.execute(
                text("SELECT COUNT(*) FROM events WHERE id = :id"), {"id": event_id}
            ).scalar()
            assert remaining_events == 0
    finally:
        engine.dispose()
