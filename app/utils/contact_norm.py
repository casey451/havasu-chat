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


# Multi-tenant hosts where a shared website domain does NOT imply the same
# business: many distinct businesses legitimately point at one of these (a social
# profile, a link-in-bio page, a review/listing aggregator, a booking
# marketplace, or a free site-builder subdomain). Two providers sharing such a
# host are NOT a duplicate signal -- using it as an identity key would wrongly
# fuse unrelated businesses. Real prod dedup runs surfaced facebook.com on 41
# rows, m.facebook.com on 6, bluepillow.com on 6, etc. Registrable bases only;
# matching is suffix-aware so subdomains (m.facebook.com, foo.wixsite.com,
# maps.google.com) are covered. Brand CHAINS (one corporate domain across many
# locations, e.g. starbucks.com) are intentionally NOT here -- those are the same
# brand and are handled by the dedup audit's geo-spread guard, not by a denylist.
NON_IDENTITY_DOMAINS: frozenset[str] = frozenset(
    {
        # social
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "youtube.com",
        "tiktok.com",
        "pinterest.com",
        # link-in-bio aggregators
        "linktr.ee",
        "linktree.com",
        "beacons.ai",
        # review / listing aggregators (google.com covers sites/maps.google.com)
        "yelp.com",
        "tripadvisor.com",
        "google.com",
        "business.site",
        # booking / ordering marketplaces
        "booking.com",
        "expedia.com",
        "airbnb.com",
        "vrbo.com",
        "bluepillow.com",
        "opentable.com",
        "doordash.com",
        "ubereats.com",
        "grubhub.com",
        # free site builders (any subdomain is a different tenant)
        "wixsite.com",
        "wordpress.com",
        "squarespace.com",
        "weebly.com",
        "godaddysites.com",
        "blogspot.com",
    }
)


def is_identity_domain(domain: str | None) -> bool:
    """True if a shared ``domain`` is a reliable same-business identity signal.

    ``domain`` should already be a bare host (e.g. from :func:`norm_domain`).
    Returns False for empty/None and for any host in (or a subdomain of)
    :data:`NON_IDENTITY_DOMAINS` -- those are multi-tenant hosts where a shared
    domain does not mean the same business. Use this to gate website-based
    matching in the reconciler's contact tier and the cross-source dedup audit.
    """
    if not domain:
        return False
    d = str(domain).strip().lower().strip(".")
    if not d:
        return False
    for shared in NON_IDENTITY_DOMAINS:
        if d == shared or d.endswith("." + shared):
            return False
    return True
