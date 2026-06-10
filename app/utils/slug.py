"""Shared slug utilities.

Extracted from the historical ``parks_rec_loader`` ``_slug`` helper when
Provider.slug landed 2026-05-13 (that module now does ``from app.utils.slug
import slugify as _slug``). The slug
shape is intentionally simple: ASCII alphanumerics + hyphens, lowercase,
no leading/trailing hyphens, "untitled" fallback for empty input.

Tests: tests/test_slug_util.py
"""

from __future__ import annotations

import re
import unicodedata


def slugify(value: str | None) -> str:
    """Convert a free-text string to a URL-safe slug.

    Mirrors the historical _slug() helper in parks_rec_loader. Strips
    non-alphanumerics, collapses runs to single hyphens, trims hyphens
    from the ends, lowercases, and falls back to "untitled" for empty
    or non-alphanumeric input.

    Unicode-aware (B1, 2026-06-10): accented letters fold to their ASCII
    base ("Cafés" → "cafes") instead of being dropped and leaving a stray
    hyphen ("caf-s" — the bug that produced the ``caf-s-and-coffee``
    taxonomy slug). Characters with no ASCII decomposition still drop.
    """
    folded = (
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-") or "untitled"


def make_unique_slug(base: str, used: set[str], *, max_length: int = 96) -> str:
    """Return ``base`` truncated to ``max_length`` if not in ``used``,
    otherwise append the lowest integer suffix ``-N`` (N ≥ 2) that yields
    an unused slug. Adds the chosen slug to ``used`` in-place.

    The truncation strips trailing hyphens left by the cut. The suffix
    is appended AFTER truncation; final length can exceed ``max_length``
    by the suffix width (e.g. 96 + len("-12") = 99). Callers that need
    a hard cap should pre-shrink ``max_length`` accordingly.
    """
    base = base[:max_length].rstrip("-") or "untitled"
    if base not in used:
        used.add(base)
        return base
    n = 2
    while True:
        candidate = f"{base}-{n}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1
