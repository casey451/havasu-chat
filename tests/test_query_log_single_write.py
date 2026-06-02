"""Slice 0: exactly one query_log row per ask turn.

Before the dedupe, an intent-claimed (or empty-fall-through) ask turn wrote TWO
query_log rows -- one from the intent layer (`runtime._log`, precise intent +
count) and one from the HTTP layer (`chat.py`, legacy sub_intent). The intent
layer now signals it logged, and `chat.py` skips. This asserts one row per turn
on all three paths: intent claim, intent empty fall-through, and no-intent-match.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider, QueryLog
from app.db.seed_helpers import derive_provider_slug
from app.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    monkeypatch.setenv("USE_LLM_ROUTER", "false")


def _count() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.count()).select_from(QueryLog)) or 0)


def _latest_intent() -> str | None:
    with SessionLocal() as db:
        row = db.scalars(select(QueryLog).order_by(QueryLog.created_at.desc())).first()
        return row.normalized_intent if row else None


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


def _post(query: str):
    with TestClient(app) as client:
        return client.post("/api/chat", json={"query": query, "session_id": "slice0"})


def test_intent_claim_writes_exactly_one_row() -> None:
    _seed_plumber()
    before = _count()
    r = _post("i need a plumber")
    assert r.status_code == 200
    assert _count() - before == 1
    assert _latest_intent() == "find_service"  # the precise row, not legacy sub_intent


def test_empty_fallthrough_writes_exactly_one_row() -> None:
    # No plumber seeded -> intent layer logs the zero-row then falls through.
    before = _count()
    with patch(
        "app.chat.unified_router.try_tier2_with_usage", return_value=("ok", 0, 0, 0)
    ):
        r = _post("i need a plumber")
    assert r.status_code == 200
    assert _count() - before == 1
    assert _latest_intent() == "find_service"  # precise zero-row coverage signal


def test_no_intent_match_writes_exactly_one_row() -> None:
    # Resolver doesn't match -> intent layer never logs; HTTP layer logs once.
    before = _count()
    with patch(
        "app.chat.unified_router.try_tier2_with_usage", return_value=("ok", 0, 0, 0)
    ):
        r = _post("where can i find a notary")
    assert r.status_code == 200
    assert _count() - before == 1
