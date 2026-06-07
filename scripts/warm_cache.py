"""Pre-warm the Tier-3 LLM cache (VPS rollout HANDOFF #5).

Mines the top recent Tier-3 queries from ``chat_logs`` (last N days, assistant
turns) plus a small static seasonal list (``scripts/warm_queries.txt``), then POSTs
each to the **public** ``/api/chat`` endpoint with a dedicated
``session_id=cache-warmer`` at low concurrency. Exercising the real endpoint
fills the cache exactly as production would — no direct DB writes.

So the first real user of the day doesn't pay full Tier-3 latency.

Read-only against the DB (query mining + a cache-key existence check); the only
writes happen server-side via the normal request path. Already-cached queries
(today's exact-key entry present) are skipped without a POST.

Usage::

    python -m scripts.warm_cache --dry-run                 # list what would warm
    python -m scripts.warm_cache                            # warm via localhost
    python -m scripts.warm_cache --base-url https://...     # warm a deployment
    python -m scripts.warm_cache --max-queries 30 --rps 0.5

Exit status: 0 normal; 1 unexpected error; 2 bad arguments.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("scripts.warm_cache")

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_SEASONAL_PATH = Path(__file__).resolve().parent / "warm_queries.txt"
_WARMER_SESSION = "cache-warmer"
_TIER3_VALUES = ("3", "tier3")


def load_seasonal(path: Path = _SEASONAL_PATH) -> list[str]:
    """Static seasonal queries; blank lines and ``#`` comments ignored."""
    if not path.is_file():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def gather_db_queries(db, *, days: int, limit: int) -> list[str]:
    """Top recent Tier-3 assistant-turn queries, most frequent first."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from app.db.models import ChatLog

    # chat_logs.created_at is naive-UTC; compare against a naive-UTC cutoff.
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rows = db.execute(
        select(ChatLog.normalized_query, func.count().label("c"))
        .where(
            ChatLog.role == "assistant",
            ChatLog.tier_used.in_(_TIER3_VALUES),
            ChatLog.normalized_query.isnot(None),
            ChatLog.normalized_query != "",
            ChatLog.created_at >= cutoff,
        )
        .group_by(ChatLog.normalized_query)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


def dedupe_normalized(queries: list[str], *, cap: int) -> list[str]:
    """Normalize, drop empties + duplicates (first occurrence wins), cap length."""
    from app.chat.normalizer import normalize

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        try:
            nq = normalize(q or "")
        except Exception:
            continue
        if not nq or nq in seen:
            continue
        seen.add(nq)
        out.append(nq)
        if len(out) >= cap:
            break
    return out


def is_cached(db, normalized_query: str) -> bool:
    """True if today's exact-key cache row exists and is unexpired. READ-ONLY.

    Mirrors the Tier-3 key (``make_cache_key(query, {"_today": <today>})`` with
    no onboarding hints) but does a plain SELECT — ``llm_cache.lookup`` would
    bump hit telemetry, which is a write.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.chat.llm_cache import make_cache_key
    from app.core.timezone import now_lake_havasu
    from app.db.models import LlmResponseCache

    key = make_cache_key(normalized_query, {"_today": now_lake_havasu().date().isoformat()})
    row = db.scalars(
        select(LlmResponseCache).where(LlmResponseCache.cache_key == key).limit(1)
    ).first()
    if row is None:
        return False
    ttl = row.ttl_until
    if ttl is None:
        return True
    if ttl.tzinfo is None:
        ttl = ttl.replace(tzinfo=timezone.utc)
    return ttl >= datetime.now(timezone.utc)


def warm_one(base_url: str, query: str, *, session_id: str, timeout: float) -> tuple[str, int]:
    """POST one query to /api/chat; return (tier_used, llm_tokens_used)."""
    import httpx

    url = base_url.rstrip("/") + "/api/chat"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json={"query": query, "session_id": session_id})
        resp.raise_for_status()
        body = resp.json()
    return str(body.get("tier_used") or ""), int(body.get("llm_tokens_used") or 0)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pre-warm the Tier-3 LLM cache (read-only DB).")
    p.add_argument("--base-url", default=_DEFAULT_BASE_URL, help=f"default {_DEFAULT_BASE_URL}")
    p.add_argument("--max-queries", type=int, default=50, help="budget guard (default 50)")
    p.add_argument("--days", type=int, default=14, help="chat_logs lookback window (default 14)")
    p.add_argument("--rps", type=float, default=1.0, help="requests/sec throttle (default 1)")
    p.add_argument("--timeout", type=float, default=30.0, help="per-request timeout seconds")
    p.add_argument("--session-id", default=_WARMER_SESSION)
    p.add_argument("--dry-run", action="store_true", help="list resolved queries; do not POST")
    p.add_argument("--verbose", "-v", action="store_true", help="INFO logging to stderr")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    if args.max_queries <= 0:
        print("--max-queries must be positive", file=sys.stderr)
        return 2

    from app.db.database import SessionLocal

    try:
        with SessionLocal() as db:
            db_q = gather_db_queries(db, days=args.days, limit=args.max_queries)
            queries = dedupe_normalized(db_q + load_seasonal(), cap=args.max_queries)

            if args.dry_run:
                print(f"# {len(queries)} queries would be warmed (max {args.max_queries}):")
                for q in queries:
                    print(("[cached] " if is_cached(db, q) else "[warm]   ") + q)
                return 0

            warmed = skipped = errors = total_tokens = 0
            delay = 1.0 / args.rps if args.rps > 0 else 0.0
            for q in queries:
                if is_cached(db, q):
                    skipped += 1
                    continue
                try:
                    tier, tokens = warm_one(
                        args.base_url, q, session_id=args.session_id, timeout=args.timeout
                    )
                    total_tokens += tokens
                    warmed += 1
                    logger.info("warmed (tier=%s tokens=%s): %s", tier, tokens, q)
                except Exception:
                    errors += 1
                    logger.exception("warm failed: %s", q)
                if delay:
                    time.sleep(delay)
    except Exception:
        logger.exception("warm_cache: run failed")
        return 1

    print(
        f"warm_cache done: warmed={warmed} skipped(cached)={skipped} "
        f"errors={errors} tokens={total_tokens}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
