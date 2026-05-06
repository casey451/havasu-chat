"""Synthetic query embeddings for admin contributions (Slice 71).

Kept for ``app/admin/router.py``, which uses ``_deterministic_embedding_1536``
when no OpenAI embedding is available. The legacy event-search pipeline that
lived in this module was removed under Backlog #36 Option A.
"""

from __future__ import annotations

import math
import re


def _deterministic_embedding_1536(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    vector = [0.0] * 1536
    for token in tokens:
        h = hash(token)
        for i in range(16):
            idx = (h + i * 7919) % 1536
            vector[idx] += 1.0 / (i + 1)
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return vector
    return [v / magnitude for v in vector]
