"""End-to-end ``POST /api/chat`` ask-mode integration coverage (Phase 3.3)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Program, Provider
from app.main import app


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.query(Program).filter(Program.source == "phase33-test").delete(synchronize_session=False)
        s.query(Provider).filter(Provider.source == "phase33-test").delete(synchronize_session=False)
        s.commit()
        s.close()


def _provider(**kwargs: object) -> Provider:
    defaults: dict[str, object] = {
        "provider_name": "Tier1 Test Gym",
        "category": "sports",
        "verified": False,
        "draft": False,
        "is_active": True,
        "source": "phase33-test",
    }
    defaults.update(kwargs)
    return Provider(**defaults)  # type: ignore[arg-type]


def _program_for_provider(provider: Provider, **kwargs: object) -> Program:
    defaults: dict[str, object] = {
        "title": "Phone Program",
        "description": "Twenty characters minimum description.",
        "activity_category": "sports",
        "schedule_days": ["Saturday"],
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:00",
        "location_name": "Lake Havasu City",
        "provider_name": provider.provider_name,
        "provider_id": provider.id,
        "source": "phase33-test",
    }
    defaults.update(kwargs)
    return Program(**defaults)  # type: ignore[arg-type]


def test_post_api_chat_tier1_phone_lookup_path(db: Session) -> None:
    provider = _provider(provider_name="PhoneCo", phone="928-555-0100")
    db.add(provider)
    db.flush()
    db.add(_program_for_provider(provider))
    db.commit()

    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": "What is the phone number for PhoneCo?", "session_id": "e2e-tier1"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    assert body["sub_intent"] == "PHONE_LOOKUP"
    assert body["tier_used"] == "1"
    assert body["llm_tokens_used"] is None
    assert isinstance(body["response"], str)
    assert body["response"].strip() != ""
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0


def test_post_api_chat_tier3_open_ended_path_uses_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_usage = SimpleNamespace(
        input_tokens=11,
        output_tokens=12,
        cache_read_input_tokens=5,
        cache_creation_input_tokens=4,
    )
    fake_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Mocked Tier 3 answer.")],
        usage=fake_usage,
    )
    mocked_tokens = 32
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: fake_message))
    fake_anthropic_module = SimpleNamespace(Anthropic=lambda **_kwargs: fake_client)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic_module)

    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": "What are some fun things to do around town this weekend?", "session_id": "e2e-tier3"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    assert body["sub_intent"] == "OPEN_ENDED"
    assert body["tier_used"] == "3"
    assert body["llm_tokens_used"] == mocked_tokens
    assert body["response"] == "Mocked Tier 3 answer."


def test_post_api_chat_out_of_scope_path() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": "Is it going to rain tomorrow?", "session_id": "e2e-oos"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "chat"
    assert body["sub_intent"] == "OUT_OF_SCOPE"
    assert body["tier_used"] == "chat"


def test_post_api_chat_response_contract_fields_and_types(db: Session) -> None:
    provider = _provider(provider_name="ShapeCo", phone="928-555-0199")
    db.add(provider)
    db.flush()
    db.add(_program_for_provider(provider, title="Shape Program"))
    db.commit()

    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": "What is the phone number for ShapeCo?", "session_id": "e2e-shape"},
        )

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
    }
    assert isinstance(body["response"], str)
    assert isinstance(body["mode"], str)
    assert body["sub_intent"] is None or isinstance(body["sub_intent"], str)
    assert body["entity"] is None or isinstance(body["entity"], str)
    assert isinstance(body["tier_used"], str)
    assert isinstance(body["latency_ms"], int)
    assert body["llm_tokens_used"] is None or isinstance(body["llm_tokens_used"], int)
