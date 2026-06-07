"""LLM response cache (Stream C, lever Cache)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select, text, update

from app.core import embeddings
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.models import LlmResponseCache

DEFAULT_TTL_DAYS = 7
SIMILARITY_THRESHOLD = 0.9
SIMILARITY_SCAN_LIMIT = 200

# pgvector path (HANDOFF #2): native ANN similarity on Postgres when the
# ``vector`` extension + ``llm_response_cache.embedding`` column exist
# (migration a7c9e1f3b5d7). Fixed at 1536 dims (text-embedding-3-small);
# switching EMBEDDINGS_PROVIDER to a different-dim model bypasses this path
# (and invalidates stored vectors -- re-embed or clear the cache).
EMBEDDING_DIM = 1536
PGVECTOR_TOPK = 10

# Per-engine probe cache: engine-url -> bool. Probes once per process; a
# probe *exception* is not cached so a transient DB hiccup can't disable
# the pgvector path for the process lifetime.
_PGVECTOR_AVAILABLE: dict = {}


def _compute_rubric_version() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    prompts_dir = repo_root / "prompts"
    files = ("system_prompt.txt", "tier2_formatter.txt", "tier2_parser.txt")
    h = hashlib.sha256()
    for fname in files:
        path = prompts_dir / fname
        if path.is_file():
            try:
                h.update(fname.encode("utf-8"))
                h.update(b":")
                h.update(path.read_bytes())
                h.update(b"\n")
            except OSError:
                continue
    return h.hexdigest()[:16]


_RUBRIC_VERSION = _compute_rubric_version()


def _hash_context(context):
    if not context:
        return "no_ctx"
    items = sorted((str(k), str(v)) for k, v in context.items() if v is not None and v != "")
    if not items:
        return "no_ctx"
    h = hashlib.sha256()
    for k, v in items:
        h.update(k.encode("utf-8"))
        h.update(b"=")
        h.update(v.encode("utf-8"))
        h.update(b";")
    return h.hexdigest()[:12]


def make_cache_key(normalized_query, context):
    from app.chat.normalizer import canonicalize_for_cache

    nq = canonicalize_for_cache((normalized_query or "").strip().lower())
    ctx_hash = _hash_context(context)
    h = hashlib.sha256()
    h.update(nq.encode("utf-8"))
    h.update(b"|")
    h.update(ctx_hash.encode("utf-8"))
    h.update(b"|")
    h.update(_RUBRIC_VERSION.encode("utf-8"))
    return h.hexdigest()[:32]


def _compute_query_embedding(text):
    """Query embedding for similarity fallback, via the provider abstraction.

    Returns ``None`` on empty input / missing key / failure (caller treats
    ``None`` as "no similarity lookup"). Provider routing + the patchable
    ``OpenAI`` seam now live in ``app.core.embeddings``.
    """
    return embeddings.embed(text)


def _cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _serialize_embedding(vec):
    if vec is None:
        return None
    try:
        return json.dumps(vec)
    except (TypeError, ValueError):
        return None


def _deserialize_embedding(s):
    if not s:
        return None
    try:
        out = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(out, list):
        return None
    try:
        return [float(x) for x in out]
    except (TypeError, ValueError):
        return None


def _bump_hit_telemetry(db, row):
    # P1-14: persist hit telemetry on its OWN short-lived session. The previous
    # code called ``db.commit()`` on the caller's request-scoped session, which
    # durably flushes any *unrelated* pending state mid-request. An isolated
    # session + atomic UPDATE keeps the increment without that side effect.
    _ = db
    from app.db.database import SessionLocal

    try:
        with SessionLocal() as s:
            s.execute(
                update(LlmResponseCache)
                .where(LlmResponseCache.id == row.id)
                .values(
                    hit_count=(LlmResponseCache.hit_count + 1),
                    last_hit_at=datetime.now(UTC),
                )
            )
            s.commit()
    except Exception:
        logging.exception("llm_cache: hit-count update failed")


# Time-sensitive queries must not match a cached row from another day. The
# exact-key path already scopes by date (the cache key embeds today's Lake
# Havasu date), but the similarity fallback only filters rubric_version + TTL —
# so "what's happening tonight" embeds ~1.0 against yesterday's row and serves a
# stale answer up to the 7-day TTL old. Guard the similarity path with a
# same-day check for these queries. (C2)
_TIME_SENSITIVE_RE = re.compile(
    r"\b("
    r"tonight|today|tomorrow|now|currently|right now|"
    r"this morning|this afternoon|this evening|this weekend|this week|"
    r"happening|open now|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend"
    r")\b"
)


def _is_time_sensitive(query: str) -> bool:
    return bool(_TIME_SENSITIVE_RE.search((query or "").lower()))


def _row_lake_havasu_date(dt):
    """Lake Havasu calendar date for a cache row's ``created_at`` (naive UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LAKE_HAVASU_TZ).date()



