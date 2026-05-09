"""End-to-end test that ``organic_context`` is wired from the API boundary into
``answer_with_tier3`` (Backlog #40 / Lane X2.1).

The renderer's ``EMERGENCY_URGENT`` regime requires non-empty organic rows
to fire (spec §1.3 — sponsored block must be paired with an organic
alternative). Lane X2 added the kwarg with a ``None`` default; this lane
populates it from ``unified_router._handle_ask`` so live POST /api/chat
traffic with the feature flag on can actually render an emergency-urgent
sponsored block.

Coverage:
- Happy path: emergency-urgent query + sponsor + matching Provider rows
  → response prepends a ``Sponsored:`` block.
- Regression: same flag/sponsor, no organic Provider rows in the catalog
  → ``_eligible`` rejects on the organic-pairing check, response is
  LLM-only (no sponsored leak).
- Helper unit guard: ``_organic_context_for_tier3`` returns ``None`` when
  the flag is off, regardless of intent — so the kwarg is a no-op for
  non-renderer traffic.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.chat.unified_router as unified_router
from app.chat import disclosure_render
from app.chat.intent_classifier import IntentResult
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import LlmResponseCache, Provider, Sponsor, SponsorStatus
from app.main import app

# ─────────── helpers ───────────


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe_state(db: Session):
    """Reset Sponsor + Provider + LLM cache so cross-test state doesn't leak."""
    db.query(Sponsor).delete()
    db.query(Provider).filter(Provider.source == "x21-test").delete(synchronize_session=False)
    db.query(LlmResponseCache).delete()
    db.commit()
    yield
    db.query(Sponsor).delete()
    db.query(Provider).filter(Provider.source == "x21-test").delete(synchronize_session=False)
    db.query(LlmResponseCache).delete()
    db.commit()


def _seed_sponsor(db: Session) -> Sponsor:
    """Sponsor that satisfies every emergency-urgent gate when paired with organic rows."""
    now_lh = now_lake_havasu()
    sp = Sponsor(
        name=f"Youth Center {_suffix()}",
        status=SponsorStatus.LIVE.value,
        active=True,
        attribution_text="community programs",
        headline="Free Saturday open gym for ages 5 to 12.",
        pitch="Drop-in welcome.",
        cta_label="Visit",
        cta_url="https://example.com/youth",
        weight=10,
        starts_at=now_lh - timedelta(days=1),
        ends_at=now_lh + timedelta(days=30),
        verified_fields_present=True,
    )
    db.add(sp)
    db.flush()
    return sp


def _seed_provider(db: Session, *, name: str, category: str = "education") -> Provider:
    p = Provider(
        provider_name=name,
        category=category,
        verified=True,
        draft=False,
        is_active=True,
        source="x21-test",
        description="Activities for kids of various ages.",
    )
    db.add(p)
    db.flush()
    return p


def _fake_openai(text: str):
    """OpenAI Chat Completions mock seam (mirrors ``test_api_chat_e2e_ask_mode``)."""
    fake_message = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=12),
    )
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: fake_message),
        )
    )


def _intent(sub_intent: str = "AGE_LOOKUP") -> IntentResult:
    """Frozen IntentResult for the helper unit test (matches the classifier shape)."""
    return IntentResult(
        mode="ask",
        sub_intent=sub_intent,
        confidence=0.85,
        entity=None,
        raw_query="where can i find activities for ages 5 to 12",
        normalized_query="where can i find activities for ages 5 to 12",
    )


# ─────────── 1. happy path: organic rows present → block prepended ───────────


