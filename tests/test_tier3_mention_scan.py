"""Tier 3 response triggers mention persistence (Phase 5.5)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.chat.intent_classifier import IntentResult
from app.db.database import SessionLocal
from app.db.models import ChatLog, LlmMentionedEntity
from app.main import app


def test_api_chat_tier3_persists_mention_row() -> None:
    tier3_text = "Check out Sunset Paddle Rentals when you visit the island."
    ask_intent = IntentResult(
        mode="ask",
        sub_intent="LISTING_INTENT",
        confidence=0.9,
        entity=None,
        raw_query="kayak",
        normalized_query="kayak",
    )
    with patch("app.chat.unified_router.classify", return_value=ask_intent):
        with patch(
            "app.chat.unified_router.try_tier1",
            return_value=None,
        ):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=(None, None, None, None),
            ):
                with patch(
                    "app.chat.unified_router.answer_with_tier3",
                    return_value=(tier3_text, 10, 5, 5),
                ):
                    with TestClient(app) as client:
                        r = client.post(
                            "/api/chat",
                            json={"query": "What kayak rentals exist?", "session_id": "tier3-mention-scan"},
                        )
    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "3"
    log_id = body.get("chat_log_id")
    assert log_id
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(LlmMentionedEntity).where(
                    LlmMentionedEntity.chat_log_id == log_id,
                    LlmMentionedEntity.mentioned_name == "Sunset Paddle Rentals",
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        m = rows[0]
        log_row = db.get(ChatLog, log_id)
        db.delete(m)
        if log_row:
            db.delete(log_row)
        db.commit()
