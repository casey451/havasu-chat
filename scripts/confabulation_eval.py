"""CLI runner for confabulation eval harness (8.8.6 step 0)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Iterable

from sqlalchemy import select

# Allow `python scripts/confabulation_eval.py` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.database import SessionLocal
from app.db.models import Program, Provider
from app.eval.confabulation_detector import InvocationResult as DetectorInput
from app.eval.confabulation_detector import detect
from app.eval.confabulation_invoker import HttpInvoker, InProcessInvoker
from app.eval.confabulation_query_gen import Probe, generate_probes, normalize_row_name_for_include
from app.eval.confabulation_report import write_jsonl, write_per_row_csv, write_summary_md


def _parse_csv_arg(s: str | None) -> set[str]:
    if not s:
        return set()
    return {normalize_row_name_for_include(x) for x in s.split(",") if x.strip()}


def _probe_name_map() -> dict[str, str]:
    out: dict[str, str] = {}
    with SessionLocal() as db:
        for p in db.scalars(select(Provider).where(Provider.draft.is_(False), Provider.is_active.is_(True))).all():
            out[p.id] = p.provider_name
        for pr in db.scalars(select(Program).where(Program.draft.is_(False), Program.is_active.is_(True))).all():
            out[pr.id] = pr.title
    return out


def _select_probes(
    probes: list[Probe],
    *,
    rows_mode: str,
    include: set[str],
    exclude: set[str],
    limit: int | None,
    name_map: dict[str, str],
) -> list[Probe]:
    q: list[Probe] = []
    for p in probes:
        if rows_mode == "providers" and p.row_type != "provider":
            continue
        if rows_mode == "programs" and p.row_type != "program":
            continue
        name = name_map.get(p.row_id, "")
        lname = normalize_row_name_for_include(name)
        if include and lname not in include:
            continue
        if exclude and lname in exclude:
            continue
        q.append(p)
    if limit is not None:
        return q[:limit]
    return q


def _flag_states(mode: str) -> list[str]:
    if mode == "both":
        return ["off", "on"]
    return [mode]


def _default_output_dir() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("scripts/confabulation_eval_results") / ts


def _run_once(invoker, probe: Probe, flag_state: str) -> dict:
    inv = invoker.invoke(probe, flag_state)
    d = DetectorInput(
        response_text=inv.response_text,
        evidence_row_dicts=inv.evidence_row_dicts,
        http_degraded=(len(inv.evidence_row_dicts) == 0),
        is_http_mode=(len(inv.evidence_row_dicts) == 0),
    )
    hits = detect(d)
    return {
        "probe": asdict(probe),
        "flag_state": flag_state,
        "response_text": inv.response_text,
        "evidence_row_dicts": inv.evidence_row_dicts,
        "tier_used": inv.tier_used,
        "latency_ms": inv.latency_ms,
        "raw_log": inv.raw_log,
        "error": inv.error,
        "hits": [asdict(h) for h in hits],
    }


def _enrich_for_reports(records: list[dict], name_map: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    for r in records:
        p = r["probe"]
        raw_hits: list[dict] = list(r.get("hits", []))
        l1 = [h for h in raw_hits if h.get("layer") == "1_advisory"]
        l2 = [h for h in raw_hits if h.get("layer") == "2"]
        l3 = [h for h in raw_hits if h.get("layer") == "3"]
        gating_hit_count = len(l2) + len(l3)
        advisory_hit_count = len(l1)
        gating_tokens = [h["token"] for h in l2 + l3]
        layer_1_advisory_tokens = [h["token"] for h in l1]
        tier = str(r.get("tier_used") or "")
        if tier == "1":
            excluded = True
            excluded_reason = "tier_1_no_formatter"
        elif tier == "chat":
            excluded = True
            excluded_reason = "tier_chat_no_formatter"
        elif tier == "3" and not l2:
            excluded = True
            excluded_reason = "tier_3_no_layer2_hits"
        else:
            excluded = False
            excluded_reason = None
        out.append(
            {
                "query_text": p["query_text"],
                "template_id": p["template_id"],
                "row_id": p["row_id"],
                "row_name": name_map.get(p["row_id"], p["row_id"]),
                "row_type": p["row_type"],
                "flag_state": r["flag_state"],
                "run_index": r.get("run_index", 0),
                "response_text": r["response_text"],
                "tier_used": r["tier_used"],
                "excluded_from_summary": excluded,
                "excluded_reason": excluded_reason,
                "latency_ms": r["latency_ms"],
                "evidence_row_dicts": r["evidence_row_dicts"],
                "hits": raw_hits,
                "layer_1_advisory_hits": l1,
                "layer_2_hits": l2,
                "layer_3_hits": l3,
                "layer_1_advisory_tokens": layer_1_advisory_tokens,
                "gating_hit_count": gating_hit_count,
                "advisory_hit_count": advisory_hit_count,
                "hit_count": gating_hit_count,
                "hit_tokens": gating_tokens,
                "gating_tokens": gating_tokens,
                "error": r["error"],
            }
        )
    return out


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run confabulation eval harness")
    ap.add_argument("--mode", choices=["inprocess", "http"], default="inprocess")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--flags", choices=["off", "on", "both"], default="both")
    ap.add_argument("--rows", choices=["providers", "programs", "both"], default="both")
    ap.add_argument("--output-dir", default=str(_default_output_dir()))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include", default="", help="Comma-separated row names")
    ap.add_argument("--exclude", default="", help="Comma-separated row names")
    args = ap.parse_args(list(argv) if argv is not None else None)

    include = _parse_csv_arg(args.include)
    exclude = _parse_csv_arg(args.exclude)
    name_map = _probe_name_map()

    with SessionLocal() as db:
        probes = generate_probes(db)
    probes = _select_probes(
        probes,
        rows_mode=args.rows,
        include=include,
        exclude=exclude,
        limit=args.limit,
        name_map=name_map,
    )

    if args.mode == "inprocess":
        invoker = InProcessInvoker(session_id="confab-eval")
    else:
        invoker = HttpInvoker(base_url=args.base_url, session_id="confab-eval")

    raw: list[dict] = []
    for p in probes:
        for flag in _flag_states(args.flags):
            for i in range(args.runs):
                rec = _run_once(invoker, p, flag)
                rec["run_index"] = i
                raw.append(rec)

    report_records = _enrich_for_reports(raw, name_map)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    write_jsonl(outdir / "runs.jsonl", report_records)
    write_summary_md(outdir / "summary.md", report_records)
    write_per_row_csv(outdir / "per_row.csv", report_records)
    print(f"Wrote {len(report_records)} runs to {outdir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
