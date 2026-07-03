"""Regression: the v4 home (``home_redesign.html``) must not leak internal
``KEY:value`` taxonomy tokens into the rendered/indexed page text.

The row template prints ``row.tags`` verbatim, so the namespaced routing tokens
(``activity:billiards``, ``facet:hours``, ``venue-kind:simulator``,
``audience:youth``) were showing up as visible tag chips and in the page source
— an SEO/quality problem. ``redesign._enrich`` now strips them to the friendly
tags (same rule as the event permalink + chat builders), while grouping/tiering
keeps using the raw tags upstream.
"""

from __future__ import annotations

from app.home.redesign import _enrich


def test_enrich_strips_internal_taxonomy_tokens() -> None:
    row = {
        "url": "",
        "title": "Mr. Lucky's Billiards & Pub",
        "tags": [
            "family",
            "activity:billiards",
            "facet:hours",
            "Free",
            "venue-kind:simulator",
            "audience:youth",
        ],
    }
    out = _enrich(row, {}, "things")
    # Friendly tags survive, in original order; every namespaced token is gone.
    assert out["tags"] == ["family", "Free"]
    assert all(":" not in t for t in out["tags"])


def test_enrich_internal_only_tags_become_empty() -> None:
    row = {"url": "", "tags": ["activity:golf", "facet:hours", "indoor:true"]}
    out = _enrich(row, {}, "classes")
    # Empty list → the template's ``{% if row.tags %}`` hides the chip row.
    assert out["tags"] == []


def test_enrich_missing_tags_is_safe() -> None:
    out = _enrich({"url": ""}, {}, "things")
    assert out["tags"] == []
