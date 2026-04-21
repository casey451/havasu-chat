"""OpenAI hint extraction for session memory (Phase 6.4).

Separate from heuristic ``classify()`` — one gpt-4.1-mini JSON call per turn when
``OPENAI_API_KEY`` is set. On failure or missing key, returns ``None`` (no-op).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[misc, assignment]


class ExtractedHints(BaseModel):
    age: int | str | None = None
    location: str | None = None


class _HintEnvelope(BaseModel):
    extracted_hints: ExtractedHints | None = None


def _load_hint_prompt() -> str:
    root = Path(__file__).resolve().parents[2]
    path = root / "prompts" / "hint_extractor.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        'Return JSON: {"extracted_hints": null} unless age or location is explicitly given '
        "per Lake Havasu local phrasing rules."
    )


def extract_hints(query: str) -> ExtractedHints | None:
    """Call gpt-4.1-mini for optional age/location hints. Returns ``None`` on skip/failure."""
    q = (query or "").strip()
    if not q:
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        return None

    model = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4.1-mini"
    system = _load_hint_prompt()
    user = f"User message:\n{q}"

    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except Exception:
        logging.exception("hint_extractor: OpenAI chat.completions.create failed")
        return None

    choice = completion.choices[0] if completion.choices else None
    raw = (choice.message.content or "").strip() if choice and choice.message else ""
    if not raw:
        return None

    usage = getattr(completion, "usage", None)
    if usage is not None:
        inp = int(getattr(usage, "prompt_tokens", 0) or 0)
        out = int(getattr(usage, "completion_tokens", 0) or 0)
        if inp > 300 or out > 100:
            logging.warning(
                "hint_extractor: token usage exceeds soft budget (inp=%s out=%s)",
                inp,
                out,
            )

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        logging.info("hint_extractor: invalid JSON from model")
        return None

    try:
        env = _HintEnvelope.model_validate(data)
    except Exception:
        logging.info("hint_extractor: envelope validation failed: %r", raw[:200])
        return None

    if env.extracted_hints is None:
        return None
    h = env.extracted_hints
    loc_ok = isinstance(h.location, str) and h.location.strip()
    if h.age is None and not loc_ok:
        return None
    return h
