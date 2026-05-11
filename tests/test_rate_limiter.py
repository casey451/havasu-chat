"""Unit tests for ``app.contrib.rate_limiter.SourceLimiter``."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.contrib.rate_limiter import _LOG_EXTRA_KEYS, SourceLimiter


def _response(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://example.com/places")
    return httpx.Response(status, request=req)


def test_source_limiter_paces_first_acquire_no_sleep() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []

    def fake_clock() -> float:
        return clock_time[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock_time[0] += seconds

    limiter = SourceLimiter("test", qps=4.0, clock=fake_clock, sleep=fake_sleep)
    limiter.acquire()
    assert sleeps == []


def test_source_limiter_paces_second_acquire() -> None:
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
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.25)


def test_source_limiter_qps_3_paces_correctly() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []

    def fake_clock() -> float:
        return clock_time[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock_time[0] += seconds

    limiter = SourceLimiter("test", qps=3.0, clock=fake_clock, sleep=fake_sleep)
    limiter.acquire()
    limiter.acquire()
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(1.0 / 3.0)


def test_source_limiter_validates_qps() -> None:
    with pytest.raises(ValueError, match="qps must be positive"):
        SourceLimiter("x", qps=0)


def test_source_limiter_validates_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries must be non-negative"):
        SourceLimiter("x", max_retries=-1)


def test_call_with_retry_passes_through_2xx() -> None:
    clock_time = [0.0]
    limiter = SourceLimiter("test", qps=1000.0, clock=lambda: clock_time[0], sleep=lambda s: None)
    calls = 0

    def fn() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(200)

    r = limiter.call_with_retry(fn)
    assert r.status_code == 200
    assert calls == 1


def test_call_with_retry_retries_on_429() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock_time[0] += s

    limiter = SourceLimiter(
        "test",
        qps=1000.0,
        backoff_initial_s=1.0,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )
    seq = [_response(429), _response(200)]
    calls = 0

    def fn() -> httpx.Response:
        nonlocal calls
        r = seq[min(calls, len(seq) - 1)]
        calls += 1
        return r

    out = limiter.call_with_retry(fn)
    assert out.status_code == 200
    assert calls == 2
    assert sleeps == [1.0]


def test_call_with_retry_retries_on_5xx() -> None:
    clock_time = [0.0]

    def fake_sleep(s: float) -> None:
        clock_time[0] += s

    limiter = SourceLimiter(
        "test",
        qps=1000.0,
        backoff_initial_s=0.5,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )
    seq = [_response(503), _response(200)]
    i = 0

    def fn() -> httpx.Response:
        nonlocal i
        r = seq[min(i, len(seq) - 1)]
        i += 1
        return r

    assert limiter.call_with_retry(fn).status_code == 200


def test_call_with_retry_does_not_retry_on_404() -> None:
    limiter = SourceLimiter("test", qps=1000.0, clock=lambda: 0.0, sleep=lambda s: None)
    calls = 0

    def fn() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(404)

    assert limiter.call_with_retry(fn).status_code == 404
    assert calls == 1


def test_call_with_retry_exhausts_after_max_retries() -> None:
    clock_time = [0.0]

    def fake_sleep(s: float) -> None:
        clock_time[0] += s

    limiter = SourceLimiter(
        "test",
        qps=1000.0,
        max_retries=5,
        backoff_initial_s=0.01,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )
    calls = 0

    def fn() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(429)

    r = limiter.call_with_retry(fn)
    assert r.status_code == 429
    assert calls == 6


def test_call_with_retry_backoff_doubles() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock_time[0] += s

    limiter = SourceLimiter(
        "test",
        qps=1000.0,
        max_retries=3,
        backoff_initial_s=1.0,
        backoff_cap_s=16.0,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )

    def fn() -> httpx.Response:
        return _response(429)

    limiter.call_with_retry(fn)
    assert sleeps == [1.0, 2.0, 4.0]


def test_call_with_retry_backoff_capped() -> None:
    clock_time = [0.0]
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock_time[0] += s

    limiter = SourceLimiter(
        "test",
        qps=1000.0,
        max_retries=5,
        backoff_initial_s=8.0,
        backoff_cap_s=10.0,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )

    def fn() -> httpx.Response:
        return _response(429)

    limiter.call_with_retry(fn)
    assert sleeps[0] == 8.0
    assert sleeps[1] == 10.0
    assert sleeps[2] == 10.0


def test_call_with_retry_emits_structured_log_on_retry() -> None:
    clock_time = [0.0]

    def fake_sleep(s: float) -> None:
        clock_time[0] += s

    limiter = SourceLimiter(
        "src_test",
        qps=1000.0,
        backoff_initial_s=0.01,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )
    n = 0

    def fn() -> httpx.Response:
        nonlocal n
        n += 1
        return _response(429) if n == 1 else _response(200)

    with patch("app.contrib.rate_limiter.logger.warning") as warn:
        limiter.call_with_retry(fn)

    retry_calls = [c for c in warn.call_args_list if c[1].get("extra", {}).get("event") == "retry"]
    assert len(retry_calls) == 1
    extra = retry_calls[0][1]["extra"]
    assert tuple(extra.keys()) == _LOG_EXTRA_KEYS
    assert extra["source"] == "src_test"
    assert extra["status"] == 429
    assert extra["attempt"] == 1


def test_call_with_retry_emits_structured_log_on_exhaustion() -> None:
    clock_time = [0.0]

    def fake_sleep(s: float) -> None:
        clock_time[0] += s

    limiter = SourceLimiter(
        "src_ex",
        qps=1000.0,
        max_retries=1,
        backoff_initial_s=0.01,
        clock=lambda: clock_time[0],
        sleep=fake_sleep,
    )

    def fn() -> httpx.Response:
        return _response(429)

    with patch("app.contrib.rate_limiter.logger.warning") as warn:
        limiter.call_with_retry(fn)

    exhausted = [c for c in warn.call_args_list if c[1].get("extra", {}).get("event") == "exhausted"]
    assert len(exhausted) == 1
    extra = exhausted[0][1]["extra"]
    assert tuple(extra.keys()) == _LOG_EXTRA_KEYS
    assert extra["event"] == "exhausted"
    assert extra["status"] == 429
    assert extra["attempt"] == 2


def test_call_with_retry_propagates_transport_error() -> None:
    limiter = SourceLimiter("test", qps=1000.0, clock=lambda: 0.0, sleep=lambda s: None)
    req = httpx.Request("GET", "http://example.invalid")

    def fn() -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    with pytest.raises(httpx.ConnectError):
        limiter.call_with_retry(fn)
