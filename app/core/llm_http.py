"""Shared HTTP read timeout for LLM SDK clients (Phase 8.2).

Anthropic and OpenAI Python clients accept ``timeout=`` on construction; this
value bounds how long a stuck request can block a worker before the SDK raises
(typically ``httpx.ReadTimeout``), which is then handled by app-level
``except`` paths and §3.11 graceful copy where applicable.
"""

from __future__ import annotations

import os

# Bounds how long a stuck LLM request blocks a worker (a threadpool slot AND a
# pooled DB connection, since the request Session is held across the call) before
# the SDK raises. Lowered from 45s and made env-tunable (audit Track 1): a 45s
# stall pinned both resources for the full window. Override LLM_READ_TIMEOUT_SEC
# to retune without a deploy.
LLM_CLIENT_READ_TIMEOUT_SEC = float(os.getenv("LLM_READ_TIMEOUT_SEC", "30"))
