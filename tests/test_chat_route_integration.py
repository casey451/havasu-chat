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

import os
import unittest
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.core.llm_messages as llm_messages
from app.chat.entity_matcher import reset_entity_matcher
from app.chat.tier2_formatter import FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR
from app.core.event_quality import CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, LlmResponseCache, Provider, Sponsor
from app.main import app
from tests._llm_mocks import patched_openai_client


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


# ─────────────── helpers for LLM-coupled coverage ───────────────


def _insert_provider_full(
    db: Session,
    *,
    provider_name: str,
    category: str = "food_drink",
    phone: str | None = None,
    verification_method: str | None = None,
    age_days: int | None = None,
    is_active: bool = True,
    draft: bool = False,
) -> str:
    """Inline-seed a Google Provider with optional verification metadata.

    Extension of ``_insert_google_provider`` for tests that need the
    confidence-tier or cache-contract attributes (``verification_method``,
    ``last_verified_at``). Mirrors the parent helper's structure plus
    Lane 3 / P2.BL.45 operator-vocab fields. Local to this file rather
    than shared because the verification fields are integration-test-
    specific (the unit tests in ``tests/test_confidence_tier.py`` build
    their own ad-hoc rows).
    """
    last_verified_at = (
        now_lake_havasu() - timedelta(days=age_days)
        if age_days is not None
        else None
    )
    p = Provider(
        provider_name=provider_name,
        category=category,
        source="google_places",
        google_place_id=f"test_place_{provider_name.lower().replace(' ', '_')}",
        phone=phone,
        is_active=is_active,
        draft=draft,
        verified=verification_method is not None,
        verification_method=verification_method,
        last_verified_at=last_verified_at,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class ChatRouteIntegrationLLMCoupledTests(unittest.TestCase):
    """LLM-coupled and Tier 2 chat-route integration coverage at the HTTP boundary.

    Closes the deferred LLM-coupled coverage from BACKLOG #63. The
    LLM-independent paths landed at ``109c7ac`` (see
    ``ChatRouteIntegrationTests`` above); this class lands the LLM-coupled
    deferrals after the project-wide LLM-mock policy was codified at
    ``docs/maintainability/llm_mock_pattern.md`` (#63 part 1). Pattern is
    ``with patch.object(llm_messages, "OpenAI", return_value=...)``;
    helpers are ``tests/_llm_mocks.py``.

    Test inventory (one per deferral area):

    1. ``test_tier2_listing_shortcut_returns_seeded_provider`` -- the
       Tier 2 deterministic listing shortcut at the HTTP boundary.
    2. ``test_tier3_fallthrough_routes_through_llm`` -- Tier 3 fallthrough
       on a query that fails Tier 1 (no factual sub_intent) and the Tier
       2 listing shortcut (no listing prefix).
    3. ``test_cache_contract_raw_text_post_processed_on_hit`` -- BACKLOG
       #49 raw-cache + serve-time post-process contract at the HTTP
       boundary.
    4. ``test_superlative_query_resolves_entity_routes_to_tier3`` --
       BACKLOG #52 alias-resolution + #62-related routing behavior at
       the HTTP boundary.
    5. ``test_operator_vocab_provider_threads_through_to_tier3_context``
       -- BACKLOG #55 confidence-tier integration surface; pins that
       operator-vocab verification methods produce the correct hedge
       fragment in the Tier 3 LLM user_text.

    State management: ``setUp`` and ``tearDown`` clear the
    ``LlmResponseCache`` and ``Sponsor`` tables to prevent cross-test
    pollution (the autouse session DB fixture in ``conftest.py`` runs
    once per session, not per test). ``Provider`` seeds are managed per-
    test via try/finally, mirroring the pattern in
    ``ChatRouteIntegrationTests``.
    """

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(LlmResponseCache).delete()
            db.query(Sponsor).delete()
            db.commit()
        reset_entity_matcher()

    def tearDown(self) -> None:
        with SessionLocal() as db:
            db.query(LlmResponseCache).delete()
            db.query(Sponsor).delete()
            db.commit()
        reset_entity_matcher()

    # ─────────── 1. Tier 2 listing shortcut ───────────

    def test_tier2_listing_shortcut_returns_seeded_provider(self) -> None:
        """Area #1: Tier 2 deterministic listing shortcut renders a seeded provider.

        Brief deviation worth flagging: the dispatch brief described area
        #1 as needing the LLM mock pattern, but
        ``app/chat/tier2_business_shortcut.py`` is a zero-token shortcut
        for "find me a X" / "any good X" listing shapes -- no LLM call.
        The right contract to pin is "the shortcut is reached at the HTTP
        boundary, not bypassed by the matcher floor or recommendation-
        shape check, and renders the seeded provider"; the LLM is patched
        with ``side_effect=AssertionError`` to prove no LLM call was
        made. If a future refactor wires the shortcut through the LLM,
        this test fails loudly -- the zero-token property is load-bearing
        for Tier 2 listing cost (Slice D's design intent).
        """
        canonical = "Mainstream Test Barbershop"
        provider_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id = _insert_provider_full(
                    db,
                    provider_name=canonical,
                    category="barbershop",
                )

            no_llm = patched_openai_client("never reached")
            no_llm.chat.completions.create.side_effect = AssertionError(
                "Tier 2 listing shortcut must not call OpenAI"
            )
            with (
                patch.dict(
                    os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False
                ),
                patch.object(llm_messages, "OpenAI", return_value=no_llm),
                TestClient(app) as client,
            ):
                r = client.post(
                    "/api/chat",
                    json={
                        "query": "find me a barber",
                        "session_id": "integ-tier2-shortcut",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(
                data["tier_used"],
                "2",
                f"Tier 2 listing shortcut expected; got tier_used={data['tier_used']!r}",
            )
            self.assertIn(
                canonical,
                data["response"],
                f"seeded provider name must appear in shortcut response; "
                f"got response={data['response']!r}",
            )
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                        db.commit()
            reset_entity_matcher()

    # ─────────── 2. Tier 3 fallthrough ───────────

    def test_tier3_fallthrough_routes_through_llm(self) -> None:
        """Area #2: Tier 3 fallthrough on a non-factual non-listing query.

        Pin: a query that ``_is_explicit_rec`` matches (here "what should
        I do tonight" matches the ``\\bwhat should i do\\b`` pattern in
        ``app/chat/unified_router.py:_EXPLICIT_REC_PATTERNS``) routes
        directly to Tier 3, the patched LLM is invoked, and the response
        text matches the patched LLM voice. No seeds -- the contract is
        about routing + LLM coupling, not catalog hits.

        The fallback shape from ``app/chat/tier3_handler.py:177`` (when
        ``OPENAI_API_KEY`` is unset) is "Something went sideways..." --
        the test would assert that string instead of the mocked voice if
        the env-var setup were missing, which is exactly the failure mode
        the LLM-mock policy doc warns about.
        """
        llm_voice = "Try the boardwalk after sunset, it's quiet then."
        fake = patched_openai_client(llm_voice)
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False
            ),
            patch.object(llm_messages, "OpenAI", return_value=fake),
            TestClient(app) as client,
        ):
            r = client.post(
                "/api/chat",
                json={
                    "query": "what should I do tonight",
                    "session_id": "integ-tier3-fallthrough",
                },
            )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        _assert_concierge_response_shape(data)
        self.assertEqual(
            data["tier_used"],
            "3",
            f"Tier 3 fallthrough expected for explicit-rec phrasing; "
            f"got tier_used={data['tier_used']!r}",
        )
        self.assertIn(
            llm_voice,
            data["response"],
            f"mocked LLM voice must reach the response body; "
            f"got response={data['response']!r}",
        )
        # Prove the patched LLM was actually called -- if production fell
        # back to the FALLBACK_MESSAGE path due to a missing API key,
        # ``create`` would never run.
        self.assertGreaterEqual(
            fake.chat.completions.create.call_count,
            1,
            "patched OpenAI client must be called at least once on Tier 3 fallthrough",
        )

    # ─────────── 3. #49 cache contract ───────────

    def test_cache_contract_raw_text_post_processed_on_hit(self) -> None:
        """Area #3: BACKLOG #49 -- raw text in cache, post-processed at serve time.

        Mirrors ``tests/test_llm_cache_raw_storage.py`` but lifted to the
        HTTP boundary. Two requests with the same query against a seeded
        LOW-tier Provider with a phone:

        - First POST (cache miss): the LLM is invoked, returns voice
          without the phone or the canonical hedge. The route runs
          ``_enforce_low_tier_phone`` at serve time before returning, so
          the response carries "recommend calling to confirm". The cache
          row stores the *raw* LLM text (without the post-process
          fragment) so a future flag flip or post-processor change
          applies correctly without stale hedge text.
        - Second POST (cache hit): the route reads the raw cached text
          and re-runs ``_enforce_low_tier_phone`` against the current
          rows. The LLM is patched with ``side_effect=AssertionError``
          to prove the cache hit path does not call OpenAI.

        Routing assumption: a query "what's the deal with <name>" with
        the seeded canonical resolves the entity (matcher hit), is not a
        factual Tier 1 sub_intent, is not ``_is_explicit_rec``-shaped (no
        "best" / "what should i do"), is not a Tier 2 listing prefix
        ("what's the" doesn't match the listing prefix patterns), and
        therefore falls through to Tier 3.
        """
        canonical = "Crestline Plumbing Test Fixture"
        provider_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id = _insert_provider_full(
                    db,
                    provider_name=canonical,
                    category="plumbing",
                    phone="(928) 555-0150",
                    verification_method="manual",
                    age_days=200,  # LOW tier (>90 days)
                )

            llm_voice = f"{canonical} might be a fit for what you need."
            fake = patched_openai_client(llm_voice)
            query = f"what's the deal with {canonical.lower()}"
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "test-key",
                        FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR: "true",
                    },
                    clear=False,
                ),
                patch.object(llm_messages, "OpenAI", return_value=fake),
                TestClient(app) as client,
            ):
                # First POST: cache miss path.
                r1 = client.post(
                    "/api/chat",
                    json={"query": query, "session_id": "integ-cache-1"},
                )
                self.assertEqual(r1.status_code, 200)
                data1 = r1.json()
                _assert_concierge_response_shape(data1)
                self.assertEqual(
                    data1["tier_used"],
                    "3",
                    f"Tier 3 fallthrough expected; got tier_used={data1['tier_used']!r}",
                )
                self.assertIn(
                    "recommend calling to confirm",
                    data1["response"].lower(),
                    f"LOW-tier post-processor must inject hedge into miss-path response; "
                    f"got response={data1['response']!r}",
                )

                # Cache row carries the RAW LLM text -- no post-process artifacts.
                with SessionLocal() as db:
                    cache_rows = db.query(LlmResponseCache).all()
                self.assertEqual(
                    len(cache_rows),
                    1,
                    f"exactly one cache row expected after one miss; got {len(cache_rows)}",
                )
                self.assertEqual(
                    cache_rows[0].response_text,
                    llm_voice,
                    "cache must store raw LLM text without post-process fragments",
                )
                self.assertNotIn(
                    "recommend calling to confirm",
                    cache_rows[0].response_text.lower(),
                    "raw cache text must NOT contain the post-processor's hedge fragment",
                )

                # Second POST: cache hit path -- mock raises if reached.
                fake.chat.completions.create.side_effect = AssertionError(
                    "OpenAI must not be called on cache hit"
                )
                r2 = client.post(
                    "/api/chat",
                    json={"query": query, "session_id": "integ-cache-2"},
                )
                self.assertEqual(r2.status_code, 200)
                data2 = r2.json()
                _assert_concierge_response_shape(data2)
                self.assertIn(
                    "recommend calling to confirm",
                    data2["response"].lower(),
                    "LOW-tier post-processor must re-run on cache hit",
                )
                self.assertEqual(
                    data1["response"],
                    data2["response"],
                    "cache hit must produce identical response to miss path",
                )
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                        db.commit()
            reset_entity_matcher()

    # ─────────── 4. #52 superlative routing ───────────

    def test_superlative_query_resolves_entity_routes_to_tier3(self) -> None:
        """Area #4: BACKLOG #52 alias-resolution at the HTTP boundary.

        Brief deviation worth flagging: the dispatch brief expected
        ``tier_used == "1"`` (Tier 1 dispatch on the resolved entity).
        That's wrong -- ``app/chat/unified_router.py:_EXPLICIT_REC_PATTERNS``
        matches ``\\bbest\\b``, so any query containing "best" routes
        directly to Tier 3 via the explicit-rec branch *before* Tier 1
        is consulted. The matcher *does* still resolve the entity (#52's
        ``CANONICAL_EXTRAS`` alias maps "plumber in lake havasu" to
        "All Seasons Plumbing"), so ``response.entity`` is the seeded
        canonical -- but ``tier_used`` is "3", not "1". The test pins
        both behaviors so a future refactor that decouples the matcher
        from the explicit-rec router (e.g. routing best-X queries to
        Tier 1 when entity resolves and Tier 1 has data) is intentional.

        BACKLOG #62 (P3, gated on enrichment) is the forward-looking
        question of whether superlative queries with multiple matching
        catalog rows should route to disambiguation rather than picking
        the alias winner; this test pins current #52 behavior, not the
        eventual #62 resolution.
        """
        canonical = "All Seasons Plumbing"
        provider_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id = _insert_provider_full(
                    db,
                    provider_name=canonical,
                    category="plumbing",
                    phone="(928) 555-0125",
                )

            llm_voice = "All Seasons Plumbing in Lake Havasu has solid reviews."
            fake = patched_openai_client(llm_voice)
            with (
                patch.dict(
                    os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False
                ),
                patch.object(llm_messages, "OpenAI", return_value=fake),
                TestClient(app) as client,
            ):
                r = client.post(
                    "/api/chat",
                    json={
                        "query": "what is the best plumber in lake havasu",
                        "session_id": "integ-52-superlative",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(
                data["entity"],
                canonical,
                f"#52 CANONICAL_EXTRAS alias must resolve entity to {canonical!r}; "
                f"got entity={data['entity']!r}",
            )
            self.assertEqual(
                data["tier_used"],
                "3",
                f"'best'-prefixed query must route to Tier 3 via explicit-rec "
                f"(not Tier 1, despite entity resolution); "
                f"got tier_used={data['tier_used']!r}",
            )
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                        db.commit()
            reset_entity_matcher()

    # ─────────── 5. #55 confidence-tier integration ───────────

    def test_operator_vocab_provider_threads_through_to_tier3_context(
        self,
    ) -> None:
        """Area #5: BACKLOG #55 operator-vocab Provider threads through to Tier 3 LLM context.

        Pin: a Provider seeded with operator-vocab ``verification_method``
        (``phone_call`` here, in the MEDIUM band at age=60 days) renders
        with the canonical hedge fragment ("as of last week", from
        ``app/chat/confidence_tier.hedge_phrase(MEDIUM)``) in the user
        text passed to OpenAI by ``app/chat/context_builder.py``. The
        contract pinned: the chat-route HTTP layer correctly threads
        operator-vocab verification metadata through to the Tier 3 LLM
        prompt context via the ``_hedge_suffix_for`` per-record helper
        (Lane CT2.B).

        Inspection technique mirrors
        ``tests/test_confidence_tier_integration_tier2.py:_user_text``:
        read the patched mock's ``call_args.kwargs["messages"][1]
        ["content"]`` to get the user_text production sent to OpenAI.
        The MEDIUM hedge is parenthetical to the Provider line in the
        Tier 3 context block.

        Routing assumption mirrors area #3's: "thoughts on <name>"
        resolves the entity (matcher hit), is not factual, not
        listing-shaped, not explicit-rec -- falls to Tier 3.
        """
        canonical = "Acme Operator Verified Plumbing"
        provider_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id = _insert_provider_full(
                    db,
                    provider_name=canonical,
                    category="plumbing",
                    phone="(928) 555-0175",
                    verification_method="phone_call",  # operator vocab
                    age_days=60,  # MEDIUM band (≤ 90 days, > 30 days)
                )

            llm_voice = f"{canonical} could be a solid pick."
            fake = patched_openai_client(llm_voice)
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "test-key",
                        FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR: "true",
                    },
                    clear=False,
                ),
                patch.object(llm_messages, "OpenAI", return_value=fake),
                TestClient(app) as client,
            ):
                r = client.post(
                    "/api/chat",
                    json={
                        "query": f"thoughts on {canonical.lower()}",
                        "session_id": "integ-55-operator-vocab",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(
                data["tier_used"],
                "3",
                f"Tier 3 fallthrough expected; got tier_used={data['tier_used']!r}",
            )

            # Inspect the Tier 3 user_text: the MEDIUM hedge fragment
            # must appear parenthetical to the seeded provider's line.
            self.assertGreaterEqual(
                fake.chat.completions.create.call_count,
                1,
                "patched OpenAI client must be called at least once on Tier 3 path",
            )
            call_kwargs = fake.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            self.assertEqual(
                len(messages),
                2,
                f"Tier 3 sends a system+user pair to OpenAI; got {len(messages)} messages",
            )
            user_text = messages[1]["content"]
            self.assertIn(
                canonical,
                user_text,
                f"seeded provider name must appear in Tier 3 user_text; "
                f"got user_text excerpt={user_text[:200]!r}",
            )
            self.assertIn(
                "as of last week",
                user_text,
                f"MEDIUM-band hedge fragment must appear in Tier 3 user_text "
                f"(operator-vocab Provider at 60 days); got user_text "
                f"excerpt={user_text[:300]!r}",
            )
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                        db.commit()
            reset_entity_matcher()


def _insert_google_provider_with_entity(
    db: Session,
    *,
    provider_name: str,
    category: str,
    phone: str | None = None,
) -> tuple[str, str]:
    """Return ``(provider_id, entity_id)`` — Google-shaped Provider + ENTITY core row."""
    from uuid import uuid4

    eid = str(uuid4())
    slug_e = f"ent-{uuid4().hex[:12]}"
    ent = Entity(
        id=eid,
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=slug_e,
        name=provider_name,
        source="google_places",
    )
    db.add(ent)
    p = Provider(
        provider_name=provider_name,
        category=category,
        source="google_places",
        google_place_id=(
            f"test_place_{provider_name.lower().replace(' ', '_')}_{uuid4().hex[:6]}"
        ),
        phone=phone,
        entity_id=eid,
        is_active=True,
        draft=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id, eid


class ChatRoutePhase1CEntityPivotTests(unittest.TestCase):
    """Phase 1C — ENTITY-linked Provider seeds preserve chat-route contracts."""

    def test_tier2_listing_shortcut_entity_linked_provider(self) -> None:
        canonical = "Eastside Entity Barbershop Test"
        provider_id: str | None = None
        entity_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id, entity_id = _insert_google_provider_with_entity(
                    db,
                    provider_name=canonical,
                    category="barbershop",
                )

            no_llm = patched_openai_client("never reached")
            no_llm.chat.completions.create.side_effect = AssertionError(
                "Tier 2 listing shortcut must not call OpenAI"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False),
                patch.object(llm_messages, "OpenAI", return_value=no_llm),
                TestClient(app) as client,
            ):
                r = client.post(
                    "/api/chat",
                    json={
                        "query": "find me a barber",
                        "session_id": "integ-p1c-tier2-entity",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(data["tier_used"], "2")
            self.assertIn(canonical, data["response"])
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                if entity_id is not None:
                    erow = db.get(Entity, entity_id)
                    if erow is not None:
                        db.delete(erow)
                db.commit()
            reset_entity_matcher()

    def test_tier1_phone_lookup_entity_linked_provider(self) -> None:
        canonical = "Entity Linked Plumbing Co Test"
        phone = "(928) 555-0111"
        provider_id: str | None = None
        entity_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id, entity_id = _insert_google_provider_with_entity(
                    db,
                    provider_name=canonical,
                    category="plumbing",
                    phone=phone,
                )

            with TestClient(app) as client:
                r = client.post(
                    "/api/chat",
                    json={
                        "query": f"phone number for {canonical}",
                        "session_id": "integ-p1c-tier1-entity",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(data["entity"], canonical)
            self.assertEqual(data["tier_used"], "1")
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                if entity_id is not None:
                    erow = db.get(Entity, entity_id)
                    if erow is not None:
                        db.delete(erow)
                db.commit()
            reset_entity_matcher()

    def test_tier2_listing_coffee_entity_linked_provider(self) -> None:
        canonical = "Lakefront Entity Coffee Lab Test"
        provider_id: str | None = None
        entity_id: str | None = None
        try:
            with SessionLocal() as db:
                provider_id, entity_id = _insert_google_provider_with_entity(
                    db,
                    provider_name=canonical,
                    category="coffee_shop",
                )

            no_llm = patched_openai_client("never reached")
            no_llm.chat.completions.create.side_effect = AssertionError(
                "Tier 2 listing shortcut must not call OpenAI"
            )
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False),
                patch.object(llm_messages, "OpenAI", return_value=no_llm),
                TestClient(app) as client,
            ):
                r = client.post(
                    "/api/chat",
                    json={
                        "query": "any good coffee shops",
                        "session_id": "integ-p1c-tier2-coffee",
                    },
                )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            _assert_concierge_response_shape(data)
            self.assertEqual(data["tier_used"], "2")
            self.assertIn(canonical, data["response"])
        finally:
            with SessionLocal() as db:
                if provider_id is not None:
                    row = db.get(Provider, provider_id)
                    if row is not None:
                        db.delete(row)
                if entity_id is not None:
                    erow = db.get(Entity, entity_id)
                    if erow is not None:
                        db.delete(erow)
                db.commit()
            reset_entity_matcher()
