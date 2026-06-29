"""slowapi limiter shared across FastAPI routes (Phase B).

``RATE_LIMIT_DISABLED``: when set to a truthy value (``1``, ``true``, ``yes``,
``on``; case-insensitive), the limiter skips checks for the whole process.
Pytest sets this via ``tests/conftest.py`` so suites are not coupled to
``limiter.reset()`` between tests.
"""

import ipaddress
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

RATE_LIMIT_MESSAGE = "Slow down a sec! Try again in a minute 😅"


def is_rate_limit_disabled() -> bool:
    v = (os.environ.get("RATE_LIMIT_DISABLED") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


# ── public-surface limits (A2: anti-scrape) ─────────────────────────────────
# slowapi accepts a zero-arg callable as a limit value and re-evaluates it per
# request (see slowapi/wrappers.py), so these read the env each call and are
# tunable at deploy time without a code change. Defaults are deliberately
# generous for humans but cap bulk pulls: HTML listing/profile pages are heavier
# to render, JSON/feed endpoints are the cheapest bulk-scrape targets so they get
# a tighter bucket.
PUBLIC_HTML_RATE_LIMIT_DEFAULT = "90/minute"
PUBLIC_API_RATE_LIMIT_DEFAULT = "30/minute"


def public_html_rate_limit() -> str:
    """Per-IP limit for public HTML listing/profile pages (env: ``PUBLIC_HTML_RATE_LIMIT``)."""
    return (
        os.environ.get("PUBLIC_HTML_RATE_LIMIT") or PUBLIC_HTML_RATE_LIMIT_DEFAULT
    ).strip()


def public_api_rate_limit() -> str:
    """Per-IP limit for public JSON/feed endpoints (env: ``PUBLIC_API_RATE_LIMIT``)."""
    return (
        os.environ.get("PUBLIC_API_RATE_LIMIT") or PUBLIC_API_RATE_LIMIT_DEFAULT
    ).strip()


def _valid_ip(value: str | None) -> str | None:
    """Return ``value`` stripped iff it parses as an IP address, else ``None``.

    Guards every header-derived key: a malformed / garbage value can never become
    a shared rate-limit bucket that collapses many clients into one.
    """
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def client_ip_key(request) -> str:
    """Rate-limit key = the real client IP.

    Precedence, in order of how authoritative the proxy in front is:

    1. **``CF-Connecting-IP``** — set by Cloudflare to the original client IP
       (a single value, not a list). When Cloudflare fronts the origin (Track
       A1), *every* request reaches us through Cloudflare's IPs, so without this
       the whole site would collapse into one rate-limit bucket. Cloudflare
       overwrites this header on the way in, so a client-spoofed value can't
       survive — safe to trust as the top key when present.
    2. **``X-Forwarded-For`` leftmost** — Railway's single-edge case (no
       Cloudflare). Railway controls the header and appends, so the leftmost
       entry is the real client and a spoofed value is pushed rightward.
    3. **Peer address** — local dev / non-proxied.

    Each header value is used only when it parses as a valid IP, so malformed
    input falls through to the next source instead of becoming a shared key.
    (P1-10; A1 Cloudflare-readiness.)

    Ref: Cloudflare — "Restoring original visitor IPs" (``CF-Connecting-IP``);
    Railway help — "Which header should I rely on for real client IP?"
    """
    cf_ip = _valid_ip(request.headers.get("cf-connecting-ip"))
    if cf_ip:
        return cf_ip
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = _valid_ip(xff.split(",")[0])
        if first:
            return first
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip_key, enabled=not is_rate_limit_disabled())
