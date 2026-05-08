"""Tier 3 post-processor — strips soft-suggest customer-service register from
LLM output before the response is returned to the user.

Even with the locked system prompt at ``prompts/system_prompt.txt`` explicitly
banning "you might want to check…" / "I'd suggest…" patterns, ``gpt-4o-mini``
occasionally produces them on synthesis queries — particularly in catalog-gap
shaped responses. This module is a deterministic safety net that runs after
Tier 3's Anthropic-shaped result is extracted but before the assistant text is
returned. Idempotent; cheap; never raises.

Design choices
--------------

- **Strip the leading phrase, preserve the pointer.** "You might want to check
  their site at https://example.com" → "their site at https://example.com".
  The URL or pointer is the user-actionable content; the soft-suggest framing
  is the customer-service register the rubric bans.
- **Whole-sentence drop only when nothing useful remains.** If stripping the
  phrase leaves an empty or near-empty sentence (no URL, no slash command, no
  proper-noun content), drop the whole sentence instead. Keeps the response
  declarative without leaving fragments like ``their website .``
- **Conservative.** Only matches a small, well-known set of soft-suggest
  patterns. Edge cases (sarcasm, quoted user text, etc.) fall through
  unchanged — better to under-rewrite than to mangle voice.
- **Run once per response.** Hooked into ``tier3_handler.answer_with_tier3``
  immediately after the LLM result is extracted. Tier 1 and Tier 2 use
  deterministic renderers; this only applies to Tier 3 LLM output.
"""

from __future__ import annotations

import re


# Each entry: (pattern, replacement). Applied in sequence on the assistant text.
# Order matters — longer/more-specific phrases first so partial matches don't
# steal them. Word-boundary anchors keep replacements scoped.
_LEADING_PHRASE_REWRITES: list[tuple[re.Pattern[str], str]] = [
    # "You might (also )?want to check (out )?(their |the )?(official )?"
    (
        re.compile(
            r"\bYou\s+might\s+(?:also\s+)?want\s+to\s+check\s+(?:out\s+)?(?:their\s+|the\s+)?(?:official\s+)?",
            re.IGNORECASE,
        ),
        "",
    ),
    # "You might (also )?want to try …"
    (
        re.compile(
            r"\bYou\s+might\s+(?:also\s+)?want\s+to\s+try\s+",
            re.IGNORECASE,
        ),
        "Try ",
    ),
    # "You may (also )?want to (consider|check|try) …"
    (
        re.compile(
            r"\bYou\s+may\s+(?:also\s+)?want\s+to\s+(?:consider|check|try)\s+",
            re.IGNORECASE,
        ),
        "",
    ),
    # "You could (also |always )?(check|try|consider) …"
    (
        re.compile(
            r"\bYou\s+could\s+(?:also\s+|always\s+)?(?:check|try|consider)\s+",
            re.IGNORECASE,
        ),
        "",
    ),
    # "I'd suggest checking/trying …"
    (
        re.compile(
            r"\bI'd\s+suggest\s+(?:checking\s+|trying\s+|looking\s+at\s+)?",
            re.IGNORECASE,
        ),
        "",
    ),
    # "I'd recommend checking …" (NOTE: "I'd recommend X" alone is the legitimate
    # Option 3 voice per rubric §4.6 and stays untouched. Only the
    # "checking …" / "looking …" intermediate verbs get stripped — they're the
    # customer-service-register scaffolding around the actual recommendation.)
    (
        re.compile(
            r"\bI'd\s+recommend\s+(?:checking|looking\s+at|reviewing)\s+(?:out\s+)?",
            re.IGNORECASE,
        ),
        "Try ",
    ),
    # "It might be worth checking/trying …"
    (
        re.compile(
            r"\bIt\s+might\s+be\s+worth\s+(?:checking|trying|looking\s+at)\s+",
            re.IGNORECASE,
        ),
        "Try ",
    ),
    # "Please consult …" / "Please refer to …" / "Please reach out to …"
    (
        re.compile(
            r"\bPlease\s+(?:consult|refer\s+to|reach\s+out\s+to|contact)\s+",
            re.IGNORECASE,
        ),
        "",
    ),
    # "Feel free to check/visit/contact …"
    (
        re.compile(
            r"\bFeel\s+free\s+to\s+(?:check|visit|contact|reach\s+out\s+to|browse)\s+",
            re.IGNORECASE,
        ),
        "",
    ),
    # "Don't hesitate to …"
    (
        re.compile(
            r"\bDon't\s+hesitate\s+to\s+(?:check|visit|contact|reach\s+out|ask)\s+",
            re.IGNORECASE,
        ),
        "",
    ),
]


# Sentence drop: when a sentence is left with nothing useful after the leading
# phrase strip, drop it entirely rather than leave the awkward fragment.
# "Useful" content = URL, /contribute, named entity-shape (Capitalized Word), or
# a digit sequence (phone, address). If a sentence has none of those, it's a
# bare suggestion remnant and we drop it.
_USEFUL_CONTENT_RE = re.compile(
    r"https?://|"           # URL
    r"\bwww\.[\w\-]+\.\w+|"  # bare domain
    r"/contribute\b|"        # slash-command pointer
    r"\b[A-Z][a-zA-Z]{2,}|"  # at least one capitalized proper-noun-shaped word
    r"\b\d{3}|"              # phone area code or address number
    r"@\w+",                 # social / email handle
)


def _is_sentence_useful(sentence: str) -> bool:
    s = sentence.strip()
    if not s:
        return False
    # Pure punctuation / whitespace remains? Drop.
    if not any(c.isalnum() for c in s):
        return False
    return bool(_USEFUL_CONTENT_RE.search(s))


def _split_sentences(text: str) -> list[str]:
    # Lightweight sentence splitter — period/exclam/question followed by space
    # and a capital letter, OR a newline. Good enough for short LLM outputs.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text.strip())
    return [p for p in parts if p is not None]


def _join_sentences(sentences: list[str]) -> str:
    cleaned = [s.strip() for s in sentences if s and s.strip()]
    return " ".join(cleaned)


def _normalize_whitespace(text: str) -> str:
    # Collapse runs of internal whitespace and stray spaces before punctuation.
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text


def strip_soft_suggest(text: str) -> str:
    """Apply leading-phrase strips, then drop sentences with no useful content
    remaining. Idempotent. Returns the input unchanged when nothing matched.

    The hook point is :func:`app.chat.tier3_handler.answer_with_tier3` — call
    this on ``result.text`` immediately after extraction, before returning to
    the unified router. Tier 1 and Tier 2 deterministic renderers don't need
    this filter.
    """
    if not text:
        return text
    out = text
    # Pass 1: leading-phrase strips.
    for pattern, replacement in _LEADING_PHRASE_REWRITES:
        out = pattern.sub(replacement, out)
    out = _normalize_whitespace(out)

    # Pass 2: sentence-level drop for fragments left empty / contentless.
    sentences = _split_sentences(out)
    kept = [s for s in sentences if _is_sentence_useful(s)]
    if not kept:
        # Don't strip the whole response to nothing — fall back to the
        # phrase-stripped form even if no sentence passed the useful check.
        return out
    return _join_sentences(kept)
