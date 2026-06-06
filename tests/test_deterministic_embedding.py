"""P1-13: synthetic admin embeddings must be process-stable.

The builtin ``hash()`` is salted per process (PYTHONHASHSEED), so embeddings
built with it changed every restart and stored admin vectors became garbage
after a redeploy. The token hash now uses blake2b.
"""

from __future__ import annotations

import hashlib
import math

from app.core.search import _deterministic_embedding_1536, _stable_token_hash


def test_embedding_is_deterministic_and_normalized() -> None:
    v1 = _deterministic_embedding_1536("coffee shop havasu")
    v2 = _deterministic_embedding_1536("coffee shop havasu")
    assert v1 == v2
    assert len(v1) == 1536
    mag = math.sqrt(sum(x * x for x in v1))
    assert abs(mag - 1.0) < 1e-9


def test_empty_text_returns_zero_vector() -> None:
    assert _deterministic_embedding_1536("") == [0.0] * 1536


def test_stable_token_hash_pins_blake2b() -> None:
    # blake2b is not affected by PYTHONHASHSEED. Pinning the digest catches a
    # regression back to the builtin hash() (which is per-process salted).
    expected = int.from_bytes(hashlib.blake2b(b"coffee", digest_size=8).digest(), "big")
    assert _stable_token_hash("coffee") == expected
