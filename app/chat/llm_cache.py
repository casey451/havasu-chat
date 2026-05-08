"""LLM response cache (Stream C, lever Cache).

Caches Tier 3 synthesis responses (and optionally Tier 2 LLM responses) keyed
by ``(normalized_query, context_hash, rubric_version)``. Hits return the cached
text and bump telemetry; misses fall through to the live LLM call, which writes
the response back into the cache after the response is produced.

Design notes
------------

- **Rubric version hash auto-invalidates on prompt changes.** Computed once at
  module import from the SHA-256 of the contents of ``prompts/system_prompt.txt``,
  ``prompts/tier2_formatter.txt``, and ``prompts/tier2_parser.txt``. Edit any
  of those files and the version flips, so old entries are filtered on lookup.
- **Context hash captures the inputs that actually affect the answer.** Today's
  date for time-windowed queries (so a "this weekend" answer doesn't bleed into
  next weekend), onboarding hints when they bias the response (visitor vs.
  local, has_kids, age, location). Catalog-row counts are NOT in the hash for
  v1 — that's a known cache-staleness vector documented for v2.
- **TTL per entry.** Caller chooses based on query shape. Default 7 days for
  evergreen recommendations; shorter TTLs are caller's responsibility (e.g.
  Tier 3 event listings should set TTL to end-of-window). Null TTL = no expiry.
- **Cache hit telemetry.** When a hit returns, the caller can log
  ``tier_used="tier3_cache"`` with 0 tokens. Fast and free to compute the
  stat from ``chat_logs.llm_tokens_used = 0`` even if the tier label isn't
  changed.
- **Defensive on errors.** Any DB error during lookup or store is logged and
  swallowed — caching failures must not break the chat path. Worst case: the
  call hits the live LLM as if the cache wasn't there.

Cache v2 (§4.3, 2026-05-08): embedding-similarity fallback
----------------------------------------------------------

When the exact ``cache_key`` lookup misses, lookup() optionally computes an
OpenAI embedding for the incoming query (``text-embedding-3-small``) and
sequentially scans live cache rows whose ``rubric_version`` matches and whose
``ttl_until`` hasn't passed, picking the row with the highest cosine
similarity ≥ :data:`SIMILARITY_THRESHOLD`. Pre-v2 rows (no embedding column
populated) are skipped during the similarity scan but still serve exact-match
hits.

The embedding API call is best-effort — any failure (missing OPENAI_API_KEY,
SDK exception, malformed response) returns ``None`` and the lookup falls back
to exact-match-only behavior. Failures must never propagate to the chat path.

Out of scope for v2 (deferred)
-------------------------------

- Catalog-row-count delta invalidation — currently relies on TTL + rubric
  version for staleness control.
- Tier 2 parser/formatter caching — Tier 3 only for v1/v2; Tier 2 listing
  shortcuts already cover most listing queries at zero token cost.
- Vector-index acceleration (pgvector / sqlite-vss) — sequential scan is
  fine while the cache is small (a few thousand rows × 1536 floats per
  embedding = a few MB). Revisit when scan latency becomes measurable in
  ``chat_logs``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.db.models import LlmResponseCache

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment,misc]

# Default TTL for evergreen recommendations. Caller can override per-call.
DEFAULT_TTL_DAYS = 7

# §4.3 (cache v2) — embedding-similarity tuning.
EMBEDDING_MODEL = "text-embedding-3-small"
# Cosine-similarity threshold for a similarity hit. 0.9 is conservative —
# text-embedding-3-small puts paraphrases of the same intent comfortably
# above 0.9 in spot-checks, while distinct intents land in the 0.5–0.8 band.
# Tune via the chat_logs review of similarity-vs-exact hits in production.
SIMILARITY_THRESHOLD = 0.9
# Hard cap on the number of rows scanned per lookup. Protects worst-case
# latency if the cache grows large before we add a vector index. At
# ``text-embedding-3-small`` (1536 dims) and pure-Python cosine, ~200 rows is
# under ~5 ms in practice.
SIMILARITY_SCAN_LIMIT = 200


def _compute_rubric_version() -> str:
    """SHA-256 of the relevant prompt files; first 16 hex chars as version tag.

    Files included: system_prompt.txt, tier2_formatter.txt, tier2_parser.txt.
    Edits to any of those auto-bump the version, invalidating cached responses
    that were generated against the old prompts.
    """
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
                # Best-effort; if a prompt file can't be read, skip it from
                # the hash. The version still reflects the readable files.
                continue
    return h.hexdigest()[:16]


# Module-level constant — computed once at import. If a prompt is edited at
# runtime (uncommon outside tests), restart the process to pick up the new
# version. The cache will treat any pre-restart entries as the wrong version
# and ignore them.
_RUBRIC_VERSION: str = _compute_rubric_version()


def _hash_context(context: Mapping[str, Any] | None) -> str:
    """Stable short hash of a context dict (12 hex chars)."""
    if not context:
        return "no_ctx"
    items = sorted(
        (str(k), str(v)) for k, v in context.items() if v is not None and v != ""
    )
    if not items:
        return "no_ctx"
    h = hashlib.sha256()
    for k, v in items:
        h.update(k.encode("utf-8"))
        h.update(b"=")
        h.update(v.encode("utf-8"))
        h.update(b";")
    return h.hexdigest()[:12]


def make_cache_key(
    normalized_query: str, context: Mapping[str, Any] | None
) -> str:
    """Compose the cache key from normalized query, context, and rubric version.

    Returns a 32-character hex string suitable for the indexed
    ``llm_response_cache.cache_key`` column.
    """
    nq = (normalized_query or "").strip().lower()
    ctx_hash = _hash_context(context)
    h = hashlib.sha256()
    h.update(nq.encode("utf-8"))
    h.update(b"|")
    h.update(ctx_hash.encode("utf-8"))
    h.update(b"|")
    h.update(_RUBRIC_VERSION.encode("utf-8"))
    return h.hexdigest()[:32]


def _compute_query_embedding(text: str) -> list[float] | None:
    """Compute an OpenAI embedding for ``text`` via ``text-embedding-3-small``.

    Returns ``None`` on any failure (missing ``OPENAI_API_KEY``, ``openai``
    package unavailable, SDK exception, malformed response). The cache path
    must remain functional with exact-match lookups when embeddings can't be
    computed; this helper is best-effort.

    Mock seam: tests patch ``app.chat.llm_cache.OpenAI`` (mirrors the canonical
    seam used in :mod:`app.core.llm_messages`).
    """
    if not text or not text.strip():
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    if OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text.strip(),
        )
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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity ∈ [-1, 1]. Returns 0.0 for empty / mismatched-length
    inputs or zero-norm vectors. Never raises — callers iterate this across
    untrusted DB rows."""
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


