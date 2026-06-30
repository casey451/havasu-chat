"""F13 — the search-vs-AI intent classifier (deterministic rule table)."""

from __future__ import annotations

import pytest

from app.chat.query_intent import INTENT_AI, INTENT_KEYWORD, classify_query_intent

_CASES = [
    # Short noun lookups stay keyword (must not regress working searches).
    ("pizza", INTENT_KEYWORD),
    ("boat rental", INTENT_KEYWORD),
    ("coffee", INTENT_KEYWORD),
    ("plumber", INTENT_KEYWORD),
    ("yoga", INTENT_KEYWORD),
    ("lake havasu tacos", INTENT_KEYWORD),
    ("In-N-Out", INTENT_KEYWORD),  # first token "in" is not interrogative
    ("swimming and splash pads", INTENT_KEYWORD),
    # Questions / natural language / intent phrases -> AI.
    ("is In-N-Out Burger open right now", INTENT_AI),  # "is" + "open"/"right now"
    ("is X open?", INTENT_AI),  # the "?"
    ("where can I get tacos tonight", INTENT_AI),  # "where" + "tonight"
    ("open now near me", INTENT_AI),  # two intent phrases
    ("what's a good plumber for a slab leak", INTENT_AI),  # "what"
    ("best sushi spot downtown", INTENT_AI),  # "best"
    ("cheapest gas", INTENT_AI),
    ("recommend a date night spot", INTENT_AI),
    # Empty / whitespace never routes to the AI.
    ("", INTENT_KEYWORD),
    ("   ", INTENT_KEYWORD),
    (None, INTENT_KEYWORD),
]


@pytest.mark.parametrize("query,expected", _CASES)
def test_classify_query_intent(query: str | None, expected: str) -> None:
    assert classify_query_intent(query) == expected


def test_best_is_word_boundary_not_substring() -> None:
    # "best" fires as a word, not inside "bestseller".
    assert classify_query_intent("bestseller books") == INTENT_KEYWORD
    assert classify_query_intent("best brewery") == INTENT_AI
