"""Shared OpenAI client singleton (T2.3).

Every LLM call site used to build a fresh ``OpenAI(...)`` per request, which
re-creates an httpx connection pool each time (no keep-alive reuse, extra TLS
handshakes on the hot chat path). ``get_openai_client`` caches one client per
``(api_key, timeout)``.

Test-seam contract (PR #138 and the wider suite): tests patch the *module
level* ``OpenAI`` symbol in each caller (``patch.object(hint_extractor,
"OpenAI", ...)``). To keep every one of those seams working, callers pass
their module symbol in as ``factory``; anything that is not the real class
(i.e. a test fake) bypasses the cache entirely and is constructed per call,
exactly like before.
"""

from __future__ import annotations

import threading
from typing import Any

try:  # same guarded-import pattern as the call sites
    from openai import OpenAI as _RealOpenAI
except Exception:  # pragma: no cover — openai always present in prod
    _RealOpenAI = None  # type: ignore[misc, assignment]

_lock = threading.Lock()
_cache: dict[tuple[str, float | None], Any] = {}


def get_openai_client(api_key: str, *, factory: Any, timeout: float | None = None) -> Any:
    """Return a shared client for the real class; build fakes fresh.

    ``factory`` is the caller's module-level ``OpenAI`` symbol so existing
    ``patch.object(module, "OpenAI", ...)`` test seams keep intercepting
    construction.
    """
    if _RealOpenAI is None or factory is not _RealOpenAI:
        return factory(api_key=api_key, timeout=timeout)
    key = (api_key, timeout)
    client = _cache.get(key)
    if client is None:
        with _lock:
            client = _cache.get(key)
            if client is None:
                client = factory(api_key=api_key, timeout=timeout)
                _cache[key] = client
    return client


def reset_openai_client_cache() -> None:
    """Test seam: drop all cached clients."""
    with _lock:
        _cache.clear()
