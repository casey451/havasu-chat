"""LLM-graded voice battery — runs every question through the live router (firing
Tier 2 / Tier 3 LLM calls when the route reaches them), then sends each
(query, response) pair to the judge LLM using ``prompts/voice_audit.txt`` as the
rubric prompt. Returns PASS / MINOR / FAIL verdicts with rule citations and
suggested rewrites for any FAILs/MINORs.

Output:
    tests/voice_battery/reports/graded_<timestamp>.md   (human-readable report)
    tests/voice_battery/reports/graded_<timestamp>.jsonl (raw rows, one per question)

Cost: ~$0.05–0.15 per full 200-question run on gpt-4o-mini after the P1.5
provider swap (varies with how often Tier 3 fires). The judge call alone is
~$0.0006 per question; the route() calls add Tier 2/3 token spend the live app
would have spent anyway.

Usage:
    # Full run, live LLM calls allowed:
    python -m scripts.voice_battery.grade

    # Smoke run, first 10 questions only:
    python -m scripts.voice_battery.grade --limit 10

    # Single intent shape:
    python -m scripts.voice_battery.grade --shape factual_phone

Environment:
    OPENAI_API_KEY    required — both the live router's Tier 2/3 calls and the
                       judge call use it. Without it, route() returns the
                       graceful fallback for synthesis paths and the judge
                       cannot grade.
    OPENAI_MODEL      optional — overrides the default model
                       (``gpt-4o-mini``) for both router calls and the judge.
                       Override via ``--judge-model`` to scope only the judge
                       call (e.g. use a stronger evaluator like ``gpt-4.1-mini``
                       while keeping the router on 4o-mini).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    """Load ``.env`` from the repo root into ``os.environ`` for missing keys.

    Voice-battery 2026-05-07: 200/200 ERROR run surfaced silent failures when
    ``OPENAI_API_KEY`` wasn't set in the shell session. Both the live router
    (Tier 2 parser/formatter, Tier 3 synthesis) and the judge call need the
    key — without it everything falls to the graceful-fallback path and the
    judge has nothing to grade. Load ``.env`` here so the harness works in a
    fresh PowerShell session without explicit ``$env:OPENAI_API_KEY = ...``.

    Existing environment variables win over ``.env`` so this is non-destructive.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # Best-effort; if .env can't be read, fall through and let downstream
        # missing-key checks handle it (with logged errors per-call).
        pass


_load_env_file()
QUESTIONS_PATH = REPO_ROOT / "tests" / "voice_battery" / "questions.yaml"
RUBRIC_PATH = REPO_ROOT / "prompts" / "voice_audit.txt"
REPORT_DIR = REPO_ROOT / "tests" / "voice_battery" / "reports"

_JUDGE_MAX_TOKENS = 700  # bumped from 300: long Tier 2 listings + framing prefix
_JUDGE_TEMPERATURE = 0.0  # made the judge's suggested_rewrite overrun the cap and
# return truncated, unparseable JSON (recorded as ERROR rows). 700 fits the longest
# rewrites observed in the battery without meaningfully changing per-call cost.


def _load_questions(path: Path) -> list[dict[str, Any]]:
    """Reuse the static_check YAML loader so the two harnesses parse identically."""
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.voice_battery.static_check import _load_yaml  # type: ignore

    return _load_yaml(path)


def _summarize_response(response: str | None, max_chars: int = 240) -> str:
    if not response:
        return ""
    one = " ".join(response.split())
    if len(one) > max_chars:
        one = one[: max_chars - 3] + "..."
    return one


