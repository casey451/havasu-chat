"""Chat-route integration test suite — closes the systematic gap from the
Phase 2 first-week test coverage audit.

Audit reference: ``docs/maintainability/phase2_midweek_coverage_audit.md``
"Cross-ticket observations" §1 — *"All three lanes ship unit-level coverage
but nothing exercises the full HTTP path POST /api/chat → unified_router →
matcher/classifier → response."*

**Scope (this file): the LLM-independent HTTP-boundary paths only.**

- ``test_min_length_floor_returns_null_match_via_route`` — #50 floor regression
  at the route boundary (smoke-catalog Class C2 case).
- ``test_empty_query_returns_422_validation_error`` — Pydantic ``min_length=1``
  + custom request-validation handler emit the concierge-specific friendly
  message.
- ``test_tier1_happy_path_returns_seeded_provider`` — full pipeline
  (normalize → classify → entity-match → tier-dispatch → response.entity).

**Deferred to BACKLOG #63** (LLM-coupled coverage; needs project-wide LLM-mock
policy first — see audit "Recommended follow-ups" §2): Tier 2 listing path,
Tier 3 fallthrough, #49 cache contract (raw text storage), #52 superlative-
routing behavior, #55 confidence-tier integration surface in the HTTP
response. ``app/core/llm_messages.py:118-120`` returns ``None`` when
``OPENAI_API_KEY`` is unset (the test env), so without an LLM mock those
paths assert the *fallback* shape — pinning the wrong contract. The
``test_disclosure_render_integration.py`` file uses ``@patch("app.core.
llm_messages.OpenAI")`` for function-level integration; whether to apply that
to HTTP-route tests is a project-wide decision deferred to #63.

Test infrastructure mirrors:

- ``tests/test_chat_route_audience_forwarding.py`` — TestClient + ``/api/chat``.
- ``tests/test_chat_route_utf8.py`` — response-shape helper + frozenset of
  expected keys.
- ``tests/test_entity_matcher.py::_insert_google_provider`` — inline
  Google-Provider seeding (operator-confirmed pattern; see #58/#60 audit
  follow-ups).
"""

from __future__ import annotations

import unittest
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chat.entity_matcher import reset_entity_matcher
from app.core.event_quality import CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


