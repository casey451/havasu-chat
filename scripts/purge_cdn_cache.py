"""Purge the Cloudflare edge cache — run after a deploy AND after any data op, so
the cold/crawler path can never serve a pre-change render (the 2026-07-07
stale-day-view report: a cold fetch showed a quarantined event + an old-build
pager while warm sessions were fresh).

The origin already sends ``Cache-Control: no-cache`` on HTML, so in the normal
case Cloudflare shouldn't cache pages — but a "Cache Everything" rule or a
per-PoP edge copy can still diverge. This makes the invalidation explicit and
idempotent instead of hoping for a header.

Gated on credentials so it is a SAFE NO-OP when unconfigured (local, forks, or
before Casey adds the secret): if ``CF_PURGE_API_TOKEN`` / ``CF_ZONE_ID`` are
absent it prints a skip line and exits 0 — it never fails a deploy or a data op.

    # after a deploy: wait until the new build is actually live, then purge
    python scripts/purge_cdn_cache.py --verify-sha "$GITHUB_SHA" --base https://askhava.com
    # after a data op: purge the pages a write can change (or --all)
    python scripts/purge_cdn_cache.py --urls https://askhava.com/events-ui,https://askhava.com/calendar

Env: ``CF_PURGE_API_TOKEN`` (a scoped token with Zone.Cache Purge) + ``CF_ZONE_ID``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://askhava.com"
_CF_API = "https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache"
BOT_UA = "Mozilla/5.0 (compatible; AskHavaDeployBot/1.0)"


def _get_json(url: str, *, timeout: float = 15.0) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": BOT_UA, "Cookie": ""})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def wait_for_deploy(base: str, sha: str, *, timeout_s: int = 300, interval_s: int = 10) -> bool:
    """Poll ``GET /health`` until its ``build_sha`` matches ``sha`` (the deploy is
    live), so a purge can't repopulate the edge with the OLD build. ``sha`` is
    matched by prefix (the meta/health SHA is short). Returns False on timeout."""
    want = sha.strip()[:12]
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        health = _get_json(base.rstrip("/") + "/health")
        last = (health or {}).get("build_sha")
        if last and (last == want or want.startswith(last) or last.startswith(want)):
            print(f"deploy live: /health build_sha={last} matches {want}")
            return True
        print(f"waiting for deploy… /health build_sha={last!r} != {want!r}")
        time.sleep(interval_s)
    print(f"::warning::deploy did not report build_sha={want} within {timeout_s}s (last={last!r})")
    return False


def purge(token: str, zone: str, urls: list[str] | None) -> bool:
    """Purge everything (urls=None) or specific URLs. Returns True on success."""
    body = {"files": urls} if urls else {"purge_everything": True}
    req = urllib.request.Request(  # noqa: S310 — fixed Cloudflare API host
        _CF_API.format(zone=zone),
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        print(f"::error::Cloudflare purge HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}")
        return False
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"::error::Cloudflare purge failed: {exc}")
        return False
    if not data.get("success"):
        print(f"::error::Cloudflare purge rejected: {data.get('errors')}")
        return False
    print(f"purged: {'specific urls' if urls else 'everything'} (zone {zone[:6]}…)")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Purge the Cloudflare edge cache (gated on creds).")
    ap.add_argument("--base", default=DEFAULT_BASE, help="Origin (for --verify-sha).")
    ap.add_argument("--verify-sha", default="", help="Wait until /health build_sha matches first.")
    ap.add_argument("--urls", default="", help="Comma-separated URLs to purge (else purge all).")
    args = ap.parse_args(argv)

    # Wait for the deploy FIRST — independent of CF creds. This doubles as the
    # post-deploy gate the canary relies on: without it, a credential-less no-op
    # would return instantly and the canary would run against the OLD build (the
    # 2026-07-07 post-deploy-verify false red).
    if args.verify_sha:
        wait_for_deploy(args.base, args.verify_sha)

    token = (os.getenv("CF_PURGE_API_TOKEN") or "").strip()
    zone = (os.getenv("CF_ZONE_ID") or "").strip()
    if not token or not zone:
        print("cache purge SKIPPED — CF_PURGE_API_TOKEN / CF_ZONE_ID not set (no-op).")
        return 0

    urls = [u.strip() for u in args.urls.split(",") if u.strip()] or None
    return 0 if purge(token, zone, urls) else 1


if __name__ == "__main__":
    raise SystemExit(main())
