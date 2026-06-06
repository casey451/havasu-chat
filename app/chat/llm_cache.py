"""LLM response cache (Stream C, lever Cache)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.openai_client import get_openai_client
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.models import LlmResponseCache

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

DEFAULT_TTL_DAYS = 7
EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.9
SIMILARITY_SCAN_LIMIT = 200


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
    nq = (normalized_query or "").strip().lower()
    ctx_hash = _hash_context(context)
    h = hashlib.sha256()
    h.update(nq.encode("utf-8"))
    h.update(b"|")
    h.update(ctx_hash.encode("utf-8"))
    h.update(b"|")
    h.update(_RUBRIC_VERSION.encode("utf-8"))
    return h.hexdigest()[:32]


def _compute_query_embedding(text):
    if not text or not text.strip():
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    if OpenAI is None:
        return None
    try:
        client = get_openai_client(  # T2.3 singleton; OpenAI stays the patchable seam
            api_key, factory=OpenAI, timeout=LLM_CLIENT_READ_TIMEOUT_SEC
        )
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text.strip())
    except Exception:
        logging.exception("llm_cache: embedding API call failed")
        return None
    try:
        vec = resp.data[0].embedding
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    if not isinstance(vec, list) or not vec:
        return None
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError):
        return None


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
    try:
        row.hit_count = (row.hit_count or 0) + 1
        row.last_hit_at = datetime.now(UTC)
        db.commit()
    except Exception:
        logging.exception("llm_cache: hit-count update failed")
        try:
            db.rollback()
        except Exception:
            pass


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


def _similarity_scan_with_embedding(db, incoming, *, time_sensitive=False):
    if incoming is None:
        return None
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
