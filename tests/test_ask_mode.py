"""Phase 3.4 — ask-mode fixture coverage (handoff §3.6): 75 queries via ``POST /api/chat``."""

from __future__ import annotations

import re
import sys
from datetime import UTC, date, datetime, time as time_of_day
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
from app.db.models import Event, Program, Provider
from app.main import app

# --- Voice-rule helpers (handoff §8.2; scope: length, filler, AI self-reference, non-empty) ---

_FILLER_SUBSTRINGS: tuple[str, ...] = (
    "certainly",
    "absolutely",
    "great question",
    "i'd be happy to",
    "let me help you",
    "sure thing",
)

_AI_SELF_REF_SUBSTRINGS: tuple[str, ...] = (
    "as an ai",
    "i'm a chatbot",
    "i don't have access to",
    "language model",
)

# Abbreviations / decimals: avoid counting internal "." as sentence breaks.
_ABBREV_OR_DECIMAL_RE = re.compile(
    r"(?<!\d)(?:[A-Za-z]\.)|(?<=\d)\.(?=\d)|(?<=[ap]m)\.(?=\s|$)",
    re.IGNORECASE,
)


def assert_response_non_empty(response: str) -> None:
    if not (response or "").strip():
        raise AssertionError(f"response is empty or whitespace-only: {response!r}")


def assert_no_filler(response: str) -> None:
    lower = response.lower()
    for needle in _FILLER_SUBSTRINGS:
        if needle in lower:
            raise AssertionError(
                f"response contains filler {needle!r} (handoff §8.2): {response!r}"
            )


def assert_no_ai_self_reference(response: str) -> None:
    lower = response.lower()
    for needle in _AI_SELF_REF_SUBSTRINGS:
        if needle in lower:
            raise AssertionError(
                f"response contains AI self-reference {needle!r} (handoff §8.2): {response!r}"
            )


def assert_response_length_ok(response: str) -> None:
    """Assert 1–3 sentences (§8.2 cap). Uses . ? ! boundaries; skips abbreviations/decimals."""
    assert_response_non_empty(response)
    t = response.strip()
    masked = _ABBREV_OR_DECIMAL_RE.sub(lambda m: m.group(0).replace(".", "\x00"), t)
    parts = re.split(r"(?<=[.!?])\s+", masked)
    parts = [p.replace("\x00", ".").strip() for p in parts if p.strip()]
    if not parts:
        parts = [t]
    n = len(parts)
    if n > 3:
        raise AssertionError(
            f"expected at most 3 sentences, got {n} (handoff §8.2): {response!r}"
        )


def assert_voice_rules(response: str) -> None:
    assert_response_non_empty(response)
    assert_response_length_ok(response)
    assert_no_filler(response)
    assert_no_ai_self_reference(response)


# --- Anthropic mock (same pattern as ``tests/test_api_chat_e2e_ask_mode.py``) ---

_MOCK_TIER3_TEXT = "Lake Havasu has trails, events, and the water. Try Rotary Park or the channel."
_MOCK_TIER3_TOKENS = 32


def _fake_anthropic_module() -> SimpleNamespace:
    fake_usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=10,
        cache_read_input_tokens=6,
        cache_creation_input_tokens=6,
    )
    fake_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=_MOCK_TIER3_TEXT)],
        usage=fake_usage,
    )
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: fake_message))
    return SimpleNamespace(Anthropic=lambda **_kwargs: fake_client)


@pytest.fixture(autouse=True)
def _mock_anthropic_sys_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module())


def _provider(**kwargs: object) -> Provider:
    base: dict[str, object] = {
        "provider_name": "AskDefault",
        "category": "sports",
        "verified": False,
        "draft": False,
        "is_active": True,
        "source": "phase34-test",
    }
    base.update(kwargs)
    return Provider(**base)  # type: ignore[arg-type]


