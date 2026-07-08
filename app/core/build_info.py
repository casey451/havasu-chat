"""One source for the running build's identity — the deployed commit SHA.

Exposed on ``GET /health`` (``build_sha``) and stamped into every page as a
``<meta name="build-sha">`` + ``<meta name="render-ts">`` pair. The cold-cache
canary asserts the page's build-sha matches the running app's (``/health``) and
that its render timestamp is recent — so a stale edge/CDN render from an OLDER
build (which still carries today's date and so slipped past the date-label check)
can no longer go silently green.

Railway injects ``RAILWAY_GIT_COMMIT_SHA`` at deploy; locally it's unset → "dev".
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

_SHA_LEN = 12


def build_sha() -> str:
    """Short SHA of the deployed commit (``"dev"`` when unset, e.g. local/tests)."""
    raw = (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")  # some PaaS use this name
        or ""
    ).strip()
    return raw[:_SHA_LEN] if raw else "dev"


def render_ts() -> str:
    """Current UTC instant as an ISO-8601 ``Z`` string, evaluated at render time.

    Used as a Jinja global (``{{ render_ts() }}``) so each response carries the
    moment it was actually rendered — a cached copy keeps its old value."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
