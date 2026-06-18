"""Post-deploy smoke runner — exercises q01-q23 against prod URL.

Usage:
    python scripts/post_deploy_smoke.py --url https://askhava.com
    python scripts/post_deploy_smoke.py --url $PROD_URL --json-out outputs/smoke_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

from app.chat.halt3_validator import (  # noqa: E402
    EvalQuerySpec,
    _tier_matches,
    load_eval_set,
)


def load_smoke_queries(eval_set_path: Path, limit: int = 23) -> list[EvalQuerySpec]:
    """Load first N queries from the HALT 3 eval set as a smoke subset."""
    return load_eval_set(eval_set_path)[:limit]


def run_one(query: str, url: str, timeout: float = 30.0) -> dict[str, Any]:
    """POST query to /api/chat and return response."""
    payload = {"query": query, "session_id": f"smoke-{uuid.uuid4().hex[:12]}"}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.post(f"{url.rstrip('/')}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


def evaluate(spec: EvalQuerySpec, response: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (passed, failure_reasons) for one query/response pair."""
    failures: list[str] = []
    actual_tier = str(response.get("tier_used", ""))
    if not _tier_matches(spec.expected_tier, actual_tier):
        failures.append(f"tier expected {spec.expected_tier}, got {actual_tier}")
    return (not failures, failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://askhava.com")
    ap.add_argument(
        "--eval-set",
        type=Path,
        default=Path("app/chat/halt3_eval_set.yaml"),
    )
    ap.add_argument("--limit", type=int, default=23)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    queries = load_smoke_queries(args.eval_set, args.limit)
    results: list[dict[str, Any]] = []
    fail_count = 0
    for spec in queries:
        qid = spec.id
        query = spec.query
        try:
            t0 = time.time()
            response = run_one(query, args.url, args.timeout)
            latency_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            results.append({"id": qid, "passed": False, "error": str(e)})
            fail_count += 1
            print(f"FAIL  {qid}: ERROR {e}", file=sys.stderr)
            continue
        passed, failures = evaluate(spec, response)
        results.append(
            {
                "id": qid,
                "passed": passed,
                "tier_used": response.get("tier_used"),
                "latency_ms": latency_ms,
                "failures": failures,
            }
        )
        if passed:
            print(f"PASS  {qid} tier={response.get('tier_used')} latency={latency_ms}ms")
        else:
            fail_count += 1
            print(f"FAIL  {qid}: {failures}", file=sys.stderr)

    summary = {
        "url": args.url,
        "total": len(results),
        "passed": len(results) - fail_count,
        "failed": fail_count,
        "results": results,
    }
    if args.json_out:
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if fail_count > 0:
        print(f"\nFAIL: {fail_count}/{len(results)} queries failed", file=sys.stderr)
        return 1
    print(f"\nPASS: {len(results)}/{len(results)} queries passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
