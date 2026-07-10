"""Whole-site health sweep — cold-fetch every public URL and flag breakage.

DB-free, cold-curl only (Googlebot UA, cookie-less), so it runs on a laptop and in
CI unchanged. Enumerates the whole surface from the sitemaps (pages + providers +
events) and asserts, per URL:

  * HTTP 200 (no 5xx / unexpected 404),
  * build-sha meta == the running build (no stale edge render),
  * a non-trivial body with a <title> (not an empty/errored shell),
  * no server-error markers in the body (Traceback / Internal Server Error / …).

Prints a per-section summary + every anomaly. Exit non-zero if any hard breakage
(non-200, error marker, empty body) is found.

    python scripts/site_health_sweep.py --base-url https://askhava.com
    python scripts/site_health_sweep.py --sections pages --sample-providers 300
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time as _time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_ERROR_MARKERS = (
    "internal server error", "traceback (most recent call last)",
    "500 internal", "something went wrong", "application error",
    "werkzeug.exceptions", "sqlalchemy.exc", "jinja2.exceptions",
)
_BUILD_RE = re.compile(r'<meta name="build-sha" content="([^"]*)"')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


@dataclass
class Result:
    url: str
    status: int
    final: str
    build: str | None
    length: int
    title: str
    anomalies: list[str] = field(default_factory=list)


def _section(path: str) -> str:
    p = path.strip("/").split("/")
    if not p or p == [""]:
        return "root"
    if p[0] in ("categories", "provider", "events", "lake-havasu"):
        return p[0]
    return "pages"


def fetch_sitemap_urls(client: httpx.Client, base: str, sections: set[str]) -> list[str]:
    urls: list[str] = []
    idx = client.get(f"{base}/sitemap.xml")
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx.text):
        name = urlparse(sm).path
        if "pages" in name and "pages" not in sections and "categories" not in sections and "lake-havasu" not in sections:
            continue
        if "providers" in name and "provider" not in sections:
            continue
        if "events" in name and "events" not in sections:
            continue
        child = client.get(sm)
        urls.extend(re.findall(r"<loc>([^<]+)</loc>", child.text))
    return urls


def check(client: httpx.Client, url: str, running: str | None) -> Result:
    _time.sleep(0.01)
    try:
        r = client.get(url)
    except Exception as e:
        return Result(url, 0, url, None, 0, "", [f"FETCH_ERROR: {type(e).__name__}"])
    text = r.text
    bm = _BUILD_RE.search(text)
    tm = _TITLE_RE.search(text)
    res = Result(url, r.status_code, str(r.url), bm.group(1) if bm else None,
                 len(text), (tm.group(1).strip()[:80] if tm else ""))
    if r.status_code != 200:
        res.anomalies.append(f"HTTP_{r.status_code}")
        return res
    low = text.lower()
    for marker in _ERROR_MARKERS:
        if marker in low:
            res.anomalies.append(f"ERROR_MARKER: {marker!r}")
            break
    if len(text) < 800:
        res.anomalies.append(f"THIN_BODY: {len(text)} bytes")
    if not tm:
        res.anomalies.append("NO_TITLE")
    if running and res.build and res.build != running:
        res.anomalies.append(f"STALE_BUILD: {res.build} != {running}")
    return res


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Whole-site health sweep (cold-curl, DB-free).")
    p.add_argument("--base-url", default="https://askhava.com")
    p.add_argument("--sections", default="pages,categories,lake-havasu,provider,events",
                   help="comma list: pages,categories,lake-havasu,provider,events")
    p.add_argument("--sample-providers", type=int, default=0,
                   help="if >0, cap /provider URLs at this many (every Nth) for a fast pass")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument("--out", default="")
    args = p.parse_args(argv)
    base = args.base_url.rstrip("/")
    sections = {s.strip() for s in args.sections.split(",") if s.strip()}

    client = httpx.Client(headers={"User-Agent": _UA}, follow_redirects=True, timeout=args.timeout)
    running = None
    hr = client.get(f"{base}/health")
    if hr.status_code == 200:
        try:
            running = json.loads(hr.text).get("build_sha")
        except Exception:
            pass
    print(f"running build_sha: {running}")

    urls = fetch_sitemap_urls(client, base, sections)
    # filter by section + optional provider sampling
    kept: list[str] = []
    prov_seen = 0
    for u in urls:
        sec = _section(urlparse(u).path)
        want = sec in sections or (sec == "categories" and "categories" in sections) \
            or (sec == "pages" and "pages" in sections) or (sec == "lake-havasu" and "lake-havasu" in sections)
        if not want:
            continue
        if sec == "provider" and args.sample_providers:
            prov_seen += 1
            if prov_seen % max(1, (2411 // args.sample_providers)) != 0:
                continue
        kept.append(u)
    print(f"sweeping {len(kept)} URLs across sections: {sorted(sections)}")

    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(lambda u: check(client, u, running), kept):
            results.append(res)
    client.close()

    by_sec: dict[str, Counter] = {}
    anomalies: list[Result] = []
    for r in results:
        sec = _section(urlparse(r.url).path)
        by_sec.setdefault(sec, Counter())["total"] += 1
        if r.anomalies:
            by_sec[sec]["anomaly"] += 1
            anomalies.append(r)
    print("\n=== per-section (total / with-anomaly) ===")
    for sec, c in sorted(by_sec.items()):
        print(f"  {sec:14} {c['total']:5} total   {c['anomaly']:4} anomalies")

    kinds = Counter(a.split(":")[0] for r in anomalies for a in r.anomalies)
    print("\n=== anomaly kinds ===")
    for k, n in kinds.most_common():
        print(f"  {n:4}  {k}")

    print(f"\n=== anomalies ({len(anomalies)}) ===")
    for r in sorted(anomalies, key=lambda x: x.url)[:120]:
        print(f"  [{','.join(r.anomalies)}] {urlparse(r.url).path}  (title={r.title!r})")

    if args.out:
        Path(args.out).write_text(
            "\n".join(f"{r.status}\t{','.join(r.anomalies)}\t{r.url}" for r in anomalies),
            encoding="utf-8")

    hard = [r for r in anomalies if any(
        a.startswith(("HTTP_", "ERROR_MARKER", "THIN_BODY", "FETCH_ERROR")) for a in r.anomalies)]
    print(f"\nHARD breakage (non-200 / error / empty): {len(hard)}")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
