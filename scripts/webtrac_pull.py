"""
CLI: pull Lake Havasu City Parks & Rec WebTrac sections.

Examples
--------
  # Parse a saved HTML response (no network):
  python scripts/webtrac_pull.py --offline tmp/webtrac_adult_sample.html

  # Live fetch the full activity universe and dump JSON:
  python scripts/webtrac_pull.py --out tmp/webtrac_all.json

  # Live fetch only Adult-category Sports:
  python scripts/webtrac_pull.py --category ADULT --type SPORT

By default the CLI prints a one-line summary per section. Use ``--json``
to dump structured records for downstream review or DB loading.

This pull is read-only; nothing is written to the catalog yet. Wiring
into the contributions queue happens in a follow-up commit once we lock
the Program-vs-Event mapping with the chat layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.webtrac import (  # noqa: E402
    Section,
    fetch_all_sections,
    filter_for_chat,
    parse_search_html,
)


def _format_line(s: Section) -> str:
    when = "?"
    if s.start_date and s.start_time:
        when = f"{s.start_date.isoformat()} {s.start_time.strftime('%I:%M%p').lstrip('0').lower()}"
    elif s.start_date:
        when = s.start_date.isoformat()
    days = "/".join(s.days) if s.days else "-"
    cost = (
        "free"
        if (s.cost_resident == 0 and s.cost_nonresident == 0)
        else (
            f"${s.cost_resident:.0f}/${s.cost_nonresident:.0f}"
            if s.cost_resident is not None and s.cost_nonresident is not None
            else "?"
        )
    )
    flag = "" if s.available_for_signup else f"  [{s.availability_label}]"
    return (
        f"  [{s.fmid}] {s.program_name} :: {s.section_name}\n"
        f"      {when} ({days}) @ {s.location or '?'} | ages {s.age_min}-{s.age_max} | {cost}{flag}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Pull WebTrac activity sections")
    p.add_argument(
        "--offline",
        type=str,
        default=None,
        help="Parse a saved HTML file instead of hitting the live site",
    )
    p.add_argument(
        "--category", type=str, default=None, help="WebTrac category code (ADULT, YOUTH, PET)"
    )
    p.add_argument(
        "--type",
        dest="type_",
        type=str,
        default=None,
        help="WebTrac type code (ACTV, AQUA, ASP, ...)",
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON instead of human-readable lines",
    )
    p.add_argument("--out", type=str, default=None, help="Write JSON to this path (implies --json)")
    p.add_argument(
        "--only-available",
        action="store_true",
        help="Apply the chat-layer filter (drop Unavailable / Full sections)",
    )
    args = p.parse_args()

    if args.offline:
        html = Path(args.offline).read_text(encoding="utf-8", errors="replace")
        sections = parse_search_html(html)
    else:
        cats = [args.category] if args.category else None
        tps = [args.type_] if args.type_ else None
        sections = fetch_all_sections(categories=cats, types=tps)

    if args.only_available:
        sections = filter_for_chat(sections)

    if args.out or args.as_json:
        payload = [s.to_dict() for s in sections]
        text = json.dumps(payload, indent=2, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {len(sections)} sections -> {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0

    by_program: dict[tuple[int, str], list[Section]] = {}
    for s in sections:
        by_program.setdefault((s.program_id, s.program_name), []).append(s)

    print(f"Found {len(sections)} sections across {len(by_program)} programs.")
    for (pid, name), rows in sorted(by_program.items(), key=lambda kv: kv[0][1].lower()):
        print(f"\n{name} ({pid}) — {len(rows)} section(s)")
        for s in rows:
            print(_format_line(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
