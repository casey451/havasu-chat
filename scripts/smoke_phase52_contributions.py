#!/usr/bin/env python3
"""Phase 5.2 smoke: admin cookie login -> POST contribution -> wait -> GET enrichment.

Run against production with Railway env injection, e.g.:
  railway run .\\.venv\\Scripts\\python.exe scripts/smoke_phase52_contributions.py

Requires ADMIN_PASSWORD. GOOGLE_PLACES_API_KEY optional (enrichment degrades if unset).
"""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = (os.environ.get("HAVASU_SMOKE_BASE") or "https://havasu-chat-production.up.railway.app").rstrip("/")
WAIT_SEC = float(os.environ.get("HAVASU_SMOKE_WAIT", "8"))


def main() -> int:
    pw = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if not pw:
        print("ERROR: ADMIN_PASSWORD is not set.", file=sys.stderr)
        print("Hint: railway run .\\.venv\\Scripts\\python.exe scripts/smoke_phase52_contributions.py", file=sys.stderr)
        return 2

    payload = {
        "entity_type": "provider",
        "submission_name": "Altitude Trampoline Park",
        "submission_url": "https://altitudetrampolinepark.com/lake-havasu-city",
        "source": "operator_backfill",
    }

    with httpx.Client(base_url=BASE, timeout=60.0, follow_redirects=False) as client:
        r_login = client.post("/admin/login", data={"password": pw})
        if r_login.status_code not in (302, 303):
            print(f"LOGIN_FAIL status={r_login.status_code} body={r_login.text[:500]!r}")
            return 1

        r_post = client.post("/admin/api/contributions", json=payload)
        if r_post.status_code != 201:
            print(f"POST_FAIL status={r_post.status_code} body={r_post.text[:800]!r}")
            return 1
        body = r_post.json()
        cid = body["id"]
        print(f"POST_OK id={cid} initial url_fetch_status={body.get('url_fetch_status')!r}")

        time.sleep(WAIT_SEC)

        r_get = client.get(f"/admin/api/contributions/{cid}")
        if r_get.status_code != 200:
            print(f"GET_FAIL status={r_get.status_code} body={r_get.text[:800]!r}")
            return 1
        row = r_get.json()

    keys = (
        "url_fetch_status",
        "url_title",
        "url_description",
        "url_fetched_at",
        "google_place_id",
        "google_enriched_data",
    )
    print("--- after wait ---")
    for k in keys:
        v = row.get(k)
        if k == "google_enriched_data" and isinstance(v, dict):
            print(f"{k}: keys={list(v.keys())[:12]}...")
        else:
            print(f"{k}: {v!r}")

    ok_url = row.get("url_fetch_status") == "success"
    ok_gp = bool(row.get("google_place_id")) or (
        isinstance(row.get("google_enriched_data"), dict)
        and row["google_enriched_data"].get("lookup_status") in ("success", "low_confidence")
    )
    if ok_url and ok_gp:
        print("SMOKE_RESULT: PASS (url success + places data present)")
        return 0
    if ok_url or ok_gp:
        print("SMOKE_RESULT: PARTIAL (only one branch populated — check logs / API key)")
        return 0
    print("SMOKE_RESULT: FAIL (enrichment still empty — check Railway logs, GOOGLE_PLACES_API_KEY, outbound network)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
