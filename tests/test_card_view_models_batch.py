"""T3.2 — batched card view-model builder.

``build_card_view_models`` must produce output byte-identical to calling
``build_card_view_model`` per entity, and must issue a constant number of
queries regardless of how many entities are requested (i.e. no N+1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import delete, event

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.providers import queries

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)  # Monday 2pm


def _count_select_queries(db, fn):  # type: ignore[no-untyped-def]
    bind = db.get_bind()
    n = {"c": 0}

    def _before(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        if statement.lstrip()[:6].upper() == "SELECT":
            n["c"] += 1

    event.listen(bind, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(bind, "before_cursor_execute", _before)
    return n["c"]


@pytest.fixture
def four_entity_ids() -> list[str]:
    suf = uuid.uuid4().hex[:8]
    ids: list[str] = []
    with SessionLocal() as db:
        for i in range(4):
            p = Provider(
                provider_name=f"Batch {suf}-{i}",
                category="home_services",
                verified=True,
                draft=False,
                is_active=True,
                pending_review=False,
                source="test-t32",
                hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
            )
            db.add(p)
            db.commit()
            ids.append(p.entity_id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(ids)))
        db.execute(delete(Entity).where(Entity.id.in_(ids)))
        db.commit()


def test_batched_matches_single_builder(four_entity_ids: list[str]) -> None:
    ids = four_entity_ids
    with SessionLocal() as db:
        singles = [queries.build_card_view_model(db, eid, now=_NOW) for eid in ids]
    with SessionLocal() as db:
        batched = queries.build_card_view_models(db, ids, now=_NOW)
    assert all(s is not None for s in singles)
    assert [vars(v) for v in batched] == [vars(v) for v in singles]


def test_batched_preserves_order_and_skips_unknown(four_entity_ids: list[str]) -> None:
    ids = four_entity_ids
    with SessionLocal() as db:
        out = queries.build_card_view_models(db, [ids[2], "nonexistent-id", ids[0]], now=_NOW)
    assert [v.entity_id for v in out] == [ids[2], ids[0]]


def test_batched_empty_returns_empty() -> None:
    with SessionLocal() as db:
        assert queries.build_card_view_models(db, [], now=_NOW) == []


def test_batched_query_count_does_not_scale_with_n(four_entity_ids: list[str]) -> None:
    ids = four_entity_ids
    with SessionLocal() as db:
        c2 = _count_select_queries(
            db, lambda: queries.build_card_view_models(db, ids[:2], now=_NOW)
        )
    with SessionLocal() as db:
        c4 = _count_select_queries(db, lambda: queries.build_card_view_models(db, ids, now=_NOW))
    # Constant query count regardless of N proves the N+1 is gone.
    assert c2 == c4, f"batched query count scaled with N: {c2} (N=2) vs {c4} (N=4)"

    with SessionLocal() as db:
        c_loop = _count_select_queries(
            db, lambda: [queries.build_card_view_model(db, eid, now=_NOW) for eid in ids]
        )
    # The old per-entity path issues strictly more queries for the same 4 rows.
    assert c4 < c_loop, f"batched ({c4}) not fewer than per-entity loop ({c_loop})"
