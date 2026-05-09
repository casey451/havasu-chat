"""Integration tests for the disclosure renderer wired into Tier 3 (Lane X2).

Spec: ``docs/maintainability/disclosure_renderer_spec.md`` §5.2 / §7.2.

These tests exercise the live ``answer_with_tier3`` call path with the
disclosure renderer enabled via the ``FEATURE_FLAG_DISCLOSURE_RENDERER``
env var. The OpenAI client is mocked the same way as ``test_tier3_handler``
(patch ``app.core.llm_messages.OpenAI``); the renderer's own unit tests
live in ``tests/test_disclosure_render.py`` and stay isolated.

Coverage map (one test per dispatch checklist item):
- flag default off → renderer never invoked, response unchanged.
- flag on, GENERIC_CATEGORY query, sponsor in DB → block injected after
  the LLM's first sentence.
- flag on, EMERGENCY_URGENT query, sponsor + organic rows → block prepended.
- flag on, SPECIFIC_QUALITY query → renderer returns None, response unchanged.
- flag on, sponsor with tone violation → renderer returns None, response unchanged.
- flag on, no eligible sponsors → response unchanged.
- renderer raises → WARN logged, response is LLM-only (no crash).
- disclosure word "Sponsored" appears verbatim in injected text.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.chat.tier3_handler as tier3_handler
import app.core.llm_messages as llm_messages
from app.chat import disclosure_render
from app.chat.intent_classifier import IntentResult
from app.chat.tier3_handler import answer_with_tier3
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.models import LlmResponseCache, Sponsor, SponsorStatus

# ─────────── helpers ───────────


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
    """Reset sponsors and the LLM response cache so cached text from a prior
    test doesn't bleed into this one (the handler stores cleaned LLM text
    keyed off the normalized query)."""
    db.query(Sponsor).delete()
    db.query(LlmResponseCache).delete()
    db.commit()
    yield
    db.query(Sponsor).delete()
    db.query(LlmResponseCache).delete()
    db.commit()


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _intent(
    *,
    sub_intent: str = "GENERAL_QUESTION",
    entity: str | None = None,
) -> IntentResult:
    """Real ``IntentResult`` with all required fields."""
    return IntentResult(
        mode="ask",
        sub_intent=sub_intent,
        confidence=0.7,
        entity=entity,
        raw_query="i need a plumber",
        normalized_query="i need a plumber",
    )


def _resp(text: str, *, prompt_tokens: int = 10, completion_tokens: int = 5) -> SimpleNamespace:
    """OpenAI Chat Completions response shape (mirrors ``test_tier3_handler``)."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_sponsor(
    db: Session,
    *,
    name: str | None = None,
    status: str = SponsorStatus.LIVE.value,
    active: bool = True,
    headline: str | None = "Hand-roasted espresso, open 7 AM to 6 PM.",
    pitch: str | None = "Sourced from regional roasters.",
    attribution_text: str | None = "local coffee roaster",
    cta_label: str = "Visit",
    cta_url: str = "https://example.com",
    weight: int = 0,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    verified_fields_present: bool = False,
) -> Sponsor:
    sp = Sponsor(
        name=name or f"Sponsor {_suffix()}",
        status=status,
        active=active,
        headline=headline,
        pitch=pitch,
        attribution_text=attribution_text,
        cta_label=cta_label,
        cta_url=cta_url,
        weight=weight,
        starts_at=starts_at,
        ends_at=ends_at,
        verified_fields_present=verified_fields_present,
    )
    db.add(sp)
    db.flush()
    return sp


