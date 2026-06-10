#!/usr/bin/env python3
"""Operator probe: AZCC session cookie TTL (Q1) + scope HttpOnly/SameSite (Q2).

Sibling to scripts/azcc_seed_cookie.py. Where the seed helper just dumps the
cookie line for paste into .env, this probe ALSO:

  * Records the full cookie attribute set (Q2: domain, path, httpOnly, secure,
    sameSite, expires) and any Set-Cookie response headers observed during the
    solve flow.
  * Drives a sequence of timed re-probes against /api/Captcha/generate using
    the captured session, recording when (if) the session expires (Q1 TTL).

Outputs a JSON report to outputs/azcc_q1_q2_operator_probe_<UTC-stamp>.json
plus a console summary at the end.

Usage:
    python scripts/azcc_q1_q2_operator_probe.py
    python scripts/azcc_q1_q2_operator_probe.py --intervals 5,15,30,60,120

Operator flow:
    1. Run the script. A Chromium window opens to the AZCC business search.
    2. Type a business name, click Business Search, solve the captcha,
       click Verify.
    3. The script detects the successful public-search XHR, dumps the Q2
       cookie scope table to stdout, and begins TTL re-probes on the
       configured schedule (default: 5, 15, 30, 60, 120 minutes after solve).
    4. Between re-probes the browser sits idle (no traffic) so we measure
       elapsed-TTL not active-TTL.
    5. The script writes the final JSON report and exits 0.
    6. Operator may Ctrl+C at any time; whatever has been collected so far
       is flushed to the JSON file in a finally block.

Exit codes:
    0  Probe completed all intervals (or operator clean-exited).
    1  Timed out waiting for the operator to solve the captcha (10 min cap).
    2  Unexpected exception during probe.

This script makes NO commits, NO migrations, and writes ONLY to outputs/.
It is intentionally read-only against the repo. Safe to run on residential
or office IPs.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SEARCH_URL = "https://arizonabusinesscenter.azcc.gov/businesssearch"
CAPTCHA_GENERATE_URL = "https://api-azbusinessconnectonline.azcc.gov/api/Captcha/generate"
PUBLIC_SEARCH_API_FRAGMENT = "publicsearch/public-search"
SOLVE_WAIT_TIMEOUT_S = 600  # 10 min for the operator to do their part
DEFAULT_INTERVALS_MIN = "5,15,30,60,120"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _print_q2_report(cookies: list[dict], set_cookie_headers: list[str]) -> None:
    print("")
    print("=" * 78)
    print("Q2 -- cookie scope (HttpOnly / SameSite / Secure / Expires / Domain / Path)")
    print("=" * 78)
    if not cookies:
        print("  (no cookies captured)")
    else:
        cols = ("name", "domain", "path", "httpOnly", "secure", "sameSite", "expires")
        widths = {
            c: max(len(c), max((len(str(ck.get(c, ""))) for ck in cookies), default=0))
            for c in cols
        }
        header = "  ".join(c.ljust(widths[c]) for c in cols)
        print("  " + header)
        print("  " + "-" * len(header))
        for ck in cookies:
            row = "  ".join(str(ck.get(c, "")).ljust(widths[c]) for c in cols)
            print("  " + row)
    print("")
    print(f"Set-Cookie response headers observed during solve: {len(set_cookie_headers)}")
    for h in set_cookie_headers:
        print(f"  > {h}")
    print("=" * 78)


def _probe_captcha_endpoint(page) -> dict:
    """Re-issue a fetch() to /api/Captcha/generate from inside the browser
    context so the credentials cookies ride along. Returns a small dict
    summarizing status + headers we care about for TTL determination.
    """
    script = f"""
    (async () => {{
        const t0 = performance.now();
        try {{
            const r = await fetch({json.dumps(CAPTCHA_GENERATE_URL)}, {{
                method: 'GET', credentials: 'include', cache: 'no-store'
            }});
            const elapsed = performance.now() - t0;
            const headers = {{}};
            r.headers.forEach((v, k) => {{ headers[k.toLowerCase()] = v; }});
            const text = await r.text();
            return {{
                status: r.status, ok: r.ok,
                elapsed_ms: Math.round(elapsed),
                bodyLength: text.length,
                bodyPrefix: text.slice(0, 60),
                retryAfter: headers['retry-after'] || null,
                rateLimit: headers['x-ratelimit-remaining'] || null,
                setCookie: headers['set-cookie'] || null,
            }};
        }} catch (e) {{
            return {{ error: String(e), elapsed_ms: Math.round(performance.now() - t0) }};
        }}
    }})()
    """
    return page.evaluate(script)


def _classify_session(probe_result: dict) -> str:
    """Map probe result -> alive / stale / unknown classification for TTL chart."""
    if "error" in probe_result:
        return f"error:{probe_result['error']}"
    status = probe_result.get("status")
    if status == 200 and probe_result.get("bodyLength", 0) > 1000:
        # captcha generate returns ~10KB base64; if we got a fresh blob, session is alive
        return "alive"
    if status in (401, 403):
        return "stale_auth"
    if status == 429:
        return "rate_limited"
    if status is None:
        return "unknown"
    return f"unexpected:{status}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--intervals",
        default=DEFAULT_INTERVALS_MIN,
        help=f"Comma-separated minute marks for TTL re-probes (default: {DEFAULT_INTERVALS_MIN})",
    )
    ap.add_argument(
        "--search-url",
        default=DEFAULT_SEARCH_URL,
        help="AZCC public business search URL",
    )
    ap.add_argument(
        "--out-dir",
        default="outputs",
        help="Directory for the JSON report (default: outputs/)",
    )
    args = ap.parse_args()

    try:
        intervals_min = sorted({int(x.strip()) for x in args.intervals.split(",") if x.strip()})
    except ValueError:
        print(
            f"--intervals must be comma-separated integers, got: {args.intervals!r}",
            file=sys.stderr,
        )
        return 2
    if not intervals_min:
        print("--intervals produced an empty list; nothing to probe.", file=sys.stderr)
        return 2

    # Lazy import so a missing playwright install gives a clean error not a stack trace
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is not installed in this env. `pip install playwright && playwright install chromium`.",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"azcc_q1_q2_operator_probe_{_utc_stamp()}.json"

    report: dict = {
        "started_at": _utc_now_iso(),
        "search_url": args.search_url,
        "intervals_min": intervals_min,
        "q2_cookies": [],
        "q2_set_cookie_headers": [],
        "solve_detected_at": None,
        "q1_probes": [],
        "ended_at": None,
        "ended_reason": None,
        "script_version": "v27-1",
    }

    captured: dict | None = None
    set_cookie_seen: list[str] = []

    def _on_response(response) -> None:
        nonlocal captured
        # Always sample Set-Cookie headers for diagnostic purposes
        try:
            headers = response.headers
        except Exception:
            headers = {}
        sc = headers.get("set-cookie") if isinstance(headers, dict) else None
        if sc:
            set_cookie_seen.append(f"[{response.status}] {response.url[:80]} :: {sc[:120]}")
        if PUBLIC_SEARCH_API_FRAGMENT not in response.url:
            return
        if response.status != 200:
            return
        try:
            body = response.json()
        except Exception:
            return
        if isinstance(body, dict) and body.get("succeeded") and body.get("data"):
            captured = body

    def _flush_and_exit(code: int, reason: str) -> int:
        report["ended_at"] = _utc_now_iso()
        report["ended_reason"] = reason
        try:
            out_path.write_text(json.dumps(report, indent=2))
            print(f"\nReport written: {out_path}")
        except Exception as exc:
            print(f"Could not write report to {out_path}: {exc}", file=sys.stderr)
        return code

    # SIGINT handler so Ctrl+C still flushes the report
    interrupted = {"flag": False}

    def _on_sigint(signum, frame):
        interrupted["flag"] = True

    signal.signal(signal.SIGINT, _on_sigint)

    print(__doc__.split("Operator flow:")[0].rstrip())
    print(f"\nReport will be written to: {out_path}")
    print(f"TTL probe schedule (minutes after solve): {intervals_min}\n")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.on("response", _on_response)
                page.set_default_navigation_timeout(120_000)
                page.set_default_timeout(60_000)
                page.goto(args.search_url, wait_until="networkidle", timeout=120_000)

                # Phase 1: wait for operator solve
                print("Browser open. Solve a captcha-gated search to begin TTL probe...")
                deadline = time.monotonic() + SOLVE_WAIT_TIMEOUT_S
                while captured is None:
                    if interrupted["flag"]:
                        return _flush_and_exit(0, "ctrl-c-before-solve")
                    page.wait_for_timeout(1_000)
                    if time.monotonic() >= deadline:
                        return _flush_and_exit(1, "solve-timeout-10min")

                report["solve_detected_at"] = _utc_now_iso()
                cookies = context.cookies()
                report["q2_cookies"] = cookies
                report["q2_set_cookie_headers"] = list(set_cookie_seen)
                _print_q2_report(cookies, set_cookie_seen)
                # Flush partial report immediately so Q2 is captured even if probe phase aborts
                out_path.write_text(json.dumps(report, indent=2))
                print(f"Q2 report flushed to {out_path}")

                # Phase 2: timed TTL re-probes
                solve_t0 = time.monotonic()
                for minute_mark in intervals_min:
                    target_s = minute_mark * 60
                    print(f"\nWaiting until T+{minute_mark} min for next probe...")
                    while time.monotonic() - solve_t0 < target_s:
                        if interrupted["flag"]:
                            return _flush_and_exit(0, f"ctrl-c-before-T+{minute_mark}min")
                        page.wait_for_timeout(2_000)
                    probe_result = _probe_captcha_endpoint(page)
                    elapsed_real_s = round(time.monotonic() - solve_t0)
                    classification = _classify_session(probe_result)
                    entry = {
                        "scheduled_minute": minute_mark,
                        "actual_elapsed_s": elapsed_real_s,
                        "probed_at": _utc_now_iso(),
                        "classification": classification,
                        "result": probe_result,
                    }
                    report["q1_probes"].append(entry)
                    print(
                        f"T+{minute_mark} min (actual +{elapsed_real_s}s): "
                        f"{classification} -- status={probe_result.get('status')}, "
                        f"bodyLength={probe_result.get('bodyLength')}"
                    )
                    # Flush after each probe so a long-running probe survives interruptions
                    out_path.write_text(json.dumps(report, indent=2))

                return _flush_and_exit(0, "completed-all-intervals")
            finally:
                browser.close()
    except Exception as exc:
        report["ended_reason"] = f"exception: {exc!r}"
        return _flush_and_exit(2, report["ended_reason"])


if __name__ == "__main__":
    sys.exit(main())
