"""Tests for ``app.chat.llm_cache`` — exact-match + §4.3 similarity fallback.

OpenAI embedding API is mocked at the canonical seam
(``app.chat.llm_cache.OpenAI``) so tests run offline. The cosine + JSON
serialize/deserialize helpers are pure functions tested directly.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.chat.llm_cache as llm_cache
from app.chat.llm_cache import (
    SIMILARITY_THRESHOLD,
    _cosine_similarity,
    _deserialize_embedding,
    _serialize_embedding,
    lookup,
    make_cache_key,
    store,
)
from app.db.database import SessionLocal
from app.db.models import LlmResponseCache


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        # Clean cache rows so tests don't leak state across runs.
        s.query(LlmResponseCache).delete()
        s.commit()
        s.close()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors_one() -> None:
    v = [1.0, 0.0, 0.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_zero() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors_negative_one() -> None:
    a = [1.0, 1.0]
    b = [-1.0, -1.0]
    assert _cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_handles_empty_and_mismatched() -> None:
    assert _cosine_similarity([], [1.0]) == 0.0
    assert _cosine_similarity([1.0], []) == 0.0
    assert _cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_similarity_zero_norm_returns_zero() -> None:
    """Zero-vector inputs would otherwise divide-by-zero — must return 0.0."""
    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine_similarity([1.0, 1.0], [0.0, 0.0]) == 0.0


def test_serialize_deserialize_round_trip() -> None:
    vec = [0.1, -0.2, 0.3, 1e-9]
    blob = _serialize_embedding(vec)
    assert blob is not None
    out = _deserialize_embedding(blob)
    assert out is not None
    assert len(out) == len(vec)
    for a, b in zip(vec, out):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def test_serialize_none_returns_none() -> None:
    assert _serialize_embedding(None) is None


def test_deserialize_handles_corrupt_input() -> None:
    """Corrupted JSON / wrong shape / non-numeric values all return None so a
    bad row simply skips the similarity scan rather than crashing it."""
    assert _deserialize_embedding(None) is None
    assert _deserialize_embedding("") is None
    assert _deserialize_embedding("not json") is None
    assert _deserialize_embedding('"a string"') is None
    assert _deserialize_embedding('{"k": 1}') is None  # dict, not list
    assert _deserialize_embedding('["not", "numeric"]') is None


# ---------------------------------------------------------------------------
# _compute_query_embedding (OpenAI seam mocked)
# ---------------------------------------------------------------------------


def _embedding_response(vec: list[float]) -> SimpleNamespace:
    """OpenAI embeddings response shape: data[0].embedding."""
    return SimpleNamespace(data=[SimpleNamespace(embedding=vec)])


def test_compute_query_embedding_returns_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([0.1, 0.2, 0.3])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        out = llm_cache._compute_query_embedding("hello world")
    assert out == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_called_once()
    kw = fake_client.embeddings.create.call_args.kwargs
    assert kw["model"] == llm_cache.EMBEDDING_MODEL
    assert kw["input"] == "hello world"


def test_compute_query_embedding_returns_none_on_empty_query() -> None:
    assert llm_cache._compute_query_embedding("") is None
    assert llm_cache._compute_query_embedding("   ") is None


def test_compute_query_embedding_returns_none_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_cache._compute_query_embedding("anything") is None


def test_compute_query_embedding_swallows_api_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding API is best-effort — exceptions must not propagate."""
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = RuntimeError("network")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        out = llm_cache._compute_query_embedding("hello")
    assert out is None


def test_compute_query_embedding_handles_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = SimpleNamespace(data=[])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        assert llm_cache._compute_query_embedding("hello") is None


# ---------------------------------------------------------------------------
# lookup — exact-match path (regression)
# ---------------------------------------------------------------------------


def test_lookup_exact_match_returns_response(db: Session) -> None:
    """With no normalized_query passed, the legacy exact-key behavior is
    preserved verbatim — embedding fallback never fires."""
    key = make_cache_key("the query", {"_today": "2026-05-08"})
    store(db, key, "the query", {"_today": "2026-05-08"}, "the cached answer", "tier3")
    assert lookup(db, key) == "the cached answer"


