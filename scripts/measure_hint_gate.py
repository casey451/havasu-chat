"""Measure hint-extractor gate selectivity (VPS rollout HANDOFF #1, measure step).

Read-only, no network. Replays the intent phrase bank (the best query corpus
committed to the repo: ~5.6k phrases across the 22 handled intents) through the
shipped signal gate ``has_hint_signal()`` to report what fraction of turns would
still trigger the synchronous gpt-4.1-mini call in ``conditional`` mode vs. be
skipped by the regex prefilter.

The bank is synthetic (templated) and weighted toward ``find_service``, so read
the per-intent rates — which are corpus-mix-independent — alongside the blended
total. ``extract_hints`` output feeds *session onboarding hints*, not tier
routing, so this measures LLM-call rate, not routing changes.

Run:  python -m scripts.measure_hint_gate
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.chat.hint_extractor import has_hint_signal

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "tests" / "fixtures" / "intent_phrase_bank.json"


def main() -> None:
    data: dict[str, list[str]] = json.loads(BANK.read_text(encoding="utf-8"))

    total = passed = 0
    per_intent_total: Counter[str] = Counter()
    per_intent_passed: Counter[str] = Counter()
    near_me = 0

    for intent, phrases in data.items():
        for p in phrases:
            total += 1
            per_intent_total[intent] += 1
            if has_hint_signal(p):
                passed += 1
                per_intent_passed[intent] += 1
                if re.search(r"near\s*(me|by)\b|nearby", p, re.I):
                    near_me += 1

    skipped = total - passed
    print(f"corpus phrases           : {total}")
    print(f"PASS gate -> LLM call    : {passed:5d}  ({passed / total:6.1%})")
    print(f"SKIP gate -> no API call : {skipped:5d}  ({skipped / total:6.1%})")
    print(f"  (residual 'near me/nearby' passers: {near_me})")
    print("Old behavior (mode=always): 100% of turns call the LLM.")
    print()
    print("Per-intent gate-pass rate:")
    for intent in sorted(per_intent_total, key=lambda k: -per_intent_passed[k] / per_intent_total[k]):
        t, pa = per_intent_total[intent], per_intent_passed[intent]
        print(f"  {intent:16s} {pa:4d}/{t:<4d} {pa / t:6.1%}")


if __name__ == "__main__":
    main()