def _build_judge_sample(q: dict[str, Any], observed_tier: str, response_text: str) -> dict[str, Any]:
    """Shape the per-question payload the judge prompt expects (per voice_audit.txt §13)."""
    tags: list[str] = []
    shape = str(q.get("intent_shape") or "")
    # Heuristic tag mapping — voice_audit.txt's optional tags help the judge pick the right pattern.
    if "out_of_scope" in shape or "oos" in shape:
        tags.append("out_of_scope")
    if "gap" in shape or "not_in_catalog" in shape:
        tags.append("not_in_catalog")
    if "intake" in shape or "contribute" in shape:
        tags.append("intake")
    if "correction" in shape or "correct" in shape:
        tags.append("correction")
    if "rec" in shape or "recommend" in shape or "open_ended" in shape:
        tags.append("explicit_rec_query")

    tier_label = "tier1" if observed_tier == "1" else "tier3" if observed_tier == "3" else "tier2"
    sample: dict[str, Any] = {
        "sample_id": str(q.get("id") or ""),
        "tier": tier_label,
        "intent_or_mode": shape,
        "user_query": str(q.get("query") or ""),
        "assistant_text": response_text or "",
    }
    if tags:
        sample["tags"] = tags
    return sample


def _judge(rubric: str, sample: dict[str, Any], judge_model: str | None) -> dict[str, Any] | None:
    """Send the sample to the judge LLM. Return parsed JSON verdict or None on failure."""
    from app.core.llm_messages import call_anthropic_messages, coerce_llm_text_to_json_object

    user_text = "Sample to audit:\n" + json.dumps(sample, ensure_ascii=False)
    result = call_anthropic_messages(
        system_prompt=rubric,
        user_text=user_text,
        max_tokens=_JUDGE_MAX_TOKENS,
        temperature=_JUDGE_TEMPERATURE,
        model=judge_model,
    )
    if result is None or not result.text:
        return None
    parsed = coerce_llm_text_to_json_object(result.text)
    if parsed is None:
        return None
    # Attach token usage as a sidecar so the report can show per-call cost discipline.
    parsed["_judge_input_tokens"] = result.usage.billable_input
    parsed["_judge_output_tokens"] = result.usage.output_tokens
    return parsed


