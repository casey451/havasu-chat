"""Phase 8 (consolidated Amendment) — chat/search UX hardening.

* /api/chat can never return a blank answer (master audit §6.6);
* /search ranking: a NAME match outranks a fresh-verified description/amenity
  match ("pool service" ranked hotels-with-pools beside pool companies, §4.6);
* the leaf page echoes the originating search term (§9.2-4);
* home headline count == the "All today" pill (same variable now, F6 §6.7);
* the F2 advertise funnel carries the chosen product through the claim hop.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.search.ranking import NAME_MATCH_BONUS, Tier2RankInputs, composite_rank_float

# --- never-empty chat responses --------------------------------------------------


def test_api_chat_never_returns_blank_text():
    from app.chat.intent_classifier import IntentResult

    ask = IntentResult(mode="ask", sub_intent="LISTING_INTENT", confidence=0.9,
                       entity=None, raw_query="wake surf charter",
                       normalized_query="wake surf charter")
    with patch("app.chat.intents.runtime.try_intent_layer", return_value=None), \
         patch("app.chat.unified_router.classify", return_value=ask), \
         patch("app.chat.unified_router.try_tier1", return_value=None), \
         patch("app.chat.unified_router.try_tier2_with_usage",
               return_value=(None, None, None, None)), \
         patch("app.chat.unified_router.answer_with_tier3",
               return_value=("", 0, 0, 0)):  # a blank LLM answer
        with TestClient(app) as client:
            r = client.post("/api/chat", json={"query": "wake surf charter",
                                               "session_id": "p8-blank"})
    assert r.status_code == 200
    body = r.json()
    assert body["response"].strip(), body
    assert body["voice"].strip(), body


# --- FTS name-match bonus ---------------------------------------------------------


def test_name_match_outranks_fresh_verified_amenity_match():
    now = datetime.now(UTC)
    # An unverified pool store whose NAME matches...
    store = composite_rank_float(Tier2RankInputs(
        fts_score=10.0, last_verified_at=None, featured=False,
        ref_now=now, name_match=True,
    ))
    # ...must outrank a fresh-verified, featured hotel whose description
    # merely mentions the pool.
    hotel = composite_rank_float(Tier2RankInputs(
        fts_score=4.0, last_verified_at=now - timedelta(days=1), featured=True,
        ref_now=now, name_match=False,
    ))
    assert store > hotel, (store, hotel)
    # Within name-matched rows, freshness still orders.
    fresh_store = composite_rank_float(Tier2RankInputs(
        fts_score=10.0, last_verified_at=now - timedelta(days=1), featured=False,
        ref_now=now, name_match=True,
    ))
    assert fresh_store > store


def test_name_match_bonus_dominates_other_bonuses():
    # 60 > verification (30) + featured (25): field identity orders first.
    assert NAME_MATCH_BONUS > 30.0 + 25.0


# --- leaf search echo -------------------------------------------------------------


def test_leaf_page_echoes_search_term():
    from app.categories import leaf_pages, leaf_query

    class _Leaf:
        slug = "jet-ski-and-watersports"
        name = "Jet Ski & Watersports"
        department_slug = "on-the-water"
        department_name = "On the Water"

    with patch.object(leaf_query, "match_leaf_query", return_value=None), \
         patch.object(leaf_pages, "resolve_leaf", return_value=_Leaf()), \
         patch.object(leaf_pages, "leaf_listing", return_value=([], 5, [])):
        r = TestClient(app).get(
            "/categories/on-the-water/jet-ski-and-watersports?q=wake surfing"
        )
    assert r.status_code == 200
    assert "Showing results for" in r.text
    assert "wake surfing" in r.text


# --- home count unification (F6) --------------------------------------------------


def test_home_headline_drops_the_count():
    # Session 1 declutter (Casey 2026-07-04): the headline "· N going on" count and
    # the "All today" count pill were both removed — the collapsed sections are the
    # scan target now, so feed.total is no longer rendered anywhere in the feed
    # header. (Original F6 intent — headline and pill can't drift — is moot once
    # neither exists.)
    from pathlib import Path

    tpl = (Path(__file__).resolve().parents[1] / "app" / "templates"
           / "home_redesign.html").read_text(encoding="utf-8")
    assert "{{ happenings }}" not in tpl
    assert "{{ feed.total }}" not in tpl  # count removed from headline + pill rail


# --- F2 product carry-through ------------------------------------------------------


def test_advertise_funnel_carries_product_to_claim():
    from app.portal import placements as placement_logic

    class _User:
        id = "u-f2"

    with patch("app.portal.router.get_current_user", return_value=_User()), \
         patch.object(placement_logic, "claimed_providers", return_value=[]):
        with TestClient(app) as client:
            r = client.get(
                "/portal/placements/new?placement_type=homepage_rotating",
                follow_redirects=False,
            )
            assert r.status_code == 303
            loc = r.headers["location"]
            assert "placement_type=homepage_rotating" in loc, loc
            # ...and the claim page names the product + offers a resume link.
            page = client.get(loc)
    assert page.status_code == 200
    assert "You're buying" in page.text or "You&#39;re buying" in page.text
    assert "pick up your placement" in page.text
