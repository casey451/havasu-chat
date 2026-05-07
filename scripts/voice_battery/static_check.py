"""Static voice battery — runs all questions in tests/voice_battery/questions.yaml
through the local chat router (zero LLM tokens for Tier 1 / Tier 2 shortcut paths;
Tier 3 routes are *not fired* — only the routing decision + intended Context payload
are recorded).

Output: tests/voice_battery/reports/static_check.md (human-readable) plus
        tests/voice_battery/reports/static_check.jsonl (raw rows).

Usage:
    python -m scripts.voice_battery.static_check

Exit code is 0 even when expectations fail — the report flags issues for review,
this is not a test runner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Defer heavy imports until after argparse / path setup so --help is fast.

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = REPO_ROOT / "tests" / "voice_battery" / "questions.yaml"
REPORT_DIR = REPO_ROOT / "tests" / "voice_battery" / "reports"
REPORT_MD = REPORT_DIR / "static_check.md"
REPORT_JSONL = REPORT_DIR / "static_check.jsonl"


def _load_yaml(path: Path) -> list[dict[str, Any]]:
    """Lightweight YAML loader — supports the subset used by questions.yaml.

    Avoids a hard dependency on PyYAML so the harness runs out-of-the-box. Falls
    back to PyYAML if PyYAML is installed and the inline parser fails.
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]

        return list(yaml.safe_load(text) or [])
    except Exception:
        # Inline minimal parser handles the question schema if PyYAML unavailable.
        return _inline_yaml(text)


