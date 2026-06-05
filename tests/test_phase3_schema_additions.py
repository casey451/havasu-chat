"""Phase 3.1 — additive schema migration + ORM (districts, alerts, cache, peer recs)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.database import SessionLocal, engine
from app.db.models import (
    AlertDispatched,
    AlertSubscription,
    District,
    Entity,
    ExternalConditionsCache,
    PeerRecommendation,
    User,
)


def _now() -> datetime:
    return datetime.now(UTC)


def test_migration_upgrade_downgrade_upgrade_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh SQLite: head → downgrade one → head (reversibility).

    Alembic ``env.py`` uses ``get_database_url()`` (env ``DATABASE_URL``), not
    only ``cfg.set_main_option`` — patch the env for this test so migrations
    hit the isolated temp file.
    """
    db_path = tmp_path / "phase31.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    eng = create_engine(url, connect_args={"check_same_thread": False})
    command.upgrade(cfg, "head")
    eng.dispose()
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    # Resolve the current alembic head dynamically so this reversibility
    # test stays green when future phases add migrations on top of
    # Phase 3.1 (Phase 4.1 added `0a1b2c3d4e5f` and was the first to
    # trip the previously hardcoded assertion against `e1f2a3b4c5d6`).
    from alembic.script import ScriptDirectory

    expected_head = ScriptDirectory.from_config(cfg).get_current_head()
    eng2 = create_engine(url, connect_args={"check_same_thread": False})
    try:
        with eng2.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert ver == expected_head
            n = conn.execute(
                text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='districts'")
            ).scalar()
            assert n == 1
            cols = conn.execute(text("PRAGMA table_info(entities)")).fetchall()
            col_names = {row[1] for row in cols}
            assert "district_id" in col_names
            ucols = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            assert "preferred_mode" in {row[1] for row in ucols}
    finally:
        eng2.dispose()


def test_entities_new_columns_types_and_defaults() -> None:
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("entities")}
    for name in (
        "heat_exposure",
        "crowd_notes",
        "boat_access",
        "seasonal_hours",
        "district_id",
    ):
        assert name in cols
        assert cols[name]["nullable"] is True
    assert cols["is_mobile_service"]["nullable"] is False
    assert cols["featured"]["nullable"] is False


def test_entities_heat_exposure_check_rejects_invalid() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with pytest.raises(Exception):
        with SessionLocal() as db:
            db.add(
                Entity(
                    entity_type="commercial",
                    slug=f"heat-bad-{suf}",
                    name="X",
                    source="seed",
                    heat_exposure="rooftop",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()


def test_alert_subscriptions_alert_type_check_rejects_invalid() -> None:
    uid = str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"at-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.commit()
    with pytest.raises(Exception):
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO alert_subscriptions "
                    "(id, user_id, alert_type, delivery_channel, created_at) "
                    "VALUES (:id, :uid, 'bogus', 'email', :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": uid, "ts": now},
            )
            conn.commit()


def test_alerts_dispatched_delivery_status_check_rejects_invalid() -> None:
    uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"ds-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.add(
            AlertSubscription(
                id=sid,
                user_id=uid,
                alert_type="heat_advisory",
                delivery_channel="email",
                created_at=now,
            )
        )
        db.commit()
    with pytest.raises(Exception):
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO alerts_dispatched "
                    "(id, subscription_id, alert_type, trigger_data, delivery_status) "
                    "VALUES (:id, :sid, 'heat_advisory', '{}', 'unknown')"
                ),
                {"id": str(uuid.uuid4()), "sid": sid},
            )
            conn.commit()


def test_districts_table_columns() -> None:
    insp = inspect(engine)
    assert insp.has_table("districts")
    names = {c["name"] for c in insp.get_columns("districts")}
    assert names >= {
        "id",
        "slug",
        "name",
        "paragraph",
        "display_order",
        "created_at",
        "updated_at",
    }


