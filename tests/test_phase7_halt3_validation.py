"""Phase 7 — HALT 3 eval-set validator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat import disclosure_render
from app.chat.halt3_validator import (
    EvalQuerySpec,
    load_eval_set,
    validate_eval_set,
)
from app.chat.unified_router import ChatResponse, route
from app.db.database import SessionLocal


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_q07_tell_me_about_fake_entity_routes_to_gap_template_not_tier3(db: Session) -> None:
    """Reproduces the prod q07 regression: 'Tell me about Totally Fake Business
    XYZ 404' falls through to tier-3 LLM which confabulates with honest prefix."""

    def _tier3_should_not_be_called(*args, **kwargs):
        raise AssertionError(
            "tier-3 LLM invoked for q07 — _unknown_entity_about_gate failed to intercept"
        )

    with patch(
        "app.chat.unified_router.answer_with_tier3", side_effect=_tier3_should_not_be_called
    ):
        r = route("Tell me about Totally Fake Business XYZ 404", "sess-q07-red", db)

    assert r.tier_used == "gap_template", f"Expected gap_template tier, got {r.tier_used}"
    assert "don't have that one in the catalog" in r.response, (
        f"Expected _UNKNOWN_ENTITY_GAP template. Got: {r.response}"
    )


def test_eval_set_loads() -> None:
    specs = load_eval_set("app/chat/halt3_eval_set.yaml")
    assert 20 <= len(specs) <= 30
    assert specs[0].id


def test_eval_spec_shape() -> None:
    valid = ("cited", "uncited", "i_dont_know")
    specs = load_eval_set(Path("app/chat/halt3_eval_set.yaml"))
    for s in specs:
        assert s.query
        exp = s.expected_disclosure_path
        if isinstance(exp, list):
            assert exp and all(p in valid for p in exp)
        else:
            assert exp in valid


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
        with patch("app.chat.halt3_validator.load_eval_set", return_value=[spec]):
            report = validate_eval_set("ignored.yaml")
        assert report.missing_data_max_confabulation == 0.0


def test_disclosure_renderer_flag_default_off() -> None:
    assert disclosure_render.is_renderer_enabled() is False


def test_cited_coverage_metric(db: Session) -> None:
    from app.chat.entity_matcher import EntityMatch

    cited_response = "Heat Hotel is in the catalog."
    with patch("app.chat.halt3_validator.route") as mock_route:
        mock_route.return_value = ChatResponse(
            response=cited_response,
            mode="ask",
            sub_intent=None,
            entity="Heat Hotel",
            tier_used="2",
            latency_ms=1,
        )
        specs = [
            EvalQuerySpec("c1", "coffee", "tier2", "cited", 0.0),
            EvalQuerySpec("c2", "barber", "tier2", "cited", 0.0),
        ]
        with (
            patch("app.chat.halt3_validator.load_eval_set", return_value=specs),
            patch(
                "app.chat.halt3_validator.extract_catalog_entities_from_text",
                return_value=[EntityMatch(name="Heat Hotel", type="provider", id="p1")],
            ),
        ):
            report = validate_eval_set("ignored.yaml", db=db)
        assert report.cited_disclosure_coverage == 1.0


def test_validator_gate_with_mocked_router(db: Session) -> None:
    from app.chat.entity_matcher import EntityMatch

    specs = load_eval_set("app/chat/halt3_eval_set.yaml")
    catalog_hit = [EntityMatch(name="Heat Hotel", type="provider", id="p1")]

    tier_map = {"tier1": "1", "tier2": "2", "tier3": "3"}

    def _expected_tier_used(spec: EvalQuerySpec) -> str:
        exp = spec.expected_tier
        if isinstance(exp, list):
            exp = exp[-1] if spec.expected_disclosure_path in ("uncited", "i_dont_know") else exp[0]
        return tier_map.get(exp, exp)

    def _fake_route(q, sid, db, **kwargs):
        spec = next((s for s in specs if s.query == q), None)
        if spec is None:
            tier_used = "2"
            response = "Heat Hotel is in the catalog."
        elif spec.expected_disclosure_path == "i_dont_know":
            tier_used = _expected_tier_used(spec)
            response = "I don't have that in the catalog yet."
        elif spec.expected_disclosure_path == "uncited":
            tier_used = _expected_tier_used(spec)
            response = "Hey." if tier_used == "chat" else "No catalog match."
        else:
            tier_used = _expected_tier_used(spec)
            response = "Heat Hotel is in the catalog."
        return ChatResponse(
            response=response,
            mode="ask",
            sub_intent=None,
            entity="Heat Hotel" if "Heat Hotel" in response else None,
            tier_used=tier_used,
            latency_ms=1,
        )

    def _extract_entities(text: str, db_arg: Session) -> list:
        low = (text or "").lower()
        if "don't have" in low or low.startswith("no catalog match") or low.startswith("hey"):
            return []
        return catalog_hit

    with (
        patch("app.chat.halt3_validator.route", side_effect=_fake_route),
        patch(
            "app.chat.halt3_validator.extract_catalog_entities_from_text",
            side_effect=_extract_entities,
        ),
    ):
        report = validate_eval_set("app/chat/halt3_eval_set.yaml", db=db)
    assert len(report.results) == len(specs)
    assert report.cited_disclosure_coverage >= 1.0
    assert report.missing_data_max_confabulation == 0.0
    failures = [(r.spec.id, r.failure_reasons) for r in report.results if not r.passed]
    assert report.all_passed is True, f"mock gate failures: {failures}"


