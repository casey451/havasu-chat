"""Phase 2 stack integration tests (handoff §3.2, §3.10, §5 Phase 2.4, §10).

End-to-end: ``POST /api/chat`` → ``unified_router.route`` → ``chat_logs`` rows.
Additive only — no production or sibling test file edits.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
from app.chat.normalizer import normalize
from app.chat.unified_router import _GREETINGS
from app.db.database import SessionLocal
from app.db.models import ChatLog, Program
from app.main import app
from app.schemas.program import ProgramCreate

# §8.7 out-of-scope voice (must match ``app.chat.unified_router._OUT_OF_SCOPE_REPLY`` verbatim).
OUT_OF_SCOPE_87 = (
    "That's outside what I cover right now — I stick to things-to-do, local businesses, and events. "
    "Want me to point you to anything else?"
)

# §3.9: no trailing ``?`` except known question-shaped copy (OOS §8.7; SMALL_TALK "how are you").
_SUBINTENT_TRAILING_QUESTION_OK: frozenset[str] = frozenset({"OUT_OF_SCOPE"})


def _latest_log_for_session(db: Session, session_id: str) -> ChatLog | None:
    sid = session_id.strip()[:128]
    return db.scalars(
        select(ChatLog)
        .where(ChatLog.session_id == sid)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
    ).first()


def _insert_altitude_program(db: Session, *, title: str) -> None:
    payload = ProgramCreate(
        title=title,
        description="Twenty characters minimum fixture.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="17:00",
        location_name="Lake Havasu City",
        provider_name="Altitude Trampoline Park — Lake Havasu City",
        tags=["phase2_integration"],
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


def _assert_body_matches_log(body: dict, row: ChatLog, *, raw_query: str) -> None:
    assert row is not None
    assert body["response"] == row.message
    assert body["mode"] == row.mode
    assert body["sub_intent"] == row.sub_intent
    assert body["entity"] == row.entity_matched
    assert body["tier_used"] == row.tier_used
    assert body["latency_ms"] == row.latency_ms
    assert body.get("llm_tokens_used") == row.llm_tokens_used
    if body.get("chat_log_id") is not None:
        assert body["chat_log_id"] == str(row.id)
    assert row.normalized_query == normalize(raw_query)


@pytest.mark.parametrize(
    ("query", "session_suffix", "expected_mode", "expected_sub"),
    [
        ("What time does altitude open?", "ask", "ask", "TIME_LOOKUP"),
        (
            "I want to add a concert at the park on Friday at 8pm.",
            "contrib",
            "contribute",
            "NEW_EVENT",
        ),
        ("That is wrong — the phone changed.", "corr", "correct", "CORRECTION"),
        ("Hi", "chat", "chat", "GREETING"),
    ],
)
def test_e2e_mode_routing_matches_chat_log(
    query: str,
    session_suffix: str,
    expected_mode: str,
    expected_sub: str,
) -> None:
    sid = f"p2-e2e-{session_suffix}-integ"
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": query, "session_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == expected_mode
    assert body["sub_intent"] == expected_sub
    with SessionLocal() as db:
        row = _latest_log_for_session(db, sid)
    _assert_body_matches_log(body, row, raw_query=query)


def test_multi_turn_session_consistency() -> None:
    sid = "p2-multiturn-same-session"
    with TestClient(app) as client:
        r1 = client.post("/api/chat", json={"query": "hey", "session_id": sid})
        r2 = client.post("/api/chat", json={"query": "hey", "session_id": sid})
        r3 = client.post("/api/chat", json={"query": "Thanks", "session_id": sid})
    assert r1.status_code == r2.status_code == r3.status_code == 200
    assert r1.json()["response"] == r2.json()["response"]
    assert r1.json()["sub_intent"] == "GREETING"
    assert r3.json()["sub_intent"] == "SMALL_TALK"

    with SessionLocal() as db:
        rows = db.scalars(
            select(ChatLog)
            .where(ChatLog.session_id == sid)
            .order_by(ChatLog.created_at.asc(), ChatLog.id.asc())
        ).all()
    assert len(rows) == 3
    assert {r.session_id for r in rows} == {sid}
    assert rows[0].id != rows[1].id != rows[2].id
    assert rows[0].created_at <= rows[1].created_at <= rows[2].created_at


def test_greeting_variant_diversity_across_sessions() -> None:
    """Across many sessions, GREETING should hit at least two of three variants (hash buckets)."""
    greetings: set[str] = set()
    with TestClient(app) as client:
        for i in range(24):
            sid = f"p2-greet-div-{i:03d}-{'x' * (i % 5)}"
            r = client.post("/api/chat", json={"query": "Hello", "session_id": sid})
            assert r.status_code == 200
            greetings.add(r.json()["response"])
    assert greetings.issubset(set(_GREETINGS))
    assert len(greetings) >= 2


def test_entity_enrichment_altitude_matches_log() -> None:
    title = f"Altitude integration fixture {uuid4().hex[:10]}"
    reset_entity_matcher()
    try:
        with SessionLocal() as db:
            _insert_altitude_program(db, title=title)
            refresh_entity_matcher(db)

        sid = "p2-entity-altitude"
        q = "what time does altitude open"
        with TestClient(app) as client:
            r = client.post("/api/chat", json={"query": q, "session_id": sid})
        assert r.status_code == 200
        body = r.json()
        canon = "Altitude Trampoline Park — Lake Havasu City"
        assert body["entity"] == canon
        with SessionLocal() as db:
            row = _latest_log_for_session(db, sid)
        assert row.entity_matched == canon
        _assert_body_matches_log(body, row, raw_query=q)
    finally:
        with SessionLocal() as db:
            for p in db.scalars(select(Program).where(Program.title == title)).all():
                db.delete(p)
            db.commit()
        reset_entity_matcher()


def test_normalization_pipeline_survives() -> None:
    raw = "  WHAT TIME DOES ALTITUDE OPEN??  "
    expected_nq = normalize(raw)
    sid = "p2-norm-pipe"
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": raw, "session_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    assert body["sub_intent"] == "TIME_LOOKUP"
    assert body["entity"] == "Altitude Trampoline Park — Lake Havasu City"
    with SessionLocal() as db:
        row = _latest_log_for_session(db, sid)
    assert row.normalized_query == expected_nq
    assert body["sub_intent"] == row.sub_intent


def test_classify_raises_second_call_graceful_e2e() -> None:
    """Actual behavior: exceptions are caught inside ``route()`` → HTTP 200 + graceful JSON."""
    from app.chat import intent_classifier

    real_classify = intent_classifier.classify
    state = {"n": 0}

    def classify_maybe_boom(q: str):
        state["n"] += 1
        if state["n"] >= 2:
            raise RuntimeError("simulated classify failure")
        return real_classify(q)

    sid = "p2-classify-boom"
    with TestClient(app) as client:
        with patch("app.chat.unified_router.classify", side_effect=classify_maybe_boom):
            r1 = client.post("/api/chat", json={"query": "Hi", "session_id": sid})
            r2 = client.post("/api/chat", json={"query": "Hi", "session_id": sid})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert "Something went sideways" in r2.json()["response"]
    assert r2.json()["mode"] == "ask"
    assert r2.json()["sub_intent"] is None

    with SessionLocal() as db:
        row_fail = _latest_log_for_session(db, sid)
    assert row_fail.message == r2.json()["response"]
    assert row_fail.mode == "ask"
    assert row_fail.sub_intent is None


@pytest.mark.parametrize(
    ("query", "label"),
    [
        ("What's the weather like in Lake Havasu?", "weather"),
        ("Where should I buy a house in Havasu?", "real_estate"),
        ("Any good restaurants?", "dining"),
    ],
)
def test_oos_end_to_end_verbatim_redirect(query: str, label: str) -> None:
    sid = f"p2-oos-{label}"
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": query, "session_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "chat"
    assert body["sub_intent"] == "OUT_OF_SCOPE"
    assert body["response"] == OUT_OF_SCOPE_87
    with SessionLocal() as db:
        row = _latest_log_for_session(db, sid)
    assert row.message == OUT_OF_SCOPE_87


def test_voice_trailing_question_guard() -> None:
    """§3.9 smoke: no ``?`` at end unless OOS §8.7 or SMALL_TALK ``how are you``."""
    cases: list[tuple[str, str, str]] = [
        ("What time does altitude open?", "p2-v-1", "ask"),
        ("Where is the BMX track?", "p2-v-2", "ask"),
        ("I want to add a concert Saturday.", "p2-v-3", "contribute"),
        ("That is wrong — the hours changed.", "p2-v-4", "correct"),
        ("Hi", "p2-v-5", "chat"),
        ("Thanks", "p2-v-6", "chat"),
        ("Bye", "p2-v-7", "chat"),
        ("What's the weather?", "p2-v-8", "chat"),
        ("Any good restaurants?", "p2-v-9", "chat"),
        ("How much does sonics cost?", "p2-v-10", "ask"),
        ("Phone number for aquatic center?", "p2-v-11", "ask"),
        ("Website for little league?", "p2-v-12", "ask"),
        ("Age requirements for junior ranger?", "p2-v-13", "ask"),
        ("Any good soccer leagues in Lake Havasu?", "p2-v-14", "ask"),
        ("When is the next BMX race?", "p2-v-15", "ask"),
        ("Is altitude open right now?", "p2-v-16", "ask"),
        ("What is fun to do this weekend?", "p2-v-17", "ask"),
        ("There is a car show Saturday.", "p2-v-18", "contribute"),
        ("Actually it's on Kiowa now.", "p2-v-19", "correct"),
        ("How are you?", "p2-v-20", "chat"),
    ]
    with TestClient(app) as client:
        for query, sid, _ in cases:
            r = client.post("/api/chat", json={"query": query, "session_id": sid})
            assert r.status_code == 200
            body = r.json()
            resp = body["response"]
            sub = body["sub_intent"]
            nq = normalize(query)
            if not resp.rstrip().endswith("?"):
                continue
            assert sub in _SUBINTENT_TRAILING_QUESTION_OK or (
                sub == "SMALL_TALK" and "how are you" in nq
            ), f"unexpected trailing '?': query={query!r} sub={sub!r} resp={resp!r}"


def test_placeholder_tier_for_non_chat_modes() -> None:
    # Ask: use open-ended text so Tier 1 is not used (shared session DB may contain
    # seeded providers from other tests, which would make a TIME_LOOKUP hit Tier 1).
    ask_q, ask_sid = ("What is fun to do this weekend?", "p2-tier-ask")
    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with patch(
            "app.chat.unified_router.answer_with_tier3",
            return_value=("tier3 stub body", 77, 50, 27),
        ):
            with TestClient(app) as client:
                r = client.post("/api/chat", json={"query": ask_q, "session_id": ask_sid})
        assert r.status_code == 200
        body = r.json()
        assert body["tier_used"] == "3"
        assert body["llm_tokens_used"] == 77
        assert body["response"] == "tier3 stub body"
    checks = [
        ("I want to add a concert Friday.", "p2-tier-co"),
        ("That is wrong — phone changed.", "p2-tier-cr"),
    ]
    with TestClient(app) as client:
        for q, sid in checks:
            r = client.post("/api/chat", json={"query": q, "session_id": sid})
            assert r.status_code == 200
            assert r.json()["tier_used"] == "placeholder"
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"query": "Hi", "session_id": "p2-tier-chat"})
    assert r.status_code == 200
    assert r.json()["tier_used"] == "chat"
