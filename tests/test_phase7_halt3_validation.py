"""Phase 7 — HALT 3 eval-set validator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.chat import disclosure_render
from app.chat.halt3_validator import (
    EvalQuerySpec,
    load_eval_set,
    validate_eval_set,
)
from app.chat.unified_router import ChatResponse


def test_eval_set_loads() -> None:
    specs = load_eval_set("app/chat/halt3_eval_set.yaml")
    assert 20 <= len(specs) <= 30
    assert specs[0].id


def test_eval_spec_shape() -> None:
    specs = load_eval_set(Path("app/chat/halt3_eval_set.yaml"))
    for s in specs:
        assert s.query
        assert s.expected_disclosure_path in ("cited", "uncited", "i_dont_know")


@patch("app.chat.halt3_validator.route")
def test_validator_runs_each_query(mock_route: pytest.Mock) -> None:
    mock_route.return_value = ChatResponse(
        response="I don't have that in the catalog yet.",
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        entity=None,
        tier_used="gap_template",
        latency_ms=1,
    )
    report = validate_eval_set("app/chat/halt3_eval_set.yaml")
    assert len(report.results) == len(load_eval_set("app/chat/halt3_eval_set.yaml"))
    assert mock_route.call_count == len(report.results)


def test_missing_data_zero_confabulation() -> None:
    with patch("app.chat.halt3_validator.route") as mock_route:
        mock_route.return_value = ChatResponse(
            response="I don't have that place in the catalog yet.",
            mode="ask",
            sub_intent=None,
            entity=None,
            tier_used="gap_template",
            latency_ms=1,
        )
        spec = EvalQuerySpec(
            id="t1",
            query="ZZZ Fake",
            expected_tier="any",
            expected_disclosure_path="i_dont_know",
            expected_confabulation_rate=0.0,
        )
        with patch(
            "app.chat.halt3_validator.load_eval_set", return_value=[spec]
        ):
            report = validate_eval_set("ignored.yaml")
        assert report.missing_data_max_confabulation == 0.0


def test_disclosure_renderer_flag_default_off() -> None:
    assert disclosure_render.is_renderer_enabled() is False


def test_cited_coverage_metric() -> None:
    with patch("app.chat.halt3_validator.route") as mock_route:
        mock_route.return_value = ChatResponse(
            response="Here are a few coffee spots.",
            mode="ask",
            sub_intent=None,
            entity=None,
            tier_used="2",
            latency_ms=1,
        )
        specs = [
            EvalQuerySpec("c1", "coffee", "tier2", "cited", 0.0),
            EvalQuerySpec("c2", "barber", "tier2", "cited", 0.0),
        ]
        with patch("app.chat.halt3_validator.load_eval_set", return_value=specs):
            report = validate_eval_set("ignored.yaml")
        assert report.cited_disclosure_coverage == 1.0


def test_validator_gate_with_mocked_router() -> None:
    def _fake_route(q, sid, db, **kwargs):
        low = q.lower()
        if any(
            tok in low
            for tok in (
                "zzz",
                "fake",
                "imaginary",
                "fabricated",
                "nonexistent",
                "missing",
                "random place",
                "wait at",
            )
        ):
            return ChatResponse(
                response="I don't have that in the catalog yet.",
                mode="ask",
                sub_intent="HOURS_LOOKUP",
                entity=None,
                tier_used="gap_template",
                latency_ms=1,
            )
        if q.strip().lower() in ("hey", "thanks", "good morning"):
            return ChatResponse(
                response="Hey.",
                mode="chat",
                sub_intent="GREETING",
                entity=None,
                tier_used="chat",
                latency_ms=1,
            )
        return ChatResponse(
            response="A few local options are listed in the catalog.",
            mode="ask",
            sub_intent="GENERAL_QUESTION",
            entity=None,
            tier_used="2",
            latency_ms=1,
        )

    with patch("app.chat.halt3_validator.route", side_effect=_fake_route):
        report = validate_eval_set("app/chat/halt3_eval_set.yaml")
    assert report.cited_disclosure_coverage >= 1.0
    assert report.missing_data_max_confabulation == 0.0
    assert report.all_passed is True


def test_boat_mode_param_forwarded() -> None:
    with patch("app.chat.halt3_validator.route") as mock_route:
        mock_route.return_value = ChatResponse(
            response="ok",
            mode="ask",
            sub_intent=None,
            entity=None,
            tier_used="2",
            latency_ms=1,
        )
        validate_eval_set("app/chat/halt3_eval_set.yaml", boat_mode=True)
        assert any(
            call.kwargs.get("query_params") == {"boat": "1"}
            for call in mock_route.call_args_list
        )
