"""WS9b — structured /search SERP: categories in results, escalation card, and
zero-result / with-result logging into the demand backlog (QueryLog)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Provider, QueryLog
from app.main import app
from app.search.routes import _keyword_category_results


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def db() -> Iterator[Session]:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mexican_eat_drink_provider(db: Session, *, mark: str) -> None:
    ent = Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"mex-{uuid.uuid4().hex[:10]}",
        name=mark,
        description=mark,
        source="test-ws9b",
    )
    db.add(ent)
    db.add(
        Provider(
            provider_name=mark,
            slug=f"mex-prov-{uuid.uuid4().hex[:10]}",
            category="food_drink",
            google_primary_category="mexican_restaurant",
            google_categories=["mexican_restaurant"],
            source="test-ws9b",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
    )


def test_category_results_empty_for_nonsense_query(db: Session) -> None:
    assert _keyword_category_results(db, q_clean=f"zzq{_suffix()}nope") == []


def test_category_results_surface_gated_cuisine_landing(db: Session) -> None:
    # Two Mexican Eat & Drink providers clear the cuisine render gate (2), so a
    # "mexican food" search surfaces the /lake-havasu/mexican landing card.
    for i in range(2):
        _mexican_eat_drink_provider(db, mark=f"WS9B Cantina {i} {_suffix()}")
    db.commit()
    cats = _keyword_category_results(db, q_clean="mexican food")
    assert any(c["url"] == "/lake-havasu/mexican" for c in cats)
    assert any(c["kind"] == "Cuisine" for c in cats)


def test_results_page_embeds_escalation_card(db: Session) -> None:
    suf = _suffix()
    mark = f"PipeFix {suf} Plumbing"
    slug = f"pipefix-{suf}"
    ent = Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=slug,
        name=mark,
        description=mark,
        source="test-ws9b",
    )
    db.add(ent)
    db.add(
        Provider(
            provider_name=mark,
            slug=slug,
            category="home_services",
            google_primary_category="plumber",
            source="test-ws9b",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
    )
    db.commit()
    with TestClient(app) as client:
        r = client.get("/search", params={"q": "plumber"})
    assert r.status_code == 200
    body = r.text
    assert mark in body  # a real result rendered
    assert "srch-escalate-inline" in body  # escalation card embedded on the SERP
    assert "/chat?q=plumber" in body


def test_with_result_query_logged_with_positive_count(db: Session) -> None:
    suf = _suffix()
    mark = f"LogCheck {suf} Diner"
    ent = Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"logcheck-{suf}",
        name=mark,
        description=mark,
        source="test-ws9b",
    )
    db.add(ent)
    db.add(
        Provider(
            provider_name=mark,
            slug=f"logcheck-{suf}",
            category="food_drink",
            source="test-ws9b",
            draft=False,
            is_active=True,
            entity_id=ent.id,
        )
    )
    db.commit()
    query = f"logcheck {suf} diner"
    with TestClient(app) as client:
        r = client.get("/search", params={"q": query})
    assert r.status_code == 200
    logged = db.scalars(
        select(QueryLog).where(QueryLog.normalized_intent == query.lower())
    ).all()
    assert logged
    assert all(row.result_count >= 1 for row in logged)
    assert all(row.min_layer == "search" for row in logged)
