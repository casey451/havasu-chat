"""Phase 6.4 — prior-entity pronoun fallback in ``unified_router`` (not entity_matcher)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
from app.chat.intent_classifier import IntentResult
from app.chat.unified_router import ChatResponse, _enrich_entity_from_db, _prior_entity_fresh, route
from app.core.session import clear_session_state, get_session
from app.db.database import SessionLocal
from app.db.models import Program
from app.schemas.program import ProgramCreate


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _intent_open() -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        confidence=0.8,
        entity=None,
        raw_query="what time does it open",
        normalized_query="what time does it open",
    )


def test_prior_entity_fresh_boundary() -> None:
    sess = {"prior_entity": {"turn_number": 1, "name": "X", "id": "i", "type": "provider"}}
    assert _prior_entity_fresh(sess, 4) is not None
    assert _prior_entity_fresh(sess, 5) is None


def test_enrich_pronoun_uses_prior_when_fuzzy_misses(db: Session) -> None:
    ir = _intent_open()
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Altitude Trampoline Park — Lake Havasu City",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what time does it open?",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity == "Altitude Trampoline Park — Lake Havasu City"


def test_enrich_explicit_entity_wins_over_prior(db: Session) -> None:
    ir = replace(
        _intent_open(),
        entity="Lake Havasu City BMX",
        raw_query="what time does bmx open",
        normalized_query="what time does bmx open",
    )
    session = {"prior_entity": {"id": "x", "name": "Altitude Trampoline Park — Lake Havasu City", "type": "provider", "turn_number": 1}}
    out = _enrich_entity_from_db(
        "what time does bmx open",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity == "Lake Havasu City BMX"


def test_enrich_stale_prior_not_used(db: Session) -> None:
    ir = _intent_open()
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Altitude Trampoline Park — Lake Havasu City",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what time does it open?",
        ir,
        db,
        session=session,
        current_turn=5,
    )
    assert out.entity is None


def test_enrich_there_matches_prior(db: Session) -> None:
    ir = replace(_intent_open(), raw_query="what about there", normalized_query="what about there")
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Havasu Lanes",
            "type": "provider",
            "turn_number": 2,
        }
    }
    out = _enrich_entity_from_db(
        "what about there?",
        ir,
        db,
        session=session,
        current_turn=3,
    )
    assert out.entity == "Havasu Lanes"


def test_enrich_no_pronoun_no_prior_fallback(db: Session) -> None:
    ir = replace(
        _intent_open(),
        raw_query="what is good for dinner",
        normalized_query="what is good for dinner",
    )
    session = {
        "prior_entity": {
            "id": "p1",
            "name": "Havasu Lanes",
            "type": "provider",
            "turn_number": 1,
        }
    }
    out = _enrich_entity_from_db(
        "what is good for dinner",
        ir,
        db,
        session=session,
        current_turn=2,
    )
    assert out.entity is None


_CANON_BMX = "Lake Havasu City BMX"
_CANON_LANES = "Havasu Lanes"
_CANON_ALT = "Altitude Trampoline Park — Lake Havasu City"


def _insert_program(db: Session, provider_name: str, title_suffix: str = "") -> str:
    suf = title_suffix or provider_name[:24]
    payload = ProgramCreate(
        title=f"Test activity {suf}",
        description="Twenty chars minimum here.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Lake Havasu City",
        provider_name=provider_name,
        tags=["prior_entity_router_test"],
    )
    p = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


@pytest.fixture
def router_program_cleanup(db: Session):
    ids: list[str] = []
    yield ids
    reset_entity_matcher()
    for pid in ids:
        row = db.get(Program, pid)
        if row is not None:
            db.delete(row)
    db.commit()
    reset_entity_matcher()


def _patch_ask_to_tier3(response_text: str):
    return patch.multiple(
        "app.chat.unified_router",
        extract_hints=lambda *a, **k: None,
        try_tier1=lambda *a, **k: None,
        try_tier2_with_usage=lambda *a, **k: (None, None, None, None),
        answer_with_tier3=lambda *a, **k: (response_text, 10, 5, 5),
    )


def _patch_ask_to_tier2(response_text: str):
    return patch.multiple(
        "app.chat.unified_router",
        extract_hints=lambda *a, **k: None,
        try_tier1=lambda *a, **k: None,
        try_tier2_with_usage=lambda *a, **k: (response_text, 8, 4, 4),
        answer_with_tier3=lambda *a, **k: ("should not run", 0, 0, 0),
    )


def test_recommended_capture_tier3_single_provider(db: Session, router_program_cleanup: list[str]) -> None:
    sid = f"pe641-t3-1-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmx1"))
    refresh_entity_matcher(db)
    msg = "What is fun this weekend?"
    with _patch_ask_to_tier3(
        f"I would try {_CANON_BMX} for bikes — the bmx track is great for kids.",
    ):
        r = route(msg, sid, db)
    assert isinstance(r, ChatResponse)
    assert r.tier_used == "3"
    pe = get_session(sid).get("prior_entity")
    assert pe is not None
    assert pe["name"] == _CANON_BMX
    assert pe["type"] == "provider"
    assert pe["turn_number"] == 1


def test_recommended_capture_tier3_two_providers_no_prior_write(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-t3-2-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmx2"))
    router_program_cleanup.append(_insert_program(db, _CANON_LANES, "lanes1"))
    refresh_entity_matcher(db)
    get_session(sid)["prior_entity"] = {
        "id": "keep",
        "name": "Prior Placeholder",
        "type": "provider",
        "turn_number": 0,
    }
    with _patch_ask_to_tier3(
        f"Either {_CANON_BMX} or {_CANON_LANES} would work tonight — both are fun.",
    ):
        r = route("open ended", sid, db)
    assert r.tier_used == "3"
    pe = get_session(sid)["prior_entity"]
    assert pe["name"] == "Prior Placeholder"


def test_recommended_capture_tier3_zero_mentions_leaves_prior(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-t3-0-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmx0"))
    refresh_entity_matcher(db)
    get_session(sid)["prior_entity"] = {
        "id": "k2",
        "name": "Stale Prior",
        "type": "provider",
        "turn_number": 0,
    }
    with _patch_ask_to_tier3("Nothing specific in the catalog for that vague ask."):
        r = route("something vague", sid, db)
    assert r.tier_used == "3"
    assert get_session(sid)["prior_entity"]["name"] == "Stale Prior"


def test_recommended_capture_tier2_single_provider(db: Session, router_program_cleanup: list[str]) -> None:
    sid = f"pe641-t2-1-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_LANES, "lanes2"))
    refresh_entity_matcher(db)
    with _patch_ask_to_tier2(f"Tonight try {_CANON_LANES} for bowling."):
        r = route("dinner and bowling ideas", sid, db)
    assert r.tier_used == "2"
    pe = get_session(sid).get("prior_entity")
    assert pe is not None
    assert pe["name"] == _CANON_LANES
    assert pe["turn_number"] == 1


def test_recommended_capture_overwrites_prior_across_turns(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-ov-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmxo"))
    router_program_cleanup.append(_insert_program(db, _CANON_LANES, "laneso"))
    refresh_entity_matcher(db)
    with _patch_ask_to_tier3(f"Start with {_CANON_BMX} for outdoor fun."):
        route("open one", sid, db)
    assert get_session(sid)["prior_entity"]["name"] == _CANON_BMX
    assert get_session(sid)["prior_entity"]["turn_number"] == 1
    with _patch_ask_to_tier3(f"Tomorrow consider {_CANON_LANES} instead."):
        route("open two", sid, db)
    pe = get_session(sid)["prior_entity"]
    assert pe["name"] == _CANON_LANES
    assert pe["turn_number"] == 2


def test_recommended_capture_duplicate_name_in_response_once(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-dd-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmxd"))
    refresh_entity_matcher(db)
    with _patch_ask_to_tier3(
        f"{_CANON_BMX} is fun. {_CANON_BMX} opens early on weekends.",
    ):
        route("tell me more", sid, db)
    pe = get_session(sid)["prior_entity"]
    assert pe["name"] == _CANON_BMX


def test_recommended_capture_overwrites_user_named_same_turn(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-pr-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_BMX, "bmxp"))
    router_program_cleanup.append(_insert_program(db, _CANON_LANES, "lanesp"))
    refresh_entity_matcher(db)
    fake = IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.85,
        entity=_CANON_BMX,
        raw_query="tell me about bmx",
        normalized_query="tell me about bmx",
    )
    with patch("app.chat.unified_router.classify", return_value=fake):
        with _patch_ask_to_tier3(f"Also check out {_CANON_LANES} for bowling."):
            r = route("tell me about bmx", sid, db)
    assert r.tier_used == "3"
    pe = get_session(sid)["prior_entity"]
    assert pe["name"] == _CANON_LANES


def test_recommended_then_pronoun_followup_resolves_altitude(
    db: Session, router_program_cleanup: list[str]
) -> None:
    sid = f"pe641-e2e-{uuid4().hex[:10]}"
    clear_session_state(sid)
    router_program_cleanup.append(_insert_program(db, _CANON_ALT, "alt1"))
    refresh_entity_matcher(db)
    with _patch_ask_to_tier3(
        f"I would hit {_CANON_ALT} for jumping — great for kids.",
    ):
        r1 = route("what should we do tomorrow", sid, db)
    assert r1.tier_used == "3"
    assert get_session(sid)["prior_entity"]["name"] == _CANON_ALT
    hours = IntentResult(
        mode="ask",
        sub_intent="HOURS_LOOKUP",
        confidence=0.9,
        entity=None,
        raw_query="what time does it open",
        normalized_query="what time does it open",
    )
    with patch("app.chat.unified_router.classify", return_value=hours):
        with patch.multiple(
            "app.chat.unified_router",
            extract_hints=lambda *a, **k: None,
            try_tier1=lambda *a, **k: f"{_CANON_ALT} opens at 10am weekdays.",
            try_tier2_with_usage=lambda *a, **k: (None, None, None, None),
            answer_with_tier3=lambda *a, **k: ("no tier3", 0, 0, 0),
        ):
            r2 = route("what time does it open?", sid, db)
    assert isinstance(r2, ChatResponse)
    assert r2.tier_used == "1"
    assert r2.entity == _CANON_ALT
    assert _CANON_ALT.split()[0] in r2.response or "10am" in r2.response
