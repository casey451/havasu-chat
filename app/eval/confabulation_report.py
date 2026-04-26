"""Writers for eval artifacts: runs JSONL, summary markdown, and per-row CSV."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: str | Path, runs: list[dict[str, Any]]) -> None:
    p = Path(path)
    _ensure_parent(p)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _gating_tokens(x: dict[str, Any]) -> list[str]:
    return [str(t) for t in (x.get("gating_tokens") or x.get("hit_tokens") or [])]


def _advisory_tokens(x: dict[str, Any]) -> list[str]:
    return [str(t) for t in (x.get("layer_1_advisory_tokens") or [])]


def write_per_row_csv(path: str | Path, runs: list[dict[str, Any]]) -> None:
    p = Path(path)
    _ensure_parent(p)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        key = (str(r.get("row_id", "")), str(r.get("row_name", "")))
        grouped[key].append(r)

    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "row_id",
                "row_name",
                "total_runs",
                "included_runs",
                "gating_runs_with_hit",
                "advisory_token_count",
                "top_3_gating_tokens",
            ]
        )
        for (row_id, row_name), rs in sorted(grouped.items(), key=lambda x: x[0][1].lower()):
            total = len(rs)
            inc = [x for x in rs if not bool(x.get("excluded_from_summary", False))]
            included_n = len(inc)
            gating_hits = sum(1 for x in inc if int(x.get("gating_hit_count", x.get("hit_count", 0)) or 0) > 0)
            adv_c = sum(int(x.get("advisory_hit_count", 0) or 0) for x in inc)
            c: Counter[str] = Counter()
            for x in inc:
                for t in _gating_tokens(x):
                    c[str(t)] += 1
            top = ", ".join(t for t, _ in c.most_common(3))
            w.writerow(
                [row_id, row_name, total, included_n, gating_hits, adv_c, top]
            )


def write_summary_md(path: str | Path, runs: list[dict[str, Any]]) -> None:
    p = Path(path)
    _ensure_parent(p)

    by_tier: Counter[str] = Counter()
    for r in runs:
        by_tier[str(r.get("tier_used", "unknown"))] += 1

    included = [r for r in runs if not bool(r.get("excluded_from_summary", False))]
    excluded = [r for r in runs if bool(r.get("excluded_from_summary", False))]
    excluded_t1 = sum(1 for r in excluded if str(r.get("tier_used", "")) == "1")
    excluded_t3_nol2 = sum(
        1
        for r in excluded
        if str(r.get("tier_used", "")) == "3" and not (r.get("layer_2_hits") or [])
    )
    tier3_l2_included = sum(
        1
        for r in included
        if str(r.get("tier_used", "")) == "3" and (r.get("layer_2_hits") or [])
    )

    def _gating_rate_nz(rs: list[dict[str, Any]]) -> int:
        return sum(1 for x in rs if int(x.get("gating_hit_count", x.get("hit_count", 0)) or 0) > 0)

    def _rate_gating(rs: list[dict[str, Any]]) -> float:
        if not rs:
            return 0.0
        return _gating_rate_nz(rs) / len(rs)

    lines: list[str] = []
    lines.append("# Confabulation Eval Summary")
    lines.append("")
    lines.append("## Inclusion policy")
    lines.append(f"- Included in gating-confabulation-rate summary: {len(included)}")
    lines.append(f"- Excluded from gating confabulation-rate summary: {len(excluded)}")
    lines.append(
        "- **Gating rate denominator:** Tier `2` always; Tier `3` when Layer 2 has at least one hit (partial inclusion; spec §3.5.2 / §3.6). "
        "Headline **confabulation rate** uses **Layer 2 + Layer 3** in Tier 2, and **Layer 2** in Tier 3; **Layer 1** is **advisory** (see spec §3.5.1 / §3.6). "
        "Tier `1` and Tier `3` runs with no Layer 2 hits are excluded from the headline denominator."
    )
    lines.append(f"- Tier 1 invocations excluded: {excluded_t1}")
    lines.append(
        f"- Tier 3 invocations excluded (no Layer 2 gating signal): {excluded_t3_nol2}"
    )
    if tier3_l2_included:
        lines.append(
            f"- Tier 3 invocations **included** due to Layer 2 hits: {tier3_l2_included}"
        )
    lines.append("")
    lines.append("## Per-flag gating confabulation rate (Layer 2 + Layer 3 only)")
    for flag in ("off", "on", "both", "unknown"):
        rs = [r for r in included if str(r.get("flag_state", "unknown")) == flag]
        if rs:
            lines.append(
                f"- `{flag}`: {_gating_rate_nz(rs)}/{len(rs)} ({_rate_gating(rs):.1%}) with ≥1 gating hit"
            )
    lines.append("")

    lines.append("## Top offending rows (by gating hits, Tier-2-included only)")
    offenders: list[tuple[str, str, int, int]] = []
    by_row_included: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in included:
        by_row_included[(str(r.get("row_id", "")), str(r.get("row_name", "")))].append(r)
    for (row_id, row_name), rs in by_row_included.items():
        bad = _gating_rate_nz(rs)
        offenders.append((row_id, row_name, len(rs), bad))
    offenders.sort(key=lambda x: (x[3], x[2]), reverse=True)
    for row_id, row_name, total, bad in offenders[:20]:
        lines.append(f"- `{row_name}` (`{row_id}`): {bad}/{total} included runs with ≥1 gating hit")
    lines.append("")

    lines.append("## Top gating confabulation tokens (Layer 2 + Layer 3, Tier-2-included only)")
    token_gating: Counter[str] = Counter()
    for r in included:
        for tok in _gating_tokens(r):
            token_gating[str(tok)] += 1
    for tok, n in token_gating.most_common(20):
        lines.append(f"- `{tok}`: {n}")
    lines.append("")

    lines.append("## Layer 1 candidate tokens (advisory — do not gate the headline rate)")
    lines.append(
        "These are **advisory** lemma-diff surface tokens for human review (spec §3.5.1). They are **not** used for the gating confabulation rate or for offender row ranking above."
    )
    token_l1: Counter[str] = Counter()
    for r in included:
        for tok in _advisory_tokens(r):
            token_l1[str(tok)] += 1
    for tok, n in token_l1.most_common(20):
        lines.append(f"- `{tok}`: {n}")
    lines.append("")

    lines.append("## Tier breakdown")
    for tier, n in sorted(by_tier.items(), key=lambda x: x[0]):
        lines.append(f"- tier `{tier}`: {n}")
    lines.append("")

    lines.append("## Regression-anchor sanity check (gating: Layer 2 + Layer 3 only)")
    for anchor in ("Aqua Beginnings", "Grace Arts Live"):
        anchor_runs = [r for r in included if str(r.get("row_name", "")).lower() == anchor.lower()]
        nhit = _gating_rate_nz(anchor_runs)
        lines.append(
            f"- `{anchor}`: {nhit}/{len(anchor_runs)} included runs with ≥1 gating hit"
        )

    p.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
