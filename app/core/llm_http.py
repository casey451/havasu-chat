"""Shared HTTP read timeout for LLM SDK clients (Phase 8.2).

Anthropic and OpenAI Python clients accept ``timeout=`` on construction; this
value bounds how long a stuck request can block a worker before the SDK raises
(typically ``httpx.ReadTimeout``), which is then handled by app-level
``except`` paths and §3.11 graceful copy where applicable.
"""

from __future__ import annotations

LLM_CLIENT_READ_TIMEOUT_SEC = 45.0
