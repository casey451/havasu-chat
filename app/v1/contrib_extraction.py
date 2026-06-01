"""Flyer/image field extraction for contribution flow (master spec §6)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.llm_messages import coerce_llm_text_to_json_object

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = (
    "You extract structured local event or business facts from user text or flyer descriptions. "
    "Return JSON only with keys: type (event|business|tip), title, date, time, venue, "
    "address, price, phone, website, host, notes. Use null for unknown fields."
)


def extract_from_text(text: str) -> dict[str, Any]:
    from app.core.llm_messages import call_anthropic_messages

    raw = (text or "").strip()
    if not raw:
        return {}
    result = call_anthropic_messages(
        system_prompt=_EXTRACT_SYSTEM,
        user_text=raw[:4000],
        max_tokens=400,
        temperature=0.0,
    )
    if result is None or not result.text:
        return {}
    parsed = coerce_llm_text_to_json_object(result.text)
    return parsed if isinstance(parsed, dict) else {}


def extract_from_image_bytes(content: bytes, *, mime: str) -> dict[str, Any]:
    """Vision extraction when OpenAI key is set; otherwise empty dict."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or not content:
        return {}
    try:
        from openai import OpenAI
    except ImportError:
        return {}

    b64 = base64.standard_b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    try:
        client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            max_tokens=500,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract fields from this flyer image for Lake Havasu City.",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
    except Exception:
        logger.exception("contrib_vision_extract_failed")
        return {}
    if not resp or not resp.choices:
        return {}
    text = (resp.choices[0].message.content or "").strip()
    parsed = coerce_llm_text_to_json_object(text)
    return parsed if isinstance(parsed, dict) else {}
