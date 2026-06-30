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
# Stoplist of capitalized words that are NOT proper-noun signal on their own.
_NOT_PROPER_NOUN = frozenset(
    {
        "this",
        "that",
        "these",
        "those",
        "the",
        "a",
        "an",
        "try",
        "visit",
        "check",
        "consider",
        "see",
        "find",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "today",
        "tomorrow",
        "yesterday",
        "lake",
        "hotel",
        "restaurant",
        "store",
        "shop",
    }
)

_USEFUL_CONTENT_RE = re.compile(
    r"https?://|"
    r"\bwww\.[\w\-]+\.\w+|"
    r"/contribute\b|"
    r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{1,})+|"  # multi-word proper noun phrase
    r"\b\d{3,}|"
    r"@\w+",
)

# Grounding-scaffold leak: the LLM referring to its retrieval input ("the
# provided rows do not include...", "based on the provided data/context"). The
# dead giveaway is the word "rows" (the SQL result set) or "provided/given
# data/context". High precision — legitimate copy never names the retrieval
# substrate. (QA diagnostic 2026-06-12, P2-1)
_SCAFFOLDING_LEAK_RE = re.compile(
    r"(provided\s+rows?|"
    r"the\s+rows?\s+(?:provided|above|listed|below|do\s+not|don'?t|do\b)|"
    r"rows?\s+(?:provided|given|listed|available)|"
    r"based\s+on\s+the\s+(?:provided\s+)?(?:rows?|data|context)|"
    r"the\s+(?:data|context)\s+provided|"
    r"don'?t\s+have\s+access\s+to\s+(?:the\s+)?(?:rows?|data|context)|"
    r"in\s+the\s+provided\s+(?:rows?|data|context))",
    re.IGNORECASE,
)

# Clean honest-gap fallback when the entire response was a scaffold leak.
_SCAFFOLDING_FALLBACK = (
    "I don't have that detail in the catalog yet. Add it at /contribute or share a link."
)


def _is_sentence_useful(sentence: str) -> bool:
    s = sentence.strip()
    if not s:
        return False
    # Pure punctuation / whitespace remains? Drop.
    if not any(c.isalnum() for c in s):
        return False
    if _USEFUL_CONTENT_RE.search(s):
        return True
    for m in re.finditer(r"\b[A-Z][a-zA-Z]{2,}\b", s):
        if m.group(0).lower() not in _NOT_PROPER_NOUN:
            return True
    return False


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

    sentences = _split_sentences(out)

    # Pass 1.5: drop grounding-scaffold leak sentences ("the provided rows do
    # not include ..."). If that empties the response, the whole thing was a
    # leak -> return a clean honest gap rather than exposing the substrate.
    non_leak = [s for s in sentences if not _SCAFFOLDING_LEAK_RE.search(s)]
    leak_dropped = len(non_leak) != len(sentences)
    if leak_dropped and not non_leak:
        return _SCAFFOLDING_FALLBACK
    sentences = non_leak

    # Pass 2: sentence-level drop for fragments left empty / contentless.
    kept = [s for s in sentences if _is_sentence_useful(s)]
    if not kept:
        # Nothing useful remains. If we dropped a scaffold leak, return the
        # clean gap; otherwise fall back to the phrase-stripped form unchanged.
        return _SCAFFOLDING_FALLBACK if leak_dropped else out
    return _join_sentences(kept)


# ---------------------------------------------------------------------------
# Ungrounded contact-info guard (F1) — the audit caught Tier 3 emitting a
# fabricated phone number ("(775) 848-5418", a Nevada area code) for a business
# that wasn't even in Context. The system prompt bans this, but gpt-4.1-mini
# still confabulates contact details on some queries. This is the deterministic
# backstop: any phone/address in the answer whose value is NOT present in the
# Context block we handed the model gets its whole sentence dropped. Better to
# omit a number than to send a caller a fake one.
#
# Regexes mirror app.chat.halt3_validator (the CI eval-set validator) but are
# duplicated locally to avoid an import cycle (halt3_validator imports
# unified_router, which transitively imports this module).
_CONTACT_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_CONTACT_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w.]*"
    r"(?:\s+[A-Z][\w.]*){0,4}\s+(?:Blvd|Ave|St|Rd|Dr|Ln|Way|Hwy|Pl)\b"
)

_UNGROUNDED_CONTACT_FALLBACK = (
    "I don't have that contact info in the catalog yet — the venue's own site or "
    "/contribute is the move."
)


def _phone_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def redact_ungrounded_contact(text: str, context_text: str | None) -> str:
    """Drop any sentence whose phone/address is not grounded in ``context_text``.

    ``context_text`` is the Context block injected into the Tier-3 user message
    (see ``app.chat.context_builder``); it carries the only facts the model was
    given, on ``phone:`` / ``address:`` lines. A phone is grounded when its
    digits appear in Context; an address is grounded when it is a substring of
    (or contains) a Context address, case-insensitively. Idempotent; returns the
    input unchanged when every contact mention is grounded (the common case).

    When *every* sentence carried an ungrounded contact detail (the whole answer
    was confabulated contact info), returns a clean honest-gap line instead of
    an empty string.
    """
    if not text:
        return text
    ctx = context_text or ""
    grounded_phones = {_phone_digits(m) for m in _CONTACT_PHONE_RE.findall(ctx)}
    grounded_addrs = [a.lower() for a in _CONTACT_ADDRESS_RE.findall(ctx)]

    sentences = _split_sentences(text)
    if not sentences:
        return text

    def _sentence_grounded(s: str) -> bool:
        for ph in _CONTACT_PHONE_RE.findall(s):
            if _phone_digits(ph) not in grounded_phones:
                return False
        for ad in _CONTACT_ADDRESS_RE.findall(s):
            al = ad.lower()
            if not any(al in g or g in al for g in grounded_addrs):
                return False
        return True

    kept = [s for s in sentences if _sentence_grounded(s)]
    if len(kept) == len(sentences):
        return text
    if not kept:
        return _UNGROUNDED_CONTACT_FALLBACK
    return _join_sentences(kept)


def scrub_scaffold_leak(text: str) -> str:
    """Drop only grounding-scaffold-leak sentences from ``text``.

    Lighter than :func:`strip_soft_suggest` — it does NOT do the leading-phrase
    rewrites or the sentence-usefulness filtering tuned for Tier-3 prose. It only
    removes sentences that name the retrieval substrate ("...aren't listed in the
    provided rows"), so it is safe to run on Tier-2 formatter output (LLM voices
    can leak the scaffold there too, e.g. a grocery lookup). If the leak was the
    whole response, returns the clean honest-gap fallback. Idempotent; returns the
    input unchanged when nothing matched.
    """
    if not text:
        return text
    sentences = _split_sentences(text)
    non_leak = [s for s in sentences if not _SCAFFOLDING_LEAK_RE.search(s)]
    if len(non_leak) == len(sentences):
        return text
    if not non_leak:
        return _SCAFFOLDING_FALLBACK
    return _join_sentences(non_leak)
