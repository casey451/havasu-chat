"""Cross-cutting feature flags read from the environment.

Each flag is a small function that re-reads its env var on every call (never
cached at import), so a config flip — or a test ``monkeypatch.setenv`` — takes
effect without reconstructing the app or its ``Jinja2Templates`` instances (the
same contract ``register_template_globals`` relies on for ``plausible_domain``).

The business side is split into two independently-launchable tiers so the FREE
claim flow can go live before PAID advertising exists:

* ``CLAIM_SURFACES_ENABLED`` (**default on**) — the free tier: the "For Business"
  nav, the homepage "claim your listing" card, provider claim CTAs, and the
  ``/portal`` + ``/portal/claim`` + ``/claim/*`` flow (magic-link sign-in → find
  your listing → claim → human review). No payment anywhere in it.
* ``ADS_ENABLED`` (**default off**) — the paid tier: the ``/sponsor`` +
  ``/advertise`` rate card, category sponsor cards, the ``/portal/placements*`` /
  ``/portal/creatives*`` buy flow, ``/merchant/*`` upgrade requests, the
  loading-overlay micro-ad, and every "Sponsored" / premium-placement upsell.

Nothing is deleted: a tier off = hidden (routes serve a "coming soon" stub),
a tier on = exactly that tier's real behavior. Launch state is claim-on/ads-off;
flipping ``ADS_ENABLED=true`` later restores paid advertising in one step.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}

CLAIM_SURFACES_FLAG = "CLAIM_SURFACES_ENABLED"
ADS_FLAG = "ADS_ENABLED"


def _flag(name: str, *, default: bool) -> bool:
    """Truthy env flag with an explicit default when unset/blank."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def claim_surfaces_enabled() -> bool:
    """Free-tier claim surfaces (default ON). Read fresh on each call."""
    return _flag(CLAIM_SURFACES_FLAG, default=True)


def ads_enabled() -> bool:
    """Paid-tier advertising surfaces (default OFF). Read fresh on each call."""
    return _flag(ADS_FLAG, default=False)
