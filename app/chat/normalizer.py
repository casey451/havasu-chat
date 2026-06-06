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


# ---------------------------------------------------------------------------
# Cache-key canonicalization (2026-06-06). The Tier-2 parser/formatter caches
# and the Tier-3 exact-key cache were keyed on the raw normalized string, so a
# courtesy lead-in or a redundant locality suffix ("... in lake havasu",
# "... near me" — this is a single-town product) made every phrasing a cache
# miss that re-paid the LLM. Strip ONLY tokens that carry no intent in this
# product; anything ambiguous stays in the key (a wrong canonical key serves a
# wrong cached answer, which is worse than a miss).
# ---------------------------------------------------------------------------

_CACHE_LEADIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:hey|hi|ok|okay)[\s,]+hava[\s,!.]+"),
    re.compile(r"^hava[\s,!.]+"),
    re.compile(r"^please[\s,]+"),
    re.compile(r"^(?:can|could|will|would)\s+you\s+(?:please\s+)?tell\s+me[\s,]+"),
)

_CACHE_SUFFIX_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\s,]+in\s+lake\s+havasu(?:\s+city)?$"),
    re.compile(r"[\s,]+in\s+havasu$"),
    re.compile(r"[\s,]+(?:in|around)\s+town$"),
    re.compile(r"[\s,]+around\s+here$"),
    re.compile(r"[\s,]+near\s+me$"),
    re.compile(r"[\s,]+nearby$"),
    re.compile(r"[\s,]+please$"),
    re.compile(r"[\s,]+thanks$"),
    re.compile(r"[\s,]+thank\s+you$"),
)


def canonicalize_for_cache(normalized_query: str) -> str:
    """Fold no-intent lead-ins/suffixes out of a cache key. Lookup-key only —
    never feed this to the LLM or to entity matching (the locality suffix IS
    meaningful to entity queries like "the hangar in lake havasu")."""
    s = (normalized_query or "").strip().lower()
    if not s:
        return s
    changed = True
    while changed:
        changed = False
        for rx in _CACHE_LEADIN_RES:
            new = rx.sub("", s).strip()
            if new and new != s:
                s, changed = new, True
        for rx in _CACHE_SUFFIX_RES:
            new = rx.sub("", s).strip()
            if new and new != s:
                s, changed = new, True
    return re.sub(r"\s+", " ", s)
