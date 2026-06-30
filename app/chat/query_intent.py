"""Deterministic search-vs-AI intent classifier (F13).

Decides whether a free-text query should be answered by the AI concierge
(questions / natural language / "open now"-style asks) or by plain keyword
search (short noun lookups like "pizza", "boat rental"). No ML — a small,
testable rule table.

Conservative by design: a query is only ``ai`` when it clearly reads as a
question or carries an intent phrase. Everything else stays ``keyword`` so the
working keyword lookups (pizza, coffee, plumber, yoga, boat rental) are
untouched.
"""

from __future__ import annotations

import re

INTENT_AI = "ai"
INTENT_KEYWORD = "keyword"

# First-token interrogatives / auxiliary verbs that signal a question even
# without a "?" ("is in-n-out open", "where can I get tacos").
_INTERROGATIVES: frozenset[str] = frozenset(
    {
        "is", "are", "am", "was", "were",
        "do", "does", "did", "can", "could", "should", "would", "will",
        "where", "what", "who", "when", "why", "how", "which",
    }
)

# Intent phrases anywhere in the query (matched on word boundaries so "best"
# doesn't fire on "bestseller" and "open now" only fires as a phrase).
_INTENT_PHRASES: tuple[str, ...] = (
    "open now", "right now", "tonight", "near me", "open late",
    "best", "cheapest", "recommend", "something to do",
)
_PHRASE_RES = tuple(re.compile(rf"\b{re.escape(p)}\b") for p in _INTENT_PHRASES)

_FIRST_WORD_RE = re.compile(r"[a-z]+")


def classify_query_intent(q: str | None) -> str:
    """Return :data:`INTENT_AI` or :data:`INTENT_KEYWORD` for a query.

    ``ai`` when the query contains a "?", starts with an interrogative/aux verb,
    or contains an intent phrase; otherwise ``keyword`` (the default — empty or
    whitespace also classifies ``keyword`` so callers never route a blank query
    to the AI)."""
    s = (q or "").strip().lower()
    if not s:
        return INTENT_KEYWORD
    if "?" in s:
        return INTENT_AI
    first = _FIRST_WORD_RE.search(s)
    if first is not None and first.group(0) in _INTERROGATIVES:
        return INTENT_AI
    if any(r.search(s) for r in _PHRASE_RES):
        return INTENT_AI
    return INTENT_KEYWORD
