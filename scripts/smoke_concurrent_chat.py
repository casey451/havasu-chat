"""Lightweight concurrent smoke test for ``POST /api/chat`` (Phase 8.2 — Part B).

This script is **not** a 50-user stress test and **not** production load testing.
It sends a modest number of mixed-intent requests from several threads to a
**local** dev server to catch gross regressions (5xx, timeouts) and to record
**p50/p95** end-to-end latency. Use before soft launch or after performance-related
changes. See :doc:`HAVA_CONCIERGE_HANDOFF.md` Phase 8.2 scope; synthetic
massive concurrency is out of scope until real traffic exists.

**What it tests:** 8 (default) client threads, each reusing a unique
``session_id``, posting queries for a few minutes with spacing between calls—
mildly concurrent, realistic for dogfooding.

**What it does *not* test:** Rail capacity, production URLs, 50+ concurrent
users, or k6/Locust-style scenarios.

**How to run**
1. From repo root, start the app (SQLite dev DB is fine), e.g.::

     python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

   (On Windows, use the project venv: ``.\\venv\\Scripts\\python.exe`` in place of ``python``.)

2. In another terminal::

     python scripts/smoke_concurrent_chat.py

   Or with custom parameters::

     python scripts/smoke_concurrent_chat.py --base-url http://127.0.0.1:8000

Set ``ANTHROPIC_API_KEY`` and ``OPENAI_API_KEY`` in the environment the **server**
uses if you want Tier 2/3 to exercise real model paths; otherwise you may see
higher **fallback** rates, which is informative but not a script failure.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.chat.tier3_handler import FALLBACK_MESSAGE

# Queries biased toward Tier 1 / 2 / 3 patterns; wording matches local seed examples where possible.
_TIER1 = (
    "What are the hours for Havasu Lanes?",
    "What is the phone number for Havasu Lanes?",
    "What are the hours for Iron Wolf Golf & Country Club?",
)
_TIER2 = (
    "What kid-friendly activities are there in Lake Havasu this weekend?",
    "What outdoor family activities can we do in Havasu City?",
    "What programs are there for kids in Lake Havasu?",
)
_TIER3 = (
    "What's a relaxing way to spend a Saturday in Lake Havasu if I'm new to the area?",
    "I have one day in town—what's worth my time at the lake?",
    "What would you recommend for a first-time visitor to Lake Havasu City?",
)


def _pick_query(sequential_index: int) -> str:
    b = sequential_index % 10
    if b < 3:
        return _TIER1[sequential_index % len(_TIER1)]
    if b < 6:
        return _TIER2[sequential_index % len(_TIER2)]
    return _TIER3[sequential_index % len(_TIER3)]


@dataclass
class _Result:
    ok: bool
    status_code: int
    elapsed_ms: float
    tier_used: str | None
    is_fallback: bool
    err: str | None = None


@dataclass
class _RunStats:
    results: list[_Result] = field(default_factory=list)


def _one_request(
    client: httpx.Client, base: str, session_id: str, body: dict[str, Any]
) -> _Result:
    url = f"{base.rstrip('/')}/api/chat"
    t0 = time.perf_counter()
    try:
        r = client.post(url, json=body, timeout=httpx.Timeout(120.0, connect=10.0))
        elapsed = (time.perf_counter() - t0) * 1000.0
        tier = None
        text = None
        try:
            j = r.json()
            tier = j.get("tier_used")
            text = j.get("response")
        except Exception:
            pass
        is_fb = text == FALLBACK_MESSAGE
        if r.status_code >= 500:
            return _Result(
                False,
                r.status_code,
                elapsed,
                str(tier) if tier is not None else None,
                is_fb,
            )
        return _Result(
            r.status_code == 200,
            r.status_code,
            elapsed,
            str(tier) if tier is not None else None,
            is_fb,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return _Result(False, 0, elapsed, None, False, str(e))


def _worker(
    base_url: str,
    thread_idx: int,
    duration_sec: float,
    interval_sec: float,
) -> _RunStats:
    session_id = f"smoke-{thread_idx:02d}-{uuid.uuid4().hex[:10]}"
    out = _RunStats()
    # Long per-request timeout: Tier 3 can be slow on cold start.
    with httpx.Client() as client:
        deadline = time.monotonic() + duration_sec
        seq = thread_idx * 10_000
        while time.monotonic() < deadline:
            q = _pick_query(seq)
            seq += 1
            res = _one_request(
                client,
                base_url,
                session_id,
                {"query": q, "session_id": session_id},
            )
            out.results.append(res)
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.0, interval_sec))
    return out


def _pctl(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    idx = min(len(s) - 1, int(round((len(s) - 1) * q)))
    return s[idx]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Origin of the Havasu Chat app (default local)",
    )
    p.add_argument("--threads", type=int, default=8, help="Concurrent worker threads (default 8)")
    p.add_argument(
        "--duration-seconds", type=int, default=180, help="How long each thread runs (default 180)"
    )
    p.add_argument(
        "--interval-seconds", type=float, default=25.0, help="Pause between calls per thread (default 25)"
    )
    args = p.parse_args()
    n_threads = max(1, int(args.threads))
    dur = float(args.duration_seconds)
    ival = float(args.interval_seconds)

    merged: list[_Result] = []
    t3_lat: list[float] = []

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        futs = [
            ex.submit(_worker, args.base_url, i, dur, ival) for i in range(n_threads)
        ]
        for f in as_completed(futs):
            s = f.result()
            merged.extend(s.results)
    for r in merged:
        if r.tier_used == "3" and r.status_code == 200 and not r.err:
            t3_lat.append(r.elapsed_ms)
    fives = sum(1 for r in merged if r.status_code >= 500)
    err_n = sum(1 for r in merged if r.err)

    latencies = [r.elapsed_ms for r in merged if r.status_code == 200 and r.err is None]
    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = _pctl(latencies, 0.95)
    p95_t3 = _pctl(t3_lat, 0.95) if t3_lat else 0.0
    fallback_n = sum(1 for r in merged if r.is_fallback)

    print("=== smoke_concurrent_chat ===")
    print(f"Base URL: {args.base_url}")
    print(f"Threads: {n_threads}  Duration (each): {dur:.0f}s  Interval: {ival:g}s")
    print(f"Total requests: {len(merged)}")
    print(
        f"p50 / p95 latency (ms, all 200s):  {p50:,.0f} / {p95:,.0f}"
    )
    if t3_lat:
        print(
            f"p50 / p95 (Tier 3 only, 200s):  {statistics.median(t3_lat):,.0f} / {p95_t3:,.0f}"
        )
    print(
        f"5xx: {fives}  client errors: {err_n}  fallback responses: {fallback_n} / {len(merged)}"
    )

    if t3_lat and p95_t3 > 20_000:
        print(
            f"WARNING: Tier 3 p95 ({p95_t3:,.0f} ms) > 20s (local; cold starts often dominate)."
        )

    if fives or err_n:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