def test_lookup_exact_match_increments_hit_count(db: Session) -> None:
    key = make_cache_key("hit-counter", {"_today": "2026-05-08"})
    store(db, key, "hit-counter", {"_today": "2026-05-08"}, "answer", "tier3")
    lookup(db, key)
    lookup(db, key)
    # P1-14: hit telemetry is persisted on an isolated session, so this session's
    # identity-mapped row is stale until expired. (On SQLite the read happened to
    # see the new value; Postgres does not refresh the cached instance.)
    db.expire_all()
    row = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()
    assert row.hit_count == 2
    assert row.last_hit_at is not None


def test_lookup_returns_none_for_missing_key(db: Session) -> None:
    assert lookup(db, "nonexistent_key_no_query") is None


def test_lookup_returns_none_for_empty_key(db: Session) -> None:
    assert lookup(db, "") is None


def test_lookup_skips_ttl_expired_row(db: Session) -> None:
    """An expired exact-match row is treated as a miss; with no
    normalized_query, no similarity fallback fires either."""
    key = make_cache_key("expired", {})
    store(db, key, "expired", {}, "stale answer", "tier3")
    # Force expiry by direct DB write.
    row = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()
    row.ttl_until = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    assert lookup(db, key) is None


# ---------------------------------------------------------------------------
# lookup — §4.3 similarity fallback
# ---------------------------------------------------------------------------


