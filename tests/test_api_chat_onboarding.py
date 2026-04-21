"""Tests for Phase 6.3 ``POST /api/chat/onboarding`` and session hint wiring."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.session import clear_session_state, get_session
from app.main import app


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sid = "onboarding-api-test-session"
    clear_session_state(sid)
    yield
    clear_session_state(sid)


def test_post_onboarding_sets_visitor_status() -> None:
    sid = "onboarding-api-test-session"
    with TestClient(app) as client:
        r = client.post(
            "/api/chat/onboarding",
            json={"session_id": sid, "visitor_status": "visiting"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["visitor_status"] == "visiting"
    assert body["has_kids"] is None
    assert get_session(sid)["onboarding_hints"]["visitor_status"] == "visiting"


def test_post_onboarding_merges_has_kids() -> None:
    sid = "onboarding-api-test-session"
    with TestClient(app) as client:
        client.post("/api/chat/onboarding", json={"session_id": sid, "visitor_status": "local"})
        r = client.post("/api/chat/onboarding", json={"session_id": sid, "has_kids": False})
    assert r.status_code == 200
    body = r.json()
    assert body["visitor_status"] == "local"
    assert body["has_kids"] is False


def test_post_onboarding_validation_requires_payload_field() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/chat/onboarding",
            json={"session_id": "onboarding-api-test-session"},
        )
    assert r.status_code == 422


def test_clear_session_state_includes_onboarding_hints() -> None:
    sid = "fresh-onb-" + uuid.uuid4().hex[:8]
    clear_session_state(sid)
    hints = get_session(sid)["onboarding_hints"]
    assert hints == {"visitor_status": None, "has_kids": None}


def test_tier3_receives_onboarding_hints_from_session() -> None:
    sid = "onb-tier3-" + uuid.uuid4().hex[:12]
    clear_session_state(sid)
    with TestClient(app) as client:
        assert client.post(
            "/api/chat/onboarding",
            json={"session_id": sid, "visitor_status": "visiting"},
        ).status_code == 200
        assert client.post(
            "/api/chat/onboarding",
            json={"session_id": sid, "has_kids": True},
        ).status_code == 200
        with patch("app.chat.unified_router.answer_with_tier3") as m:
            m.return_value = ("stub", 1, 1, 0)
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=(None, None, None, None),
            ):
                with patch("app.chat.unified_router.try_tier1", return_value=None):
                    cr = client.post(
                        "/api/chat",
                        json={"session_id": sid, "query": "What is fun this weekend?"},
                    )
    assert cr.status_code == 200
    m.assert_called_once()
    hints = m.call_args.kwargs.get("onboarding_hints")
    assert hints == {"visitor_status": "visiting", "has_kids": True}