def _program(provider: Provider, **kwargs: object) -> Program:
    base: dict[str, object] = {
        "title": "Default Program",
        "description": "Twenty characters minimum description.",
        "activity_category": "sports",
        "schedule_days": ["Saturday"],
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:00",
        "location_name": "Lake Havasu City",
        "provider_name": provider.provider_name,
        "provider_id": provider.id,
        "source": "phase34-test",
    }
    base.update(kwargs)
    return Program(**base)  # type: ignore[arg-type]


def _event(provider: Provider, **kwargs: object) -> Event:
    base: dict[str, object] = {
        "title": "Default Event",
        "normalized_title": "default event",
        "date": date(2099, 6, 15),
        "start_time": time_of_day(9, 0),
        "end_time": time_of_day(11, 0),
        "location_name": "Lake Havasu City",
        "location_normalized": "lake havasu city",
        "description": "Twenty characters minimum event description.",
        "event_url": "https://example.com/e",
        "status": "live",
        "source": "phase34-test",
        "provider_id": provider.id,
    }
    base.update(kwargs)
    e = Event(**base)  # type: ignore[arg-type]
    if getattr(e, "normalized_title", None) == "default event" and "title" in kwargs:
        t = str(kwargs.get("title", "")).strip()
        e.normalized_title = t.lower()
    return e


@pytest.fixture(scope="module")
def _phase34_seed() -> None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        pa = _provider(
            provider_name="AskAlpha Services",
            phone="928-555-1001",
            address="100 Main St, Lake Havasu City, AZ",
            website="https://askalpha.example",
            hours="Mon–Sun 10:00 AM – 8:00 PM",
        )
        pb = _provider(
            provider_name="AskBeta Services",
            phone="928-555-2002",
            address="200 Side St, Lake Havasu City, AZ",
            website="https://askbeta.example",
            hours="Mon–Sun 10:00 AM – 8:00 PM",
        )
        db.add(pa)
        db.add(pb)
        db.flush()

        db.add(
            _program(
                pa,
                title="Alpha Kickers",
                cost="$15 per session",
                age_min=6,
                age_max=12,
            )
        )
        db.add(
            _program(
                pb,
                title="Beta Swim",
                cost="$20 per session",
                age_min=4,
                age_max=9,
            )
        )
        db.flush()

        db.add(
            _event(
                pa,
                title="Alpha Open Meet",
                normalized_title="alpha open meet",
                date=date(2099, 6, 1),
            )
        )
        db.add(
            _event(
                pb,
                title="Beta Winter Bash",
                normalized_title="beta winter bash",
                date=date(2099, 7, 4),
            )
        )
        db.commit()
        refresh_entity_matcher(db)
        yield
    finally:
        db.query(Event).filter(Event.source == "phase34-test").delete(synchronize_session=False)
        db.query(Program).filter(Program.source == "phase34-test").delete(synchronize_session=False)
        db.query(Provider).filter(Provider.source == "phase34-test").delete(synchronize_session=False)
        db.commit()
        reset_entity_matcher()
        db.close()


pytestmark = pytest.mark.usefixtures("_phase34_seed")