def _inline_yaml(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_field: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- ") and indent == 0:
            if current is not None:
                items.append(current)
            current = {}
            list_field = None
            after = stripped[2:]
            if ":" in after:
                k, _, v = after.partition(":")
                current[k.strip()] = _coerce(v.strip())
            continue
        if current is None:
            continue
        if ":" in stripped and indent == 2:
            k, _, v = stripped.partition(":")
            v = v.strip()
            if not v:
                # Could be a list field on the next line.
                list_field = k.strip()
                current[list_field] = []
                continue
            current[k.strip()] = _coerce(v)
            list_field = None
        elif stripped.startswith("- ") and list_field is not None:
            current[list_field].append(_coerce(stripped[2:].strip()))
    if current is not None:
        items.append(current)
    return items


def _coerce(v: str) -> Any:
    s = v.strip()
    if not s:
        return ""
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        if not body:
            return []
        return [_coerce(p.strip()) for p in body.split(",")]
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        return s


def _summarize_response(response: str | None) -> str:
    if not response:
        return ""
    one = " ".join(response.split())
    if len(one) > 240:
        one = one[:237] + "..."
    return one


def _grade_row(
    q: dict[str, Any], observed_tier: str, response: str | None
) -> tuple[str, str]:
    """Quick deterministic grading: PASS/FAIL on tier match + must_contain checks.

    For nuanced voice judgments the harness defers to the (separate) LLM grader —
    this static pass only catches routing regressions and hard string assertions.
    """
    expected_tier = str(q.get("expected_tier") or "")
    if expected_tier and observed_tier and observed_tier != expected_tier:
        return ("FAIL", f"tier_mismatch: expected={expected_tier} observed={observed_tier}")
    must_contain = q.get("must_contain") or []
    if response is not None and isinstance(must_contain, list):
        for s in must_contain:
            if s and isinstance(s, str) and s.lower() not in response.lower():
                return ("FAIL", f"missing must_contain: {s!r}")
    must_not = q.get("must_not_contain") or []
    if response is not None and isinstance(must_not, list):
        for s in must_not:
            if s and isinstance(s, str) and s.lower() in response.lower():
                return ("FAIL", f"present must_not_contain: {s!r}")
    return ("PASS", "")


def _run() -> int:
    if not QUESTIONS_PATH.is_file():
        print(f"questions.yaml not found at {QUESTIONS_PATH}", file=sys.stderr)
        return 2
    questions = _load_yaml(QUESTIONS_PATH)
    if not questions:
        print("questions.yaml parsed but empty", file=sys.stderr)
        return 2

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Imports deferred to keep --help fast; also so a broken app doesn't kill argparse.
    from app.chat.unified_router import route as _route

    rows: list[dict[str, Any]] = []
    by_shape: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # We open one DB session for all queries to keep the run tight; route() uses it
    # for entity resolution + Tier 1 SQL lookups.
    from app.db.database import SessionLocal

    allow_llm = os.getenv("VOICE_BATTERY_ALLOW_LLM") == "1"
    if not allow_llm:
        # Suppress the API key so Tier 3 / Tier 2 LLM parser short-circuit to fallback
        # without spending tokens. The router treats unset key as "graceful fallback".
        # P1.5: provider swapped Anthropic -> OpenAI, so the key to nuke is OPENAI_API_KEY.
        os.environ["OPENAI_API_KEY"] = ""

    started = datetime.utcnow().isoformat() + "Z"

    with SessionLocal() as db:
        for q in questions:
            qid = str(q.get("id") or "")
            query = str(q.get("query") or "")
            shape = str(q.get("intent_shape") or "")
            try:
                resp = _route(query, session_id=None, db=db)
                tier = resp.tier_used or ""
                response_text = resp.response or ""
                tokens = resp.llm_tokens_used
                latency_ms = resp.latency_ms
                error: str | None = None
            except Exception as exc:  # pragma: no cover - defensive
                tier = "exception"
                response_text = ""
                tokens = None
                latency_ms = None
                error = f"{type(exc).__name__}: {exc}"

            verdict, reason = _grade_row(q, tier, response_text)
            row = {
                "id": qid,
                "query": query,
                "intent_shape": shape,
                "expected_tier": str(q.get("expected_tier") or ""),
                "observed_tier": tier,
                "response": _summarize_response(response_text),
                "tokens_used": tokens,
                "latency_ms": latency_ms,
                "verdict": verdict,
                "reason": reason,
                "error": error,
                "notes": q.get("notes") or "",
            }
            rows.append(row)
            by_shape[shape].append(row)

    finished = datetime.utcnow().isoformat() + "Z"

    # Write JSONL (one row per question)
    with REPORT_JSONL.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Aggregate stats.
    total = len(rows)
    pass_n = sum(1 for r in rows if r["verdict"] == "PASS")
    fail_n = total - pass_n
    nonzero_token_factual_listing = [
        r
        for r in rows
        if r["expected_tier"] in ("1", "2") and (r["tokens_used"] or 0) > 0
    ]

    lines: list[str] = []
    lines.append("# Voice battery — static check report")
    lines.append("")
    lines.append(f"**Run started:** {started}  ")
    lines.append(f"**Run finished:** {finished}")
    lines.append("")
    lines.append(f"- Total questions: **{total}**")
    lines.append(f"- PASS: **{pass_n}**")
    lines.append(f"- FAIL: **{fail_n}**")
    lines.append(
        f"- Tier 1/2 cases that spent tokens (cost-discipline violations): "
        f"**{len(nonzero_token_factual_listing)}**"
    )
    lines.append("")
    lines.append("Tier 3 cases were routed but the LLM call was suppressed (no key) so")
    lines.append("they show the fallback message; Tier 3 voice quality is graded separately by the")
    lines.append("LLM grader (`scripts/voice_battery/grade.py`, not run here).")
    lines.append("")
    lines.append("---")
    lines.append("")

    for shape in sorted(by_shape):
        bucket = by_shape[shape]
        lines.append(f"## {shape} ({len(bucket)} cases)")
        lines.append("")
        lines.append("| id | expected | observed | verdict | response (truncated) |")
        lines.append("|---|---|---|---|---|")
        for r in bucket:
            resp = (r["response"] or "").replace("|", "\\|")
            if len(resp) > 120:
                resp = resp[:117] + "..."
            lines.append(
                f"| {r['id']} | {r['expected_tier']} | {r['observed_tier']} | "
                f"{r['verdict']} | {resp} |"
            )
        # Notes / FAILs detail
        fails = [r for r in bucket if r["verdict"] == "FAIL" or r["notes"]]
        if fails:
            lines.append("")
            lines.append("**Detail (FAILs and pre-flagged notes):**")
            lines.append("")
            for r in fails:
                tag = "FAIL" if r["verdict"] == "FAIL" else "note"
                head = f"- `{r['id']}` ({tag}): "
                bits: list[str] = []
                if r["reason"]:
                    bits.append(r["reason"])
                if r["notes"]:
                    bits.append(str(r["notes"]))
                lines.append(head + " — ".join(bits))
                lines.append(f"  - query: `{r['query']}`")
                lines.append(f"  - response: `{r['response']}`")
        lines.append("")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD.relative_to(REPO_ROOT)}")
    print(f"Wrote {REPORT_JSONL.relative_to(REPO_ROOT)}")
    print(f"Total: {total}, PASS: {pass_n}, FAIL: {fail_n}, Tier1/2 token leaks: {len(nonzero_token_factual_listing)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.parse_args()
    return _run()


if __name__ == "__main__":
    sys.exit(main())
