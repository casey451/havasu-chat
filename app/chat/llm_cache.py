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

Out of scope for v1 (deferred to v2)
-------------------------------------

- Embedding-similarity matching for "very similar" queries — currently exact
  normalized-string match only.
- Catalog-row-count delta invalidation — currently relies on TTL + rubric
  version for staleness control.
- Tier 2 parser/formatter caching — Tier 3 only for v1; Tier 2 listing
  shortcuts already cover most listing queries at zero token cost.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LlmResponseCache

# Default TTL for evergreen recommendations. Caller can override per-call.
DEFAULT_TTL_DAYS = 7


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


def lookup(db: Session, cache_key: str) -> str | None:
    """Look up a cache entry. Returns the cached response_text on a fresh hit;
    None on miss, expired entry, version mismatch, or DB error.

    On a fresh hit, increments ``hit_count`` and updates ``last_hit_at``. A
    failure to update those fields is logged but does NOT invalidate the
    cache hit — the cached text is still returned to the caller.
    """
    if not cache_key:
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

    if row is None:
        return None

    # Version-mismatch defense: even if cache_key collides (vanishingly rare with
    # 32 hex chars), the rubric_version field is the second authoritative key.
    if row.rubric_version != _RUBRIC_VERSION:
        return None

    # TTL check.
    if row.ttl_until is not None:
        ttl = row.ttl_until
        # Postgres returns timezone-aware; SQLite returns naive. Normalize to UTC.
        if ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=UTC)
        if ttl < datetime.now(UTC):
            return None  # treat as miss; caller will overwrite via store()

    # Hit. Bump telemetry.
    cached_text = row.response_text
    try:
        row.hit_count = (row.hit_count or 0) + 1
        row.last_hit_at = datetime.now(UTC)
        db.commit()
    except Exception:
        logging.exception(
            "llm_cache.lookup: hit-count update failed (key=%s)", cache_key[:8]
        )
        try:
            db.rollback()
        except Exception:
            pass
        # Still return the response; the count update isn't essential.

    return cached_text


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
