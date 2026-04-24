"""
Backfill ``Provider.embedding`` for rows with ``NULL`` embedding (Phase 8.11c).

Runs **after** :mod:`app.contrib.google_bulk_ingest` (8.11b). Uses the same OpenAI
embedding model as event extraction: ``text-embedding-3-small`` (1536-dim).
See :func:`app.core.extraction.generate_embedding` and
:func:`app.core.search.generate_query_embedding_with_source`.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.db.models import Provider

EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_TEXT_MAX_CHARS = 8000
MAX_RETRIES = 3
RETRY_DELAYS_SEC = (1, 2, 4)
BETWEEN_BATCH_SLEEP_SEC = 0.5

logger = logging.getLogger(__name__)


@dataclass
class EmbedCounters:
    scanned: int = 0
    embedded: int = 0
    skipped_no_name: int = 0
    skipped_only_name: int = 0
    errors: int = 0


def _norm(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def build_embedding_text(
    provider_name: str | None,
    category: str | None,
    description: str | None,
) -> str | None:
    """Apply the fallback chain. Return the text to embed, or None if unembeddable.

    - Full: '<name> | <category> | <description>'
    - Two-part (no description): '<name> | <category>' or '<name> | <description>' if category empty
    - One-part: '<name>'  — caller increments ``skipped_only_name`` and logs a warning
    - None (no name): caller increments ``skipped_no_name``

    Strip whitespace; treat empty strings as None. Truncate result to
    :data:`EMBED_TEXT_MAX_CHARS` for API safety.
    """
    name = _norm(provider_name)
    cat = _norm(category)
    desc = _norm(description)
    if not name:
        return None
    if not desc:
        if cat:
            text = f"{name} | {cat}"
        else:
            text = name
    else:
        if cat:
            text = f"{name} | {cat} | {desc}"
        else:
            text = f"{name} | {desc}"
    if len(text) > EMBED_TEXT_MAX_CHARS:
        return text[: EMBED_TEXT_MAX_CHARS]
    return text


def _openai_client_for_embed() -> OpenAI:
    """Build the OpenAI client for embedding. Raises ``RuntimeError`` with a clear message on misconfiguration."""
    if OpenAI is None:
        raise RuntimeError(
            "The openai package is not installed; install project dependencies to backfill embeddings."
        )
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it in the environment, or use --dry-run to preview without calling OpenAI."
        )
    return OpenAI(api_key=key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)


def _embed_batch_for_texts_api(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings; same pattern as :func:`app.core.extraction.generate_embedding`."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    by_index: dict[int, list[float]] = {}
    for d in response.data:
        by_index[int(d.index)] = list(d.embedding)
    n = len(texts)
    return [by_index[i] for i in range(n)]


def _call_embed_with_retries(
    client: OpenAI,
    texts: list[str],
    provider_ids: list[str],
) -> list[list[float]] | None:
    for attempt in range(MAX_RETRIES):
        try:
            return _embed_batch_for_texts_api(client, texts)
        except Exception as e:
            is_last = attempt == MAX_RETRIES - 1
            if is_last:
                logger.error(
                    "google_bulk_embed: batch failed after %s attempts, provider_ids=%r: %s: %s",
                    MAX_RETRIES,
                    provider_ids,
                    type(e).__name__,
                    e,
                )
                return None
            delay = RETRY_DELAYS_SEC[min(attempt, len(RETRY_DELAYS_SEC) - 1)]
            logger.warning(
                "google_bulk_embed: embedding attempt %s failed (%s: %s), retrying in %ss",
                attempt + 1,
                type(e).__name__,
                e,
                delay,
            )
            time.sleep(delay)
    return None


def run_embed(
    db: Session,
    *,
    batch_size: int = 50,
    dry_run: bool = False,
) -> EmbedCounters:
    out = EmbedCounters()
    client: OpenAI | None = None
    if not dry_run:
        try:
            client = _openai_client_for_embed()
        except RuntimeError as e:
            logger.error("google_bulk_embed: %s", e)
            raise

    def process_batch(providers: list[Provider], *, is_dry: bool) -> None:
        pairs: list[tuple[Provider, str]] = []
        for p in providers:
            out.scanned += 1
            text = build_embedding_text(p.provider_name, p.category, p.description)
            c_n = _norm(p.category)
            d_n = _norm(p.description)
            if text is None:
                out.skipped_no_name += 1
                logger.error(
                    "google_bulk_embed: skip provider id=%s: missing or empty provider_name",
                    p.id,
                )
                continue
            if not c_n and not d_n:
                out.skipped_only_name += 1
                logger.warning(
                    "google_bulk_embed: name-only text for id=%s (no category, no description)",
                    p.id,
                )
            pairs.append((p, text))

        if not pairs:
            return
        if is_dry:
            return
        assert client is not None  # set at start of run_embed when not dry_run

        ttexts = [t for _, t in pairs]
        pids = [p.id for p, _ in pairs]
        vecs = _call_embed_with_retries(client, ttexts, pids) if ttexts else None
        if vecs is None and ttexts:
            out.errors += len(pairs)
            return
        for (p, _), vec in zip(pairs, vecs):
            p.embedding = vec
        db.commit()
        out.embedded += len(pairs)

    if dry_run:
        ids = list(
            db.scalars(
                select(Provider.id).where(Provider.embedding.is_(None)).order_by(Provider.id)
            ).all()
        )
        for i in range(0, len(ids), batch_size):
            chunk = ids[i : i + batch_size]
            prows: dict[str, Provider] = {
                p.id: p
                for p in db.scalars(
                    select(Provider).where(Provider.id.in_(chunk))
                )
            }
            batch = [prows[pid] for pid in chunk if pid in prows]
            process_batch(batch, is_dry=True)
        return out

    while True:
        batch = list(
            db.scalars(
                select(Provider)
                .where(Provider.embedding.is_(None))
                .order_by(Provider.id)
                .limit(batch_size)
            )
        )
        if not batch:
            break
        process_batch(batch, is_dry=False)
        if client is not None:
            time.sleep(BETWEEN_BATCH_SLEEP_SEC)
    return out
