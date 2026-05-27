"""Backlog #49 — Tier 3 cache stores raw LLM text; post-process runs on cache hit."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import Session

import app.core.llm_messages as llm_messages
from app.chat import tier2_formatter as tf
from app.chat.intent_classifier import IntentResult
from app.chat.tier3_handler import answer_with_tier3
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import (
    ContactPoint,
    Entity,
    EntityCategory,
    Event,
    Hours,
    LlmResponseCache,
    Location,
    Offering,
    Program,
    Provider,
    Schedule,
    SourceEvidence,
)

_FLAG = tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def isolated_catalog(db: Session) -> Session:
    """Wipe catalog plus LLM cache plus the Entity subtree inside a savepoint.

    Entity-subtree children (EntityCategory/Location/Hours/ContactPoint/
    Offering/Schedule/SourceEvidence) and Entity itself are cleared per v42 §2
    hardening so Entity rows from prior tests cannot pollute matcher lookups.
    """
    nested = db.begin_nested()
    db.execute(delete(LlmResponseCache))
    # FK-safe delete order: rows referencing entities.id first, then Entity
    # itself. See test_context_builder.isolated_catalog for the full rationale.
    db.execute(delete(Program))
    db.execute(delete(Event))
    db.execute(delete(Provider))
    db.execute(delete(EntityCategory))
    db.execute(delete(Location))
    db.execute(delete(Hours))
    db.execute(delete(ContactPoint))
    db.execute(delete(Offering))
    db.execute(delete(Schedule))
    db.execute(delete(SourceEvidence))
    db.execute(delete(Entity))
    db.flush()
    yield db
    try:
        nested.rollback()
    except ResourceClosedError:
        pass


def _intent(*, entity=None) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.7,
        entity=entity,
        raw_query="anything",
        normalized_query="anything",
    )


def _aware_age(age_days: int):
    return now_lake_havasu() - timedelta(days=age_days)


def _add_provider(db, *, name, age_days, method, phone):
    p = Provider(
        provider_name=name,
        category="services",
        phone=phone,
        verified=True,
        draft=False,
        is_active=True,
        last_verified_at=_aware_age(age_days),
        verification_method=method,
    )
    db.add(p)
    db.flush()
    return p


def _resp(text, *, prompt_tokens=12, completion_tokens=8):
    from types import SimpleNamespace

    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _patched_openai(text):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(text)
    return fake


def test_cache_row_stores_raw_llm_without_phone_hedge(isolated_catalog, monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Crestline Plumbing",
        age_days=200,
        method="manual",
        phone="(928) 855-3333",
    )
    db.flush()

    llm_voice = "Crestline Plumbing might be a fit."
    fake = _patched_openai(llm_voice)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    assert "recommend calling to confirm" in text.lower(), text
    row = db.scalars(select(LlmResponseCache).limit(1)).first()
    assert row is not None
    assert row.response_text == llm_voice
    assert "Their listed number is" not in row.response_text


def test_cache_hit_reruns_postprocessor(monkeypatch, isolated_catalog):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Crestline Plumbing",
        age_days=200,
        method="manual",
        phone="(928) 855-3333",
    )
    db.flush()

    llm_voice = "Crestline Plumbing might be a fit."
    fake = _patched_openai(llm_voice)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        t1, *_ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )
        fake.chat.completions.create.side_effect = AssertionError(
            "LLM must not run on cache hit"
        )
        t2, *_ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    assert "recommend calling to confirm" in t1.lower()
    assert "recommend calling to confirm" in t2.lower()
    assert t1.strip() == t2.strip()
