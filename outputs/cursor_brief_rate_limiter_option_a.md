# Cursor Brief — Phase 2.5 Rate-Limiter, Option A Implementation

> **Operator note:** paste to a fresh Cursor chat. Parallel-eligible with the CC profile-page lane (zero file overlap). Authored 2026-05-13 by Cowork primary from the 8 locked §8 decisions in `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md` (§1 summary table) and the design at `docs/maintainability/phase2_5_rate_limiter_design.md` (§4 Option A interface, §6 integration points). The decisions are LOCKED — do not relitigate. The design's choice of Option A for P1 is fixed.

---

## §0 Baseline confirmation (do this FIRST and report before editing code)

1. `git log --oneline -5` — top should be the slug-lane commits + rate-limiter docs commits from session-13. Report the top 5 SHAs.
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — should show ≥1442 tests.
4. `python -m alembic heads` — single head `f1a2b3c4d5e6` (slug lane).
5. Read `docs/maintainability/phase2_5_rate_limiter_design.md` end-to-end (§0–§9; §8 has the **LOCKED** status block at top — read it before §1 of the doc).
6. Read `docs/maintainability/phase2_5_rate_limiter_decisions_memo.md` §1 summary table only.
7. Read `app/contrib/places_client.py` end-to-end. Note: `httpx.Client` at line 96; error envelope at lines 99–126; uses `os.getenv("GOOGLE_PLACES_API_KEY")` at line 30.
8. Read `scripts/places_discovery.py` lines 1–135 (enough to see `INTER_REQUEST_SLEEP_S = 0.25` at line 74 + the DIY retry block at lines 95–129).
9. Read `scripts/places_enrichment.py` lines 70–140 (enough to see `INTER_REQUEST_SLEEP_S = 0.15` at line 75 and the matching DIY retry block).
10. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches, **HALT and report**. Don't proceed.

---

## §1 Why this lane exists

The Phase 2.5 third-party-source rate-limiter design is DESIGN-COMPLETE; all 7 §8 questions + 1 design-doc §3 extra are LOCKED per the 2026-05-13 decisions memo. This lane implements **Option A** (in-process semaphore + retry/backoff): a new `app/contrib/rate_limiter.py` module exposing `SourceLimiter.call_with_retry`, with `GOOGLE_PLACES_LIMITER` as the canonical instance. Closes Gap A (runtime path has no backoff per design §1.2) and Gap B (script-side retry duplication per design §1.2). Preserves both operator-tuned QPS values (4 QPS lookup path, 6.5 QPS enrichment sweep) via per-instance `qps=` override.

---

## §2 Locked decisions (from memo + 2026-05-13 decision round; do not relitigate)

| # | Locked answer |
|---|---|
| Q1 — scope framing | "Third-party-source rate-limiter" is correct; CSV ingest stays out of scope. |
| Q2 — default QPS | **4 QPS default + per-instance `qps=` override.** Lookup path uses default; enrichment script overrides to 6.5 QPS at construction. |
| Q3 — failure mode | Keep `PlacesLookupResult(status="error", error_message="http_429_retry_exhausted")` envelope. No retry queue, no alerts (P2). |
| Q4 — observability | Structured logs to existing logger (no new DB table in P1). Shared `extra=` dict shape across all emissions. |
| Q5 — concurrency | **Single-process P1.** Ship Option A only. Option B (DB-backed token bucket) is NOT in this lane. |
| Q6 — `url_fetcher.py` | Defer. Leave a `# TODO(rate-limit): per-host throttling — see follow-up` comment near `fetch_url_metadata`. |
| Q7 — OpenAI | Eventually wrap, NOT in P1. Don't rename `call_anthropic_messages`. Don't add a limiter instance for OpenAI in this lane. |
| §3 extra — `river_scene.py` | Out of scope per design §9. Don't touch. |

**Two impl-side carry-overs from memo §3:**