def test_emergency_urgent_block_prepends_when_organic_providers_seeded(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sponsor + matching organic Provider rows + flag on → ``Sponsored:`` block prepended."""
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    _seed_sponsor(db)
    # Provider whose name contains the keyword "Activities" so the helper's
    # keyword-match query finds at least one organic row.
    _seed_provider(db, name="Kids Activities Studio", category="education")
    db.commit()

    fake_client = _fake_openai("Two free kids activities at the Aquatic Center this weekend.")
    monkeypatch.setattr("app.core.llm_messages.OpenAI", lambda **_kwargs: fake_client)

    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={
                    "query": "where can i find activities for ages 5 to 12",
                    "session_id": f"x21-emergency-happy-{_suffix()}",
                },
            )

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    assert body["sub_intent"] == "AGE_LOOKUP"
    assert body["tier_used"] == "3"
    text = body["response"]
    # Block prepended; "Sponsored: Youth Center" precedes the LLM text.
    assert "Sponsored:" in text
    assert "Youth Center" in text
    assert "community programs" in text
    sponsored_idx = text.find("Sponsored:")
    organic_idx = text.find("Two free kids activities")
    assert sponsored_idx >= 0 and organic_idx >= 0
    assert sponsored_idx < organic_idx, (
        f"sponsored block must precede LLM text for EMERGENCY_URGENT; got: {text!r}"
    )


# ─────────── 2. regression: no organic rows → renderer suppresses ───────────


def test_emergency_urgent_suppressed_when_no_matching_providers(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same flag + sponsor, but no Provider rows match the query keywords →
    ``_organic_context_for_tier3`` returns None → ``_eligible`` fails the
    organic-pairing check → renderer returns None → response is LLM-only.
    """
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    _seed_sponsor(db)
    # Deliberately no Provider rows that match "where can i find activities for ages".
    db.commit()

    fake_client = _fake_openai("No matching kids activities in the catalog.")
    monkeypatch.setattr("app.core.llm_messages.OpenAI", lambda **_kwargs: fake_client)

    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={
                    "query": "where can i find activities for ages 5 to 12",
                    "session_id": f"x21-emergency-suppressed-{_suffix()}",
                },
            )

    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "3"
    text = body["response"]
    assert "Sponsored" not in text, (
        f"renderer must suppress when no organic pairing exists; got: {text!r}"
    )
    assert text == "No matching kids activities in the catalog."


# ─────────── 3. helper guard: flag off → no-op ───────────


def test_helper_returns_none_when_feature_flag_off(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_organic_context_for_tier3`` must short-circuit before any DB work
    when the feature flag is unset, so non-renderer traffic pays no cost.
    """
    monkeypatch.delenv(disclosure_render.FEATURE_FLAG_ENV_VAR, raising=False)
    _seed_sponsor(db)
    _seed_provider(db, name="Kids Activities Studio")
    db.commit()

    result = unified_router._organic_context_for_tier3(_intent("AGE_LOOKUP"), db)
    assert result is None


def test_helper_returns_none_for_non_emergency_regime(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag on, but the regime is GENERIC_CATEGORY (no organic-pairing
    requirement) → helper returns None and the renderer's generic-category
    branch handles the kwarg as a no-op.
    """
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _seed_provider(db, name="Kids Activities Studio")
    db.commit()

    result = unified_router._organic_context_for_tier3(
        _intent("GENERAL_QUESTION"), db
    )
    assert result is None


def test_helper_returns_provider_dicts_when_keywords_match(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _seed_provider(db, name="Kids Activities Studio", category="education")
    _seed_provider(db, name="Wildly Unrelated Auto Shop", category="auto")
    db.commit()

    rows = unified_router._organic_context_for_tier3(_intent("AGE_LOOKUP"), db)
    assert rows is not None
    assert len(rows) >= 1
    names = {r["provider_name"] for r in rows}
    assert "Kids Activities Studio" in names
    # Auto shop has no overlapping keyword (no "activities", "ages", "find",
    # "where" in its name or "auto" category text), so it should not appear.
    assert "Wildly Unrelated Auto Shop" not in names


# ─────────── 4. flag-off integration regression: response unchanged ───────────


def test_flag_off_response_has_no_sponsored_block_even_with_seeded_inventory(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: with the feature flag unset, the X2.1 wiring must not change
    the chat output even when a fully-eligible sponsor + matching providers
    exist in the DB.
    """
    monkeypatch.delenv(disclosure_render.FEATURE_FLAG_ENV_VAR, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _seed_sponsor(db)
    _seed_provider(db, name="Kids Activities Studio")
    db.commit()

    fake_client = _fake_openai("Plain LLM answer.")
    monkeypatch.setattr("app.core.llm_messages.OpenAI", lambda **_kwargs: fake_client)

    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=(None, None, None, None),
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={
                    "query": "where can i find activities for ages 5 to 12",
                    "session_id": f"x21-flag-off-{_suffix()}",
                },
            )

    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "3"
    assert body["response"] == "Plain LLM answer."
    assert "Sponsored" not in body["response"]