def _vector_literal(vec):
    """pgvector text literal ('[f1,f2,...]') for CAST(:q AS vector) binding."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _pgvector_available(db) -> bool:
    """True when the bind is Postgres with the vector extension AND the
    ``embedding`` column present (i.e. migration a7c9e1f3b5d7 has run)."""
    try:
        bind = db.get_bind()
    except Exception:
        return False
    if bind is None or bind.dialect.name != "postgresql":
        return False
    key = str(getattr(bind, "url", "postgresql"))
    cached = _PGVECTOR_AVAILABLE.get(key)
    if cached is not None:
        return cached
    try:
        has_ext = bool(
            db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
        )
        has_col = bool(
            db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'llm_response_cache' "
                    "AND column_name = 'embedding'"
                )
            ).scalar()
        )
    except Exception:
        logging.exception("llm_cache: pgvector availability probe failed")
        return False
    _PGVECTOR_AVAILABLE[key] = has_ext and has_col
    return _PGVECTOR_AVAILABLE[key]


def _similarity_scan_pgvector(db, incoming, *, time_sensitive=False):
    """Indexed nearest-neighbour scan via pgvector (cosine, ``<=>``).

    Same filters as the Python scan (rubric_version, TTL, same-day guard for
    time-sensitive queries); the SIMILARITY_THRESHOLD cutoff is applied in
    Python on the returned top-K. Raises on DB errors -- the caller falls
    back to the Python scan.
    """
    now = datetime.now(UTC)
    today = now.astimezone(LAKE_HAVASU_TZ).date() if time_sensitive else None
    rows = db.execute(
        text(
            "SELECT id, response_text, created_at, "
            "       1 - (embedding <=> CAST(:q AS vector)) AS score "
            "FROM llm_response_cache "
            "WHERE rubric_version = :rv "
            "  AND embedding IS NOT NULL "
            "  AND (ttl_until IS NULL OR ttl_until >= :now) "
            "ORDER BY embedding <=> CAST(:q AS vector) "
            "LIMIT :k"
        ),
        {
            "q": _vector_literal(incoming),
            "rv": _RUBRIC_VERSION,
            # ttl_until is stored naive-UTC (see store_with_embedding).
            "now": now.replace(tzinfo=None),
            "k": PGVECTOR_TOPK,
        },
    ).fetchall()
    for row_id, response_text, created_at, score in rows:
        if score is None or float(score) < SIMILARITY_THRESHOLD:
            # Rows are distance-ordered; once below threshold, all later
            # rows are too.
            break
        if time_sensitive:
            row_date = _row_lake_havasu_date(created_at)
            if row_date is not None and row_date != today:
                continue
        _bump_hit_telemetry(db, SimpleNamespace(id=row_id))
        return response_text
    return None


def _similarity_scan_with_embedding(db, incoming, *, time_sensitive=False):
    if incoming is None:
        return None
    # pgvector fast path (HANDOFF #2): only for vectors matching the
    # column's fixed dim; a pgvector *error* falls back to the Python
    # scan, but a clean miss (None) is final -- same data, same filters.
    if len(incoming) == EMBEDDING_DIM and _pgvector_available(db):
        try:
            return _similarity_scan_pgvector(
                db, incoming, time_sensitive=time_sensitive
            )
        except Exception:
            logging.exception(
                "llm_cache: pgvector scan failed; falling back to Python scan"
            )
    now = datetime.now(UTC)
    today = now.astimezone(LAKE_HAVASU_TZ).date() if time_sensitive else None
    try:
        candidates = list(
            db.scalars(
                select(LlmResponseCache)
                .where(
                    LlmResponseCache.rubric_version == _RUBRIC_VERSION,
                    LlmResponseCache.query_embedding.isnot(None),
                )
                .order_by(LlmResponseCache.created_at.desc())
                .limit(SIMILARITY_SCAN_LIMIT)
            ).all()
        )
    except Exception:
        logging.exception("llm_cache: similarity-scan select failed")
        return None
    best_row = None
    best_score = -1.0
    for row in candidates:
        if row.ttl_until is not None:
            ttl = row.ttl_until
            if ttl.tzinfo is None:
                ttl = ttl.replace(tzinfo=UTC)
            if ttl < now:
                continue
        if time_sensitive:
            row_date = _row_lake_havasu_date(row.created_at)
            if row_date is not None and row_date != today:
                continue
        vec = _deserialize_embedding(row.query_embedding)
        if vec is None:
            continue
        score = _cosine_similarity(incoming, vec)
        if score >= SIMILARITY_THRESHOLD and score > best_score:
            best_row = row
            best_score = score
    if best_row is None:
        return None
    cached_text = best_row.response_text
    _bump_hit_telemetry(db, best_row)
    return cached_text


def _similarity_lookup(db, normalized_query):
    nq = (normalized_query or "").strip()
    if not nq:
        return None
    incoming = _compute_query_embedding(nq)
    if incoming is None:
        return None
    return _similarity_scan_with_embedding(
        db, incoming, time_sensitive=_is_time_sensitive(nq)
    )


def lookup_with_embedding(db, cache_key, normalized_query=None):
    """Lookup variant that also returns the embedding computed for similarity fallback."""
    if cache_key:
        try:
            row = db.scalars(
                select(LlmResponseCache).where(LlmResponseCache.cache_key == cache_key).limit(1)
            ).first()
        except Exception:
            logging.exception("llm_cache.lookup: select failed (key=%s)", cache_key[:8])
            return None, None
        fresh_exact_hit = row is not None and row.rubric_version == _RUBRIC_VERSION
        if fresh_exact_hit and row.ttl_until is not None:
            ttl = row.ttl_until
            if ttl.tzinfo is None:
                ttl = ttl.replace(tzinfo=UTC)
            if ttl < datetime.now(UTC):
                fresh_exact_hit = False
        if fresh_exact_hit:
            cached_text = row.response_text
            _bump_hit_telemetry(db, row)
            return cached_text, None
    if normalized_query:
        nq = (normalized_query or "").strip()
        if not nq:
            return None, None
        embedding = _compute_query_embedding(nq)
        if embedding is None:
            return None, None
        cached_text = _similarity_scan_with_embedding(
            db, embedding, time_sensitive=_is_time_sensitive(nq)
        )
        return cached_text, embedding
    return None, None


def lookup(db, cache_key, normalized_query=None):
    if not cache_key:
        if normalized_query:
            return _similarity_lookup(db, normalized_query)
        return None
    try:
        row = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == cache_key).limit(1)
        ).first()
    except Exception:
        logging.exception("llm_cache.lookup: select failed (key=%s)", cache_key[:8])
        return None
    fresh_exact_hit = row is not None and row.rubric_version == _RUBRIC_VERSION
    if fresh_exact_hit and row.ttl_until is not None:
        ttl = row.ttl_until
        if ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=UTC)
        if ttl < datetime.now(UTC):
            fresh_exact_hit = False
    if fresh_exact_hit:
        cached_text = row.response_text
        _bump_hit_telemetry(db, row)
        return cached_text
    if normalized_query:
        return _similarity_lookup(db, normalized_query)
    return None


def _store_pg_vector(db, cache_key, embedding_blob):
    """Best-effort mirror of the JSON embedding into the pgvector column.

    Only 1536-dim vectors are written (the column is ``vector(1536)``);
    other dims leave the column NULL and the row serves exact-key hits +
    the Python similarity fallback only.
    """
    if embedding_blob is None or not _pgvector_available(db):
        return
    vec = _deserialize_embedding(embedding_blob)
    if vec is None or len(vec) != EMBEDDING_DIM:
        return
    try:
        db.execute(
            text(
                "UPDATE llm_response_cache "
                "SET embedding = CAST(:v AS vector) WHERE cache_key = :ck"
            ),
            {"v": _vector_literal(vec), "ck": cache_key},
        )
        db.commit()
    except Exception:
        logging.exception("llm_cache: pgvector mirror write failed")
        try:
            db.rollback()
        except Exception:
            pass


def store_with_embedding(
    db,
    cache_key,
    normalized_query,
    context,
    response_text,
    tier_used,
    *,
    precomputed_embedding=None,
    ttl_days=None,
):
    """Store variant that accepts a pre-computed embedding vector."""
    if not response_text or not cache_key:
        return
    nq = (normalized_query or "").strip().lower()
    ctx_hash = _hash_context(context)
    days = ttl_days if (ttl_days is not None and ttl_days > 0) else DEFAULT_TTL_DAYS
    ttl_until = datetime.now(UTC) + timedelta(days=days)
    if precomputed_embedding is not None:
        embedding_blob = _serialize_embedding(precomputed_embedding)
    else:
        embedding_blob = _serialize_embedding(_compute_query_embedding(nq))
    try:
        existing = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == cache_key).limit(1)
        ).first()
        if existing is not None:
            existing.normalized_query = nq[:500]
            existing.context_hash = ctx_hash
            existing.rubric_version = _RUBRIC_VERSION
            existing.response_text = response_text
            existing.tier_used = tier_used
            existing.created_at = datetime.now(UTC)
            existing.hit_count = 0
            existing.last_hit_at = None
            existing.ttl_until = ttl_until
            existing.query_embedding = embedding_blob
        else:
            entry = LlmResponseCache(
                cache_key=cache_key,
                normalized_query=nq[:500],
                context_hash=ctx_hash,
                rubric_version=_RUBRIC_VERSION,
                response_text=response_text,
                tier_used=tier_used,
                created_at=datetime.now(UTC),
                hit_count=0,
                last_hit_at=None,
                ttl_until=ttl_until,
                query_embedding=embedding_blob,
            )
            db.add(entry)
        db.commit()
        _store_pg_vector(db, cache_key, embedding_blob)
    except Exception:
        logging.exception(
            "llm_cache.store: write failed (key=%s, tier=%s)", cache_key[:8], tier_used
        )
        try:
            db.rollback()
        except Exception:
            pass


def store(db, cache_key, normalized_query, context, response_text, tier_used, ttl_days=None):
    """Persist ``response_text`` at insert time.

    Tier 3 callers (see ``tier3_handler.answer_with_tier3``) store **raw** LLM
    output so deterministic post-processors can run on cache hits without stale
    hedges after flag flips (Backlog #49).
    """
    store_with_embedding(
        db,
        cache_key,
        normalized_query,
        context,
        response_text,
        tier_used,
        ttl_days=ttl_days,
    )


def get_rubric_version() -> str:
    return _RUBRIC_VERSION
