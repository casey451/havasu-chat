"""Unit tests for Tier 3 component_meta post-LLM probe (BUILD.md step 5 Phase 5E)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.core.llm_messages as llm_messages
from app.chat.intent_classifier import IntentResult
from app.chat.llm_router import RouterDecision
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier3_handler import answer_with_tier3
from app.chat.unified_router import route
from app.db.database import SessionLocal


def _intent(
    *,
    entity: str | None = "Bridgewater 5K",
    sub_intent: str | None = "OPEN_ENDED",
) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub_intent,
        confidence=0.9,
        entity=entity,
        raw_query="tell me about something",
        normalized_query="tell me about something",
    )


def _event_row(**overrides: object) -> dict:
    row = {
        "type": "event",
        "name": "Bridgewater 5K",
        "date": "2026-05-31",
        "start_time": "08:00",
        "end_time": "10:00",
        "location_name": "Rotary Park",
        "description": "Annual waterfront 5K along the Bridgewater Channel.",
        "event_url": "https://example.com/5k",
        "tags": ["fitness"],
    }
    row.update(overrides)
    return row


def _provider_row(**overrides: object) -> dict:
    row = {
        "type": "provider",
        "name": "Channel Brewing",
        "slug": "channel-brewing",
        "category": "restaurant",
        "google_primary_category": "restaurant",
        "google_place_id": "places/abc123",
        "address": "123 Main St\nLake Havasu City AZ",
        "phone": "9284531400",
        "website": "https://example.com/channel",
        "hours": "Mon–Sun 11 AM – 9 PM",
        "hours_structured": {
            "monday": [{"open": "11:00", "close": "21:00"}],
        },
        "description": "Local brewery with a patio on the channel.",
        "google_rating": 4.6,
        "google_review_count": 212,
    }
    row.update(overrides)
    return row


def _llm_resp(text: str) -> SimpleNamespace:
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _disable_intent_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Tier-3 component-threading test routes through the legacy path; the
    # intent layer (front-of-tier-2) is covered by tests/test_intent_*. Disable
    # it so routing reaches Tier 3 deterministically regardless of seeded rows.
    monkeypatch.setenv("USE_INTENT_LAYER", "0")


def _run_tier3(
    db: Session,
    *,
    intent: IntentResult | None = None,
    component_meta: dict | None = None,
    tier3_rows: list[dict] | None = None,
    llm_text: str = "Tier 3 voice line about the entity.",
    env: dict[str, str] | None = None,
) -> tuple[str, dict | None]:
    meta = component_meta if component_meta is not None else {}
    rows = tier3_rows if tier3_rows is not None else [_event_row()]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _llm_resp(llm_text)
    env_patch = {"OPENAI_API_KEY": "test-key", **(env or {})}
    with patch.dict(os.environ, env_patch, clear=False):
        with patch.object(llm_messages, "OpenAI", return_value=fake_client):
            with patch(
                "app.chat.tier3_handler.build_context_and_rows_for_tier3",
                return_value=("Context block", rows),
            ):
                with patch(
                    "app.chat.tier3_handler.cache_lookup_with_embedding",
                    return_value=(None, None),
                ):
                    text, *_ = answer_with_tier3(
                        "tell me about it",
                        intent or _intent(),
                        db,
                        component_meta=meta,
                    )
    return text, meta


def test_tier3_component_probe_off_by_default(db: Session) -> None:
    meta: dict = {}
    text, meta = _run_tier3(db, component_meta=meta, tier3_rows=[_event_row()])
    assert text == "Tier 3 voice line about the entity."
    assert meta == {}


def test_tier3_emits_single_card_when_flag_on(db: Session) -> None:
    meta: dict = {}
    text, meta = _run_tier3(
        db,
        component_meta=meta,
        tier3_rows=[_event_row()],
        env={"HAVA_TIER3_COMPONENTS": "1"},
    )
    assert text == "Tier 3 voice line about the entity."
    assert meta.get("type") == "single_card"
    assert meta["data"]["title"] == "Bridgewater 5K"
    assert meta["data"]["facts"]
    assert meta["data"]["actions"]


def test_tier3_emits_single_business_card_for_provider(db: Session) -> None:
    meta: dict = {}
    intent = _intent(entity="Channel Brewing")
    text, meta = _run_tier3(
        db,
        intent=intent,
        component_meta=meta,
        tier3_rows=[_provider_row()],
        env={"HAVA_TIER3_COMPONENTS": "1"},
    )
    assert text == "Tier 3 voice line about the entity."
    assert meta.get("type") == "single_business_card"
    assert meta["data"]["title"] == "Channel Brewing"
    assert meta["data"]["facts"]
    assert meta["data"]["actions"]


def test_tier3_skips_probe_when_intent_entity_missing(db: Session) -> None:
    meta: dict = {}
    intent = _intent(entity=None)
    _, meta = _run_tier3(
        db,
        intent=intent,
        component_meta=meta,
        tier3_rows=[_event_row()],
        env={"HAVA_TIER3_COMPONENTS": "1"},
    )
    assert meta == {}


def test_tier3_probe_failure_swallowed(db: Session) -> None:
    meta: dict = {}
    with patch(
        "app.chat.component_builders.is_single_card_query",
        side_effect=RuntimeError("probe boom"),
    ):
        text, meta = _run_tier3(
            db,
            component_meta=meta,
            tier3_rows=[_event_row()],
            env={"HAVA_TIER3_COMPONENTS": "1"},
        )
    assert text == "Tier 3 voice line about the entity."
    assert meta == {}


def test_tier3_returns_none_component_for_gap_response(db: Session) -> None:
    meta: dict = {}
    _, meta = _run_tier3(
        db,
        component_meta=meta,
        tier3_rows=[],
        env={"HAVA_TIER3_COMPONENTS": "1"},
    )
    assert meta == {}


def test_tier3_cache_hit_still_runs_probe(db: Session) -> None:
    meta: dict = {}
    rows = [_event_row()]
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "HAVA_TIER3_COMPONENTS": "1"}):
        with patch(
            "app.chat.tier3_handler.cache_lookup_with_embedding",
            return_value=("Cached tier3 voice.", None),
        ):
            with patch(
                "app.chat.tier3_handler.build_context_and_rows_for_tier3",
                return_value=("Context block", rows),
            ) as build_ctx:
                text, *_ = answer_with_tier3(
                    "tell me about it",
                    _intent(),
                    db,
                    component_meta=meta,
                )
    build_ctx.assert_called_once()
    assert text.startswith("Cached tier3 voice.")
    assert meta.get("type") == "single_card"
    assert meta["data"]["title"] == "Bridgewater 5K"


def test_tier3_unified_router_threads_component_meta(db: Session) -> None:
    captured: list[dict | None] = []

    def _capture(*_a, **kwargs):
        captured.append(kwargs.get("component_meta"))
        return ("Tier3 stub", 0, 0, 0)

    with patch.dict(os.environ, {"USE_LLM_ROUTER": "false"}, clear=False):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch("app.chat.unified_router.answer_with_tier3", side_effect=_capture) as t3:
                # Path 5: Tier 2 miss -> Tier 3 fallback
                with patch(
                    "app.chat.unified_router.try_tier2_with_usage",
                    return_value=(None, None, None, None),
                ):
                    route("What's at the skate park?", "sess-t3-thread-5", db)
                assert captured[-1] is not None
                assert isinstance(captured[-1], dict)

                # Path 4: explicit-rec -> Tier 3
                route("What should I do tonight?", "sess-t3-thread-4", db)
                assert captured[-1] is not None

                tier2_decision = RouterDecision.model_validate(
                    {
                        "mode": "ask",
                        "sub_intent": "OPEN_ENDED",
                        "entity": None,
                        "router_confidence": 0.9,
                        "tier_recommendation": "2",
                        "tier2_filters": Tier2Filters.model_validate(
                            {"time_window": "next_week", "parser_confidence": 0.9}
                        ),
                    }
                )
                tier3_decision = RouterDecision.model_validate(
                    {
                        "mode": "ask",
                        "sub_intent": "OPEN_ENDED",
                        "entity": None,
                        "router_confidence": 0.8,
                        "tier_recommendation": "3",
                        "tier2_filters": None,
                    }
                )

                with patch.dict(os.environ, {"USE_LLM_ROUTER": "true"}, clear=False):
                    # Path 1: LLM router None -> Tier 3
                    with patch("app.chat.unified_router.llm_router.route", return_value=None):
                        route("open ended question", "sess-t3-thread-1", db)
                    assert captured[-1] is not None

                    # Path 2: router tier2 miss -> Tier 3
                    with patch(
                        "app.chat.unified_router.llm_router.route",
                        return_value=tier2_decision,
                    ):
                        with patch(
                            "app.chat.unified_router.try_tier2_with_filters_with_usage",
                            return_value=(None, None, None, None),
                        ):
                            route("events next week", "sess-t3-thread-2", db)
                    assert captured[-1] is not None

                    # Path 3: router tier3 direct
                    with patch(
                        "app.chat.unified_router.llm_router.route",
                        return_value=tier3_decision,
                    ):
                        route("something open ended", "sess-t3-thread-3", db)
                    assert captured[-1] is not None

    assert t3.call_count >= 5
    assert all(isinstance(m, dict) for m in captured)
