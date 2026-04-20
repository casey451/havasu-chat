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


limiter = Limiter(key_func=get_remote_address, enabled=not is_rate_limit_disabled())