def _patched_openai(text: str):
    """Context-manager pair that puts ``OPENAI_API_KEY`` and a mocked OpenAI client."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _resp(text)
    return fake_client


# ─────────── 1. feature flag default off ───────────


def test_feature_flag_default_off_no_renderer_invoked(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag unset → no renderer call; response is the LLM text unchanged."""
    monkeypatch.delenv(disclosure_render.FEATURE_FLAG_ENV_VAR, raising=False)
    # If the renderer were invoked, this sponsor would qualify; assert it isn't.
    _make_sponsor(db, name="Brew Haven")
    db.commit()

    spy = MagicMock(side_effect=AssertionError("renderer must not run when flag is off"))
    monkeypatch.setattr(
        tier3_handler, "_maybe_render_sponsored_block", spy
    )

    fake = _patched_openai("Plumbers in Havasu are easy enough to find.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3("i need a plumber", _intent(), db)

    assert "Sponsored" not in text
    assert text == "Plumbers in Havasu are easy enough to find."
    spy.assert_not_called()


# ─────────── 2. generic-category injection ───────────


def test_generic_category_injects_block_after_first_sentence(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _make_sponsor(
        db,
        name="Brew Haven",
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM to 6 PM.",
        pitch="Sourced from regional roasters.",
    )
    db.commit()

    fake = _patched_openai("Hava Cafe is a solid choice. The Daily Grind is also nearby.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "where can i grab coffee", _intent(sub_intent="GENERAL_QUESTION"), db
        )

    # Block injected after first sentence.
    assert text.startswith("Hava Cafe is a solid choice.")
    assert "Sponsored: Brew Haven — local coffee roaster" in text
    assert "Hand-roasted espresso" in text
    # Tail of the LLM text is preserved verbatim.
    assert "The Daily Grind is also nearby." in text


# ─────────── 3. emergency-urgent prepended ───────────


def test_emergency_urgent_prepends_block_when_organic_context_supplied(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    # Bind aware datetimes (TZAwareDateTime); ORM loads naive Lake Havasu wall
    # clock — handler/query_context stay aligned with ``now_lake_havasu()`` stripping.
    now_lh = now_lake_havasu()
    _make_sponsor(
        db,
        name="Youth Center",
        attribution_text="community programs",
        headline="Free Saturday open gym for ages 5 to 12.",
        pitch="Drop-in welcome.",
        verified_fields_present=True,
        starts_at=now_lh - timedelta(days=1),
        ends_at=now_lh + timedelta(days=30),
    )
    db.commit()

    fake = _patched_openai("Two free kids activities this weekend at the Aquatic Center.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "free kids activities this weekend",
            _intent(sub_intent="COST_LOOKUP"),
            db,
            organic_context=[{"title": "Aquatic Center open swim"}],
        )

    # Block precedes the LLM text.
    assert text.startswith("Sponsored: Youth Center — community programs")
    # LLM text follows after a paragraph break.
    assert "Two free kids activities this weekend" in text
    sponsored_idx = text.find("Sponsored:")
    organic_idx = text.find("Two free kids activities")
    assert sponsored_idx < organic_idx


# ─────────── 4. specific-quality regime suppresses ───────────


def test_specific_quality_regime_does_not_inject(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _make_sponsor(db, name="Brew Haven")  # eligible but should be ignored
    db.commit()

    fake = _patched_openai("Barley Brothers is open 11 AM to 10 PM.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "what are barley brothers hours",
            _intent(sub_intent="HOURS_LOOKUP", entity="Barley Brothers"),
            db,
        )

    assert "Sponsored" not in text
    assert text == "Barley Brothers is open 11 AM to 10 PM."


# ─────────── 5. tone violation suppresses ───────────


def test_tone_violation_sponsor_does_not_inject(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _make_sponsor(
        db,
        name="Best Coffee Ever",
        attribution_text="award-winning cafe",
        headline="Best coffee in Lake Havasu!",
        pitch="A perfect spot every time.",
    )
    db.commit()

    fake = _patched_openai("Hava Cafe is a solid choice.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "where can i grab coffee", _intent(sub_intent="GENERAL_QUESTION"), db
        )

    assert "Sponsored" not in text
    assert text == "Hava Cafe is a solid choice."


# ─────────── 6. no eligible sponsors ───────────


def test_no_eligible_sponsors_response_unchanged(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty sponsors table → renderer returns None, response is plain LLM."""
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    # No sponsors inserted.

    fake = _patched_openai("Hava Cafe is a solid choice.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "where can i grab coffee", _intent(sub_intent="GENERAL_QUESTION"), db
        )

    assert "Sponsored" not in text
    assert text == "Hava Cafe is a solid choice."


# ─────────── 7. renderer raises → WARN + LLM-only ───────────


def test_renderer_exception_logs_warn_and_falls_through(
    db: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _make_sponsor(db, name="Brew Haven")
    db.commit()

    def _boom(*_a, **_k):
        raise RuntimeError("synthetic renderer failure")

    # Patch the X1 entry point the integration helper calls; the helper
    # catches the exception and logs WARN.
    monkeypatch.setattr(disclosure_render, "render_sponsored_block", _boom)

    fake = _patched_openai("Hava Cafe is a solid choice.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with caplog.at_level(logging.WARNING, logger=""):
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            text, _, _, _ = answer_with_tier3(
                "where can i grab coffee",
                _intent(sub_intent="GENERAL_QUESTION"),
                db,
            )

    assert text == "Hava Cafe is a solid choice."
    assert "Sponsored" not in text
    assert any(
        "disclosure renderer raised" in r.message.lower()
        or "synthetic renderer failure" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]


# ─────────── 8. disclosure word verbatim ───────────


def test_disclosure_word_verbatim_in_injected_text(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The literal "Sponsored" from ``DISCLOSURE_WORD`` appears in chat output."""
    monkeypatch.setenv(disclosure_render.FEATURE_FLAG_ENV_VAR, "true")
    _make_sponsor(
        db,
        name="Brew Haven",
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM to 6 PM.",
    )
    db.commit()

    fake = _patched_openai("Hava Cafe is a solid choice.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _, _ = answer_with_tier3(
            "where can i grab coffee", _intent(sub_intent="GENERAL_QUESTION"), db
        )

    assert disclosure_render.DISCLOSURE_WORD == "Sponsored"
    assert "Sponsored" in text  # verbatim, not "Featured" / "Partner" / etc.
    # Confirm we didn't drift to a synonym.
    for drift in ("Featured:", "Partner:", "Recommended:", "Spotlight:"):
        assert drift not in text, drift
