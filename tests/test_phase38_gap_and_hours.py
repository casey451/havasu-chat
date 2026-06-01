"""Phase 3.8 — HOURS_LOOKUP phrasing variants + catalog-gap template (no Tier 3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chat.unified_router import _GAP_TAIL, route
from app.db.database import SessionLocal
from app.db.models import Provider
from app.main import app


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _disable_llm_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_ROUTER", "false")


@pytest.mark.parametrize(
    "query,expected_sub",
    [
        ("Is altitude open late on friday?", "HOURS_LOOKUP"),
        ("Is sonics open early on monday?", "HOURS_LOOKUP"),
        ("What time does altitude close on friday?", "TIME_LOOKUP"),
    ],
)
def test_hours_and_close_phrasing_sub_intents(query: str, expected_sub: str) -> None:
    from app.chat.intent_classifier import classify

    r = classify(query)
    assert r.mode == "ask"
    assert r.sub_intent == expected_sub


def test_open_late_hits_tier1_when_provider_hours_in_db(db: Session) -> None:
    p = Provider(
        provider_name="Altitude Trampoline Park — Lake Havasu City",
        category="recreation",
        hours="10:00 AM – 8:00 PM daily",
        phone="928-555-0199",
        source="seed",
    )
    db.add(p)
    db.commit()
    r = route("Is altitude open late on friday?", "sess-p38-late", db)
    assert r.mode == "ask"
    assert r.sub_intent == "HOURS_LOOKUP"
    assert r.tier_used == "1"
    assert r.llm_tokens_used is None
    low = r.response.lower()
    assert "altitude" in low or "open" in low or "fri" in low or "am" in low or "pm" in low


@pytest.mark.parametrize(
    ("query", "expected_sub"),
    [
        ("What are the hours for zzznonexistent999xyz?", "HOURS_LOOKUP"),
        ("Where is Totally Fictional Venue XYZ?", "LOCATION_LOOKUP"),
        ("When is the zzznonexistentevent999abc?", "DATE_LOOKUP"),
        # Slice F3: extended to all Tier 1 factual sub_intents
        ("phone number for zzznonexistentbiz999", "PHONE_LOOKUP"),
        ("website for nonexistentplace999xyz", "WEBSITE_LOOKUP"),
        ("rating for some imaginary biz xyz", "RATING_LOOKUP"),
        ("how many reviews does zzzfakeplace999 have", "REVIEW_COUNT_LOOKUP"),
    ],
)
def test_catalog_gap_skips_tier3(query: str, expected_sub: str, db: Session) -> None:
    with patch(
        "app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)
    ) as t2:
        with patch("app.chat.unified_router.answer_with_tier3") as m3:
            r = route(query, f"sess-gap-{expected_sub}", db)
    t2.assert_called_once()
    m3.assert_not_called()
    assert r.mode == "ask"
    assert r.sub_intent == expected_sub
    assert r.tier_used == "gap_template"
    assert r.llm_tokens_used is None
    assert "catalog" in r.response.lower()
    assert r.response.rstrip().endswith(_GAP_TAIL)
    assert "/contribute" in r.response


def test_recommendation_query_skips_gap_template(db: Session) -> None:
    """Slice F3: 'where should I eat tonight' looks like LOCATION_LOOKUP but is a
    recommendation, not a missing-entity lookup. Gap template would mislead — must
    fall through to Tier 2/Tier 3 instead."""
    with patch(
        "app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)
    ):
        with patch(
            "app.chat.unified_router.answer_with_tier3",
            return_value=("Tier 3 reply text", 100, 50, 50),
        ) as m3:
            r = route("where should I eat tonight?", "sess-rec-skip", db)
    m3.assert_called_once()
    assert r.tier_used == "3"
    assert "catalog" not in r.response.lower()


def test_near_match_typo_returns_did_you_mean(db: Session) -> None:
    """Slice F: severe-typo queries hit the near-match band (55–75) and surface a
    'closest match' disambiguation reply instead of the standard gap template."""
    inserted_ids: list[str] = []
    try:
        p = Provider(
            provider_name="Mudshark Brewery and Public House",
            category="food_drink",
            source="google_places",
            google_place_id="test_near_mudshark",
            is_active=True,
            draft=False,
            phone="928-555-0000",
            address="100 Test St",
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        inserted_ids.append(p.id)

        from app.chat.entity_matcher import refresh_entity_matcher

        refresh_entity_matcher(db)

        with patch(
            "app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)
        ):
            with patch("app.chat.unified_router.answer_with_tier3") as m3:
                # "mdshrkbrwry" scores ~65 (NEAR band) — too far to resolve directly,
                # close enough that we can answer using the near match as the entity.
                r = route("phone for mdshrkbrwry", "sess-near-typo", db)
        m3.assert_not_called()
        assert r.tier_used == "gap_template"
        # UX: Tier 1 answer first (which names the entity + has the phone), then a
        # soft escape hatch. No yes/no question.
        assert "Mudshark Brewery and Public House" in r.response
        assert "928-555-0000" in r.response
        assert "/contribute" in r.response
        assert "different place" in r.response.lower()
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        from app.chat.entity_matcher import reset_entity_matcher

        reset_entity_matcher()


def test_strong_tied_ambiguous_entity_picks_alphabetically(db: Session) -> None:
    """Slice F §3.2 (post-revert): the matcher picks the alphabetically-first
    canonical on a tie and Tier 1 fires with that pick. The picked provider may not
    be the one the user intended, but it's deterministic and the alternatives (gap
    template implying nothing exists, or a graceful fallback when Tier 3 is broken)
    are worse UX. A real disambiguation reply is a future slice."""
    inserted_ids: list[str] = []
    try:
        for name in ("Joes Pizza Downtown", "Joes Pizza Channel"):
            p = Provider(
                provider_name=name,
                category="food_drink",
                source="google_places",
                google_place_id=f"test_amb_{name.lower().replace(chr(32), '_')}",
                is_active=True,
                draft=False,
                phone="928-555-0000",
                address="100 Test St",
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            inserted_ids.append(p.id)

        from app.chat.entity_matcher import refresh_entity_matcher

        refresh_entity_matcher(db)

        r = route("phone for joes pizza", "sess-amb-pick", db)
        assert r.tier_used == "1"
        # Alphabetic tiebreak: "Joes Pizza Channel" < "Joes Pizza Downtown"
        assert "Joes Pizza Channel" in r.response
        assert "928-555-0000" in r.response
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        from app.chat.entity_matcher import reset_entity_matcher

        reset_entity_matcher()


def test_listing_shaped_query_skips_gap_template(db: Session) -> None:
    """Slice F3: 'find me a barber' is a Tier 2 listing, not a Tier 1 gap. Even though
    the LOCATION_LOOKUP regex doesn't fire here, defensively confirm any listing-shaped
    query routes to Tier 2 not the gap path."""
    with patch(
        "app.chat.unified_router.try_tier2_with_usage",
        return_value=("A few barbers in Lake Havasu City:\n• Test Barber", 0, 0, 0),
    ) as t2:
        r = route("find me a barber in LHC", "sess-listing-skip", db)
    t2.assert_called_once()
    assert r.tier_used == "2"


def test_q22_fake_hotel_misroutes_to_heat_hotel_on_prod_shape(db: Session) -> None:
    """Reproduces the prod q22 regression: 'rating for Fabricated Hotel Name 555'
    misroutes to Heat Hotel via near-match because near_match_subject_overlaps
    is fail-open for non-'where is X' queries."""
    from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher

    inserted_ids: list[str] = []
    try:
        p = Provider(
            provider_name="Heat Hotel",
            category="lodging",
            source="google_places",
            google_place_id="test_heat_hotel_q22",
            is_active=True,
            draft=False,
            google_rating=4.5,
            google_review_count=406,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        inserted_ids.append(p.id)

        refresh_entity_matcher(db)

        r = route("rating for Fabricated Hotel Name 555", "sess-q22-red", db)

        assert "Heat Hotel" not in r.response, (
            "near_match_subject_overlaps still fail-open — Heat Hotel surfaced "
            "for a clearly-fake query 'Fabricated Hotel Name 555'. "
            f"Response was: {r.response}"
        )
        assert "4.5" not in r.response
        assert r.tier_used == "gap_template"
        assert r.response.rstrip().endswith(_GAP_TAIL)
        assert "/contribute" in r.response
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        reset_entity_matcher()


def test_q03_what_restaurants_open_now_reaches_tier2(db: Session) -> None:
    """Reproduces the prod q03 regression: 'what restaurants are open now'
    hits the gap-template path instead of tier-2 listing when tier-2's LLM
    parser returns None / low-confidence filters."""
    from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher

    inserted_ids: list[str] = []
    try:
        for i, name in enumerate(["Bad Miguel's", "Denny's", "Mario's Italian"]):
            p = Provider(
                provider_name=name,
                category="eat-drink",
                source="google_places",
                google_place_id=f"test_restaurant_q03_{i}",
                is_active=True,
                draft=False,
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            inserted_ids.append(p.id)

        refresh_entity_matcher(db)

        with patch(
            "app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)
        ):
            r = route("what restaurants are open now", "sess-q03-red", db)

        assert "/contribute" not in r.response, (
            "Gap-template fired despite category-open-now listing pattern. "
            "is_category_open_now_listing probe missing or not wired. "
            f"Response was: {r.response}"
        )
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        reset_entity_matcher()


def test_post_api_chat_gap_template_contract() -> None:
    with patch(
        "app.chat.unified_router.try_tier2_with_usage", return_value=(None, None, None, None)
    ) as t2:
        with patch("app.chat.unified_router.answer_with_tier3") as m3:
            with TestClient(app) as client:
                r = client.post(
                    "/api/chat",
                    json={
                        "query": "Where is Totally Fictional Venue XYZ?",
                        "session_id": "p38-gap-http",
                    },
                )
    t2.assert_called_once()
    m3.assert_not_called()
    assert r.status_code == 200
    body = r.json()
    assert body["tier_used"] == "gap_template"
    resp = body.get("response") or ""
    assert resp.rstrip().endswith(_GAP_TAIL)
    assert "/contribute" in resp
    assert body["llm_tokens_used"] is None
    assert body["sub_intent"] == "LOCATION_LOOKUP"
