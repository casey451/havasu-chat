"""Per-source rate-limiter for outbound third-party API calls.

P1 implementation (Option A in docs/maintainability/phase2_5_rate_limiter_design.md):
in-process semaphore w/ sleep-based QPS pacing + exponential-backoff retry. The
public ``SourceLimiter`` interface is designed so a future Option B (DB-backed
token bucket) is a drop-in replacement when concurrent workers ship — caller
code does not change.

Locked decisions (2026-05-13):
- Q2: 4 QPS default; per-instance ``qps=`` override (enrichment uses 6.5).
- Q3: retry-exhausted 429 returns to caller via the response object;
      caller decides how to envelope the failure. SourceLimiter does NOT
      raise on exhaustion — it returns the final response or raises only
      on transport errors (httpx.RequestError, httpx.TimeoutException).
- Q4: structured logger.warning() on each retry + on exhaustion. Shared
      ``extra=`` dict shape (see ``_LOG_EXTRA_KEYS``).
- Q5: single-process P1; no cross-process state.

See ``docs/maintainability/phase2_5_rate_limiter_decisions_memo.md`` for the
per-question evidence and rationale.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Final

import httpx

logger = logging.getLogger(__name__)


_LOG_EXTRA_KEYS: Final = ("source", "event", "status", "attempt", "elapsed_s")


class SourceLimiter:
    """Per-source rate-limiter + retry policy for outbound HTTP calls.

    One instance per third-party source (Google Places, future OpenAI, etc.).
    Thread-safe within a single process; not multi-process-safe. The interface
    is stable across the P1 → P2 (Option A → Option B) migration so that the
    swap is a one-file change.

    Parameters
    ----------
    source:
        Stable identifier (e.g. ``"google_places"``). Used in structured logs.
    qps:
        Sustained queries-per-second budget. The limiter enforces this via
        sleep-based pacing: at most one acquire() per ``1.0 / qps`` seconds.
    max_retries:
        Number of retries on retryable HTTP statuses. The initial attempt
        does not count; ``max_retries=5`` means up to 6 total attempts.
    backoff_initial_s:
        First backoff sleep duration. Doubles per attempt up to ``backoff_cap_s``.
    backoff_cap_s:
        Maximum backoff sleep. After this cap, further attempts sleep this long.
    retry_statuses:
        HTTP statuses that trigger a retry. Per-source policy — Google Places
        retries on 429/5xx; OpenAI would also respect a ``retry-after`` header
        (future instance, not P1).
    clock:
        Monotonic-clock callable. Inject for tests; defaults to ``time.monotonic``.
    sleep:
        Sleep callable. Inject for tests; defaults to ``time.sleep``.
    """

    def __init__(
        self,
        source: str,
        *,
        qps: float = 4.0,
        max_retries: int = 5,
        backoff_initial_s: float = 1.0,
        backoff_cap_s: float = 16.0,
        retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504}),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if qps <= 0:
            raise ValueError(f"qps must be positive; got {qps!r}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative; got {max_retries!r}")
        self.source = source
        self.qps = qps
        self.max_retries = max_retries
        self.backoff_initial_s = backoff_initial_s
        self.backoff_cap_s = backoff_cap_s
        self.retry_statuses = retry_statuses
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call_at: float | None = None
        self._min_interval_s: float = 1.0 / qps

    def acquire(self) -> None:
        """Block until the next call slot is available (sleep-based pacing)."""
        with self._lock:
            now = self._clock()
            if self._last_call_at is None:
                self._last_call_at = now
                return
            elapsed = now - self._last_call_at
            wait = self._min_interval_s - elapsed
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
            self._last_call_at = now

    def call_with_retry(self, fn: Callable[[], httpx.Response]) -> httpx.Response:
        """Call ``fn`` with acquire-pacing + retry on configured statuses.

        Returns the final ``httpx.Response`` (including the last response when
        retries are exhausted — caller decides how to envelope). Raises only
        on transport errors propagated from ``fn``.

        Logs structured warnings on each retry and on exhaustion, with the
        shared ``extra=`` dict shape (see ``_LOG_EXTRA_KEYS``).
        """
        attempt = 0
        backoff = self.backoff_initial_s
        start = self._clock()
        while True:
            self.acquire()
            response = fn()
            if response.status_code not in self.retry_statuses:
                return response
            if attempt >= self.max_retries:
                logger.warning(
                    "rate_limiter.exhausted",
                    extra={
                        "source": self.source,
                        "event": "exhausted",
                        "status": response.status_code,
                        "attempt": attempt + 1,
                        "elapsed_s": round(self._clock() - start, 3),
                    },
                )
                return response
            logger.warning(
                "rate_limiter.retry",
                extra={
                    "source": self.source,
                    "event": "retry",
                    "status": response.status_code,
                    "attempt": attempt + 1,
                    "elapsed_s": round(self._clock() - start, 3),
                },
            )
            self._sleep(backoff)
            backoff = min(backoff * 2, self.backoff_cap_s)
            attempt += 1


GOOGLE_PLACES_LIMITER: Final = SourceLimiter("google_places", qps=4.0)
