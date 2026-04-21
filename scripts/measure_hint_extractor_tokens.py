"""One-off: mean OpenAI tokens for hint_extractor-style calls (Phase 6.4 gate).

Run from repo root with OPENAI_API_KEY set. Uses the same prompt file and
parameters as ``app.chat.hint_extractor``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402
from app.chat.hint_extractor import _load_hint_prompt  # noqa: E402

try:
    from openai import OpenAI
except ImportError:
    print("openai not installed", file=sys.stderr)
    raise SystemExit(1)

QUERIES = [
    "my 6-year-old likes BMX",
    "what's open right now",
    "we're staying near the channel",
    "Events tomorrow",
    "Things to do this weekend",
    "Thanks",
    "my kid wants something fun",
    "good things near the island bridge",
    "When does the farmers market start on Thursday?",
    "Is altitude open late on Friday?",
    "Does Rotary Park have programs for 8-year-olds?",
    "Pick one thing to do with kids this weekend",
]


def main() -> int:
    ensure_dotenv_loaded()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2
    model = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4.1-mini"
    system = _load_hint_prompt()
    client = OpenAI(api_key=api_key)
    ins: list[int] = []
    outs: list[int] = []
    for q in QUERIES:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"User message:\n{q}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        u = getattr(completion, "usage", None)
        if u is None:
            continue
        ins.append(int(getattr(u, "prompt_tokens", 0) or 0))
        outs.append(int(getattr(u, "completion_tokens", 0) or 0))
    if not ins:
        print("no usage rows", file=sys.stderr)
        return 1
    print(f"n={len(ins)}")
    print(f"mean_prompt_tokens={sum(ins) / len(ins):.2f}")
    print(f"mean_completion_tokens={sum(outs) / len(outs):.2f}")
    print(f"max_prompt_tokens={max(ins)} max_completion_tokens={max(outs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
