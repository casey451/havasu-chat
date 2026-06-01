"""Integration tests for the Tier 3 LOW-tier phone post-processor (Lane CT2.B.1).

Spec: docs/maintainability/confidence_tier_integration_spec.md section 10 plus
Backlog #42. The post-processor (``_enforce_low_tier_phone``) is the same
deterministic helper Lane CT2.A wired into Tier 2; this lane threads the
row list to the post-LLM site in ``tier3_handler.answer_with_tier3`` via
the sibling helper ``rows_for_tier3_classification``.

Coverage map (one test per Backlog #42 dispatch checklist item):

1. LOW provider, LLM omitted phone -> post-process appends.
2. LOW provider, LLM already mentioned the phone -> no double-append.
3. LOW provider, LLM already hedged -> no double-hedge.
4. HIGH provider, LLM omitted phone -> post-process leaves response alone.
5. Feature flag off -> post-process never runs (asserted via spy).
6. No Provider rows -> post-process is a no-op (rows list empty).
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import Session

import app.chat.tier3_handler as tier3_handler
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
    Offering/Schedule/SourceEvidence) and Entity itself are now also cleared
    per v42 §2 hardening, so Entity rows seeded by prior tests cannot pollute
    matcher lookups in this test.
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
    """Return aware ``last_verified_at`` ``age_days`` days in the past.

    ``Provider.last_verified_at`` is a ``TZAwareDateTime`` column (Lane S1.1
    / Backlog #41a) - writes require aware datetimes; reads come back naive
    Lake-Havasu wall-clock per the column type.
    """
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
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _patched_openai(text):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(text)
    return fake


def test_low_tier_provider_no_phone_in_response_appends_phone(isolated_catalog, monkeypatch):
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

    fake = _patched_openai("Crestline Plumbing might be a fit.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    assert "(928) 855-3333" in text, text
    assert "recommend calling to confirm" in text.lower(), text


def test_low_tier_provider_phone_already_in_response_no_double_append(
    isolated_catalog, monkeypatch
):
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

    fake = _patched_openai("Crestline Plumbing -- (928) 855-3333 is the listed line.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    assert text.count("(928) 855-3333") == 1, text
    assert "Their listed number is" not in text, text


def test_low_tier_provider_already_hedged_no_double_hedge(isolated_catalog, monkeypatch):
    """LLM already includes the canonical hedge fragment but happens to omit
    the phone -- the post-processor's already-hedged guard keeps it from
    bolting on a second hedge sentence.
    """
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

    fake = _patched_openai("Crestline Plumbing might fit -- recommend calling to confirm hours.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    assert text.lower().count("recommend calling to confirm") == 1, text
    assert "Their listed number is" not in text, text


def test_high_tier_provider_no_phone_appended(isolated_catalog, monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Acme Plumbing",
        age_days=1,
        method="owner_confirmed",
        phone="(928) 855-1111",
    )
    db.flush()

    fake = _patched_openai("Acme Plumbing is a solid pick.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3("i need a plumber", _intent(entity="Acme Plumbing"), db)

    assert "(928) 855-1111" not in text, text
    assert "Their listed number is" not in text, text
    assert "recommend calling to confirm" not in text.lower(), text


def test_flag_off_post_process_skipped(isolated_catalog, monkeypatch):
    """Flag unset: ``_enforce_low_tier_phone`` must never be invoked."""
    monkeypatch.delenv(_FLAG, raising=False)
    db = isolated_catalog
    _add_provider(
        db,
        name="Crestline Plumbing",
        age_days=200,
        method="manual",
        phone="(928) 855-3333",
    )
    db.flush()

    spy = MagicMock(
        side_effect=AssertionError("_enforce_low_tier_phone must not run when feature flag is off")
    )
    monkeypatch.setattr(tier3_handler, "_enforce_low_tier_phone", spy)

    fake = _patched_openai("Crestline Plumbing might be a fit.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "i need a plumber", _intent(entity="Crestline Plumbing"), db
        )

    spy.assert_not_called()
    assert text == "Crestline Plumbing might be a fit."


def test_no_providers_in_query_post_process_no_op(isolated_catalog, monkeypatch):
    """Empty Provider table -> ``rows_for_tier3_classification`` returns []
    and the post-processor's loop never enters its body.
    """
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog

    fake = _patched_openai("No catalog rows match.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3("anything", _intent(), db)

    assert text == "No catalog rows match."
    assert "Their listed number is" not in text
