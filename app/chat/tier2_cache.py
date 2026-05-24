"""Tier 2 parser + formatter exact-key cache (Lane B-2).

Reuses the existing ``LlmResponseCache`` table with new ``tier_used`` namespace
values (``tier2_parser`` and ``tier2_formatter``). Exact-key only -- no
similarity fallback, no embedding RTTs. The two LLM calls in
``app/chat/tier2_handler.py`` are the dominant Tier 2 spend; cache hits collapse
them to zero LLM tokens.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.llm_cache import _hash_context, get_rubric_version
from app.chat.tier2_schema import Tier2Filters
from app.db.models import LlmResponseCache

PARSER_TIER = "tier2_parser"
FORMATTER_TIER = "tier2_formatter"
PARSER_TTL_DAYS = 1
FORMATTER_TTL_DAYS = 1


def _parser_cache_key(normalized_query: str, today_iso: str) -> str:
    nq = (normalized_query or "").strip().lower()
    h = hashlib.sha256()
    h.update(b"tier2_parser|")
    h.update(nq.encode("utf-8"))
    h.update(b"|")
    h.update((today_iso or "").encode("utf-8"))
    h.update(b"|")
    h.update(get_rubric_version().encode("utf-8"))
    return h.hexdigest()[:32]


def lookup_parser(db: Session, normalized_query: str, today_iso: str) -> Tier2Filters | None:
    """Return cached Tier2Filters for (query, today_iso), or None on miss."""
    key = _parser_cache_key(normalized_query, today_iso)
    try:
        row = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == key).limit(1)
        ).first()
    except Exception:
        logging.exception("tier2_cache.lookup_parser: select failed (key=%s)", key[:8])
        return None
    if row is None:
        return None
    if row.rubric_version != get_rubric_version():
        return None
    if row.ttl_until is not None:
        ttl = row.ttl_until
        if ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=UTC)
        if ttl < datetime.now(UTC):
            return None
    if row.tier_used != PARSER_TIER:
        return None
    try:
        payload = json.loads(row.response_text)
    except (json.JSONDecodeError, TypeError):
        logging.warning("tier2_cache.lookup_parser: stored payload is not JSON (key=%s)", key[:8])
        return None
    try:
        filters = Tier2Filters.model_validate(payload)
    except Exception:
        logging.warning("tier2_cache.lookup_parser: payload does not validate (key=%s)", key[:8])
        return None
    try:
        row.hit_count = (row.hit_count or 0) + 1
        row.last_hit_at = datetime.now(UTC)
        db.commit()
    except Exception:
        logging.exception("tier2_cache.lookup_parser: hit-count update failed")
        try:
            db.rollback()
        except Exception:
            pass
    return filters


def store_parser(db: Session, normalized_query: str, today_iso: str, filters: Tier2Filters) -> None:
    """Persist a successful parse. Failed parses (filters=None) are NOT cached."""
    if filters is None:
        return
    key = _parser_cache_key(normalized_query, today_iso)
    payload = json.dumps(filters.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    ttl_until = datetime.now(UTC) + timedelta(days=PARSER_TTL_DAYS)
    try:
        existing = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == key).limit(1)
        ).first()
        if existing is not None:
            existing.normalized_query = (normalized_query or "")[:500]
            existing.context_hash = _hash_context({"_today": today_iso})
            existing.rubric_version = get_rubric_version()
            existing.response_text = payload
            existing.tier_used = PARSER_TIER
            existing.created_at = datetime.now(UTC)
            existing.hit_count = 0
            existing.last_hit_at = None
            existing.ttl_until = ttl_until
            existing.query_embedding = None
        else:
            entry = LlmResponseCache(
                cache_key=key,
                normalized_query=(normalized_query or "")[:500],
                context_hash=_hash_context({"_today": today_iso}),
                rubric_version=get_rubric_version(),
                response_text=payload,
                tier_used=PARSER_TIER,
                created_at=datetime.now(UTC),
                hit_count=0,
                last_hit_at=None,
                ttl_until=ttl_until,
                query_embedding=None,
            )
            db.add(entry)
        db.commit()
    except Exception:
        logging.exception("tier2_cache.store_parser: write failed (key=%s)", key[:8])
        try:
            db.rollback()
        except Exception:
            pass


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    """Deterministic hash of the rows payload as the formatter sees it."""
    rows_json = json.dumps(rows or [], ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(rows_json.encode("utf-8"))
    return h.hexdigest()[:16]


def _formatter_cache_key(normalized_query: str, rows: list[dict[str, Any]]) -> str:
    nq = (normalized_query or "").strip().lower()
    h = hashlib.sha256()
    h.update(b"tier2_formatter|")
    h.update(nq.encode("utf-8"))
    h.update(b"|")
    h.update(_rows_hash(rows).encode("utf-8"))
    h.update(b"|")
    h.update(get_rubric_version().encode("utf-8"))
    return h.hexdigest()[:32]


def lookup_formatter(db: Session, normalized_query: str, rows: list[dict[str, Any]]) -> str | None:
    """Return cached formatter text for (query, rows), or None on miss."""
    key = _formatter_cache_key(normalized_query, rows)
    try:
        row = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == key).limit(1)
        ).first()
    except Exception:
        logging.exception("tier2_cache.lookup_formatter: select failed (key=%s)", key[:8])
        return None
    if row is None:
        return None
    if row.rubric_version != get_rubric_version():
        return None
    if row.ttl_until is not None:
        ttl = row.ttl_until
        if ttl.tzinfo is None:
            ttl = ttl.replace(tzinfo=UTC)
        if ttl < datetime.now(UTC):
            return None
    if row.tier_used != FORMATTER_TIER:
        return None
    text = row.response_text
    try:
        row.hit_count = (row.hit_count or 0) + 1
        row.last_hit_at = datetime.now(UTC)
        db.commit()
    except Exception:
        logging.exception("tier2_cache.lookup_formatter: hit-count update failed")
        try:
            db.rollback()
        except Exception:
            pass
    return text


def store_formatter(db: Session, normalized_query: str, rows: list[dict[str, Any]], text: str) -> None:
    """Persist successful formatter output. Empty / None text NOT cached."""
    if not text:
        return
    key = _formatter_cache_key(normalized_query, rows)
    ttl_until = datetime.now(UTC) + timedelta(days=FORMATTER_TTL_DAYS)
    try:
        existing = db.scalars(
            select(LlmResponseCache).where(LlmResponseCache.cache_key == key).limit(1)
        ).first()
        if existing is not None:
            existing.normalized_query = (normalized_query or "")[:500]
            existing.context_hash = _rows_hash(rows)
            existing.rubric_version = get_rubric_version()
            existing.response_text = text
            existing.tier_used = FORMATTER_TIER
            existing.created_at = datetime.now(UTC)
            existing.hit_count = 0
            existing.last_hit_at = None
            existing.ttl_until = ttl_until
            existing.query_embedding = None
        else:
            entry = LlmResponseCache(
                cache_key=key,
                normalized_query=(normalized_query or "")[:500],
                context_hash=_rows_hash(rows),
                rubric_version=get_rubric_version(),
                response_text=text,
                tier_used=FORMATTER_TIER,
                created_at=datetime.now(UTC),
                hit_count=0,
                last_hit_at=None,
                ttl_until=ttl_until,
                query_embedding=None,
            )
            db.add(entry)
        db.commit()
    except Exception:
        logging.exception("tier2_cache.store_formatter: write failed (key=%s)", key[:8])
        try:
            db.rollback()
        except Exception:
            pass
