"""Shared contact-field normalizers for cross-source matching/dedup.

ONE home for the website-domain and phone normalizers that the dedup audit, the
ingest reconciler's contact tier, and the merge primitive all need, so matching
behaves identically everywhere (Item D of CROSS_SOURCE_DEDUP_SESSION.md).

IMPORTANT semantic note -- two different "website normalizers" exist on purpose:

  * :func:`norm_domain` here reduces a URL to its BARE HOST (path/query stripped):
    ``https://joes.com/menu`` -> ``joes.com``. Use this for DEDUP/identity
    matching, where two pages on one site mean the same business.

  * ``scripts.golakehavasu_partners_load._norm_web`` keeps the FULL PATH
    (scheme/www/trailing-slash-insensitive only): ``joes.com/menu`` stays
    ``joes.com/menu``. The CVB loader's idempotency key relies on that exact
    behavior, so it is deliberately NOT replaced by this module.

:func:`norm_phone` (last-10-digit) is identical everywhere and is the canonical
implementation; callers should import it from here.
"""

from __future__ import annotations


def norm_domain(url: str | None) -> str | None:
    """Reduce a website URL to a bare host (scheme/www/path/query/port stripped).

    For DEDUP/identity matching only -- see the module docstring for why this is
    distinct from the CVB loader's path-preserving ``_norm_web``.
    """
    if not url:
        return None
    s = str(url).strip().lower()
    for pre in ("https://", "http://"):
        if s.startswith(pre):
            s = s[len(pre) :]
    if s.startswith("www."):
        s = s[4:]
    for sep in ("/", "?", "#"):
        idx = s.find(sep)
        if idx != -1:
            s = s[:idx]
    if ":" in s:
        s = s.split(":", 1)[0]
    return s.strip().strip(".") or None


def norm_phone(phone: str | None) -> str | None:
    """Last 10 digits (a leading US country code stripped); None if fewer than 10.

    So ``(702) 787-9568`` and ``+1 702-787-9568`` compare equal. Returns None
    when fewer than 10 digits remain (too little to be a confident identity key).
    """
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else None
