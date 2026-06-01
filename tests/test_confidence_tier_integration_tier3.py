"""Integration tests for the confidence-tier classifier wired into Tier 3 (Lane CT2.B).

Spec: ``docs/maintainability/confidence_tier_integration_spec.md`` section 3 / section 6.2.

These tests exercise ``build_context_for_tier3`` directly with provider /
event ORM rows whose ``last_verified_at`` and ``verification_method``
attributes drive the confidence-tier classifier.

Note on aware datetimes: ``Provider.last_verified_at`` / ``Event.last_verified_at``
use ``TZAwareDateTime`` (Backlog #41a); fixtures pass timezone-aware values.
SQLite still stores without tz metadata; the ORM normalizes on read.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import Session

from app.chat import tier2_formatter as tf
from app.chat.context_builder import (
    _hedge_suffix_for,
    build_context_for_tier3,
)
from app.chat.intent_classifier import IntentResult
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import (
    ContactPoint,
    Entity,
    EntityCategory,
    Event,
    Hours,
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
        s.close()


@pytest.fixture
def isolated_catalog(db: Session) -> Session:
    """Empty catalog for this test only; rolled back so the shared test DB stays clean.

    Clears the legacy top-level tables (Provider/Event/Program) AND the Entity
    subtree (Entity + its FK-child rows in EntityCategory, Location, Hours,
    ContactPoint, Offering, Schedule, SourceEvidence). Hardening per v42 §2.
    """
    nested = db.begin_nested()
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


def _intent(*, entity: str | None = None) -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.8,
        entity=entity,
        raw_query="q",
        normalized_query="q",
    )


def _aware_age(age_days: int):
    return now_lake_havasu() - timedelta(days=age_days)


def _add_provider(
    db: Session,
    *,
    name: str,
    age_days: int | None = None,
    method: str | None = None,
    phone: str | None = None,
    include_verification: bool = True,
) -> Provider:
    last_verified_at = None
    if include_verification and age_days is not None:
        last_verified_at = _aware_age(age_days)
    p = Provider(
        provider_name=name,
        category="services",
        phone=phone,
        verified=True,
        draft=False,
        is_active=True,
        last_verified_at=last_verified_at,
        verification_method=method if include_verification else None,
    )
    db.add(p)
    db.flush()
    return p


def test_hedge_suffix_high_returns_empty(monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    record = SimpleNamespace(
        last_verified_at=now_lake_havasu() - timedelta(days=1),
        verification_method="owner_confirmed",
    )
    assert _hedge_suffix_for(record, now=now_lake_havasu()) == ""


def test_hedge_suffix_medium_returns_as_of_last_week(monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    record = SimpleNamespace(
        last_verified_at=now_lake_havasu() - timedelta(days=14),
        verification_method="scraper",
    )
    assert _hedge_suffix_for(record, now=now_lake_havasu()) == " (as of last week)"


def test_hedge_suffix_low_returns_recommend_calling(monkeypatch):
    monkeypatch.setenv(_FLAG, "true")
    record = SimpleNamespace(
        last_verified_at=now_lake_havasu() - timedelta(days=200),
        verification_method="manual",
    )
    assert _hedge_suffix_for(record, now=now_lake_havasu()) == " (recommend calling to confirm)"


def test_flag_off_byte_identical_context_block(monkeypatch, isolated_catalog: Session):
    monkeypatch.delenv(_FLAG, raising=False)
    db = isolated_catalog
    _add_provider(
        db,
        name="Acme Plumbing",
        age_days=200,
        method="manual",
        phone="(928) 855-1111",
    )
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert "(recommend calling to confirm)" not in ctx
    assert "(as of last week)" not in ctx
    assert "Provider: Acme Plumbing\n" in ctx or ctx.endswith("Provider: Acme Plumbing")


def test_flag_on_high_tier_no_hedge_suffix(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Acme Plumbing",
        age_days=1,
        method="owner_confirmed",
        phone="(928) 855-1111",
    )
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert "Provider: Acme Plumbing" in ctx
    assert "(recommend calling to confirm)" not in ctx
    assert "(as of last week)" not in ctx


def test_flag_on_medium_tier_hedge_suffix_inlined(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Bayview Plumbing",
        age_days=14,
        method="scraper",
        phone="(928) 855-2222",
    )
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert "Provider: Bayview Plumbing (as of last week)" in ctx
    assert "(recommend calling to confirm)" not in ctx


def test_flag_on_low_tier_hedge_suffix_inlined(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Crestline Plumbing",
        age_days=200,
        method="manual",
        phone="(928) 855-3333",
    )
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert "Provider: Crestline Plumbing (recommend calling to confirm)" in ctx


def test_flag_on_mixed_tier_rows_each_carries_own_hedge(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db, name="Acme Plumbing", age_days=1, method="owner_confirmed", phone="(928) 855-1111"
    )
    _add_provider(
        db, name="Bayview Plumbing", age_days=14, method="scraper", phone="(928) 855-2222"
    )
    _add_provider(
        db, name="Crestline Plumbing", age_days=200, method="manual", phone="(928) 855-3333"
    )
    ctx = build_context_for_tier3("anything", _intent(), db)

    assert "Provider: Acme Plumbing\n" in ctx
    assert "Provider: Bayview Plumbing (as of last week)" in ctx
    assert "Provider: Crestline Plumbing (recommend calling to confirm)" in ctx

    acme_segment = ctx.split("Provider: Acme")[1].split("Provider:")[0]
    assert "as of last week" not in acme_segment
    assert "recommend calling to confirm" not in acme_segment

    bay_segment = ctx.split("Provider: Bayview")[1].split("Provider:")[0]
    assert "recommend calling to confirm" not in bay_segment


def test_legacy_row_classifies_low(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    _add_provider(
        db,
        name="Old School Plumbing",
        include_verification=False,
        phone="(928) 555-0001",
    )
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert "Provider: Old School Plumbing (recommend calling to confirm)" in ctx


def test_event_row_low_tier_carries_hedge_suffix(monkeypatch, isolated_catalog: Session):
    monkeypatch.setenv(_FLAG, "true")
    db = isolated_catalog
    p = _add_provider(
        db,
        name="Event Host",
        age_days=1,
        method="owner_confirmed",
        phone="(928) 555-9000",
    )
    today = date.today()
    db.add(
        Event(
            title="Stale Festival",
            normalized_title="stale festival",
            date=today + timedelta(days=10),
            start_time=time(18, 0),
            location_name="Park",
            location_normalized="park",
            description="Twenty chars minimum ev.",
            provider_id=p.id,
            status="live",
            last_verified_at=_aware_age(200),
        )
    )
    db.flush()
    ctx = build_context_for_tier3("events?", _intent(), db)
    assert "Stale Festival" in ctx
    assert "(recommend calling to confirm)" in ctx
    event_line = next(
        (line for line in ctx.splitlines() if "Stale Festival" in line),
        "",
    )
    assert event_line.endswith("(recommend calling to confirm)")


def test_system_prompt_contains_hedge_instruction():
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.txt"
    body = prompt_path.read_text(encoding="utf-8")
    assert "Confidence hedges in Context lines" in body
    assert "(as of last week)" in body
    assert "(recommend calling to confirm)" in body
    assert "verbatim" in body
    assert "never paraphrase" in body or "do not paraphrase" in body
