"""Validate a generated phrase bank against the real resolver and write the dataset.

Takes a JSON file of ``{intent_key: [phrases]}`` (or the Phase-2 workflow result
shape ``{result: {banks: [{intent, phrases}]}}``), runs each phrase through
``app.chat.intents.resolver.resolve``, and keeps only phrases that route to their
labeled intent. Writes the validated dataset to
``tests/data/intent_phrase_bank.json`` and prints a per-intent accuracy report.

This makes the LLM-generated phrases a trustworthy regression asset: every phrase
in the committed dataset provably routes as labeled against the current resolver.

Usage:  PYTHONPATH=. python scripts/build_intent_phrase_bank.py <input.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.chat.intents.resolver import resolve

_OUT = Path("tests/fixtures/intent_phrase_bank.json")


def _load_banks(raw: dict) -> list[dict]:
    if "banks" in raw:
        return raw["banks"]
    if "result" in raw and isinstance(raw["result"], dict):
        return raw["result"].get("banks", [])
    # plain {intent: [phrases]}
    return [{"intent": k, "phrases": v} for k, v in raw.items() if isinstance(v, list)]


def main() -> None:
    src = Path(sys.argv[1])
    raw = json.loads(src.read_text(encoding="utf-8"))
    banks = _load_banks(raw)

    validated: dict[str, list[str]] = {}
    total = kept = 0
    print(f"{'intent':<18} kept/seen  dropped phrases (route elsewhere)")
    print("-" * 72)
    for bank in banks:
        intent = bank["intent"]
        phrases = bank.get("phrases", [])
        ok: list[str] = []
        dropped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for p in phrases:
            key = p.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            r = resolve(p)
            got = r.intent_key if r else None
            if got == intent:
                ok.append(p)
            else:
                dropped.append((p, got or "None"))
        validated[intent] = ok
        total += len(seen)
        kept += len(ok)
        drop_str = "; ".join(f"{p!r}->{g}" for p, g in dropped[:4])
        more = f" (+{len(dropped) - 4})" if len(dropped) > 4 else ""
        print(f"{intent:<18} {len(ok):>3}/{len(seen):<3}     {drop_str}{more}")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
    pct = (100.0 * kept / total) if total else 0.0
    print("-" * 72)
    print(f"TOTAL kept {kept}/{total} ({pct:.0f}%) -> {_OUT}")


if __name__ == "__main__":
    main()
