from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat.llm_router import RouterDecision
from app.chat.tier2_schema import Tier2Filters
from app.chat.unified_router import route
from app.db.database import SessionLocal
from app.db.models import Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _tier2_decision() -> RouterDecision:
    return RouterDecision.model_validate(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "entity": None,
            "router_confidence": 0.9,
            "tier_recommendation": "2",
            "tier2_filters": Tier2Filters.model_validate(
                {
                    "time_window": "next_week",
                    "open_now": False,
                    "parser_confidence": 0.9,
                    "fallback_to_tier3": False,
                }
            ),
        }
    )


def _tier3_decision() -> RouterDecision:
    return RouterDecision.model_validate(
        {
            "mode": "ask",
            "sub_intent": "OPEN_ENDED",
            "entity": None,
            "router_confidence": 0.8,
            "tier_recommendation": "3",
            "tier2_filters": None,
        }
    )


def test_flag_on_tier2_uses_router_filters_and_skips_parser(db: Session) -> None:
    with patch.dict("os.environ", {"USE_LLM_ROUTER": "true"}):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch("app.chat.unified_router.llm_router.route", return_value=_tier2_decision()):
                with patch(
                    "app.chat.unified_router.try_tier2_with_filters_with_usage",
                    return_value=("Tier2 from router", 12, 7, 5),
                ) as t2_from_filters:
                    with patch(
                        "app.chat.unified_router.try_tier2_with_usage",
                        side_effect=AssertionError("legacy parser path must be skipped"),
                    ):
                        with patch(
                            "app.chat.unified_router.answer_with_tier3",
                            side_effect=AssertionError("Tier3 should not run when Tier2 succeeds"),
                        ):
                            r = route("events next week", "sess-router-t2", db)
    assert r.tier_used == "2"
    assert r.response == "Tier2 from router"
    t2_from_filters.assert_called_once()


def test_flag_on_router_tier3_routes_to_tier3(db: Session) -> None:
    with patch.dict("os.environ", {"USE_LLM_ROUTER": "true"}):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch("app.chat.unified_router.llm_router.route", return_value=_tier3_decision()):
                with patch(
                    "app.chat.unified_router.answer_with_tier3",
                    return_value=("Tier3 from router", 8, 5, 3),
                ) as t3:
                    with patch(
                        "app.chat.unified_router.try_tier2_with_filters_with_usage",
                        side_effect=AssertionError("Tier2 should not run for router tier 3"),
                    ):
                        r = route("what should I do this weekend", "sess-router-t3", db)
    assert r.tier_used == "3"
    assert r.response == "Tier3 from router"
    t3.assert_called_once()


def test_flag_on_router_failure_falls_back_to_tier3(db: Session) -> None:
    with patch.dict("os.environ", {"USE_LLM_ROUTER": "true"}):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch("app.chat.unified_router.llm_router.route", return_value=None):
                with patch(
                    "app.chat.unified_router.answer_with_tier3",
                    return_value=("Tier3 after router fail", 6, 4, 2),
                ) as t3:
                    r = route("events in october", "sess-router-none", db)
    assert r.tier_used == "3"
    assert r.response == "Tier3 after router fail"
    t3.assert_called_once()


def test_flag_off_preserves_existing_classifier_path(db: Session) -> None:
    with patch.dict("os.environ", {"USE_LLM_ROUTER": "false"}):
        with patch("app.chat.unified_router.try_tier1", return_value=None):
            with patch(
                "app.chat.unified_router.try_tier2_with_usage",
                return_value=("Legacy tier2 path", 9, 5, 4),
            ) as legacy_t2:
                with patch(
                    "app.chat.unified_router.llm_router.route",
                    side_effect=AssertionError("router must not run when flag is off"),
                ):
                    r = route("events tomorrow", "sess-router-off", db)
    assert r.tier_used == "2"
    assert r.response == "Legacy tier2 path"
    legacy_t2.assert_called_once()


def test_tier1_fast_path_runs_regardless_of_flag_state(db: Session) -> None:
    p = Provider(
        provider_name="Altitude Trampoline Park — Lake Havasu City",
        category="recreation",
        hours="10:00 AM – 8:00 PM daily",
        phone="928-555-0199",
        source="seed",
    )
    db.add(p)
    db.commit()

    with patch.dict("os.environ", {"USE_LLM_ROUTER": "false"}):
        with patch("app.chat.unified_router.llm_router.route") as router_off:
            r_off = route("What time does altitude open?", "sess-tier1-off", db)
    with patch.dict("os.environ", {"USE_LLM_ROUTER": "true"}):
        with patch("app.chat.unified_router.llm_router.route") as router_on:
            r_on = route("What time does altitude open?", "sess-tier1-on", db)

    assert r_off.tier_used == "1"
    assert r_on.tier_used == "1"
    assert r_off.response == r_on.response
    router_off.assert_not_called()
    router_on.assert_not_called()
