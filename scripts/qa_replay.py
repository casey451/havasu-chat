#!/usr/bin/env python3
"""Ask Hava chat QA replay + scorer.

Replays the Lake Havasu persona question bank against a running chat endpoint
(local dev or prod), captures the response shape, assigns a verdict bucket, and
prints a summary. Use it to measure a fix before/after.

Origin: 2026-06-12 QA diagnostic (ASK_HAVA_CHAT_QA_DIAGNOSTIC_2026-06-12.md).
The verdict buckets mirror that report so deltas are comparable.

Usage:
    # parse the question bank from the deep-research report markdown
    python scripts/qa_replay.py --bank deep-research-report.md --base http://127.0.0.1:8000

    # against prod (rate-limited; the script paces itself)
    python scripts/qa_replay.py --bank deep-research-report.md --base https://askhava.com

    # write a per-question CSV and compare to a prior run
    python scripts/qa_replay.py --bank bank.md --base ... --csv out.csv --baseline askhava_qa_results.csv

This script makes outbound HTTP calls only to the --base you pass and never
writes to the repo or DB. Safe to run read-only against prod.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter

# --- question-bank extraction (matches the 2026-06-12 diagnostic, 296 qs) ---

_SECTION_MAP = {
    "Master question bank for water users": "water",
    "Master question bank for land, family, and lifestyle users": "land",
    "Master question bank for resident and practical-service users": "resident",
    "The question patterns that matter most": "pattern",
}


def _split_questions(blob: str) -> list[str]:
    out = []
    for part in re.findall(r"[^?]*\?", blob):
        q = part.strip().lstrip(" .—-")
        if len(q) > 4:
            out.append(q)
    return out


def extract_bank(path: str) -> list[dict]:
    """Parse persona + pattern questions out of the bank markdown."""
    text = open(path, encoding="utf-8").read()
    section = None
    questions: list[dict] = []
    for ln in text.split("\n"):
        h = re.match(r"^##+\s+(.*)", ln)
        if h:
            title = h.group(1).strip()
            section = _SECTION_MAP.get(title, section)
            continue
        m = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", ln)
        if m and section in ("water", "land", "resident"):
            for q in _split_questions(m.group(2)):
                questions.append({"section": section, "persona": m.group(1).strip(), "question": q})
            continue
        mb = re.match(r"^-\s+\*\*(.+?):\*\*\s*(.*)$", ln)
        if mb and section == "pattern":
            for q in _split_questions(mb.group(2)):
                questions.append({"section": "pattern", "persona": mb.group(1).strip(), "question": q})
    seen, uniq = set(), []
    for q in questions:
        if q["question"] in seen:
            continue
        seen.add(q["question"])
        uniq.append(q)
    return uniq


# --- replay ---

def call(base: str, question: str, timeout: int = 40) -> dict:
    body = json.dumps({"query": question}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode())
        comp = j.get("component") or {}
        data = comp.get("data") or {}
        items = data.get("items") or []
        return {
            "http": 200,
            "voice": j.get("voice") or j.get("response") or "",
            "mode": j.get("mode"),
            "sub_intent": j.get("sub_intent"),
            "tier_used": j.get("tier_used"),
            "latency_ms": j.get("latency_ms"),
            "comp_type": comp.get("type"),
            "comp_category": data.get("category"),
            "n_items": len(items),
            "top_items": [{"name": it.get("name"), "category": it.get("category")} for it in items[:6]],
        }
    except urllib.error.HTTPError as e:
        return {"http": e.code, "voice": "", "error": str(e.code)}
    except Exception as e:  # noqa: BLE001
        return {"http": -1, "voice": "", "error": str(e)[:120]}


# --- scoring (verdict buckets from the diagnostic) ---

GRAB1 = {"928DesertDetailing", "Big Easy Storage", "BlackSheep RV LLC",
         "Britton's Auto Truck & RV Repair", "High Octane Storage"}
GRAB2 = {"Dick Samp Memorial", "Havasu View RV Space", "Sara Park Hiking Trail",
         "The Gravel Pit", "Windsor Campgrounds"}
_EVENT_WORDS = ("event", "festival", "tonight", "this week", "this month", "vendor",
                "market", "speedway", "tee time", "calendar", "happening")


def verdict(rec: dict) -> str:
    v = (rec.get("voice") or "").strip()
    ct = rec.get("comp_type")
    tier = rec.get("tier_used")
    names = {it.get("name") or "" for it in (rec.get("top_items") or [])}
    if "outside what I cover" in v:
        return "OUT_OF_SCOPE_MISFIRE"
    if ct == "business_list" and (GRAB1 <= names or GRAB2 <= names):
        return "GRABBAG_MISMATCH"
    if ct in ("week_strip", "day_agenda"):
        ql = rec["question"].lower()
        return "EVENT_LIST" if any(w in ql for w in _EVENT_WORDS) else "EVENT_MISFIRE"
    if tier == "gap_template":
        return "KEYWORD_ARTIFACT" if " is at " in v else "HONEST_GAP"
    if tier == "3":
        return "LLM_PROSE"
    if ct == "business_list":
        return "LIST"
    return "OTHER"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True, help="path to the question-bank markdown")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="chat host base URL")
    ap.add_argument("--csv", help="write per-question results here")
    ap.add_argument("--baseline", help="prior CSV to diff verdict counts against")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds between calls (prod rate-limits)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of questions (0 = all)")
    args = ap.parse_args()

    bank = extract_bank(args.bank)
    if args.limit:
        bank = bank[: args.limit]
    print(f"loaded {len(bank)} questions from {args.bank}; replaying against {args.base}")

    rows = []
    for i, q in enumerate(bank, 1):
        rec = {**q, **call(args.base, q["question"])}
        rec["verdict"] = verdict(rec) if rec.get("http") == 200 else "HTTP_" + str(rec.get("http"))
        rows.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(bank)}")
        time.sleep(args.pace)

    counts = Counter(r["verdict"] for r in rows)
    print("\nVerdict distribution:")
    for k, n in counts.most_common():
        print(f"  {n:4d}  {k}")

    if args.baseline:
        try:
            base_counts = Counter(r["verdict"] for r in csv.DictReader(open(args.baseline)))
            print("\nDelta vs baseline (this run - baseline):")
            for k in sorted(set(counts) | set(base_counts)):
                d = counts.get(k, 0) - base_counts.get(k, 0)
                if d:
                    print(f"  {d:+4d}  {k}")
        except FileNotFoundError:
            print(f"(baseline {args.baseline} not found)")

    if args.csv:
        cols = ["section", "persona", "question", "verdict", "tier_used", "mode", "sub_intent",
                "comp_type", "comp_category", "n_items", "voice", "latency_ms"]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                r = dict(r)
                r["voice"] = (r.get("voice") or "").replace("\n", " ").strip()
                w.writerow(r)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
