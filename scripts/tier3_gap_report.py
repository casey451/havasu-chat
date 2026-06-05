"""Tier-3 / gap-template demand report — find the queries the intent layer misses.

Every chat turn is logged with the tier that answered it (``chat_logs.tier_used``:
'1' regex, '2' DB lookup, '3' LLM synthesis, 'gap_template' canned no-answer).
Tier-3 and gap_template are the EXPENSIVE / UNSATISFYING tail: a question the
cheap deterministic layers couldn't handle. This script clusters those queries so
recurring gaps surface as candidate new intents (which are CODE in this repo —
``tier1_templates`` regexes, ``intents/resolver``, ``intents/dicts`` — so the
output is review material for a human-authored PR, not an automated write).

Thin by design (discovery plan workstream B): one file, one workflow, a ranked
report artifact. PRE-LAUNCH CAVEAT: tier-3 traffic today is mostly dev/test
noise, so treat early reports as a smoke test of the pipeline, not a roadmap.
Note also that ``USE_INTENT_LAYER`` defaults OFF in prod — enabling it is itself
probably the single biggest tier-3-shrinking lever, and it's already built.

Read-only: SELECTs chat_logs, embeds query strings (text-embedding-3-small,
~$0.001/run), writes nothing to the DB.

Usage
-----
    python scripts/tier3_gap_report.py
    python scripts/tier3_gap_report.py --days 14 --min-cluster 3 --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.extraction import generate_embedding  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import ChatLog  # noqa: E402

GAP_TIERS = ("3", "gap_template")
DEFAULT_DAYS = 30
DEFAULT_THRESHOLD = 0.82  # cosine; queries above this fold into one cluster
DEFAULT_MIN_CLUSTER = 2  # only report a cluster with at least this many distinct queries


@dataclass(frozen=True)
class GapQuery:
    query: str
    count: int  # occurrences in the window
    mode: str | None = None
    sub_intent: str | None = None


@dataclass
class Cluster:
    representative: str  # the highest-count member's query text
    members: list[GapQuery] = field(default_factory=list)

    @property
    def distinct(self) -> int:
        return len(self.members)

    @property
    def total(self) -> int:
        return sum(m.count for m in self.members)


# A vectorizer maps a string to an embedding. Default hits text-embedding-3-small
# (falling back to a deterministic local vector when no key); tests inject a stub.
Vectorizer = Callable[[str], list[float]]


def load_gap_queries(db: Session, *, days: int = DEFAULT_DAYS, limit: int | None = None) -> list[GapQuery]:
    """Distinct tier-3 / gap_template queries in the window, by occurrence count.

    Aggregates on the lowercased/trimmed ``normalized_query`` so "Best Tacos" and
    "best tacos " collapse. Keeps a representative mode/sub_intent per group.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    qkey = func.lower(func.trim(ChatLog.normalized_query)).label("qkey")
    stmt = (
        select(
            qkey,
            func.count().label("cnt"),
            func.max(ChatLog.mode).label("mode"),
            func.max(ChatLog.sub_intent).label("sub_intent"),
        )
        .where(ChatLog.tier_used.in_(GAP_TIERS))
        .where(ChatLog.normalized_query.is_not(None))
        .where(func.length(func.trim(ChatLog.normalized_query)) >= 2)
        .where(ChatLog.created_at >= cutoff)
        .group_by(qkey)
        .order_by(func.count().desc(), qkey)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    out: list[GapQuery] = []
    for qkey_v, cnt, mode, sub_intent in db.execute(stmt).all():
        if not qkey_v or not str(qkey_v).strip():
            continue
        out.append(GapQuery(query=str(qkey_v).strip(), count=int(cnt), mode=mode, sub_intent=sub_intent))
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def cluster_queries(
    queries: list[GapQuery],
    vectorize: Vectorizer = generate_embedding,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Cluster]:
    """Greedy single-pass clustering by cosine similarity to a cluster's
    representative (its first, highest-count member). O(n*k); fine for the small
    pre-launch query volume. Queries should arrive count-desc so the most common
    phrasing anchors each cluster."""
    clusters: list[Cluster] = []
    reps: list[list[float]] = []  # parallel to clusters: representative embeddings
    for gq in queries:
        vec = vectorize(gq.query)
        best_i, best_sim = -1, threshold
        for i, rep_vec in enumerate(reps):
            sim = _cosine(vec, rep_vec)
            if sim >= best_sim:
                best_i, best_sim = i, sim
        if best_i >= 0:
            clusters[best_i].members.append(gq)
        else:
            clusters.append(Cluster(representative=gq.query, members=[gq]))
            reps.append(vec)
    return clusters


def rank_gaps(clusters: list[Cluster], *, min_cluster: int = DEFAULT_MIN_CLUSTER) -> list[Cluster]:
    """Clusters worth a human look: at least ``min_cluster`` distinct queries,
    ranked by total occurrences then breadth."""
    keep = [c for c in clusters if c.distinct >= min_cluster]
    keep.sort(key=lambda c: (c.total, c.distinct), reverse=True)
    return keep


def _mode_summary(c: Cluster) -> str:
    modes = Counter(m.mode for m in c.members if m.mode)
    return ", ".join(f"{k}×{v}" for k, v in modes.most_common(3)) or "—"


def run(*, days: int, threshold: float, min_cluster: int, limit: int | None) -> tuple[list[GapQuery], list[Cluster]]:
    with SessionLocal() as db:
        queries = load_gap_queries(db, days=days, limit=limit)
    clusters = cluster_queries(queries, threshold=threshold)
    return queries, rank_gaps(clusters, min_cluster=min_cluster)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cluster tier-3 / gap_template queries into demand gaps")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"Look-back window (default {DEFAULT_DAYS})")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Cosine merge threshold")
    ap.add_argument("--min-cluster", type=int, default=DEFAULT_MIN_CLUSTER, help="Min distinct queries to report")
    ap.add_argument("--limit", type=int, default=None, help="Cap distinct queries embedded")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    queries, gaps = run(
        days=args.days, threshold=args.threshold, min_cluster=args.min_cluster, limit=args.limit
    )
    total_q = sum(q.count for q in queries)

    if args.as_json:
        print(
            json.dumps(
                {
                    "window_days": args.days,
                    "distinct_queries": len(queries),
                    "total_occurrences": total_q,
                    "gap_clusters": len(gaps),
                    "clusters": [
                        {
                            "representative": c.representative,
                            "distinct": c.distinct,
                            "total": c.total,
                            "members": [
                                {"query": m.query, "count": m.count, "mode": m.mode} for m in c.members
                            ],
                        }
                        for c in gaps
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(f"Tier-3 / gap-template demand report — last {args.days} days")
    print(f"  {len(queries)} distinct gap queries · {total_q} occurrences · {len(gaps)} recurring clusters")
    if not queries:
        print("  No tier-3/gap_template traffic in the window (expected pre-launch).")
        return 0
    print("-" * 72)
    for i, c in enumerate(gaps, 1):
        print(f"{i:>3}. [{c.total:>3}× / {c.distinct} phrasings] {c.representative}")
        print(f"      modes: {_mode_summary(c)}")
        for m in sorted(c.members, key=lambda x: x.count, reverse=True)[:5]:
            if m.query != c.representative:
                print(f"        · {m.query}  (×{m.count})")
    if not gaps:
        print("  No recurring clusters above the min-cluster threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