def _insert_google_provider(
    db: Session,
    *,
    provider_name: str,
    phone: str | None = None,
    is_active: bool = True,
    draft: bool = False,
) -> str:
    """Inline-seed a Google-sourced Provider row.

    Mirrors ``tests/test_entity_matcher.py::_insert_google_provider`` plus an
    optional ``phone`` field — needed so Tier-1 PHONE_LOOKUP (``app/chat/
    tier1_handler.py:110``) finds concrete data and returns a "1" route
    instead of falling through to Tier 2. Kept local to this file rather
    than extending the entity-matcher test helper, since it's a route-test-
    specific need.
    """
    p = Provider(
        provider_name=provider_name,
        category="food_drink",
        source="google_places",
        google_place_id=f"test_place_{provider_name.lower().replace(' ', '_')}",
        phone=phone,
        is_active=is_active,
        draft=draft,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


# Mirrors ``tests/test_chat_route_utf8.py::_EXPECTED_RESPONSE_KEYS`` — pinning
# the ConciergeChatResponse JSON shape here too so a future schema field add /
# remove is loud across both files.
_EXPECTED_RESPONSE_KEYS = frozenset(
    {
        "response",
        "voice",
        "component",
        "mode",
        "sub_intent",
        "entity",
        "tier_used",
        "latency_ms",
        "llm_tokens_used",
        "chat_log_id",
    }
)


def _assert_concierge_response_shape(data: dict[str, Any]) -> None:
    """Response matches :class:`ConciergeChatResponse` JSON shape."""
    assert set(data.keys()) == _EXPECTED_RESPONSE_KEYS, (
        f"unexpected response keys diff: {set(data.keys()) ^ _EXPECTED_RESPONSE_KEYS}"
    )
    assert isinstance(data["latency_ms"], int)
    assert isinstance(data["component"], dict)
    assert "type" in data["component"]


class ChatRouteIntegrationTests(unittest.TestCase):
    """LLM-independent end-to-end coverage for ``POST /api/chat``."""

    def test_min_length_floor_returns_null_match_via_route(self) -> None:
        """#50 floor regression at the HTTP boundary.

        Single-char query passes Pydantic ``min_length=1`` but the matcher's
        ``_MIN_QUERY_LENGTH=3`` floor blocks entity resolution. Smoke catalog
        Class C2 (2026-05-08) flagged that without the floor, ``"a"`` matched
        short canonical prefixes ("A & A Electronics Assembly", …) and produced
        wrong-entity Tier-1 answers. Pins the absence of that regression at the
        route boundary — not just at the matcher layer where the unit tests
        in ``tests/test_entity_matcher.py::MinimumQueryLengthFloor*`` live.
        """
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={"query": "a", "session_id": "integ-50-floor"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        _assert_concierge_response_shape(data)
        self.assertIsNone(
            data["entity"],
            f"matcher floor must produce null entity for sub-floor query; got {data['entity']!r}",
        )
        self.assertIsNotNone(data["chat_log_id"])

    def test_empty_query_returns_422_validation_error(self) -> None:
        """Pydantic schema validation rejects empty query at the request layer.

        ``ConciergeChatRequest.query: str = Field(min_length=1)`` (see
        ``app/schemas/chat.py``). The custom request-validation handler at
        ``app/main.py:384`` routes the violation through
        ``app.core.event_quality.friendly_errors`` which special-cases the
        concierge ``query`` field via ``_errors_touch_concierge_query_field``.
        Pins both the validation contract AND the operator-friendly response
        shape so a future schema relaxation OR copy-edit is intentional.
        """
        with TestClient(app) as client:
            r = client.post(
                "/api/chat",
                json={"query": "", "session_id": "integ-empty"},
            )
        self.assertEqual(r.status_code, 422)
        # Lock the exact response body. Imported constant keeps the test in
        # lock-step with the source string — a copy-edit moves both together.
        self.assertEqual(
            r.json(),
            {"message": CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE},
        )

    def test_tier1_happy_path_returns_seeded_provider(self) -> None:
        """End-to-end Tier-1-routed entity resolution with concrete fact data.

        Seeds a Google Provider with a distinctive canonical AND a phone
        number, posts a Tier-1-shaped factual query (``"phone number for
        <name>"``), and asserts the route's full pipeline succeeds at Tier 1:

        - normalize → ``"phone number for acme plumbing test fixture"``
        - classify → ``sub_intent=PHONE_LOOKUP``
        - ``_enrich_entity_from_db`` → ``entity="Acme Plumbing Test Fixture"``
          (via ``match_entity`` against the freshly-refreshed index)
        - tier-1 dispatch → ``try_tier1`` reads ``provider.phone`` and renders
          a fact-shaped reply (``app/chat/tier1_handler.py:110``)
        - ConciergeChatResponse.entity == seeded canonical, tier_used == "1"

        Why ``"1"`` is asserted strictly (not ``{"1", "gap_template"}``):
        the gap-template path at ``unified_router.py:137`` short-circuits
        when ``intent_result.entity`` is non-empty, so once the matcher
        resolves the seeded provider, ``"gap_template"`` is structurally
        unreachable on this path. The only failure modes are ``"1"`` (Tier-1
        succeeded) or ``"2"`` (Tier-1 returned None, fell through to Tier-2
        LLM path). Pinning ``"1"`` makes a regression in either direction
        loud — including a future seed-helper change that drops the phone
        field and silently downgrades to Tier 2 fallback.

        The contract being pinned is *entity resolution + Tier-1 dispatch at
        the HTTP boundary*; matcher-only behavior is unit-tested in
        ``tests/test_entity_matcher.py``, and Tier-1 PHONE_LOOKUP rendering
        is unit-tested in ``tests/test_tier1_handler.py``.
        """
        canonical = "Acme Plumbing Test Fixture"
        # 555-0100 — North American "fictional" phone range (never assigned to
        # real subscribers; safe for tests).
        phone = "(928) 555-0100"
        provider_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id = _insert_google_provider(
                    db, provider_name=canonical, phone=phone
                )

            with TestClient(app) as client:
                r = client.post(
                    "/api/chat",
                    json={
                        "query": f"phone number for {canonical}",
                        "session_id": "integ-tier1-happy",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(
                data["entity"],
                canonical,
                f"matcher must resolve seeded canonical; got entity={data['entity']!r}",
            )
            self.assertEqual(
                data["tier_used"],
                "1",
                f"expected Tier-1 dispatch; got tier_used={data['tier_used']!r}",
            )
            self.assertIsNotNone(data["chat_log_id"])
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                        db.commit()
            # Bust the matcher's module-level ``_rows`` cache so this test's
            # seeded canonical doesn't bleed into a later test that builds
            # the index against pre-test DB state.
            reset_entity_matcher()
