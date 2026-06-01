"""
Lightweight data-source health check.

Probes every external upstream Hava depends on (city PDFs, WebTrac, River
Scene sitemap, NWS, USGS) and checks that required API keys are present.
Prints a red/green table and exits non-zero if anything critical fails, so
it can be dropped into a cron or CI job later to catch silent breakage --
e.g. the kind where the city moved the Aquatic Center schedule to PDFs and
the old scraper quietly returned nothing for days.

Usage
-----
    python scripts/check_sources_health.py
    python scripts/check_sources_health.py --json
    python scripts/check_sources_health.py --include-az   # also probe the
        brittle AZ business-license sites (off by default; they're slow and
        flaky and only matter if you actively use contributor enrichment)

Exit code: 0 if all CRITICAL checks pass, 1 otherwise. WARN-level checks
(missing optional keys, brittle enrichment sources) never fail the run.

This script only checks that upstreams are REACHABLE and shaped as expected.
It does NOT confirm the parsers still produce correct records -- for that,
run ``python scripts/run_scrapes.py --json`` (city scrapers) and verify the
record counts are non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass

import httpx

# ---------------------------------------------------------------------------
# Probe targets. URLs mirror the source-of-truth modules noted in comments;
# keep them in sync if a module's endpoint changes.
# ---------------------------------------------------------------------------

USER_AGENT = "Hava-healthcheck/0.1 (+https://github.com/casey451/havasu-chat)"
TIMEOUT = httpx.Timeout(30.0, connect=15.0)

# (label, url, expected_content_type_substring_or_None, critical)
# content_type None means "any 2xx is fine".
HTTP_CHECKS: list[tuple[str, str, str | None, bool]] = [
    # City -- app/contrib/lhcaz_aquatic_pdf.py EXERCISE_PDF_URL / SWIM_PDF_URL
    (
        "Aquatic: exercise PDF",
        "https://www.lhcaz.gov/DocumentCenter/View/7325/Exercise-Class-Schedule-PDF",
        "application/pdf",
        True,
    ),
    (
        "Aquatic: lap/open swim PDF",
        "https://www.lhcaz.gov/DocumentCenter/View/7326/Lap-and-Open-Swim-Schedule-PDF",
        "application/pdf",
        True,
    ),
    # Parks & rec registration -- app/contrib/webtrac.py BASE_URL
    (
        "WebTrac registration host",
        "https://register.lhcaz.gov/webtrac/web/splash.html",
        None,
        True,
    ),
    # Events -- app/contrib/river_scene.py SITEMAP_INDEX_URL + events child
    (
        "River Scene sitemap index",
        "https://riverscenemagazine.com/wp-sitemap.xml",
        "xml",
        True,
    ),
    (
        "River Scene events sitemap",
        "https://riverscenemagazine.com/wp-sitemap-posts-events-1.xml",
        "xml",
        True,
    ),
    # Conditions -- app/conditions/nws.py (api.weather.gov) ; LHC point.
    (
        "NWS weather API",
        "https://api.weather.gov/points/34.4839,-114.3224",
        None,
        True,
    ),
    # Conditions -- app/conditions/usgs.py (OGC API root)
    (
        "USGS water data API",
        "https://api.waterdata.usgs.gov/ogcapi/v0/",
        None,
        True,
    ),
]

# Brittle AZ business-license enrichment sources (only probed with --include-az).
AZ_CHECKS: list[tuple[str, str, str | None, bool]] = [
    ("AZ ROC (contractors)", "https://azroc.my.site.com/AZRoc/s/contractor-search", None, False),
    ("AZ Corp Commission", "https://arizonabusinesscenter.azcc.gov/businesssearch", None, False),
    ("BBB Lake Havasu", "https://www.bbb.org/us/az/lake-havasu-city", None, False),
]

# (label, env_var, critical) -- key presence only, no quota burn.
ENV_CHECKS: list[tuple[str, str, bool]] = [
    ("AirNow AQI key", "AIRNOW_API_KEY", False),
    ("Google Places key", "GOOGLE_PLACES_API_KEY", True),
]


@dataclass
class Result:
    label: str
    status: str  # "OK" / "WARN" / "FAIL"
    detail: str = ""
    critical: bool = False


def _check_http(
    client: httpx.Client,
    label: str,
    url: str,
    expect_ct: str | None,
    critical: bool,
) -> Result:
    try:
        # GET (not HEAD) -- some city/CDN endpoints 405 or mislead on HEAD.
        resp = client.get(url, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001 -- any network error is a failure
        return Result(label, "FAIL" if critical else "WARN", f"unreachable: {exc!r}", critical)

    if resp.status_code >= 400:
        return Result(label, "FAIL" if critical else "WARN", f"HTTP {resp.status_code}", critical)

    ct = resp.headers.get("content-type", "")
    if expect_ct and expect_ct.lower() not in ct.lower():
        return Result(
            label,
            "FAIL" if critical else "WARN",
            f"HTTP {resp.status_code} but content-type={ct!r} (expected {expect_ct!r})",
            critical,
        )
    return Result(label, "OK", f"HTTP {resp.status_code} {ct}".strip(), critical)


def _check_env(label: str, var: str, critical: bool) -> Result:
    val = (os.environ.get(var) or "").strip()
    if val:
        return Result(label, "OK", f"{var} set", critical)
    return Result(label, "FAIL" if critical else "WARN", f"{var} not set", critical)


def run(include_az: bool = False) -> list[Result]:
    results: list[Result] = []
    checks = list(HTTP_CHECKS) + (list(AZ_CHECKS) if include_az else [])
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        for label, url, expect_ct, critical in checks:
            results.append(_check_http(client, label, url, expect_ct, critical))
    for label, var, critical in ENV_CHECKS:
        results.append(_check_env(label, var, critical))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe Hava's external data sources")
    ap.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON")
    ap.add_argument(
        "--include-az",
        action="store_true",
        help="Also probe the brittle AZ license sites (slow, non-critical)",
    )
    args = ap.parse_args()

    results = run(include_az=args.include_az)
    failed = [r for r in results if r.status == "FAIL"]

    if args.as_json:
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "results": [
                        {
                            "label": r.label,
                            "status": r.status,
                            "detail": r.detail,
                            "critical": r.critical,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
    else:
        width = max(len(r.label) for r in results)
        print("Data-source health check\n" + "-" * (width + 28))
        for r in results:
            mark = {"OK": "OK  ", "WARN": "WARN", "FAIL": "FAIL"}[r.status]
            print(f"  [{mark}] {r.label.ljust(width)}  {r.detail}")
        n_ok = sum(1 for r in results if r.status == "OK")
        n_warn = sum(1 for r in results if r.status == "WARN")
        print("-" * (width + 28))
        print(f"  {n_ok} ok, {n_warn} warn, {len(failed)} fail")
        if failed:
            print("  CRITICAL failures: " + ", ".join(r.label for r in failed))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
