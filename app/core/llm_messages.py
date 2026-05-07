"""OpenAI Chat Completions helpers for H2 consolidation (see ``docs/maintainability/h2_consolidation_decision.md``).

Provider swap (2026-05-07): every Anthropic call site was migrated to OpenAI ``gpt-4o-mini``
to cut LLM cost ~7x. The ``Usage`` dataclass keeps its Anthropic-shaped field names for
backward compatibility with ``chat_logs.llm_tokens_used`` interpretation; ``cache_*`` fields
are zeroed out (OpenAI's prompt caching is automatic and not surfaced per-call here).

**Mock-seam invariants (§5)** — future edits that regress these break the suite; update tests
deliberately if you change them intentionally.

- Use top-level ``from openai import OpenAI`` (mirrors ``app/chat/hint_extractor.py`` so
  ``patch.object(...)`` works the same way across both modules).
- Construct the client only as ``OpenAI(api_key=..., timeout=LLM_CLIENT_READ_TIMEOUT_SEC)``
  with **no** extra keyword arguments. ``timeout`` comes from :mod:`app.core.llm_http`.
- Call ``client.chat.completions.create`` with **exactly** these kwargs and no others:
  ``model``, ``max_tokens``, ``temperature``, ``messages``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment,misc]

DEFAULT_MODEL = "gpt-4o-mini"


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
        """Extract from OpenAI usage object; missing fields default to 0; None → all zeros.

        OpenAI surfaces ``prompt_tokens`` / ``completion_tokens``. Cached input lives in
        ``prompt_tokens_details.cached_tokens`` and is a *subset* of ``prompt_tokens``,
        so we leave ``cache_read_input_tokens`` at 0 to keep ``billable_input`` honest
        (no double-counting).
        """
        if sdk_usage is None:
            return cls(0, 0, 0, 0)
        return cls(
            int(getattr(sdk_usage, "prompt_tokens", 0) or 0),
            int(getattr(sdk_usage, "completion_tokens", 0) or 0),
            0,
            0,
        )


@dataclass(frozen=True)
class AnthropicResult:
    """Kept for backward compatibility with the Anthropic-era helper return type.

    Field semantics are unchanged: ``text`` is the assistant message body, ``usage``
    is the normalized token counts, ``raw`` is the SDK response object.
    """

    text: str
    usage: Usage
    raw: Any


def _resolve_model(model: str | None) -> str:
    if model is not None:
        m = str(model).strip()
        if m:
            return m
    env_m = (os.getenv("OPENAI_MODEL") or "").strip()
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
    """OpenAI chat.completions wrapper. Name retained for call-site stability.

    Returns None when no response object exists:

    - Missing or empty ``OPENAI_API_KEY``
    - ``openai`` package unavailable (import failed)
    - Any exception raised during ``chat.completions.create``
    - Missing or falsy response object returned after ``create`` (defensive)

    On a successful API call, always returns :class:`AnthropicResult`, including when
    extracted text is empty: ``AnthropicResult(text="", usage=<from SDK>, raw=<resp>)``.
    Callers that distinguish "empty response with billed tokens" from "no response"
    should branch on ``result is None`` first, then on ``result.text``.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    if OpenAI is None:
        return None

    resolved_model = _resolve_model(model)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        resp = client.chat.completions.create(
            model=resolved_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
    except Exception:
        logging.exception(
            "call_anthropic_messages: OpenAI SDK call failed (model=%s)",
            resolved_model,
        )
        return None

    if not resp:
        return None

    choice = resp.choices[0] if getattr(resp, "choices", None) else None
    text = ""
    if choice is not None and getattr(choice, "message", None) is not None:
        text = (choice.message.content or "").strip()

    return AnthropicResult(
        text=text,
        usage=Usage.from_sdk_usage(getattr(resp, "usage", None)),
        raw=resp,
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
