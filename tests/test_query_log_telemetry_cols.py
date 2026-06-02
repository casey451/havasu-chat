"""Phase 2 Slice 1: query_log telemetry columns (min_layer, sub_intent).

The conftest runs Alembic migrations on the session test DB, so these passing
proves the d1e2f3a4b5c6 migration applied. Asserts the intent layer records the
matcher layer and the writer persists the sub-intent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.chat.intents.runtime import try_intent_layer
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider, QueryLog
from app.db.seed_helpers import derive_provider_slug
from app.v1.query_log import log_query_intent


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_INTENT_LAYER", "1")


def _seed_plumber() -> None:
    with SessionLocal() as db:
        p = Provider(
            provider_name="Ace Plumbing Co",
            category="home_services",
            subcategory="home-services",
            google_rating=4.8,
            slug=derive_provider_slug(db, "Ace Plumbing Co"),
            source="test",
            lat=34.4839,
            lng=-114.3225,
            draft=False,
            is_active=True,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()


def _latest(db, intent: str) -> QueryLog | None:
    return db.scalars(
        select(QueryLog)
        .where(QueryLog.normalized_intent == intent)
        .order_by(QueryLog.created_at.desc())
    ).first()


def test_model_has_telemetry_columns() -> None:
    assert hasattr(QueryLog, "min_layer")
    assert hasattr(QueryLog, "sub_intent")


def test_runtime_records_l1_layer() -> None:
    _seed_plumber()
    with SessionLocal() as db:
        try_intent_layer("i need a plumber", db)
        row = _latest(db, "find_service")
    assert row is not None
    assert row.min_layer == "L1"
    assert row.result_count >= 1


def test_runtime_records_l2_layer_with_slot() -> None:
    _seed_plumber()
    with SessionLocal() as db:
        # area slot promotes the match to L2 (district degrades to all when sparse).
        try_intent_layer("plumber in english village", db)
        row = _latest(db, "find_service")
    assert row is not None
    assert row.min_layer == "L2"


def test_empty_turn_records_layer_and_zero_count() -> None:
    # No plumber seeded -> zero-row coverage signal, still records the layer.
    with SessionLocal() as db:
        try_intent_layer("i need a plumber", db)
        row = _latest(db, "find_service")
    assert row is not None
    assert row.result_count == 0
    assert row.min_layer == "L1"


def test_writer_persists_sub_intent() -> None:
    with SessionLocal() as db:
        log_query_intent(
            db,
            normalized_intent="LIST_BY_CATEGORY",
            sub_intent="LIST_BY_CATEGORY",
            mode="ask",
        )
        row = db.scalars(
            select(QueryLog)
            .where(QueryLog.sub_intent == "LIST_BY_CATEGORY")
            .order_by(QueryLog.created_at.desc())
        ).first()
    assert row is not None
    assert row.sub_intent == "LIST_BY_CATEGORY"
