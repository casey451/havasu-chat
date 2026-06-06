"""Detect upstream changes to the captured gym/class schedules.

The 110 classes in ``docs/scraper/captured_class_schedules.json`` were a
one-time vision-assisted capture (2026-06-06) -- most of the 14 venues do not
publish machine-readable schedules (Wix images, Mindbody/Momence widgets,
JS-rendered pages), so they cannot be re-scraped automatically. This checker
closes the freshness gap: every run it fingerprints each venue's schedule
source and compares against the committed baseline. A mismatch means the venue
changed something -- time for a targeted re-capture of just that venue.

Per-venue overrides (``docs/scraper/schedule_drift_config.json``) may set
``mode`` and/or a replacement ``url`` (e.g. Elite's broken-HTTPS site). Modes:
  * ``text``       -- hash of the page's visible text (script/style stripped,
                      whitespace collapsed). Default.
  * ``image_urls`` -- hash of the page's image URLs (query strings stripped).
                      For image-based schedules: Wix/Squarespace media URLs are
                      content-addressed, so replacing the schedule image changes
                      the URL even though the page text never does.

Usage:
  python scripts/schedule_drift_check.py                  # check vs baseline
  python scripts/schedule_drift_check.py --write-baseline # refresh baseline

Exit code is 0 unless the checker itself crashes; drift is signalled in the
output (and ``drifted=`` in ``$GITHUB_OUTPUT`` when set) so the workflow can
open a GitHub issue rather than fail the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

_ROOT = Path(__file__).resolve().parents[1]
DATASET = _ROOT / "docs" / "scraper" / "captured_class_schedules.json"
CONFIG = _ROOT / "docs" / "scraper" / "schedule_drift_config.json"
BASELINE = _ROOT / "docs" / "scraper" / "schedule_fingerprints.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AskHavaScheduleWatch/1.0; "
        "+https://havasuchat.com)"
    )
}
_TIMEOUT = 30.0


def _visible_text_fingerprint(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _image_urls_fingerprint(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if src:
            urls.add(src.split("?")[0])
    for m in re.finditer(r"url\(['\"]?([^'\")]+)['\"]?\)", html):
        urls.add(m.group(1).split("?")[0])
    # Wix serves content-addressed media; the sorted URL list is a stable,
    # text-noise-free signal that flips exactly when an image is replaced.
    joined = "\n".join(sorted(urls))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fingerprint(html: str, mode: str) -> str:
    if mode == "image_urls":
        return _image_urls_fingerprint(html)
    return _visible_text_fingerprint(html)


def _fetch(url: str, client: httpx.Client) -> str:
    r = client.get(url, timeout=_TIMEOUT, headers=_HEADERS)
    r.raise_for_status()
    return r.text


def load_sources() -> list[tuple[str, str, str]]:
    """(venue, url, mode) for every captured venue with a source_url."""
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    config: dict[str, dict] = {}
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    out: list[tuple[str, str, str]] = []
    for v in data.get("venues", []):
        name = v["provider_name"]
        cfg = config.get(name) or {}
        url = (cfg.get("url") or v.get("source_url") or "").strip()
        if not url:
            continue
        out.append((name, url, cfg.get("mode", "text")))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write-baseline", action="store_true",
                   help="refresh the committed baseline fingerprints")
    args = p.parse_args(argv)

    baseline: dict[str, dict] = {}
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    drifted: list[str] = []
    errored: list[str] = []
    fresh: dict[str, dict] = {}

    with httpx.Client(follow_redirects=True) as client:
        for name, url, mode in load_sources():
            try:
                fp = fingerprint(_fetch(url, client), mode)
            except Exception as e:  # network/HTTP -- report, never crash the run
                print(f"ERROR {name}: {type(e).__name__}: {e}", file=sys.stderr)
                errored.append(name)
                continue
            fresh[name] = {"mode": mode, "fingerprint": fp,
                           "captured": date.today().isoformat(), "url": url}
            prev = (baseline.get(name) or {}).get("fingerprint")
            if prev is None:
                print(f"NEW   {name} (no baseline entry)")
                drifted.append(name)
            elif prev != fp:
                print(f"DRIFT {name} -- schedule source changed since "
                      f"{(baseline.get(name) or {}).get('captured', '?')}")
                drifted.append(name)
            else:
                print(f"OK    {name}")

    if args.write_baseline:
        merged = dict(baseline)
        merged.update(fresh)
        BASELINE.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"baseline written: {BASELINE} ({len(merged)} venues)")

    print(f"\nchecked={len(fresh) + len(errored)} drifted={len(drifted)} "
          f"errors={len(errored)}")
    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"drifted={', '.join(drifted)}\n")
            fh.write(f"errored={', '.join(errored)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
