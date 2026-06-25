"""Outbound-link health checker for the directory's stored URLs.

The directory carries thousands of outbound links -- provider websites + Facebook
pages, and event URLs -- that rot silently as businesses close, rename, or move.
The :mod:`app.monitoring.freshness` monitor only catches *stale feeds* (data not
updating); it says nothing about whether a stored link still resolves. This module
walks those links and classifies each, so a dead link surfaces for review instead
of greeting a user with a 404.

It is built to run continuously on the always-on VPS (idle CPU, a stable IP that
can crawl politely), yielding to the scrape/backup jobs. This module is the pure
core -- collection, per-URL classification, and a paced scan loop with injectable
network + sleep seams so it is fully testable offline. The CLI
(``scripts/link_health_scan.py``) wires it to the live DB and prints a dry-run
report; persistence + the admin queue land in a follow-up once the report is
reviewed.

Read-only: it issues outbound HTTP and writes nothing. The SSRF guard
(:func:`app.contrib.url_fetcher.is_blocked_target`) runs before any connection
because the URLs originate from remote/scraped data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; AskHavaLinkCheck/1.0; +https://askhava.com)"

# Status categories (coarse on purpose -- the admin only needs to triage).
OK = "ok"  # 2xx / 3xx -- resolves
BROKEN = "broken"  # 4xx/5xx other than the anti-bot codes -- a real dead link
UNREACHABLE = "unreachable"  # DNS failure, timeout, connection refused
BLOCKED_BY_SITE = "blocked_by_site"  # 401/403/429 -- often anti-bot, NOT proof of death
SSRF_BLOCKED = "ssrf_blocked"  # our guard refused to connect (private/reserved host)

# Categories that warrant a human look (BLOCKED_BY_SITE is excluded -- a 403 from a
# bot wall does not mean the business is gone, so flagging it would be noise).
ACTIONABLE = frozenset({BROKEN, UNREACHABLE})


@dataclass(frozen=True)
class LinkRef:
    """One stored URL and where it came from."""

    url: str
    kind: str  # provider_website | provider_facebook | event_url
    entity_id: str
    label: str


@dataclass
class LinkResult:
    ref: LinkRef
    category: str
    http_status: int | None
    detail: str

    @property
    def actionable(self) -> bool:
        return self.category in ACTIONABLE


@dataclass
class ScanReport:
    results: list[LinkResult] = field(default_factory=list)
    skipped_duplicate_urls: int = 0

    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.category] = counts.get(r.category, 0) + 1
        return counts

    @property
    def actionable(self) -> list[LinkResult]:
        return [r for r in self.results if r.actionable]


# --------------------------------------------------------------------------- #
# Collection (read-only DB)
# --------------------------------------------------------------------------- #
def _clean(url: str | None) -> str:
    return (url or "").strip()


def collect_links(db) -> list[LinkRef]:
    """Every outbound link worth checking: active providers + live events."""
    from sqlalchemy import select

    from app.db.models import Event, Provider

    refs: list[LinkRef] = []
    rows = db.execute(
        select(Provider.id, Provider.provider_name, Provider.website, Provider.facebook).where(
            Provider.is_active
        )
    )
    for pid, name, website, facebook in rows:
        if _clean(website):
            refs.append(LinkRef(_clean(website), "provider_website", str(pid), name or ""))
        if _clean(facebook):
            refs.append(LinkRef(_clean(facebook), "provider_facebook", str(pid), name or ""))
    events = db.execute(
        select(Event.id, Event.title, Event.event_url).where(
            Event.event_url != "", Event.status == "live"
        )
    )
    for eid, title, url in events:
        if _clean(url):
            refs.append(LinkRef(_clean(url), "event_url", str(eid), title or ""))
    return refs


# --------------------------------------------------------------------------- #
# Per-URL classification
# --------------------------------------------------------------------------- #
def categorize(http_status: int) -> str:
    if http_status in (401, 403, 429):
        return BLOCKED_BY_SITE
    if http_status >= 400:
        return BROKEN
    return OK


def check_one(url: str, *, timeout: float = 12.0) -> tuple[str, int | None, str]:
    """Resolve one URL to (category, http_status, detail). Never raises.

    HEAD first (cheap); fall back to GET when a server rejects HEAD (405/501) or
    errors, since many sites only answer GET. The SSRF guard runs first.
    """
    from app.contrib.url_fetcher import is_blocked_target

    blocked, reason = is_blocked_target(url)
    if blocked:
        return (SSRF_BLOCKED, None, reason or "blocked target")

    try:
        import httpx
    except Exception:  # pragma: no cover -- httpx always present in prod
        return (UNREACHABLE, None, "httpx unavailable")

    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.head(url)
            if resp.status_code in (405, 501) or resp.status_code >= 400:
                # Retry with GET -- HEAD is often unsupported or differently gated.
                resp = client.get(url)
            code = resp.status_code
    except httpx.HTTPError as exc:
        return (UNREACHABLE, None, f"{type(exc).__name__}: {exc}".strip()[:160])

    return (categorize(code), code, f"HTTP {code}")


# --------------------------------------------------------------------------- #
# Paced scan loop (injectable network + sleep for tests)
# --------------------------------------------------------------------------- #
def scan_links(
    refs: list[LinkRef],
    *,
    checker: Callable[[str], tuple[str, int | None, str]] = check_one,
    sleeper: Callable[[float], None] | None = None,
    per_host_delay: float = 0.0,
    should_pause: Callable[[], bool] | None = None,
    pause_poll: float = 30.0,
    limit: int | None = None,
) -> ScanReport:
    """Check each unique URL once, politely.

    * de-dupes identical URLs (many rows can share one), checking each once;
    * paces requests per host by ``per_host_delay`` so we never hammer one domain;
    * yields to heavier jobs: while ``should_pause()`` is true it sleeps
      ``pause_poll`` seconds and re-checks before continuing.

    ``sleeper`` defaults to ``time.sleep`` but is injectable so tests run instantly.
    """
    if sleeper is None:
        import time

        sleeper = time.sleep

    report = ScanReport()
    seen: set[str] = set()
    last_hit: dict[str, float] = {}
    checked = 0
    import time as _time

    for ref in refs:
        if limit is not None and checked >= limit:
            break
        if ref.url in seen:
            report.skipped_duplicate_urls += 1
            continue
        seen.add(ref.url)

        # Yield to the scrape/backup jobs.
        while should_pause is not None and should_pause():
            logger.info("link_health: pausing (a higher-priority job is running)")
            sleeper(pause_poll)

        host = urlsplit(ref.url).hostname or ""
        if per_host_delay and host in last_hit:
            wait = per_host_delay - (_time.monotonic() - last_hit[host])
            if wait > 0:
                sleeper(wait)

        category, code, detail = checker(ref.url)
        last_hit[host] = _time.monotonic()
        report.results.append(LinkResult(ref, category, code, detail))
        checked += 1

    return report
