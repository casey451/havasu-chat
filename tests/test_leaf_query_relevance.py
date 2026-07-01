"""Query-aware relevance on leaf pages (2026-07-01 search fix, item 1).

A niche search ("wake surfing") 302s to a broad leaf and used to render in
dampened-rating order, burying newer on-topic shops. The originating ?q= now
floats query-relevant providers to the top; a generic query is a no-op.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.categories import leaf_query
from app.categories.leaf_pages import (
    _float_query_matches,
    _provider_matches_terms,
    _relevance_terms,
)
from app.main import app


def _p(pid: str, name: str, *, subcategory: str = "", category: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=pid, provider_name=name, subcategory=subcategory, category=category)


def test_relevance_terms_drops_stop_and_locality() -> None:
    assert _relevance_terms("wake surfing") == ["wake", "surfing"]
    # locality + generic bucket words fall out; "jet"/"ski" survive
    assert _relevance_terms("jet ski rentals in lake havasu") == ["jet", "ski"]
    assert _relevance_terms("") == []
    assert _relevance_terms(None) == []


def test_provider_matches_terms_stems_and_substrings() -> None:
    wakesurf = _p("1", "Lake Havasu Wakesurf Co.", subcategory="watersports")
    jetski = _p("2", "Lake Havasu Jet Ski Rentals", subcategory="watersports")
    # "wake" is a substring of "wakesurf"; "surfing" shares the "surf" stem.
    assert _provider_matches_terms(wakesurf, ["wake"])
    assert _provider_matches_terms(wakesurf, ["surfing"])
    assert not _provider_matches_terms(jetski, ["wake", "surfing"])
    assert _provider_matches_terms(jetski, ["jet", "ski"])


def test_float_query_matches_floats_relevant_first() -> None:
    rows = [
        _p("a", "Lake Havasu Jet Ski Rentals"),
        _p("b", "Waterbuzz Fly Boarding"),
        _p("c", "Lake Havasu Wakesurf Co."),
        _p("d", "Wakesurf Havasu"),
    ]
    out = _float_query_matches(rows, "wake surfing", set())
    assert [p.id for p in out[:2]] == ["c", "d"]  # wakesurf shops floated
    assert {p.id for p in out} == {"a", "b", "c", "d"}  # no rows lost


def test_float_query_matches_keeps_paid_pins_first() -> None:
    rows = [_p("pin", "Sponsored Jetski"), _p("c", "Wakesurf Havasu"), _p("x", "Boat Tours")]
    out = _float_query_matches(rows, "wakesurf", {"pin"})
    assert out[0].id == "pin"  # paid pin stays on top
    assert out[1].id == "c"  # then the relevant match


def test_float_query_matches_noop_without_query_or_match() -> None:
    rows = [_p("a", "Jet Ski Rentals"), _p("b", "Boat Tours")]
    assert _float_query_matches(rows, None, set()) == rows
    assert _float_query_matches(rows, "wakesurf", set()) == rows  # nothing matches


def test_chat_leaf_redirect_carries_query() -> None:
    # A leaf-matching search carries ?q= so the leaf can float on-topic results.
    class _Leaf:
        department_slug = "on-the-water"
        slug = "jet-ski-and-watersports"

    with patch.object(leaf_query, "match_leaf_query", return_value=_Leaf()):
        r = TestClient(app).get("/chat?q=wake surfing", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("/categories/on-the-water/jet-ski-and-watersports?q=")
    assert "wake" in loc