def _serialize_embedding(vec: list[float] | None) -> str | None:
    """JSON-encode a float list for storage in ``query_embedding`` (Text)."""
    if vec is None:
        return None
    try:
        return json.dumps(vec)
    except (TypeError, ValueError):
        return None


def _deserialize_embedding(s: str | None) -> list[float] | None:
    """Inverse of :func:`_serialize_embedding`; returns ``None`` on any
    decode/shape error so a corrupted row simply skips the similarity scan."""
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


def _bump_hit_telemetry(db: Session, row: LlmResponseCache) -> None:
    """Increment ``hit_count`` / refresh ``last_hit_at`` on a cache hit row.

    Failures are logged but do not invalidate the hit — the cached text was
    already returned to the caller by then.
    """
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


def _similarity_lookup(
    db: Session, normalized_query: str
) -> str | None:
    """Sequential cosine-similarity scan over live cache rows.

    Returns the response_text of the highest-similarity row that exceeds
    :data:`SIMILARITY_THRESHOLD`, or ``None`` if no row qualifies (or if the
    embedding API call fails). Bumps hit telemetry on the matched row.

    Filters: matching ``rubric_version``, non-expired ``ttl_until``, non-null
    ``query_embedding``. Caps the scan at :data:`SIMILARITY_SCAN_LIMIT` rows
    ordered by most-recent ``created_at`` so the freshest entries get
    considered first if the cache ever exceeds the cap.
    """
    nq = (normalized_query or "").strip()
    if not nq:
        return None
    incoming = _compute_query_embedding(nq)
    if incoming is None:
        return None

    now = datetime.now(UTC)
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

    best_row: LlmResponseCache | None = None
    best_score = -1.0
    for row in candidates:
        # TTL filter (Postgres tz-aware vs SQLite naive — normalize to UTC).
        if row.ttl_until is not None:
            ttl = row.ttl_until
            if ttl.tzinfo is None:
                ttl = ttl.replace(tzinfo=UTC)
            if ttl < now:
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
    logging.info(
        "llm_cache: similarity hit (score=%.3f, key=%s)",
        best_score,
        (best_row.cache_key or "")[:8],
    )
    cached_text = best_row.response_text
    _bump_hit_telemetry(db, best_row)
    return cached_text


