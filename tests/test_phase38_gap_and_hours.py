"""Phase 3.8 — HOURS_LOOKUP phrasing variants + catalog-gap template (no Tier 3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chat.unified_router import route
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.mark.parametrize(
    "query,expected_sub",
    [
        ("Is altitude open late on friday?", "HOURS_LOOKUP"),
        ("Is sonics open early on monday?", "HOURS_LOOKUP"),
        ("What time does altitude close on friday?", "TIME_LOOKUP"),
    ],
)
def test_hours_and_close_phrasing_sub_intents(query: str, expected_sub: str) -> None:
    from app.chat.intent_classifier import classify

    r = classify(query)
    assert r.mode == "ask"
    assert r.sub_intent == expected_sub


def test_open_late_hits_tier1_when_provider_hours_in_db(db: Session) -> None:
    p = Provider(
        provider_name="Altitude Trampoline Park — Lake Havasu City",
        category="recreation",
        hours="10:00 AM – 8:00 PM daily",
        phone="928-555-0199",
        source="seed",
    )
    db.add(p)
    db.commit()
    r = route("Is altitude open late on friday?", "sess-p38-late", db)
    assert r.mode == "ask"
    assert r.sub_intent == "HOURS_LOOKUP"
    assert r.tier_used == "1"
    assert r.llm_tokens_used is None
    low = r.response.lower()
    assert "altitude" in low or "open" in low or "fri" in low or "am" in low or "pm" in low


@pytest.mark.parametrize(
    ("query", "expected_sub"),
    [
        ("What are the hours for zzznonexistent999xyz?", "HOURS_LOOKUP"),
        ("Where is Totally Fictional Venue XYZ?", "LOCATION_LOOKUP"),
        ("When is the zzznonexistentevent999abc?", "DATE_LOOKUP"),
    ],
)
def test_catalog_gap_skips_tier3(query: str, expected_sub: str, db: Session) -> None:
    with patch("app.chat.unified_router.answer_with_tier3") as m3:
        r = route(query, f"sess-gap-{expected_sub}", db)
    m3.assert_not_called()
    assert r.mode == "ask"
    assert r.sub_intent == expected_sub
    assert r.tier_used == "gap_template"
    assert r.llm_tokens_used is None
    assert "catalog" in r.response.lower()
    assert "/contribute" in r.response


def test_post_api_chat_gap_template_contract() -> None:
    with patch("app.chat.unified_router.answer_with_tier3") as m3:
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={"query": "Where is Totally Fictional Venue XYZ?", "session_id": "p38-gap-http"},
            )
    m3.assert_not_called()
    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "gap_template"
    assert "/contribute" in (body.get("response") or "")
    assert body["llm_tokens_used"] is None
    assert body["sub_intent"] == "LOCATION_LOOKUP"