def _seed_cache_row(
    db: Session,
    *,
    query: str,
    response_text: str,
    embedding: list[float] | None,
    rubric_version: str | None = None,
    ttl_offset_days: float = 7.0,
    cache_key: str | None = None,
) -> LlmResponseCache:
    """Insert a cache row with a hand-picked embedding so similarity tests are
    deterministic (no real OpenAI call)."""
    key = cache_key or make_cache_key(query, {"_seed": query})
    row = LlmResponseCache(
        cache_key=key,
        normalized_query=query[:500].lower(),
        context_hash="seed_ctx",
        rubric_version=rubric_version or llm_cache._RUBRIC_VERSION,
        response_text=response_text,
        tier_used="tier3",
        created_at=datetime.now(UTC),
        hit_count=0,
        last_hit_at=None,
        ttl_until=datetime.now(UTC) + timedelta(days=ttl_offset_days),
        query_embedding=_serialize_embedding(embedding),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_similarity_lookup_hits_when_threshold_exceeded(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored row with embedding = [1, 0]; incoming query embedding ~ [1, 0]
    → cosine ≈ 1.0 → above threshold → similarity hit."""
    seeded = _seed_cache_row(
        db,
        query="what is fun for kids in havasu",
        response_text="kid-friendly answer",
        embedding=[1.0, 0.0, 0.0],
    )

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([0.99, 0.01, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        # Use a different cache_key (forces the exact path to miss); pass the
        # normalized_query so the similarity scan kicks in.
        result = lookup(db, "no_such_exact_key_zzz", normalized_query="paraphrase of fun")
    assert result == "kid-friendly answer"

    # Telemetry on the matched row should have bumped.
    db.refresh(seeded)
    assert seeded.hit_count == 1
    assert seeded.last_hit_at is not None


def test_similarity_lookup_misses_below_threshold(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cosine similarity 0.5 is below the 0.9 threshold — no hit."""
    _seed_cache_row(
        db,
        query="seed query",
        response_text="seed answer",
        embedding=[1.0, 0.0],
    )
    fake_client = MagicMock()
    # Vectors at ~60° → cosine = 0.5
    fake_client.embeddings.create.return_value = _embedding_response([0.5, math.sqrt(0.75)])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "no_such_exact_key", normalized_query="distant query")
    assert result is None


def test_similarity_lookup_skips_rows_without_embedding(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-v2 rows (query_embedding = NULL) must be skipped during the scan
    even if the SQL filter somehow surfaces them — defensive."""
    _seed_cache_row(
        db,
        query="legacy",
        response_text="legacy answer",
        embedding=None,
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "different_key", normalized_query="incoming")
    assert result is None


def test_similarity_lookup_skips_expired_rows(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """An expired row must not be returned even if its embedding is identical
    to the incoming query."""
    _seed_cache_row(
        db,
        query="stale",
        response_text="stale answer",
        embedding=[1.0, 0.0],
        ttl_offset_days=-1.0,  # already expired
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "different_key", normalized_query="match")
    assert result is None


def test_similarity_lookup_skips_rubric_version_mismatch(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows from a previous prompt-revision must not surface, even with a
    perfect-similarity embedding match."""
    _seed_cache_row(
        db,
        query="old rubric",
        response_text="old answer",
        embedding=[1.0, 0.0],
        rubric_version="deadbeef" * 2,  # arbitrary non-current version
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "different_key", normalized_query="match")
    assert result is None


def test_similarity_lookup_picks_best_match_among_candidates(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple rows pass the threshold; the one with the highest similarity
    wins."""
    _seed_cache_row(
        db,
        query="okay match",
        response_text="okay-match answer",
        embedding=[0.95, 0.31],  # ~0.95 cosine vs [1, 0]
        cache_key="row_okay",
    )
    _seed_cache_row(
        db,
        query="great match",
        response_text="great-match answer",
        embedding=[0.999, 0.045],  # ~0.999 cosine vs [1, 0]
        cache_key="row_great",
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "different_key", normalized_query="incoming")
    assert result == "great-match answer"


def test_lookup_no_normalized_query_skips_similarity_path(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Callers that omit normalized_query (e.g. cache hygiene tooling) must
    not trigger an embedding API call — exact-match-only behavior."""
    _seed_cache_row(
        db,
        query="seed",
        response_text="seed answer",
        embedding=[1.0, 0.0],
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "no_such_key")
    assert result is None
    fake_client.embeddings.create.assert_not_called()


def test_lookup_falls_back_to_similarity_on_exact_miss(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact-key miss but normalized_query provided → similarity scan runs."""
    _seed_cache_row(
        db,
        query="seeded",
        response_text="seeded answer",
        embedding=[1.0, 0.0],
    )
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([1.0, 0.0])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        result = lookup(db, "absent_key", normalized_query="anything")
    assert result == "seeded answer"
    fake_client.embeddings.create.assert_called_once()


# ---------------------------------------------------------------------------
# store — embedding writes (or NULL on failure)
# ---------------------------------------------------------------------------


def test_store_writes_embedding_when_api_succeeds(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _embedding_response([0.5, 0.5, 0.5])
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        key = make_cache_key("store-with-emb", {})
        store(db, key, "store-with-emb", {}, "answer text", "tier3")
    row = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()
    assert row.query_embedding is not None
    decoded = _deserialize_embedding(row.query_embedding)
    assert decoded == [0.5, 0.5, 0.5]


def test_store_writes_null_embedding_when_api_fails(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Embedding API failure must not block the cache write — the row still
    serves exact-match hits, just no similarity match for it."""
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = RuntimeError("api boom")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_cache, "OpenAI", return_value=fake_client):
        key = make_cache_key("store-no-emb", {})
        store(db, key, "store-no-emb", {}, "answer text", "tier3")
    row = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()
    assert row.query_embedding is None
    assert row.response_text == "answer text"


def test_store_skips_empty_response() -> None:
    """No-op for empty response_text — kept here as a regression hedge."""
    db = SessionLocal()
    try:
        store(db, "any_key", "any query", {}, "", "tier3")
        # Should be a no-op; no exception, no row inserted.
        rows = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == "any_key").all()
        assert rows == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Threshold sanity check
# ---------------------------------------------------------------------------


def test_similarity_threshold_is_strict_enough() -> None:
    """Document the threshold's intent: paraphrase-tight, not synonym-broad.
    If this assertion ever flips intentionally, edit the comment in
    llm_cache.py and the docstring at the top of this file too."""
    assert SIMILARITY_THRESHOLD >= 0.85
    assert SIMILARITY_THRESHOLD <= 0.95


# ---------------------------------------------------------------------------
# Lane B-1 -- in-request embedding memo + deferred store
# ---------------------------------------------------------------------------


def test_lookup_with_embedding_returns_vector_on_miss(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lookup_with_embedding returns the computed vector when similarity misses."""
    calls: list[str] = []

    def fake_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.01] * 1536

    monkeypatch.setattr(llm_cache, "_compute_query_embedding", fake_embed)

    text, vec = llm_cache.lookup_with_embedding(
        db,
        cache_key="nonexistent_b1_test_key_zzzzzzzzzzzzzzzz",
        normalized_query="lane b-1 sentinel query",
    )
    assert text is None, "no cache row exists yet"
    assert vec is not None, "must return the embedding for the caller to reuse"
    assert len(calls) == 1, f"embedding should run once, ran {len(calls)} times"


def test_store_with_embedding_skips_embed_call_when_precomputed(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """store_with_embedding does not re-embed when precomputed_embedding is passed."""
    calls: list[str] = []

    def fake_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.02] * 1536

    monkeypatch.setattr(llm_cache, "_compute_query_embedding", fake_embed)

    fake_vec = [0.99] * 1536
    llm_cache.store_with_embedding(
        db,
        cache_key="b1_store_key_yyyyyyyyyyyyyyyy",
        normalized_query="b1 store test",
        context={"k": "v"},
        response_text="answer",
        tier_used="tier3",
        precomputed_embedding=fake_vec,
    )
    assert len(calls) == 0, "embedding API must not be called when vector provided"


def test_miss_path_runs_embedding_once_end_to_end(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Combined: lookup_with_embedding + store_with_embedding -> exactly one embed call."""
    calls: list[str] = []

    def fake_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.03] * 1536

    monkeypatch.setattr(llm_cache, "_compute_query_embedding", fake_embed)

    text, vec = llm_cache.lookup_with_embedding(
        db,
        cache_key="b1_combined_key_xxxxxxxxxxxxxxxx",
        normalized_query="b1 combined",
    )
    assert text is None
    llm_cache.store_with_embedding(
        db,
        cache_key="b1_combined_key_xxxxxxxxxxxxxxxx",
        normalized_query="b1 combined",
        context={},
        response_text="answer",
        tier_used="tier3",
        precomputed_embedding=vec,
    )
    assert len(calls) == 1, f"end-to-end miss should embed once, embedded {len(calls)} times"


def test_legacy_lookup_and_store_still_work(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Backward compat: callers that still use lookup() + store() must keep working."""
    monkeypatch.setattr(llm_cache, "_compute_query_embedding", lambda t: [0.04] * 1536)

    out = llm_cache.lookup(
        db,
        cache_key="b1_legacy_key_wwwwwwwwwwwwwwww",
        normalized_query="b1 legacy",
    )
    assert out is None
    llm_cache.store(
        db,
        cache_key="b1_legacy_key_wwwwwwwwwwwwwwww",
        normalized_query="b1 legacy",
        context={},
        response_text="answer",
        tier_used="tier3",
    )
    hit = llm_cache.lookup(db, cache_key="b1_legacy_key_wwwwwwwwwwwwwwww")
    assert hit == "answer"


def test_bump_telemetry_does_not_commit_callers_pending_state(db: Session) -> None:
    """P1-14: _bump_hit_telemetry persists the hit on an isolated session, so it
    must NOT commit unrelated pending state on the caller's session."""
    key = make_cache_key("p114", {})
    store(db, key, "p114", {}, "answer", "tier3")
    row = db.query(LlmResponseCache).filter(LlmResponseCache.cache_key == key).one()

    # An unrelated, uncommitted row on the caller's session.
    pending_key = "p114_unrelated_pending"
    db.add(
        LlmResponseCache(
            cache_key=pending_key,
            normalized_query="x",
            context_hash="c",
            rubric_version=llm_cache._RUBRIC_VERSION,
            response_text="pending",
            tier_used="tier3",
            hit_count=0,
        )
    )

    llm_cache._bump_hit_telemetry(db, row)

    # A fresh session must NOT see the unrelated pending row — the old code's
    # db.commit() would have durably flushed it mid-request.
    with SessionLocal() as other:
        leaked = (
            other.query(LlmResponseCache)
            .filter(LlmResponseCache.cache_key == pending_key)
            .first()
        )
    assert leaked is None, "_bump committed the caller's unrelated pending row"
    db.rollback()  # discard the pending row so teardown stays clean
