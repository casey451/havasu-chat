"""slowapi limiter shared across FastAPI routes (Phase B).

``RATE_LIMIT_DISABLED``: when set to a truthy value (``1``, ``true``, ``yes``,
``on``; case-insensitive), the limiter skips checks for the whole process.
Pytest sets this via ``tests/conftest.py`` so suites are not coupled to
``limiter.reset()`` between tests.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

RATE_LIMIT_MESSAGE = "Slow down a sec! Try again in a minute 😅"


def is_rate_limit_disabled() -> bool:
    v = (os.environ.get("RATE_LIMIT_DISABLED") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def client_ip_key(request) -> str:
    """Rate-limit key = the real client IP.

    Behind Railway's edge proxy, ``request.client.host`` (what
    ``get_remote_address`` returns) is the *proxy's* IP, so every user shares one
    120/min bucket. Railway sets ``X-Forwarded-For`` at the edge and its leftmost
    entry is the real client IP (Railway controls the header and appends, so a
    client-spoofed value is pushed rightward) — safe to key on for rate limiting
    on Railway. Falls back to the peer address when the header is absent (local
    dev / non-proxied). (P1-10)

    Ref: Railway help — "Which header should I rely on for real client IP?"
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip_key, enabled=not is_rate_limit_disabled())