def test_alert_subscriptions_unique_triplet_rejects_duplicate() -> None:
    uid = str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"uq-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.add(
            AlertSubscription(
                id=str(uuid.uuid4()),
                user_id=uid,
                alert_type="aqi_alert",
                delivery_channel="email",
                created_at=now,
            )
        )
        db.commit()
        db.add(
            AlertSubscription(
                id=str(uuid.uuid4()),
                user_id=uid,
                alert_type="aqi_alert",
                delivery_channel="email",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_user_delete_cascades_subscriptions_and_dispatched() -> None:
    """SQLite CASCADE from users → alert_subscriptions → alerts_dispatched."""
    uid, sid, did = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"ca-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.add(
            AlertSubscription(
                id=sid,
                user_id=uid,
                alert_type="lake_hazard",
                delivery_channel="sms",
                created_at=now,
            )
        )
        db.flush()
        db.add(
            AlertDispatched(
                id=did,
                subscription_id=sid,
                alert_type="lake_hazard",
                trigger_data={"x": 1},
                dispatched_at=now,
                delivery_status="queued",
            )
        )
        db.commit()

    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        try:
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
            conn.commit()
        finally:
            # PRAGMA foreign_keys is per SQLite connection and survives the
            # pool checkin; a later test reusing this pooled connection would
            # suddenly run under FK enforcement (e.g. the autouse cleanup
            # sweep erroring on entity deletes). Reset before returning the
            # connection to the pool — same hazard the sibling FK tests
            # (test_entity_schema, test_photos_schema) handle via dispose().
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.commit()

    with SessionLocal() as db:
        assert db.query(AlertSubscription).filter_by(id=sid).count() == 0
        assert db.query(AlertDispatched).filter_by(id=did).count() == 0


def test_external_conditions_cache_upsert_by_source() -> None:
    with SessionLocal() as db:
        src = f"test_{uuid.uuid4().hex[:8]}"
        row = ExternalConditionsCache(
            source=src,
            fetched_at=_now(),
            data={"v": 1},
            ttl_seconds=600,
        )
        db.add(row)
        db.commit()
        row2 = db.merge(
            ExternalConditionsCache(
                source=src,
                fetched_at=_now(),
                data={"v": 2},
                ttl_seconds=900,
                error_count=0,
            )
        )
        db.commit()
        db.refresh(row2)
        assert row2.data == {"v": 2}
        assert row2.ttl_seconds == 900


def test_peer_recommendations_unique_pair_rejects_duplicate() -> None:
    uid, eid = str(uuid.uuid4()), str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"pr-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.add(
            Entity(
                id=eid,
                entity_type="place",
                slug=f"pr-place-{eid[:8]}",
                name="P",
                source="seed",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            PeerRecommendation(
                id=str(uuid.uuid4()),
                recommender_user_id=uid,
                entity_id=eid,
                recommendation_text="great",
                status="pending",
                created_at=now,
            )
        )
        db.commit()
        db.add(
            PeerRecommendation(
                id=str(uuid.uuid4()),
                recommender_user_id=uid,
                entity_id=eid,
                recommendation_text="again",
                status="pending",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_peer_recommendations_status_check_rejects_invalid() -> None:
    uid, eid = str(uuid.uuid4()), str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                id=uid,
                email=f"st-{uid[:8]}@example.com",
                created_at=now,
            )
        )
        db.add(
            Entity(
                id=eid,
                entity_type="event",
                slug=f"st-ev-{eid[:8]}",
                name="E",
                source="seed",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    with pytest.raises(Exception):
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO peer_recommendations "
                    '(id, recommender_user_id, entity_id, "text", status, created_at) '
                    "VALUES (:id, :uid, :eid, 'x', 'draft', :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": uid, "eid": eid, "ts": now},
            )
            conn.commit()


def test_user_preferred_mode_defaults_to_default() -> None:
    uid = str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        u = User(id=uid, email=f"pm-{uid[:8]}@example.com", created_at=now)
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.preferred_mode == "default"


def test_entity_featured_defaults_false() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e = Entity(
            entity_type="commercial",
            slug=f"feat-{suf}",
            name="F",
            source="seed",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        assert e.featured is False


def test_entity_is_mobile_service_defaults_false() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        e = Entity(
            entity_type="program",
            slug=f"mob-{suf}",
            name="M",
            source="seed",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        assert e.is_mobile_service is False


def test_entity_district_relationship_when_set() -> None:
    did, eid = str(uuid.uuid4()), str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            District(
                id=did,
                slug=f"d-{did[:8]}",
                name="Test District",
                paragraph="Hello.",
                display_order=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Entity(
                id=eid,
                entity_type="place",
                slug=f"dist-{eid[:8]}",
                name="Place",
                source="seed",
                district_id=did,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        e = db.get(Entity, eid)
        assert e is not None
        assert e.district is not None
        assert e.district.slug.startswith("d-")


def test_entity_district_relationship_none_when_null() -> None:
    eid = str(uuid.uuid4())
    now = _now()
    with SessionLocal() as db:
        db.add(
            Entity(
                id=eid,
                entity_type="place",
                slug=f"nd-{eid[:8]}",
                name="No D",
                source="seed",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        e = db.get(Entity, eid)
        assert e is not None
        assert e.district is None


def test_entities_indexes_include_phase31() -> None:
    insp = inspect(engine)
    idx_names = {i["name"] for i in insp.get_indexes("entities")}
    assert "ix_entities_district_id" in idx_names
    assert "ix_entities_featured" in idx_names
