"""Meta-description sanitation (P1.8).

Provider ``about`` text and event blurbs are free-form: they contain
newlines, repeated whitespace, and run past what SERPs display. Raw
newlines inside ``<meta name="description" content="...">`` are legal but
read as churned markup in snippets; mid-sentence chops read as broken.

``meta_description`` is registered as the shared Jinja filter
``meta_desc`` (see ``app.core.provider_name.register_template_filters``)
and applied wherever a dynamic string feeds a description/og:description
tag. Static hand-written descriptions don't need it but tolerate it —
the function is idempotent on clean input.
"""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")

#: Don't sentence-truncate to a stub — if the last sentence boundary inside
#: the budget leaves less than this many characters, fall back to a word cut.
_MIN_SENTENCE_LEN = 60


def meta_description(value: object, max_len: int = 160) -> str:
    """Collapse whitespace and truncate at a sentence boundary.

    - All whitespace runs (including newlines) collapse to single spaces.
    - Text within ``max_len`` is returned as-is (after collapsing).
    - Longer text is cut at the last sentence end inside the budget when
      that keeps at least ``_MIN_SENTENCE_LEN`` characters; otherwise at
      the last word boundary with a single ellipsis character appended.
    """
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    if len(text) <= max_len:
        return text

    window = text[:max_len]
    last_end = None
    for match in _SENTENCE_END_RE.finditer(window):
        last_end = match.end()
    if last_end is not None and last_end >= _MIN_SENTENCE_LEN:
        return window[:last_end]

    # Word-boundary fallback. Reserve one char for the ellipsis.
    cut = window[: max_len - 1]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"
