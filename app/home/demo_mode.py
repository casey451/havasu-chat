"""HAVA_DEMO_MODE gate -- suppress mock_data fallback in production.

Background: the legacy home router falls back to mock_data when DB rows
are empty (Channel Brewing Co., Aquatic Center, etc.). That content
leaked to real visitors of prod /home whenever the live queries returned
nothing. The Direction C session opener flagged this as the #1 lesson
from the prior session.

Solution: gate mock_data behind an env var, default OFF. Demos,
screenshots, template development can flip it on locally; prod never
sees mocked content unless someone explicitly sets HAVA_DEMO_MODE=1.

Truthy values for ``HAVA_DEMO_MODE`` (case-insensitive): ``1 true yes on``.
Anything else (including unset) reads as off.

Pairs with ``app.home.feature_flags.home_redesign_enabled`` -- same
parsing vocabulary, same posture (env-driven, no query override since
this isn't a per-request concern).
"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def demo_mode_enabled() -> bool:
    """Return True when HAVA_DEMO_MODE env var is truthy.

    Default: False. Mock content stays out of prod render paths unless
    an operator explicitly opts in.
    """
    raw = os.environ.get("HAVA_DEMO_MODE", "")
    return raw.strip().lower() in _TRUTHY
