"""Cross-cutting feature flags read from the environment.

Each flag is a small function that re-reads its env var on every call (never
cached at import), so a test can ``monkeypatch.setenv`` and see the change
without reconstructing the app or its ``Jinja2Templates`` instances — the same
contract ``register_template_globals`` relies on for ``plausible_domain``.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}

# The single env var gating every advertiser / business-owner surface (see
# BUSINESS_SURFACES_ENABLED usages: header/footer "For Business" links, the
# homepage claim/advertise marquee, category sponsor cards, provider claim CTAs,
# and the /portal, /sponsor, /advertise, /claim, /merchant routes). Default OFF
# so the consumer site can go live before the business side is finished; flag ON
# restores exactly today's behavior — nothing is deleted, only hidden.
BUSINESS_SURFACES_FLAG = "BUSINESS_SURFACES_ENABLED"


def business_surfaces_enabled() -> bool:
    """True when the business/advertiser surfaces should render.

    OFF (default) hides every owner-facing CTA and serves a "coming soon" page
    on the business routes; ON reproduces today's full behavior. Read fresh on
    each call so a config flip (or a test monkeypatch) takes effect immediately.
    """
    return (os.getenv(BUSINESS_SURFACES_FLAG) or "").strip().lower() in _TRUE
