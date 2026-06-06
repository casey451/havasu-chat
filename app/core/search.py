"""Synthetic query embeddings for admin contributions (Slice 71).

Kept for ``app/admin/router.py``, which uses ``_deterministic_embedding_1536``
when no OpenAI embedding is available. The legacy event-search pipeline that
lived in this module was removed under Backlog #36 Option A.
"""

from __future__ import annotations

import hashlib
import math
import re


def _stable_token_hash(token: str) -> int:
    """Process-stable 64-bit hash. The builtin ``hash()`` is salted per process
    (PYTHONHASHSEED), so embeddings built with it changed every restart and
    stored admin vectors became garbage after a redeploy. (P1-13)"""
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
    )


def _deterministic_embedding_1536(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    vector = [0.0] * 1536
    for token in tokens:
        h = _stable_token_hash(token)
        for i in range(16):
            idx = (h + i * 7919) % 1536
            vector[idx] += 1.0 / (i + 1)
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return vector
    return [v / magnitude for v in vector]
