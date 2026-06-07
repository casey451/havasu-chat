"""Provider-routed text embeddings (VPS rollout HANDOFF #3).

A single seam for embedding generation so the provider can be swapped without
touching call sites (ingest tagging in ``app.core.extraction`` and the
similarity cache in ``app.chat.llm_cache``).

``EMBEDDINGS_PROVIDER``:
- ``openai`` (default): OpenAI embeddings API, ``text-embedding-3-small``
  (1536-dim). Uses the shared client singleton; ``OPENAI_API_KEY`` required.
- ``local``: an **OpenAI-compatible** endpoint at ``EMBEDDINGS_BASE_URL`` (e.g.
  Ollama serving ``nomic-embed-text`` on the VPS). ``EMBEDDINGS_API_KEY`` is
  optional (local servers ignore it; the OpenAI client just needs a non-empty
  string).

Model override: ``EMBEDDINGS_MODEL`` (defaults to ``text-embedding-3-small`` for
openai, ``nomic-embed-text`` for local).

**Dimension caveat.** Local models emit different dimensions than OpenAI's 1536.
Vectors stored under one provider are NOT comparable to another's. The cache's
``_cosine_similarity`` already returns 0.0 when ``len(a) != len(b)``, so a
dimension mismatch degrades safely to "no similarity match" rather than a wrong
hit — but a provider switch effectively invalidates the existing cache (re-embed
or clear it to regain similarity hits). Ingest-time vectors should likewise be
regenerated if the provider changes.

Returns ``None`` on empty input, missing key/URL, or any failure — the caller
owns the fallback policy (ingest keeps a deterministic fallback; the cache
treats ``None`` as "no similarity lookup").
"""

from __future__ import annotations

import logging
import os

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.openai_client import get_openai_client

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover — openai always present in prod
    OpenAI = None  # type: ignore[misc, assignment]

DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
DEFAULT_LOCAL_MODEL = "nomic-embed-text"
_VALID_PROVIDERS = {"openai", "local"}


def provider() -> str:
    """Resolved provider; unrecognized values fall back to ``openai``."""
    p = (os.getenv("EMBEDDINGS_PROVIDER") or "openai").strip().lower()
    return p if p in _VALID_PROVIDERS else "openai"


def _model() -> str:
    explicit = (os.getenv("EMBEDDINGS_MODEL") or "").strip()
    if explicit:
        return explicit
    return DEFAULT_LOCAL_MODEL if provider() == "local" else DEFAULT_OPENAI_MODEL


def _openai_client():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        return None
    # Shared singleton + patchable seam (OpenAI symbol), same as other callers.
    return get_openai_client(api_key, factory=OpenAI, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)


def _local_client():
    base_url = (os.getenv("EMBEDDINGS_BASE_URL") or "").strip()
    if not base_url or OpenAI is None:
        return None
    # Local servers (Ollama) ignore the key, but the OpenAI client requires a
    # non-empty string. Constructed directly (not via the api_key-keyed
    # singleton) so the base_url is honored; local volume is low (cache misses +
    # ingest), so per-call construction is fine.
    api_key = (os.getenv("EMBEDDINGS_API_KEY") or "").strip() or "local"
    return OpenAI(api_key=api_key, base_url=base_url, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)


def _coerce(resp) -> list[float] | None:
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


def embed(text: str) -> list[float] | None:
    """Embed ``text`` via the configured provider, or ``None`` on any failure.

    Client construction is inside the try/except so the test suite's
    no-network ``OpenAI`` blocker (and any real outage) degrades to ``None``
    rather than raising — every caller's best-effort contract.
    """
    if not text or not text.strip():
        return None
    prov = provider()
    try:
        client = _local_client() if prov == "local" else _openai_client()
        if client is None:
            return None
        resp = client.embeddings.create(model=_model(), input=text.strip())
    except Exception:
        logging.exception("embeddings: %s embedding call failed", prov)
        return None
    return _coerce(resp)
