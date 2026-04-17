"""
Diagnostic script: fire ~25 realistic queries at the live Havasu Chat app,
summarise results, flag anomalies, and cross-reference search_debug.log.
Output saved to scripts/diagnose_output.txt.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from uuid import uuid4

BASE_URL = "https://web-production-bbe17.up.railway.app"
OUTPUT_FILE = Path(__file__).parent / "diagnose_output.txt"
LOG_FILE = Path(__file__).parent.parent / "search_debug.log"

TEST_QUERIES = [
    # Specific activities
    "boat races this weekend",
    "boat race",
    "concert tonight",
    "live music friday",
    "yoga class",
    "pickleball",
    # Date phrases
    "what's on tonight",
    "anything tomorrow",
    "things to do this weekend",
    "events saturday",
    "next friday",
    "next week",
    # Audience
    "kids activities",
    "something for my 8 year old",
    "family friendly events",
    "adults only",
    # Open-ended
    "what's happening",
    "things to do",
    "anything fun",
    "surprise me",
    # Edge cases
    "hi",
    "idk",
    "boat rces ths weeknd",  # typos
    "I am looking for something really fun to do this coming weekend with my whole family including my 3 kids ages 5 7 and 10",  # very long
    "x",  # very short
]


def chat(session_id: str, message: str) -> dict:
    payload = json.dumps({"session_id": session_id, "message": message}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"response": f"HTTP {e.code}", "intent": "ERROR", "data": {}}
    except Exception as exc:
        return {"response": f"ERROR: {exc}", "intent": "ERROR", "data": {}}


def first_line(text: str, limit: int = 90) -> str:
    first = text.strip().split("\n")[0]
    return first[:limit] + ("…" if len(first) > limit else "")


def run() -> None:
    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding, errors="replace"))
        lines.append(s)

    out("=" * 70)
    out("HAVASU CHAT — SEARCH DIAGNOSTIC")
    out(f"Target: {BASE_URL}")
    out("=" * 70)
    out()

    results = []
    top_responses: Counter = Counter()

    for query in TEST_QUERIES:
        sid = str(uuid4())
        data = chat(sid, query)
        response_text = data.get("response", "")
        intent = data.get("intent", "?")
        count = data.get("data", {}).get("count", "?")
        first = first_line(response_text)
        top_responses[first] += 1
        results.append({
            "query": query,
            "intent": intent,
            "count": count,
            "first_line": first,
            "full_response": response_text,
        })
        status = "OK"
        if "ERROR" in intent:
            status = "ERR"
        elif response_text.strip() == "":
            status = "EMPTY"
        out(f"{status}  [{intent:<16}] Q: {query!r}")
        out(f"   → {first}")
        out()

    # ── Anomaly detection ────────────────────────────────────────────────
    out("=" * 70)
    out("ANOMALY FLAGS")
    out("=" * 70)
    out()

    # Same first line appearing 3+ times = scoring problem
    for resp_line, n in top_responses.most_common():
        if n >= 3:
            offenders = [r["query"] for r in results if r["first_line"] == resp_line]
            out(f"!! REPEATED TOP RESULT (x{n}): {resp_line!r}")
            out(f"   Triggered by: {offenders}")
            out()

    # No results
    no_result = [r for r in results if r["count"] == 0 or "Nothing" in r["first_line"] or "No " in r["first_line"][:6]]
    if no_result:
        out("-- ZERO-RESULT queries (may be correct or may need synonym help):")
        for r in no_result:
            out(f"   * {r['query']!r}  -> {r['first_line']}")
        out()

    # Errors
    errors = [r for r in results if r["intent"] == "ERROR"]
    if errors:
        out("XX ERRORS:")
        for r in errors:
            out(f"   * {r['query']!r}  -> {r['first_line']}")
        out()

    if not no_result and not errors and all(n < 3 for n in top_responses.values()):
        out("OK No obvious anomalies detected.")
        out()

    # ── Full responses ────────────────────────────────────────────────────
    out("=" * 70)
    out("FULL RESPONSES")
    out("=" * 70)
    for r in results:
        out()
        out(f"QUERY   : {r['query']!r}")
        out(f"INTENT  : {r['intent']}   COUNT: {r['count']}")
        out("RESPONSE:")
        for ln in r["full_response"].splitlines():
            out("  " + ln)
        out("-" * 50)

    # ── Log tail ──────────────────────────────────────────────────────────
    out()
    out("=" * 70)
    out("SEARCH DEBUG LOG (last 500 lines)")
    out("=" * 70)
    if LOG_FILE.exists():
        all_lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = all_lines[-500:]
        for ln in tail:
            out(ln)
    else:
        out(f"(log file not found at {LOG_FILE})")
        out("Note: on Railway the log lives inside the container; run this script")
        out("locally against a local server, or download the file via Railway shell.")

    out()
    out("=" * 70)
    out(f"Output saved to: {OUTPUT_FILE}")
    out("=" * 70)

    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
