"""Tests for Phase 2.3 ``POST /api/chat`` (concierge unified router API)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_post_api_chat_returns_concierge_shape() -> None:
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": "Hi", "session_id": "api-test-1"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "response",
        "mode",
        "sub_intent",
        "entity",
        "tier_used",
        "latency_ms",
        "llm_tokens_used",
        "chat_log_id",
    }
    assert body["mode"] == "chat"
    assert body["sub_intent"] == "GREETING"
    assert body["tier_used"] == "chat"
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] > 0
    assert not body["response"].rstrip().endswith("?")


def test_post_api_chat_session_id_nullable() -> None:
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": "Thanks", "session_id": None})
    assert r.status_code == 200
    assert r.json()["mode"] == "chat"
    assert r.json()["sub_intent"] == "SMALL_TALK"


def test_post_api_chat_omitted_session_id() -> None:
    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with patch(
            "app.chat.unified_router.answer_with_tier3",
            return_value=("API tier3 stub.", 42, 25, 17),
        ):
            with TestClient(app) as client:
                r = client.post("/api/chat", json={"query": "What is fun to do this weekend?"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "ask"
    assert data["response"] == "API tier3 stub."
    assert data["tier_used"] == "3"
    assert data["llm_tokens_used"] == 42


def test_post_api_chat_validation_empty_query() -> None:
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": ""})
    assert r.status_code == 422


def test_track_a_post_chat_unchanged() -> None:
    """Static UI path ``POST /chat`` (message + session_id) must still work."""
    with TestClient(app) as client:
        r = client.post("/chat", json={"session_id": "track-a-ui", "message": "Hi"})
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "intent" in body
    assert "data" in body
