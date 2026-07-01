"""Tier 3 response triggers mention persistence (Phase 5.5)."""

from __future__ import annotations

import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.chat.intent_classifier import IntentResult
from app.db.database import SessionLocal
from app.db.models import ChatLog, LlmMentionedEntity
from app.main import app


def _poll_for_mention_rows(
    log_id: str, mentioned_name: str, *, timeout_s: float = 5.0
) -> list[LlmMentionedEntity]:
    """Deterministically await the mention-scan background task's commit.

    ``scan_and_save_mentions`` runs via Starlette ``BackgroundTasks`` wrapped in
    :func:`app.core.background.with_retry`. ``TestClient`` normally drains
    background tasks before returning, but ``with_retry`` sleeps between
    attempts on transient failures (e.g. a SQLite write-lock collision with the
    test process's own open sessions), and under ``pytest -n`` the extra
    scheduling jitter widened that window into observed flakes. Poll with a
    bounded timeout instead of asserting immediately (and never ``sleep()`` a
    fixed amount): returns as soon as a row is visible, or after ``timeout_s``
    with whatever is there so the caller's assertion produces a real failure.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        with SessionLocal() as db:
            rows = list(
                db.execute(
                    select(LlmMentionedEntity).where(
                        LlmMentionedEntity.chat_log_id == log_id,
                        LlmMentionedEntity.mentioned_name == mentioned_name,
                    )
                )
                .scalars()
                .all()
            )
        if rows or time.monotonic() >= deadline:
            return rows
        time.sleep(0.05)

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
    # The intent layer would claim "what kayak rentals exist?" itself when the
    # catalog has no kayak row (honest bounded-empty, 2026-07-01 topical gate) —
    # patch it out so this test keeps exercising the Tier-3 mention-scan
    # persistence it is actually for.
    with patch("app.chat.intents.runtime.try_intent_layer", return_value=None):
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
                                json={
                                    "query": "What kayak rentals exist?",
                                    "session_id": "tier3-mention-scan",
                                },
                            )
    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "3"
    log_id = body.get("chat_log_id")
    assert log_id
    rows = _poll_for_mention_rows(log_id, "Sunset Paddle Rentals")
    assert len(rows) == 1
    with SessionLocal() as db:
        m = db.get(LlmMentionedEntity, rows[0].id)
        log_row = db.get(ChatLog, log_id)
        if m:
            db.delete(m)
        if log_row:
            db.delete(log_row)
        db.commit()
