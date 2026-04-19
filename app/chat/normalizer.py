"""Normalize user queries before intent classification and entity matching."""

from __future__ import annotations

import re
import string

# Apply after lowercasing. Apostrophe forms first, then apostrophe-less variants.
_CONTRACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwhat's\b"), "what is"),
    (re.compile(r"\bwhen's\b"), "when is"),
    (re.compile(r"\bwhere's\b"), "where is"),
    (re.compile(r"\bwho's\b"), "who is"),
    (re.compile(r"\bhow's\b"), "how is"),
    (re.compile(r"\bit's\b"), "it is"),
    (re.compile(r"\bthat's\b"), "that is"),
    (re.compile(r"\bthere's\b"), "there is"),
    (re.compile(r"\bi'm\b"), "i am"),
    (re.compile(r"\bwhats\b"), "what is"),
    (re.compile(r"\bwhens\b"), "when is"),
    (re.compile(r"\bwheres\b"), "where is"),
    (re.compile(r"\bwhos\b"), "who is"),
)

_EDGE_CHARS = frozenset(string.punctuation + string.whitespace)


def _strip_edge_punct_ws(text: str) -> str:
    if not text:
        return text
    lo, hi = 0, len(text)
    while lo < hi and text[lo] in _EDGE_CHARS:
        lo += 1
    while hi > lo and text[hi - 1] in _EDGE_CHARS:
        hi -= 1
    return text[lo:hi]


def normalize(query: str) -> str:
    """Return a normalized query string for routing.

    - Lowercase
    - Strip leading/trailing whitespace and punctuation
    - Expand common informal contractions (``whens`` → ``when is``, etc.)
    - Collapse internal runs of whitespace to a single space
    - Preserve internal hyphens and apostrophes (e.g. ``o'clock``, ``co-op``)
    """
    if not query:
        return ""
    s = query.strip().lower()
    for pattern, repl in _CONTRACTIONS:
        s = pattern.sub(repl, s)
    s = _strip_edge_punct_ws(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