# (query, expected_sub_intent, use_open_now_utc_patch)
TIER1_FIXTURES: list[tuple[str, str, bool]] = [
    # PHONE_LOOKUP ×4
    ("What is the phone number for AskAlpha Services?", "PHONE_LOOKUP", False),
    ("Contact number for AskAlpha Services?", "PHONE_LOOKUP", False),
    ("Call AskBeta Services — what number should I use?", "PHONE_LOOKUP", False),
    ("I need the phone for AskBeta Services.", "PHONE_LOOKUP", False),
    # WEBSITE_LOOKUP ×4
    ("Website for AskAlpha Services?", "WEBSITE_LOOKUP", False),
    ("What is the URL for AskBeta Services?", "WEBSITE_LOOKUP", False),
    ("Web address for AskAlpha Services?", "WEBSITE_LOOKUP", False),
    ("Do you have the site for AskBeta Services?", "WEBSITE_LOOKUP", False),
    # AGE_LOOKUP ×4
    ("What age groups does AskAlpha Services accept?", "AGE_LOOKUP", False),
    ("Age requirements for programs at AskAlpha Services?", "AGE_LOOKUP", False),
    ("How old does my kid need to be at AskBeta Services?", "AGE_LOOKUP", False),
    ("Youngest age for classes at AskBeta Services?", "AGE_LOOKUP", False),
    # COST_LOOKUP ×4
    ("How much does Alpha Kickers cost at AskAlpha Services?", "COST_LOOKUP", False),
    ("What is the pricing for AskAlpha Services programs?", "COST_LOOKUP", False),
    ("Fees for Beta Swim at AskBeta Services?", "COST_LOOKUP", False),
    ("Cost for classes at AskBeta Services?", "COST_LOOKUP", False),
    # TIME_LOOKUP ×4
    ("What time does Alpha Kickers start at AskAlpha Services?", "TIME_LOOKUP", False),
    ("Opening time for Saturday class at AskAlpha Services?", "TIME_LOOKUP", False),
    ("What time is Beta Swim at AskBeta Services?", "TIME_LOOKUP", False),
    ("Start time for lessons at AskBeta Services?", "TIME_LOOKUP", False),
    # HOURS_LOOKUP ×4
    ("What are the hours for AskAlpha Services?", "HOURS_LOOKUP", False),
    ("Business hours AskBeta Services?", "HOURS_LOOKUP", False),
    ("When does AskAlpha Services close — hours?", "HOURS_LOOKUP", False),
    ("Hours for AskBeta Services?", "HOURS_LOOKUP", False),
    # LOCATION_LOOKUP ×4
    ("Where is AskAlpha Services located?", "LOCATION_LOOKUP", False),
    ("Address for AskBeta Services?", "LOCATION_LOOKUP", False),
    ("Location of AskAlpha Services?", "LOCATION_LOOKUP", False),
    ("Where can I find AskBeta Services?", "LOCATION_LOOKUP", False),
    # DATE_LOOKUP ×4
    ("When is Alpha Open Meet at AskAlpha Services?", "DATE_LOOKUP", False),
    ("What dates is the Alpha Open Meet at AskAlpha Services?", "DATE_LOOKUP", False),
    ("When is Beta Winter Bash at AskBeta Services?", "DATE_LOOKUP", False),
    ("Dates for Beta Winter Bash at AskBeta Services?", "DATE_LOOKUP", False),
    # NEXT_OCCURRENCE ×4
    ("When is the next Alpha Open Meet at AskAlpha Services?", "NEXT_OCCURRENCE", False),
    ("When's the next Beta Winter Bash at AskBeta Services?", "NEXT_OCCURRENCE", False),
    ("Next occurrence of Alpha Open Meet at AskAlpha Services?", "NEXT_OCCURRENCE", False),
    ("When's the next class at AskBeta Services?", "NEXT_OCCURRENCE", False),
    # OPEN_NOW ×4 (UTC noon inside 10–8 window)
    ("Is AskAlpha Services open right now?", "OPEN_NOW", True),
    ("Is AskBeta Services open right now?", "OPEN_NOW", True),
    ("Open right now at AskAlpha Services?", "OPEN_NOW", True),
    ("Currently open at AskBeta Services?", "OPEN_NOW", True),
    # 41st — extra PHONE_LOOKUP
    ("What number for AskAlpha Services?", "PHONE_LOOKUP", False),
]

