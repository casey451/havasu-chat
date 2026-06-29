"""Off-site canary scan (A4): check watched competitor sites for our canary
watermark phrases. Read-only — issues outbound GETs and writes nothing.

    python scripts/canary_scan.py                 # scan the default watch list
    python scripts/canary_scan.py URL [URL ...]   # scan specific URLs

Exits 2 if any canary phrase is found (so a cron job can alert on non-zero),
0 if clean. Wire it to a periodic VPS/cron job to get continuous coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.monitoring.canary_scanner import (
    DEFAULT_WATCH_URLS,
    format_canary_report,
    scan_for_leaks,
)


def main(argv: list[str]) -> int:
    urls = tuple(argv) if argv else DEFAULT_WATCH_URLS
    print(f"canary scan: checking {len(urls)} URL(s) for canary phrases…")
    hits = scan_for_leaks(urls)
    subject, body = format_canary_report(hits)
    print(subject)
    print(body)
    return 2 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
