"""Anthropic Messages API helpers for H2 consolidation (see ``docs/maintainability/h2_consolidation_decision.md``).

**Mock-seam invariants (§5)** — future edits that regress these break the suite; update tests
deliberately if you change them intentionally.

- Use package-level ``import anthropic`` (never ``from anthropic import Anthropic``) so
  ``patch.object(anthropic, "Anthropic", ...)`` and patches on
  ``app.core.llm_messages.anthropic.Anthropic`` hit the same class.
- Construct the client only as ``anthropic.Anthropic(api_key=..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)``
  with **no** extra keyword arguments. ``timeout`` comes from :mod:`app.core.llm_http`.
- Call ``client.messages.create`` with **exactly** these kwargs and no others:
  ``model``, ``max_tokens``, ``temperature``, ``system``, ``messages``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment,misc]

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int

    @property
    def billable_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )

    @classmethod
    def from_sdk_usage(cls, sdk_usage: Any) -> Usage:
        """Extract from SDK usage object; missing fields default to 0; None → all zeros."""
        if sdk_usage is None:
            return cls(0, 0, 0, 0)
        return cls(
            int(getattr(sdk_usage, "input_tokens", 0) or 0),
            int(getattr(sdk_usage, "output_tokens", 0) or 0),
            int(getattr(sdk_usage, "cache_read_input_tokens", 0) or 0),
            int(getattr(sdk_usage, "cache_creation_input_tokens", 0) or 0),
        )


@dataclass(frozen=True)
class AnthropicResult:
    text: str
    usage: Usage
    raw: Any


def _extract_text_from_message(msg: Any) -> str:
    """Concatenate text from all text-type content blocks; ignore non-text blocks; '' if none."""
    parts: list[str] = []
    content = getattr(msg, "content", None) or []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text":
            t = getattr(block, "text", "") or ""
            if t:
                parts.append(t)
    return " ".join(parts).strip()


def _resolve_model(model: str | None) -> str:
    if model is not None:
        m = str(model).strip()
        if m:
            return m
    env_m = (os.getenv("ANTHROPIC_MODEL") or "").strip()
    if env_m:
        return env_m
    return DEFAULT_MODEL


def call_anthropic_messages(
    *,
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    temperature: float,
    model: str | None = None,
) -> AnthropicResult | None:
    """Returns None when no response object exists:

    - Missing or empty ``ANTHROPIC_API_KEY``
    - ``anthropic`` package unavailable (import failed)
    - Any exception raised during ``messages.create``
    - Missing or falsy response object returned after ``create`` (defensive)

    On a successful API call, always returns :class:`AnthropicResult`, including when
    extracted text is empty: ``AnthropicResult(text="", usage=<from SDK>, raw=<msg>)``.
    Callers that distinguish "empty response with billed tokens" from "no response"
    should branch on ``result is None`` first, then on ``result.text``.
    """
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return None
    if anthropic is None:
        return None

    resolved_model = _resolve_model(model)
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user_message = [{"role": "user", "content": user_text}]

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        msg = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_blocks,
            messages=user_message,
        )
    except Exception:
        return None

    if not msg:
        return None

    text = _extract_text_from_message(msg)
    return AnthropicResult(
        text=text,
        usage=Usage.from_sdk_usage(getattr(msg, "usage", None)),
        raw=msg,
    )


def coerce_llm_text_to_json_object(raw: str) -> dict[str, Any] | None:
    """Strip leading/trailing triple-backtick fences (with or without language tag).
    Return parsed dict if it's a JSON object; None otherwise."""
    s = raw.strip()
    if not s:
        return None
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl == -1:
            return None
        inner = s[first_nl + 1 :]
        fence = inner.rfind("```")
        if fence != -1:
            inner = inner[:fence]
        s = inner.strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def load_prompt(name: str) -> str:
    """Read prompts/<name>.txt at repo root. Raise FileNotFoundError if missing.

    No optional fallback parameter — caller-side fallbacks (e.g. tier3) stay at the call site.
    """
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"prompt missing: {path}")
    return path.read_text(encoding="utf-8").strip()
