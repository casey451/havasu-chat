"""Phase 2b — the /calendar discovery page + the concierge intent-router.

Covers the deterministic intent parser, the server-rendered /calendar page
(real per-day data, removable "Hava understood" chips, a11y, noindex), and the
FLAG-GATED concierge router: lake routes (discovery → /calendar, else → search)
while desert keeps the conversational fallback unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.categories import cuisine_pages, leaf_query
from app.categories.subcategories import cuisine_query_slug
from app.home.calendar_view import is_discovery_query, parse_calendar_query
from app.main import app

# ── intent parser (pure) ────────────────────────────────────────────────────

def test_parse_extracts_day_time_audience_age() -> None:
    f = parse_calendar_query("things for my 8 year old tuesday and thursday afternoons")
    assert f["aud"] == "kids" and f["age"] == "8" and f["part"] == "afternoon"
    assert "Tue" in f["days"] and "Thu" in f["days"]


def test_parse_type_and_weekend() -> None:
    f = parse_calendar_query("live music this weekend")
    assert f["type"] == "music"
    assert set(f["days"]) == {"Sat", "Sun"}


def test_parse_tonight_is_today_evening() -> None:
    f = parse_calendar_query("what's happening tonight")
    assert f["part"] == "evening" and f["days"] == ["Today"]


def test_is_discovery_query() -> None:
    assert is_discovery_query("what's happening tonight")
    assert is_discovery_query("live music this weekend")
    assert is_discovery_query("kids stuff today")
    assert not is_discovery_query("best sushi spot downtown")
    assert not is_discovery_query("a plumber for a leak")


# ── /calendar page ──────────────────────────────────────────────────────────

def test_calendar_renders_lake_and_noindex() -> None:
    r = TestClient(app).get("/calendar")
    assert r.status_code == 200
    b = r.text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_calendar.css" in b
    assert 'name="robots" content="noindex' in b
    assert "noindex" in (r.headers.get("x-robots-tag") or "")
    assert b.count("<h1") == 1
    assert 'role="search"' in b  # the refine form
    assert 'aria-label="Time of day"' in b  # segmented controls


def test_calendar_understood_chips_from_query() -> None:
    b = TestClient(app).get("/calendar?q=live+music+this+weekend").text
    assert "Hava understood" in b
    assert "Live music" in b  # derived title
    assert "Music" in b  # type chip
    assert "“live music this weekend”" in b  # readback


def test_calendar_structural_a11y() -> None:
    for path in ("/calendar", "/calendar?q=kids+tomorrow", "/calendar?q=live+music+tonight"):
        checker = _A11yChecker()
        checker.feed(TestClient(app).get(path).text)
        issues = checker.finish()
        assert not issues, f"{path}: " + "; ".join(sorted(set(issues)))


def _sample_groups() -> list[dict]:
    return [{
        "key": "events", "label": "Around town", "icon": "", "count": 1, "open": True,
        "rows": [{"time_label": "6:00 PM", "title": "Sunset Paddle", "venue": "Site Six", "url": "/events/1", "recurring": False}],
    }]


def test_calendar_columns_bind_real_rows() -> None:
    with patch("app.home.events_views.day_groups", return_value=_sample_groups()):
        b = TestClient(app).get("/calendar?days=Today").text
    assert 'class="col"' in b
    assert "Sunset Paddle" in b and "Site Six" in b


# ── concierge intent-router (flag-gated) ────────────────────────────────────

class _FakeLeaf:
    department_slug = "home-property-services"
    slug = "plumbers"


def test_chat_lake_routes_nonquestion_discovery_to_calendar() -> None:
    # A non-question discovery ask (no "?", no interrogative, no AI intent
    # phrase) still routes to the /calendar surface. ("things to do this
    # weekend" is discovery via the day/weekend filter but stays keyword-class.)
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get(
            "/chat?q=things to do this weekend&theme=lake", follow_redirects=False
        )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/calendar?q=")


def test_chat_lake_unplaced_query_serves_ai_scaffold() -> None:
    # F13: an unplaced query no longer dead-ends at keyword /search — it renders
    # the AI chat scaffold (chat-new.js fires the turn from ?q on load).
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get(
            "/chat?q=sushi spot downtown&theme=lake", follow_redirects=False
        )
    assert r.status_code == 200
    assert 'id="thread"' in r.text


def test_chat_lake_question_serves_ai_scaffold() -> None:
    # F13: a question-shaped query goes straight to the AI (ahead of leaf /
    # discovery routing), even when a leaf would otherwise match.
    with patch.object(leaf_query, "match_leaf_query", return_value=_FakeLeaf()):
        r = TestClient(app).get(
            "/chat?q=is In-N-Out Burger open right now?&theme=lake", follow_redirects=False
        )
    assert r.status_code == 200
    assert 'id="thread"' in r.text


def test_chat_service_leaf_routes_in_both_themes() -> None:
    with patch.object(leaf_query, "match_leaf_query", return_value=_FakeLeaf()):
        for suffix in ("", "&theme=lake"):
            r = TestClient(app).get(f"/chat?q=plumbers{suffix}", follow_redirects=False)
            assert r.status_code == 302
            assert r.headers["location"] == "/categories/home-property-services/plumbers"


# ── cuisine/dish routing (N1/N2, 2026-07-01) ─────────────────────────────────
# A plain cuisine search ("mexican food", "tacos", "sushi") must land on the
# Eat & Drink listing filtered to that cuisine — NEVER the events calendar. The
# calendar's own discovery matcher fires on bare "food"/"taco", so the fix
# intercepts ahead of the /calendar branch.


class _FakeRestaurantsLeaf:
    department_slug = "eat-drink"
    slug = "restaurants"


def test_cuisine_query_slug_maps_dishes_to_cuisine() -> None:
    # Bare dish/cuisine words and "<cuisine> food/restaurant(s)" phrasings all
    # resolve to their cuisine slug (one leading qualifier tolerated).
    assert cuisine_query_slug("mexican food") == "mexican"
    assert cuisine_query_slug("mexican restaurants") == "mexican"
    assert cuisine_query_slug("tacos") == "mexican"
    assert cuisine_query_slug("good mexican food") == "mexican"
    assert cuisine_query_slug("pizza") == "pizza"
    assert cuisine_query_slug("italian food") == "italian"
    assert cuisine_query_slug("italian restaurant") == "italian"
    assert cuisine_query_slug("chinese food") == "chinese"
    assert cuisine_query_slug("thai food") == "thai"
    assert cuisine_query_slug("sushi") == "japanese"
    assert cuisine_query_slug("bbq") == "bbq"
    assert cuisine_query_slug("seafood") == "seafood"
    assert cuisine_query_slug("steak") == "steakhouse"
    assert cuisine_query_slug("burgers") == "burgers"
    # bare cuisine word (no food tail) still resolves
    assert cuisine_query_slug("mexican") == "mexican"
    assert cuisine_query_slug("italian") == "italian"


def test_cuisine_query_slug_ignores_events_and_non_food() -> None:
    # An event/temporal signal keeps the query on the calendar side; generic
    # "food"/"restaurants" and non-food queries aren't cuisine-shaped.
    assert cuisine_query_slug("taco festival") is None
    assert cuisine_query_slug("food truck night") is None
    assert cuisine_query_slug("cooking class") is None
    assert cuisine_query_slug("mexican food festival") is None
    assert cuisine_query_slug("food") is None
    assert cuisine_query_slug("restaurants") is None
    assert cuisine_query_slug("plumbers") is None


def test_chat_cuisine_routes_to_cuisine_landing_not_calendar() -> None:
    # "mexican food" would otherwise trip is_discovery_query (bare "food") and
    # 302 to /calendar. With a publishable cuisine page it lands there instead.
    assert is_discovery_query("mexican food")  # the trap this fix defuses
    with patch.object(cuisine_pages, "is_publishable_cuisine", return_value=True):
        r = TestClient(app).get("/chat?q=mexican food", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/lake-havasu/mexican"
    assert not r.headers["location"].startswith("/calendar")


def test_chat_cuisine_falls_back_to_restaurants_leaf_when_thin() -> None:
    # Cuisine page too thin to publish → the generic Restaurants leaf, still not
    # the calendar.
    with (
        patch.object(cuisine_pages, "is_publishable_cuisine", return_value=False),
        patch.object(leaf_query, "match_leaf_query", return_value=_FakeRestaurantsLeaf()),
    ):
        r = TestClient(app).get("/chat?q=sushi", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/categories/eat-drink/restaurants"
    assert not r.headers["location"].startswith("/calendar")


def test_chat_genuine_food_event_still_routes_to_calendar() -> None:
    # The guard is narrow: an actual food *event* keeps its calendar route.
    with patch.object(leaf_query, "match_leaf_query", return_value=None):
        r = TestClient(app).get("/chat?q=taco festival", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/calendar?q=")


@pytest.mark.parametrize(
    "query",
    [
        "mexican food",
        "italian food",
        "chinese food",
        "thai food",
        "greek food",
        "tacos",
        "pizza",
        "sushi",
        "burgers",
        "bbq",
        "seafood",
        "steak",
        "mexican",
        "italian",
    ],
)
def test_chat_cuisine_query_never_routes_to_calendar(query: str) -> None:
    # Guardrail (N1/N2): no cuisine/dish search may 302 to the events calendar.
    # With a publishable cuisine page each lands on its /lake-havasu/{cuisine}
    # landing; the assertion that matters is simply "not /calendar".
    with patch.object(cuisine_pages, "is_publishable_cuisine", return_value=True):
        r = TestClient(app).get(f"/chat?q={query}", follow_redirects=False)
    assert r.status_code == 302
    assert not r.headers["location"].startswith("/calendar")
