"""Durable ingest suppression: do-not-import identities + placeholder addresses.

Some scraped listings must stay OUT of the catalog even though the upstream
source keeps re-publishing them. A one-off ``is_active = False`` doesn't hold —
the next partner/places re-scrape matches the row and reactivates it (see
``golakehavasu_partners_load`` line ~499, ``canonical.is_active = True``). This
module is the version-controlled blocklist the loaders check FIRST, so a
suppressed identity is skipped on every future run.

It also centralizes the recurring "placeholder address" problem: the CVB feed
lists dozens of operators at the visitor center's own address ("Go Lake Havasu
Visitor Center, 422 English Village…"). That is not a real business location, so
it should be stored as NULL rather than a shared fake pin — WITHOUT suppressing
the (often legitimate) businesses themselves.
"""

from __future__ import annotations

import re

from app.contrib.ingest_reconciler import slugify

# Business identities to skip on every ingest, keyed by ``slugify(name)`` so a
# re-scrape can neither insert a fresh row nor reactivate a deactivated one.
# Deactivating the existing rows is a separate (gated) data op; this keeps the
# deactivation from being undone. Add a slug here to durably retire a listing.
SUPPRESSED_BUSINESS_SLUGS: frozenset[str] = frozenset(
    {
        # ("Wake Surf Adventures" was suppressed here 2026-07-01 as dormant;
        # UNSUPPRESSED 2026-07-01 PM per Casey [ASK #7] — the business is active
        # (4.7★ Birdeye, live site/Facebook). The reinstate ships as a gated
        # data op that re-attributes the existing row before re-scrapes match.)
        # 2026-07-01 Phase 3 (consolidated audit 3.3): non-businesses the 06-30
        # deactivation could not hold down — the partner re-scrape reactivated
        # the Marine Association safety PROGRAM row within a day (re-verified
        # active on 07-01). Suppress durably; the deactivations ride the gated
        # apply script.
        slugify("Lake Havasu Marine Association Designated Operator Program"),
        slugify("Outdoor Enthusiasts"),
    }
)


def is_suppressed_business(name: str | None) -> bool:
    """True when a scraped listing's name is on the durable do-not-import list."""
    return slugify(name or "") in SUPPRESSED_BUSINESS_SLUGS


# The CVB visitor-center address, used as a shared placeholder for operators with
# no storefront. Matched loosely (normalized substring) so punctuation/spacing
# variants still register.
_PLACEHOLDER_ADDRESS_NEEDLES: tuple[str, ...] = (
    "go lake havasu visitor center",
    "422 english village",
)
_WS_RE = re.compile(r"\s+")


def is_placeholder_address(address: str | None) -> bool:
    """True when ``address`` is the shared visitor-center placeholder, not a real
    business location."""
    norm = _WS_RE.sub(" ", (address or "").strip().lower())
    if not norm:
        return False
    return any(needle in norm for needle in _PLACEHOLDER_ADDRESS_NEEDLES)


def clean_placeholder_address(address: str | None) -> str | None:
    """Return ``None`` for a placeholder address, else the address unchanged —
    so ingest stores a real location or nothing, never a shared fake pin."""
    return None if is_placeholder_address(address) else address
