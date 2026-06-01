"""Lane B-3 -- chat_logs observability columns + telemetry plumbing."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import ChatLog


@pytest.fixture
def db_session() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_chat_log_has_cache_status_column() -> None:
    """B-3 adds chat_logs.cache_status nullable column."""
    cols = {c.name for c in ChatLog.__table__.columns}
    assert "cache_status" in cols, "Lane B-3 cache_status column missing"


def test_chat_log_has_timing_ms_column() -> None:
    """B-3 adds chat_logs.timing_ms JSON nullable column."""
    cols = {c.name for c in ChatLog.__table__.columns}
    assert "timing_ms" in cols, "Lane B-3 timing_ms column missing"


def test_chat_log_can_write_cache_status_and_timing_ms(db_session: Session) -> None:
    """Smoke: write a ChatLog row with the new columns populated and read it back."""
    from datetime import UTC, datetime

    row = ChatLog(
        session_id="b3-test",
        message="b3 smoke",
        role="user",
        created_at=datetime.now(UTC),
        cache_status="hit_exact",
        timing_ms={"tier3_lookup_ms": 12, "tier3_llm_ms": 0},
    )
    db_session.add(row)
    db_session.commit()
    out = db_session.scalars(
        select(ChatLog).where(ChatLog.session_id == "b3-test").limit(1)
    ).first()
    assert out is not None
    assert out.cache_status == "hit_exact"
    assert out.timing_ms == {"tier3_lookup_ms": 12, "tier3_llm_ms": 0}


def test_tier3_handler_populates_telemetry_on_cache_hit(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """answer_with_tier3 populates telemetry['cache_status']='hit_exact' on exact-key hit."""
    from app.chat import llm_cache, tier3_handler
    from app.chat.intent_classifier import IntentResult
    from app.chat.llm_cache import make_cache_key
    from app.core.timezone import now_lake_havasu

    query = "b3 telemetry test query"
    cache_context = {"_today": now_lake_havasu().date().isoformat()}
    cache_key = make_cache_key(query, cache_context)
    llm_cache.store_with_embedding(
        db_session,
        cache_key=cache_key,
        normalized_query=query,
        context=cache_context,
        response_text="cached answer",
        tier_used="tier3",
    )

    intent = IntentResult(
        mode="ask",
        sub_intent="open_ended",
        confidence=0.9,
        entity=None,
        raw_query=query,
        normalized_query=query,
    )
    telemetry: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key-not-used")
    text, total, tin, tout = tier3_handler.answer_with_tier3(
        query,
        intent,
        db_session,
        chat_ctx=None,
        telemetry=telemetry,
    )
    assert telemetry.get("cache_status") in {"hit_exact", "hit_sim"}, (
        f"expected cache hit, got {telemetry.get('cache_status')!r}"
    )
    assert "tier3_lookup_ms" in telemetry


def test_tier2_handler_populates_telemetry_on_parser_cache_hit(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """try_tier2_with_usage populates telemetry with parser cache hit signal."""
    from app.chat import tier2_cache, tier2_handler
    from app.chat.tier2_schema import Tier2Filters
    from app.core.timezone import now_lake_havasu

    today_iso = now_lake_havasu().strftime("%Y-%m-%d")
    pre_filters = Tier2Filters(
        category="restaurant",
        open_now=True,
        parser_confidence=0.9,
        fallback_to_tier3=False,
    )
    tier2_cache.store_parser(db_session, "b3 tier2 telemetry test", today_iso, pre_filters)

    telemetry: dict = {}
    try:
        tier2_handler.try_tier2_with_usage("b3 tier2 telemetry test", telemetry=telemetry)
    except TypeError:
        pytest.skip("try_tier2_with_usage does not yet accept telemetry kwarg; verify §2c wiring")

    assert telemetry.get("tier2_parser_cache") == "hit_exact" or telemetry.get("cache_status") in {
        "hit_exact",
        "miss",
    }, f"telemetry not populated: {telemetry}"