def test_validator_catches_hardening_failure_modes_with_mocked_router(db: Session) -> None:
    """F3: hardened validator catches Goodhart failure modes with adversarial mocks."""
    adversarial_responses = {
        "q07": (
            "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. "
            "Their listed number is (928) 502-4001 -- recommend calling to confirm."
        ),
        "q05": "Sure, here are a few local options worth checking out.",
        "q08": (
            "I don't have that one in the catalog, but you can try "
            "1450 N McCulloch Blvd, (928) 555-0199, open Tue-Sat 9-6."
        ),
    }

    specs = load_eval_set("app/chat/halt3_eval_set.yaml")
    spec_by_id = {s.id: s for s in specs}

    from app.chat.entity_matcher import EntityMatch

    catalog_hit = [EntityMatch(name="Heat Hotel", type="provider", id="p1")]

    def _route_by_spec(q, sid, db_arg, **kwargs):
        matching_id = next(
            (sid_ for sid_, sp in spec_by_id.items() if sp.query == q),
            None,
        )
        if matching_id in adversarial_responses:
            return ChatResponse(
                response=adversarial_responses[matching_id],
                mode="ask",
                sub_intent=None,
                entity=None,
                tier_used="3",
                latency_ms=10,
            )
        return ChatResponse(
            response="Heat Hotel is in the catalog.",
            mode="ask",
            sub_intent=None,
            entity="Heat Hotel",
            tier_used="2",
            latency_ms=10,
        )

    def _extract_entities(text, db_arg):
        if "Heat Hotel" in text:
            return catalog_hit
        return []

    with (
        patch("app.chat.halt3_validator.route", side_effect=_route_by_spec),
        patch(
            "app.chat.halt3_validator.extract_catalog_entities_from_text",
            side_effect=_extract_entities,
        ),
    ):
        report = validate_eval_set("app/chat/halt3_eval_set.yaml", db=db)

    failed_ids = {r.spec.id for r in report.results if not r.passed}
    assert "q07" in failed_ids, (
        "q07 adversarial response (honest prefix + invented phone) should FAIL "
        "after G2+G3 hardening but PASSed. Validator regression."
    )
    assert "q05" in failed_ids, (
        "q05 adversarial response (tier-3 cited claim with no real entity) should "
        "FAIL after G5 hardening but PASSed. G5 evidence gate not active."
    )
    assert "q08" in failed_ids, (
        "q08 adversarial response (honest prefix + invented address) should FAIL "
        "after G2+G3 hardening but PASSed."
    )


@pytest.mark.skipif(
    __import__("os").environ.get("HAVASU_USE_DEV_DB_FOR_TESTS") != "1",
    reason="Full HALT3 eval needs dev catalog (HAVASU_USE_DEV_DB_FOR_TESTS=1).",
)
def test_halt3_validator_full_eval_set_with_hardening() -> None:
    """Post-Phase 7.5.2: validator runs 30/30 against the hardened eval set."""
    report = validate_eval_set("app/chat/halt3_eval_set.yaml")
    failed = [r for r in report.results if not r.passed]
    assert not failed, f"{len(failed)} validator rows FAILED:\n" + "\n".join(
        f"  {r.spec.id}: {r.failure_reasons}" for r in failed
    )
    assert report.all_passed
    assert report.cited_disclosure_coverage >= 1.0
    assert report.missing_data_max_confabulation <= 0.0
    assert len(report.results) >= 30


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
            call.kwargs.get("query_params") == {"boat": "1"} for call in mock_route.call_args_list
        )


def test_f5_lead_in_clause_enters_about_gate(db: Session) -> None:
    """Phase 7.5.3 F5: conversational lead-in clauses must not defeat the
    about-gate. Pre-fix: 'Hey, tell me about X' bypasses the gate and falls
    through to tier-3 LLM. Post-fix: the lead-in is absorbed by _LEAD_IN_PREFIX
    and the gate fires identically to bare 'tell me about X'.
    """
    from unittest.mock import patch

    from app.chat.unified_router import route

    def _tier3_should_not_be_called(*args, **kwargs):
        raise AssertionError("tier-3 LLM invoked for F5 lead-in shape — _LEAD_IN_PREFIX failed")

    queries = [
        "Hey, tell me about Totally Fake Business XYZ 404",
        "Quick question — describe Totally Fake Business XYZ 404",
        "OK so, what is Totally Fake Business XYZ 404",
    ]
    with patch(
        "app.chat.unified_router.answer_with_tier3",
        side_effect=_tier3_should_not_be_called,
    ):
        for q in queries:
            r = route(q, f"sess-f5-{abs(hash(q)) % 10000}", db)
            assert r.tier_used == "gap_template", (
                f"Expected gap_template for {q!r}, got {r.tier_used}. Response: {r.response}"
            )


def test_f5_about_gate_query_eligible_lead_in_positive() -> None:
    """Unit-level: _about_gate_query_eligible must accept lead-in shapes."""
    from app.chat.unified_router import _about_gate_query_eligible

    assert _about_gate_query_eligible("Hey, tell me about Heat Hotel")
    assert _about_gate_query_eligible("Quick question — describe Heat Hotel")
    assert _about_gate_query_eligible("OK so, what is Heat Hotel")
    # Bare shapes still fire (no regression):
    assert _about_gate_query_eligible("tell me about Heat Hotel")
    assert _about_gate_query_eligible("describe Heat Hotel")


def test_f5_about_gate_no_overmatch_on_mid_sentence() -> None:
    """Negative: mid-sentence 'tell me about' inside a quoted string does NOT fire.
    The lead-in prefix requires punctuation; quoted-context drift should miss."""
    from app.chat.unified_router import _about_gate_query_eligible

    assert not _about_gate_query_eligible(
        "the description says 'tell me about your services' is the legit?"
    )