def lookup(db: Session, cache_key: str, normalized_query: str | None = None) -> str | None:
    """Look up a cache entry. Returns the cached response_text on a fresh hit;
    None on miss, expired entry, version mismatch, or DB error.

    Two-phase: exact ``cache_key`` match first (fast O(1) via index); on miss,
    optionally falls back to embedding-similarity scan if ``normalized_query``
    is provided and an embedding can be computed for it. Pass ``None`` (or
    omit) to force exact-match-only behavior — used by callers that already
    know the query is a cache-key probe (e.g. cache hygiene tooling).

    On a fresh hit, increments ``hit_count`` and updates ``last_hit_at``. A
    failure to update those fields is logged but does NOT invalidate the
    cache hit — the cached text is still returned to the caller.
    """
    if not cache_key:
        # No exact key — try similarity if we have a query to embed.
        if normalized_query:
            return _similarity_lookup(db, normalized_query)
        return None
    try:
        row = db.scalars(
            select(LlmResponseCache)
            .where(LlmResponseCache.cache_key == cache_key)
            .limit(1)
        ).first()
    except Exception:
        logging.exception("llm_cache.lookup: select failed (key=%s)", cache_key[:8])
        return None

    fresh_exact_hit = row is not None and row.rubric_version == _RUBRIC_VERSION
    if fresh_exact_hit and row.ttl_until is not None:
        # TTL check (normalize to UTC across SQLite naive / Postgres tz-aware).
        ttl = row.ttl_until
        if ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=UTC)
        if ttl < datetime.now(UTC):
            fresh_exact_hit = False  # treat as miss; will overwrite via store()

    if fresh_exact_hit:
        cached_text = row.response_text
        _bump_hit_telemetry(db, row)
        return cached_text

    # Exact-match miss — fall back to embedding-similarity scan if the caller
    # gave us a query. Stale-version / TTL-expired rows still let us try the
    # similarity path; the scan filters by current rubric_version on its own.
    if normalized_query:
        return _similarity_lookup(db, normalized_query)
    return None


def store(
    db: Session,
    cache_key: str,
    normalized_query: str,
    context: Mapping[str, Any] | None,
    response_text: str,
    tier_used: str,
    ttl_days: float | None = None,
) -> None:
    """Write a cache entry. Idempotent — replaces existing on key collision.

    Empty ``response_text`` is silently skipped (don't pollute the cache with
    fallback messages). DB errors are logged and swallowed.

    ``ttl_days`` controls expiry. Default = ``DEFAULT_TTL_DAYS``. Pass ``None``
    explicitly only if you want no expiry — the function distinguishes "not
    provided" (use default) from "explicitly None" by treating any non-numeric
    falsy value as default; pass ``float("inf")`` or just don't expect None to
    mean "no expiry" if you need that — for v1, all callers go through the
    default path.
    """
    if not response_text or not cache_key:
        return
    nq = (normalized_query or "").strip().lower()
    ctx_hash = _hash_context(context)
    days = ttl_days if (ttl_days is not None and ttl_days > 0) else DEFAULT_TTL_DAYS
    ttl_until = datetime.now(UTC) + timedelta(days=days)

    # §4.3 (cache v2): compute the query embedding so future similarity
    # lookups can find this entry. Best-effort — if the embedding API call
    # fails, we still write the row with ``query_embedding=NULL`` and the
    # entry serves exact-match hits only. Never gate the cache write on the
    # embedding call.
    embedding_blob = _serialize_embedding(_compute_query_embedding(nq))

    try:
        existing = db.scalars(
            select(LlmResponseCache)
            .where(LlmResponseCache.cache_key == cache_key)
            .limit(1)
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
            "llm_cache.store: write failed (key=%s, tier=%s)",
            cache_key[:8],
            tier_used,
        )
        try:
            db.rollback()
        except Exception:
            pass


def get_rubric_version() -> str:
    """Expose the current rubric version (for diagnostics / external tooling)."""
    return _RUBRIC_VERSION