def _run(args: argparse.Namespace) -> int:
    if not QUESTIONS_PATH.is_file():
        print(f"questions.yaml not found at {QUESTIONS_PATH}", file=sys.stderr)
        return 2
    if not RUBRIC_PATH.is_file():
        print(f"voice_audit.txt rubric not found at {RUBRIC_PATH}", file=sys.stderr)
        return 2

    questions = _load_questions(QUESTIONS_PATH)
    if not questions:
        print("questions.yaml parsed but empty", file=sys.stderr)
        return 2

    rubric = RUBRIC_PATH.read_text(encoding="utf-8").strip()

    # Optional filtering for partial runs (smoke tests, single-shape audits).
    if args.shape:
        questions = [q for q in questions if str(q.get("intent_shape") or "") == args.shape]
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]
    if not questions:
        print("No questions matched the filters; nothing to grade.", file=sys.stderr)
        return 2

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    report_md = REPORT_DIR / f"graded_{ts}.md"
    report_jsonl = REPORT_DIR / f"graded_{ts}.jsonl"

    # Imports deferred — keeps --help fast and allows graceful failure if the app fails to import.
    from app.chat.unified_router import route as _route
    from app.db.database import SessionLocal

    rows: list[dict[str, Any]] = []
    by_shape: dict[str, list[dict[str, Any]]] = defaultdict(list)
    started = datetime.utcnow().isoformat() + "Z"

    judge_input_total = 0
    judge_output_total = 0

    # Open the JSONL stream eagerly so partial runs leave usable artifacts on interrupt.
    with report_jsonl.open("w", encoding="utf-8") as jf, SessionLocal() as db:
        for idx, q in enumerate(questions, start=1):
            qid = str(q.get("id") or "")
            query = str(q.get("query") or "")
            shape = str(q.get("intent_shape") or "")

            try:
                resp = _route(query, session_id=None, db=db)
                tier = resp.tier_used or ""
                response_text = resp.response or ""
                tokens = resp.llm_tokens_used
                latency_ms = resp.latency_ms
                route_error: str | None = None
            except Exception as exc:  # pragma: no cover — defensive
                tier = "exception"
                response_text = ""
                tokens = None
                latency_ms = None
                route_error = f"{type(exc).__name__}: {exc}"
                logging.exception("grade: route() raised on %s", qid)

            sample = _build_judge_sample(q, tier, response_text)
            verdict_obj = None
            judge_error: str | None = None
            if response_text:
                try:
                    verdict_obj = _judge(rubric, sample, args.judge_model)
                except Exception as exc:  # pragma: no cover — defensive
                    judge_error = f"{type(exc).__name__}: {exc}"
                    logging.exception("grade: judge call raised on %s", qid)
            else:
                judge_error = "skipped: empty assistant_text"

            verdict = "ERROR"
            cited: list[str] = []
            summary = ""
            rewrite: str | None = None
            judge_notes = ""
            if verdict_obj is not None:
                verdict = str(verdict_obj.get("verdict") or "ERROR").upper()
                cited_raw = verdict_obj.get("voice_rules_cited") or []
                if isinstance(cited_raw, list):
                    cited = [str(x) for x in cited_raw]
                summary = str(verdict_obj.get("summary") or "")
                rewrite_raw = verdict_obj.get("suggested_rewrite")
                rewrite = None if rewrite_raw is None else str(rewrite_raw)
                judge_notes = str(verdict_obj.get("notes") or "")
                judge_input_total += int(verdict_obj.get("_judge_input_tokens") or 0)
                judge_output_total += int(verdict_obj.get("_judge_output_tokens") or 0)

            row = {
                "id": qid,
                "query": query,
                "intent_shape": shape,
                "expected_tier": str(q.get("expected_tier") or ""),
                "observed_tier": tier,
                "response": _summarize_response(response_text),
                "response_full": response_text,
                "tokens_used": tokens,
                "latency_ms": latency_ms,
                "verdict": verdict,
                "voice_rules_cited": cited,
                "summary": summary,
                "suggested_rewrite": rewrite,
                "judge_notes": judge_notes,
                "route_error": route_error,
                "judge_error": judge_error,
                "yaml_notes": q.get("notes") or "",
            }
            rows.append(row)
            by_shape[shape].append(row)
            jf.write(json.dumps(row, ensure_ascii=False) + "\n")
            jf.flush()

            verdict_glyph = {"PASS": ".", "MINOR": "m", "FAIL": "F", "ERROR": "E"}.get(verdict, "?")
            print(f"[{idx:3d}/{len(questions)}] {qid:<28s} tier={tier:<5s} {verdict_glyph} {summary[:60]}", flush=True)

    finished = datetime.utcnow().isoformat() + "Z"

    counts = Counter(r["verdict"] for r in rows)
    total = len(rows)
    pass_n = counts.get("PASS", 0)
    minor_n = counts.get("MINOR", 0)
    fail_n = counts.get("FAIL", 0)
    error_n = counts.get("ERROR", 0)

    # Cost approximation for the JUDGE only (router cost is logged separately in chat_logs).
    # Rough per-token rates for gpt-4o-mini at 2026-05 — update if you change judge_model.
    judge_input_cost = judge_input_total / 1_000_000 * 0.15
    judge_output_cost = judge_output_total / 1_000_000 * 0.60
    judge_total_cost = judge_input_cost + judge_output_cost

    lines: list[str] = []
    lines.append("# Voice battery — LLM-graded report")
    lines.append("")
    lines.append(f"**Run started:** {started}  ")
    lines.append(f"**Run finished:** {finished}")
    lines.append("")
    lines.append(f"- Total questions: **{total}**")
    lines.append(f"- PASS: **{pass_n}**")
    lines.append(f"- MINOR: **{minor_n}**")
    lines.append(f"- FAIL: **{fail_n}**")
    if error_n:
        lines.append(f"- ERROR (judge unreachable / parsed empty): **{error_n}**")
    lines.append("")
    lines.append("**Judge cost (approximate, gpt-4o-mini rates):**")
    lines.append(f"- Judge input tokens: {judge_input_total:,}")
    lines.append(f"- Judge output tokens: {judge_output_total:,}")
    lines.append(f"- Estimated judge spend: ${judge_total_cost:.4f}")
    lines.append("")
    lines.append("Router-side spend (Tier 2 parser/formatter, Tier 3 synthesis) is logged in")
    lines.append("`chat_logs` separately; query that table to see live-app cost contribution.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # FAILs first — flat list across shapes, since these are the action items.
    fails = [r for r in rows if r["verdict"] == "FAIL"]
    if fails:
        lines.append(f"## FAIL — {len(fails)} cases")
        lines.append("")
        for r in fails:
            lines.append(f"### {r['id']} — {r['intent_shape']}")
            lines.append("")
            lines.append(f"- **query:** `{r['query']}`")
            lines.append(f"- **observed tier:** {r['observed_tier']} (expected {r['expected_tier']})")
            cited = ", ".join(r["voice_rules_cited"]) if r["voice_rules_cited"] else "(none)"
            lines.append(f"- **rules cited:** {cited}")
            lines.append(f"- **response:** {r['response']}")
            lines.append(f"- **summary:** {r['summary']}")
            if r["suggested_rewrite"]:
                lines.append(f"- **suggested rewrite:** {r['suggested_rewrite']}")
            if r["judge_notes"]:
                lines.append(f"- **judge notes:** {r['judge_notes']}")
            if r["yaml_notes"]:
                lines.append(f"- **YAML pre-flag:** {r['yaml_notes']}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Then MINORs grouped by intent shape, to make patterns obvious.
    minors = [r for r in rows if r["verdict"] == "MINOR"]
    if minors:
        lines.append(f"## MINOR — {len(minors)} cases")
        lines.append("")
        by_shape_minor: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in minors:
            by_shape_minor[r["intent_shape"]].append(r)
        for shape in sorted(by_shape_minor):
            bucket = by_shape_minor[shape]
            lines.append(f"### {shape} ({len(bucket)})")
            lines.append("")
            for r in bucket:
                cited = ", ".join(r["voice_rules_cited"]) if r["voice_rules_cited"] else "(none)"
                lines.append(f"- `{r['id']}` — {r['summary']}")
                lines.append(f"  - query: `{r['query']}`  ·  rules: {cited}")
                lines.append(f"  - response: {r['response']}")
                if r["suggested_rewrite"]:
                    lines.append(f"  - rewrite: {r['suggested_rewrite']}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # ERRORs — judge failures, route exceptions
    errors = [r for r in rows if r["verdict"] == "ERROR"]
    if errors:
        lines.append(f"## ERROR — {len(errors)} cases (judge unreachable or response empty)")
        lines.append("")
        for r in errors:
            err = r["judge_error"] or r["route_error"] or "(no error captured)"
            lines.append(f"- `{r['id']}` — {err}")
            lines.append(f"  - query: `{r['query']}`")
            lines.append(f"  - response: {r['response']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary table by shape — quick pattern-spotting view.
    lines.append("## Verdict distribution by intent shape")
    lines.append("")
    lines.append("| shape | n | PASS | MINOR | FAIL | ERROR |")
    lines.append("|---|---|---|---|---|---|")
    for shape in sorted(by_shape):
        bucket = by_shape[shape]
        bcounts = Counter(r["verdict"] for r in bucket)
        lines.append(
            f"| {shape} | {len(bucket)} | {bcounts.get('PASS', 0)} | "
            f"{bcounts.get('MINOR', 0)} | {bcounts.get('FAIL', 0)} | {bcounts.get('ERROR', 0)} |"
        )
    lines.append("")

    report_md.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"Wrote {report_md.relative_to(REPO_ROOT)}")
    print(f"Wrote {report_jsonl.relative_to(REPO_ROOT)}")
    print(
        f"Total: {total}  PASS: {pass_n}  MINOR: {minor_n}  FAIL: {fail_n}  ERROR: {error_n}"
    )
    print(f"Judge spend (approx): ${judge_total_cost:.4f}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run only the first N questions (smoke testing). 0 = full battery.",
    )
    p.add_argument(
        "--shape",
        type=str,
        default="",
        help="Restrict to one intent_shape value (e.g. 'factual_phone').",
    )
    p.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help=(
            "Override the judge model only (router uses OPENAI_MODEL env var as usual). "
            "Useful for upgrading the evaluator (e.g. 'gpt-4.1-mini') while keeping "
            "the live app on the cheaper model."
        ),
    )
    args = p.parse_args()
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