- **HTTP library mismatch.** `places_client.py:11, 96–97` uses `httpx`. `places_discovery.py:39, ~110` and `places_enrichment.py:40, ~118` use `requests`. **Decision for this lane: standardize the scripts on `httpx`** (the runtime path already is). The `call_with_retry` signature is `Callable[[], httpx.Response]`. This is the cleanest path; the alternative (library-agnostic signature) is YAGNI today and muddies the contract.
- **`PAGINATION_SLEEP_S` is not retry logic.** `places_discovery.py:75` exists because Google's `nextPageToken` takes ~2s to become valid. Keep that constant + its `time.sleep` inline in `places_discovery.py`. Do NOT fold it into `SourceLimiter`.

---

## §3 Module structure

Create:

```
app/contrib/rate_limiter.py    # new: SourceLimiter class + GOOGLE_PLACES_LIMITER instance
tests/test_rate_limiter.py     # new: unit tests w/ injectable clock
```

Edit:

```
app/contrib/places_client.py   # route lookup_provider through GOOGLE_PLACES_LIMITER
scripts/places_discovery.py    # delete inline retry; httpx switch; route through GOOGLE_PLACES_LIMITER
scripts/places_enrichment.py   # delete inline retry; httpx switch; route through GOOGLE_PLACES_LIMITER (qps=6.5 override)
app/contrib/url_fetcher.py     # add TODO comment near fetch_url_metadata
tests/test_places_client.py    # extend with one regression test pinning lookup_provider routes through the limiter
```

---

## §4 `app/contrib/rate_limiter.py` — `SourceLimiter` class

Author the module with this public surface. Match the docstring style and import ordering of the project's existing `app/contrib/*.py` files (use `from __future__ import annotations` at the top, etc.).

```python
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
        self._last_call_at: float = 0.0
        self._min_interval_s: float = 1.0 / qps

    def acquire(self) -> None:
        """Block until the next call slot is available (sleep-based pacing)."""
        with self._lock:
            now = self._clock()
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
        last_response: httpx.Response | None = None
        while True:
            self.acquire()
            response = fn()
            if response.status_code not in self.retry_statuses:
                return response
            last_response = response
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


# Canonical instances. Construct at module top so each call site uses the
# shared limiter (matches design §4 anti-pattern checklist: no global
# singleton hidden in module state — these are named module-level instances).
GOOGLE_PLACES_LIMITER: Final = SourceLimiter("google_places", qps=4.0)
```

Notes for Cursor:

- The retry semantics intentionally **return the last response** rather than raising on exhaustion. This preserves the existing caller envelope in `places_client.py` (which inspects `r.status_code` and returns `PlacesLookupResult(status="error", error_message="http_429")`). Caller can detect exhaustion by inspecting the response status + (optionally) reading a header — but for P1, the caller simply maps to the locked Q3 envelope via the existing non-2xx handler at `places_client.py:120–126`.
- **Thread-safety:** the lock around `acquire()` guarantees that within a single process, two threads cannot both think the next slot is ready. For multi-process correctness, the Option B migration replaces `_last_call_at` with a DB-backed token bucket; the public interface (`acquire`, `call_with_retry`) does not change.
- **No log handler configuration.** The module gets a logger via `logging.getLogger(__name__)`; whatever the project's existing log handler config is will pick it up. Don't add a `logging.basicConfig` call.
- **Structured-log shape lock.** All emissions use exactly `_LOG_EXTRA_KEYS`. If a future call site wants additional fields, add a new key to the constant + update all emissions (don't silently mutate per-call).

---

## §5 `app/contrib/places_client.py` — route through `GOOGLE_PLACES_LIMITER`

Anchored Edit only. Two changes:

### §5.1 Add import

Insert after the existing `import httpx` (line 11):

```python
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER
```

### §5.2 Replace the bare `httpx.Client.post` call

Current code at `places_client.py:95–97`:

```python
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            r = client.post(PLACES_SEARCH_URL, headers=headers, json=body)
```

Replace with:

```python
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            r = GOOGLE_PLACES_LIMITER.call_with_retry(
                lambda: client.post(PLACES_SEARCH_URL, headers=headers, json=body)
            )
```

The existing exception handling at lines 98–109 (TimeoutException, RequestError) stays exactly as-is. The non-2xx handler at lines 120–126 also stays exactly as-is — it now absorbs retry-exhausted 429s via the locked Q3 envelope, with `error_message=f"http_{r.status_code}"` reading `"http_429"`. **No change to the error envelope copy** — the design's reference to `"http_429_retry_exhausted"` was a hypothetical from the original §8 question phrasing; impl-side, the existing `"http_429"` is fine. The retry-exhaustion event is visible in the structured logs (Q4) which is sufficient.

---

## §6 `scripts/places_discovery.py` — refactor to use the limiter

### §6.1 Switch `requests` → `httpx`

Replace the `import requests` line (~line 39) with:

```python
import httpx
```

Update all `requests.Response` references to `httpx.Response`. Update all call sites that used `requests.Session()` or `requests.post(...)` to the `httpx.Client(...)` equivalent — typically `httpx.Client(timeout=...)` as a context manager wrapping the post call. If the script uses any `requests`-specific feature (e.g. `requests.exceptions.ConnectionError`), translate to the `httpx` equivalent (`httpx.RequestError`, `httpx.TimeoutException`). Cursor: confirm by reading the script's actual usage; the design doc cited the DIY retry block at lines 95–129 but the imports + Session setup may live earlier.

### §6.2 Delete the inline retry block

The retry block at approximately lines 95–129 (re-confirm by reading) wraps the request in a `for attempt in range(MAX_RETRIES):` loop with status-code checks + sleeps. Replace this block with a single `call_with_retry` call:

```python
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER  # at the top, with other imports

# in request_text_search() (approximate; preserve the function's actual signature):
with httpx.Client(timeout=TIMEOUT_S) as client:
    r = GOOGLE_PLACES_LIMITER.call_with_retry(
        lambda: client.post(PLACES_SEARCH_URL, headers=headers, json=body)
    )
```

Delete these constants from the script (they now live in `SourceLimiter`):

- `INTER_REQUEST_SLEEP_S = 0.25`
- `RETRY_STATUSES = {...}` (or however the script names it)
- `MAX_RETRIES = 5`
- Backoff constants if any

**Keep:** `PAGINATION_SLEEP_S = 2.0` and its `time.sleep(PAGINATION_SLEEP_S)` call between paginated requests. This is not retry logic; it exists because Google's `nextPageToken` takes a couple seconds to become valid. The locked decision is that this stays inline.

### §6.3 Update script-side error reporting

If the script currently prints `[label] http_429 after N retries — giving up` style messages, those can stay. The `SourceLimiter` adds structured-log emissions; the script's stdout is unchanged.

### §6.4 If the script ever raises `RuntimeError` on retry exhaustion

Some scripts in this codebase raise `RuntimeError` when retry exhaustion happens — that's a different shape from `call_with_retry`, which returns the last response. After the refactor, the script should inspect the returned response status and raise/log as appropriate at the call site. Match the existing script's behavior — if it was raising, keep raising on non-2xx after `call_with_retry` returns.

---

## §7 `scripts/places_enrichment.py` — same refactor, override `qps=6.5`

Per locked Q2, the enrichment script keeps its 6.5 QPS cadence via a per-instance limiter override. Don't use `GOOGLE_PLACES_LIMITER` for this script's calls. Instead:

### §7.1 Construct a local limiter at module top

```python
from app.contrib.rate_limiter import SourceLimiter

# Enrichment uses 6.5 QPS (operator-tuned) — distinct from the lookup path's
# 4 QPS default. Both are well under Google Places New's 600 QPM ceiling.
_ENRICHMENT_LIMITER = SourceLimiter("google_places_enrichment", qps=6.5)
```

The `source` string is `"google_places_enrichment"` (not `"google_places"`) so structured-log emissions distinguish lookup-path retries from enrichment-sweep retries. Operator-observability matters here — Q4 chose structured logs precisely so the operator can answer "is 429 exhaustion rare or frequent, and on which path?"

### §7.2 Route `request_place_details` through `_ENRICHMENT_LIMITER`

Same shape as §6.2 but using `_ENRICHMENT_LIMITER.call_with_retry(...)`. Delete the duplicated inline retry block. Keep any `PAGINATION_SLEEP_S` (if present in this script — it might not be) and any non-retry sleeps.

Switch `requests` → `httpx` as in §6.1.

---

## §8 `app/contrib/url_fetcher.py` — add TODO comment

No code change. Insert a comment immediately before the `def fetch_url_metadata(...)` line:

```python
# TODO(rate-limit): per-host throttling against arbitrary contributor URLs.
# Locked-deferred per phase2_5_rate_limiter_design.md §8 Q6 (2026-05-13).
# Per-host throttling is a different shape (LRU+TTL host map, no fixed budget
# per host) than SourceLimiter's per-source model. Inbound 1/hour/IP at
# app/api/routes/contribute.py:48-58 is the de facto outbound limit today.
```

Confirm by reading the file first — the function name may be `fetch_url_metadata` per memo §2.6, but verify line offset before inserting.

---

## §9 Tests

### §9.1 `tests/test_rate_limiter.py` (new)

Unit tests against `SourceLimiter`. Use injectable `clock` + `sleep` so no real-time sleeping happens in tests. Pattern:

```python
def test_source_limiter_paces_acquires() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []
    def fake_clock() -> float:
        return clock_time[0]
    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock_time[0] += seconds
    limiter = SourceLimiter("test", qps=4.0, clock=fake_clock, sleep=fake_sleep)
    limiter.acquire()
    limiter.acquire()
    assert sleeps == [0.25]  # second acquire slept 1/4 second to honor qps=4
```

Required tests (12+ total):

1. `test_source_limiter_paces_first_acquire_no_sleep` — first acquire on a fresh limiter does not sleep.
2. `test_source_limiter_paces_second_acquire` — second acquire sleeps to honor qps.
3. `test_source_limiter_qps_3_paces_correctly` — qps=3 means min interval 1/3 ≈ 0.333s.
4. `test_source_limiter_validates_qps` — `SourceLimiter("x", qps=0)` raises `ValueError`.
5. `test_source_limiter_validates_max_retries` — `max_retries=-1` raises `ValueError`.
6. `test_call_with_retry_passes_through_2xx` — fn returns 200; called once; result is the 200 response.
7. `test_call_with_retry_retries_on_429` — fn returns 429 then 200; called twice; result is the 200; backoff slept once.
8. `test_call_with_retry_retries_on_5xx` — same as 429 but with 503.
9. `test_call_with_retry_does_not_retry_on_404` — fn returns 404; called once; result is the 404.
10. `test_call_with_retry_exhausts_after_max_retries` — fn returns 429 always; called `1 + max_retries` times; result is the final 429.
11. `test_call_with_retry_backoff_doubles` — exhaustion path with `max_retries=3`; assert sleeps are `[backoff_initial_s, backoff_initial_s*2, backoff_initial_s*4]` (capped at `backoff_cap_s`).
12. `test_call_with_retry_backoff_capped` — when `backoff > backoff_cap_s`, the next sleep is the cap.
13. `test_call_with_retry_emits_structured_log_on_retry` — assert `logger.warning` called with `extra={"source": ..., "event": "retry", "status": 429, "attempt": 1, "elapsed_s": ...}`. Use `caplog` fixture or `unittest.mock.patch.object(logger, "warning")`.
14. `test_call_with_retry_emits_structured_log_on_exhaustion` — assert `event="exhausted"` log.
15. `test_call_with_retry_propagates_transport_error` — fn raises `httpx.RequestError`; call_with_retry propagates (does not retry).

Use the fixture style of `tests/test_directory_schema.py` and `tests/test_slug_util.py` — straight `def test_...` functions, no class wrapper unless needed.

### §9.2 `tests/test_places_client.py` (extend)

Add one regression test that pins `lookup_provider` routes through the limiter:

```python
def test_lookup_provider_routes_through_google_places_limiter(monkeypatch):
    """Pin that lookup_provider uses GOOGLE_PLACES_LIMITER.call_with_retry."""
    from app.contrib import places_client
    called = []
    def fake_call_with_retry(fn):
        called.append(fn)
        return fn()  # invoke the lambda — let the test's httpx mock handle the actual HTTP
    monkeypatch.setattr(
        "app.contrib.places_client.GOOGLE_PLACES_LIMITER.call_with_retry",
        fake_call_with_retry,
    )
    # ... existing httpx mock setup ...
    result = places_client.lookup_provider("Acme Plumbing")
    assert len(called) == 1, "lookup_provider must invoke call_with_retry exactly once"
```

The existing `tests/test_places_client.py` (read it first) has its own mocking patterns — match them. If the file uses `httpx.MockTransport` or `respx`, use the same. Don't introduce a new mocking style.

### §9.3 Existing places-client tests should keep passing

The refactor is behavior-preserving for 2xx and non-retryable statuses. The 429-and-retry-then-success path was previously not covered (no retry existed); the new behavior is gated by the new limiter. No existing test should need modification.

If any existing test does fail, report the failure verbatim in the final report; don't paper over.

---

## §10 What NOT to do

- **No `git add`, `git commit`, `git push`, `--amend`.** Report when done; operator commits.
- **Don't add Redis.** Option C is rejected per design §4. No new infrastructure.
- **Don't add a DB migration.** Option B (DB-backed token bucket) is deferred per locked Q5; no schema changes.
- **Don't add observability tooling beyond `logger.warning(...)`.** Q4 locked structured logs to existing destination. No new log handlers, no Sentry hook, no SQL-backed telemetry table.
- **Don't extend `SourceLimiter` to wrap OpenAI/Anthropic in this lane.** Q7 locked: eventually wrap, not P1. No `OPENAI_LIMITER` constant; no instance in `app/core/llm_messages.py`.
- **Don't rename `call_anthropic_messages`.** The name is intentionally retained per `app/core/llm_messages.py:1–17` header.
- **Don't fold `river_scene.py::_sleep_polite` in.** Out of scope per design §9.
- **Don't change `places_discovery.py::PAGINATION_SLEEP_S`** — it's not retry logic.
- **Don't change `places_client.py`'s error envelope** — the existing `error_message=f"http_{r.status_code}"` is the locked Q3 behavior.
- **Don't add a "global throttle" abstraction** that caps total outbound QPS across all sources — design §4 anti-pattern checklist.
- **Don't construct `SourceLimiter` as a global singleton hidden in module state** — design §4 anti-pattern. Named module-level instances are the pattern.
- **Don't `time.sleep` inside `places_client.py` directly** — the whole point is the call site stops caring how the throttle is enforced.
- **Don't touch the chat-route runtime** (`app/chat/`).
- **Don't run any computer-use or browser-automation tools.** Pure code lane.

---

## §11 Phased commit boundaries (recommended)

This lane is small enough to ship as one commit. If you want two for review separation:

**Phase A — limiter module + lookup-path integration + tests.** Files: `app/contrib/rate_limiter.py`, `app/contrib/places_client.py`, `tests/test_rate_limiter.py`, `tests/test_places_client.py`, `app/contrib/url_fetcher.py` (TODO comment). Commit message: `feat(contrib): SourceLimiter + Google Places lookup-path integration (Phase 2.5 rate-limiter Option A)`. Acceptance: pytest 1442 + new tests pass; `lookup_provider` test pins limiter routing.

**Phase B — scripts collapse.** Files: `scripts/places_discovery.py`, `scripts/places_enrichment.py`. Commit message: `refactor(scripts): collapse Places discovery + enrichment DIY retry into SourceLimiter`. Acceptance: dry-run discovery returns same place count vs pre-refactor; enrichment dry-run resumes correctly.

If shipping as one commit, message: `feat(contrib): Phase 2.5 third-party-source rate-limiter (Option A) + Places integration`.

---

## §12 Final report format

When done, paste back a single message with:

1. **§0 baseline values** (HEAD, pytest count, alembic head).
2. **Files created** (paths + line counts).
3. **Files modified** (paths + net line counts).
4. **Tests added** (count + brief description of each).
5. **Final pytest count** (expected 1442 + tests added).
6. **Ruff status** (clean / autofixes applied / remaining issues).
7. **`requests` → `httpx` translation report** — list any non-trivial idiom changes (e.g. session creation pattern, exception-class translation).
8. **Pragmatic deviations** — anything you adapted from this brief with rationale.
9. **Anything that surprised you** or that the operator should know before they commit.
10. **Confirmation that you did NOT run `git add`/`commit`/`push`/`--amend`.**

Ready. Start at §0.