# (query, expected_sub_intent) — Tier 3; sub_intent varies (not only OPEN_ENDED)
TIER3_FIXTURES: list[tuple[str, str | None]] = [
    ("What is fun to do with kids this weekend in Lake Havasu?", "OPEN_ENDED"),
    ("Tell me about lake havasu activities for visitors.", "OPEN_ENDED"),
    ("We are visiting for two days — any ideas?", "OPEN_ENDED"),
    ("Anything happening downtown tonight?", "OPEN_ENDED"),
    ("What should I do Saturday afternoon near the lake?", "OPEN_ENDED"),
    ("Ideas for a family with a toddler this week?", "OPEN_ENDED"),
    ("Suggest a quiet coffee spot downtown?", "OPEN_ENDED"),
    ("Paddleboard spots beginners enjoy around the Bridgewater Channel?", "OPEN_ENDED"),
    ("Any good soccer leagues in Lake Havasu?", "LIST_BY_CATEGORY"),
    ("What karate classes are available for kids?", "LIST_BY_CATEGORY"),
    ("Show me all swim lessons in town.", "LIST_BY_CATEGORY"),
    ("Find gymnastics programs for beginners.", "LIST_BY_CATEGORY"),
    ("What basketball programs exist here?", "LIST_BY_CATEGORY"),
    ("Programs for toddlers in Havasu?", "LIST_BY_CATEGORY"),
    ("List of tennis lessons around town.", "LIST_BY_CATEGORY"),
    ("Any youth baseball leagues I should know about?", "OPEN_ENDED"),
    ("When is the next farmers market date?", "NEXT_OCCURRENCE"),
    ("When's the next fireworks show?", "NEXT_OCCURRENCE"),
    ("Next class at a gym in town?", "NEXT_OCCURRENCE"),
    ("When is the next BMX race?", "NEXT_OCCURRENCE"),
    ("When does little league start?", "DATE_LOOKUP"),
    ("What creative workshops exist this month?", "OPEN_ENDED"),
    ("Any hidden gem beaches along the Parker Strip?", "OPEN_ENDED"),
    ("What time does the class start?", "TIME_LOOKUP"),
    ("Closing time tonight?", "TIME_LOOKUP"),
    ("How much does a trampoline session cost at altitude?", "COST_LOOKUP"),
    ("Fees for the junior ranger program?", "COST_LOOKUP"),
    ("Phone number for a place not in our seed data?", "PHONE_LOOKUP"),
    ("Best spot to watch the sunset from a car?", "OPEN_ENDED"),
    ("Website for Made Up Sports Club?", "WEBSITE_LOOKUP"),
    ("What is there to do after dark on the island?", "OPEN_ENDED"),
    ("What age groups does a fake program accept?", "AGE_LOOKUP"),
    ("Is Made Up Place open right now?", "OPEN_NOW"),
    ("When is the next event at Fake Provider Inc?", "NEXT_OCCURRENCE"),
]


@pytest.mark.parametrize("query,expected_sub,use_open_now_patch", TIER1_FIXTURES)
def test_tier1_fixtures(
    query: str,
    expected_sub: str,
    use_open_now_patch: bool,
) -> None:
    fixed_now = datetime(2026, 4, 19, 18, 0, 0, tzinfo=UTC)

    def _post() -> object:
        with TestClient(app) as client:
            return client.post(
                "/api/chat",
                json={"query": query, "session_id": "phase34-tier1"},
            )

    if use_open_now_patch:
        with patch("app.chat.tier1_handler._utcnow", return_value=fixed_now):
            r = _post()
    else:
        r = _post()

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    assert body["sub_intent"] == expected_sub
    assert body["tier_used"] == "1"
    assert body["llm_tokens_used"] is None
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    resp = body["response"]
    assert_voice_rules(resp)


@pytest.mark.parametrize("query,expected_sub", TIER3_FIXTURES)
def test_tier3_fixtures(query: str, expected_sub: str | None) -> None:
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": query, "session_id": "phase34-tier3"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "ask"
    if expected_sub is not None:
        assert body["sub_intent"] == expected_sub
    assert body["tier_used"] == "3"
    assert body["llm_tokens_used"] == _MOCK_TIER3_TOKENS
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    assert body["response"] == _MOCK_TIER3_TEXT
    assert_voice_rules(body["response"])


def test_fixture_counts_total_75() -> None:
    assert len(TIER1_FIXTURES) == 41
    assert len(TIER3_FIXTURES) == 34
    assert len(TIER1_FIXTURES) + len(TIER3_FIXTURES) == 75
