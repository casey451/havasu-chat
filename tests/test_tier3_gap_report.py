"""Tests for scripts/tier3_gap_report.py.

Covers cosine, the greedy clustering + ranking (with an injected deterministic
vectorizer so nothing hits the embedding API), and the DB aggregation/filtering
in load_gap_queries (tier filter, window, null/short exclusion, count rollup).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import ChatLog
from scripts import tier3_gap_report as gr

# ---------------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------------


def test_cosine_identical_orthogonal_degenerate() -> None:
    assert gr._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert gr._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert gr._cosine([], [1.0]) == 0.0
    assert gr._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# ---------------------------------------------------------------------------
# clustering + ranking (injected vectorizer — no network)
# ---------------------------------------------------------------------------

_VEC = {
    "best tacos": [1.0, 0.0, 0.0],
    "good tacos": [0.99, 0.01, 0.0],  # ~parallel to best tacos -> same cluster
    "kayak rental": [0.0, 1.0, 0.0],  # orthogonal -> own cluster
    "boat rental": [0.0, 0.99, 0.02],  # ~parallel to kayak rental
}


def _vec(q: str) -> list[float]:
    return _VEC[q]


def test_cluster_merges_parallel_splits_orthogonal() -> None:
    queries = [
        gr.GapQuery("best tacos", 5),
        gr.GapQuery("good tacos", 3),
        gr.GapQuery("kayak rental", 4),
        gr.GapQuery("boat rental", 1),
    ]
    clusters = gr.cluster_queries(queries, _vec, threshold=0.82)
    assert len(clusters) == 2
    by_rep = {c.representative: c for c in clusters}
    assert by_rep["best tacos"].distinct == 2
    assert by_rep["best tacos"].total == 8
    assert by_rep["kayak rental"].distinct == 2
    assert by_rep["kayak rental"].total == 5


def test_cluster_representative_is_first_member() -> None:
    # Highest-count arrives first (caller sorts count-desc) -> anchors the cluster.
    clusters = gr.cluster_queries(
        [gr.GapQuery("best tacos", 9), gr.GapQuery("good tacos", 2)], _vec, threshold=0.82
    )
    assert len(clusters) == 1
    assert clusters[0].representative == "best tacos"


def test_high_threshold_keeps_everything_separate() -> None:
    # "best tacos" vs "good tacos" cosine ~0.99995; a threshold above that must
    # refuse to merge even near-parallel vectors.
    clusters = gr.cluster_queries(
        [gr.GapQuery("best tacos", 1), gr.GapQuery("good tacos", 1)], _vec, threshold=0.99999
    )
    assert len(clusters) == 2


def test_rank_gaps_filters_and_sorts() -> None:
    singleton = gr.Cluster("lonely", [gr.GapQuery("lonely", 50)])
    small = gr.Cluster("a", [gr.GapQuery("a", 2), gr.GapQuery("a2", 1)])  # total 3
    big = gr.Cluster("b", [gr.GapQuery("b", 5), gr.GapQuery("b2", 4)])  # total 9
    ranked = gr.rank_gaps([singleton, small, big], min_cluster=2)
    assert [c.representative for c in ranked] == ["b", "a"]  # singleton dropped, big first


# ---------------------------------------------------------------------------
# load_gap_queries (DB)
# ---------------------------------------------------------------------------


def _log(session: str, *, q: str | None, tier: str, days_ago: int = 0, mode: str = "ask") -> ChatLog:
    return ChatLog(
        id=str(uuid.uuid4()),
        session_id=session,
        message="probe",
        role="assistant",
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago),
        mode=mode,
        sub_intent="OPEN_ENDED",
        tier_used=tier,
        normalized_query=q,
    )


def test_load_gap_queries_filters_and_aggregates() -> None:
    marker = uuid.uuid4().hex[:8]
    sess = f"test-gap-{marker}"
    taco = f"zz {marker} best tacos"
    kayak = f"zz {marker} kayak rental"
    try:
        with SessionLocal() as db:
            db.add_all(
                [
                    _log(sess, q=taco, tier="3"),
                    _log(sess, q=taco, tier="3"),
                    _log(sess, q=taco, tier="gap_template"),  # counts toward taco (3 total)
                    _log(sess, q=kayak, tier="3"),
                    _log(sess, q=f"zz {marker} tier1 excluded", tier="1"),  # wrong tier
                    _log(sess, q=f"zz {marker} too old", tier="3", days_ago=60),  # outside window
                    _log(sess, q=None, tier="3"),  # null query
                ]
            )
            db.commit()
        with SessionLocal() as db:
            rows = {gq.query: gq for gq in gr.load_gap_queries(db, days=30) if marker in gq.query}
        assert rows[taco].count == 3
        assert rows[kayak].count == 1
        assert not any("tier1 excluded" in q for q in rows)
        assert not any("too old" in q for q in rows)
    finally:
        with SessionLocal() as db:
            db.execute(delete(ChatLog).where(ChatLog.session_id == sess))
            db.commit()
