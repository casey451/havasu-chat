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
from datetime import datetime
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
    workers: int = 1,
    chunk_size: int = 64,
) -> ScanReport:
    """Check each unique URL, politely, optionally in parallel.

    * de-dupes identical URLs (many rows can share one), checking each once;
    * yields to heavier jobs: while ``should_pause()`` is true it sleeps
      ``pause_poll`` seconds and re-checks (between chunks when parallel);
    * ``workers == 1`` (default) is the sequential, per-host-throttled path used
      by tests; ``workers > 1`` runs a thread pool per chunk for a fast full
      sweep (per-host pacing is relaxed — fine since stored URLs are mostly
      distinct hosts and the pool is small).

    ``sleeper`` defaults to ``time.sleep`` but is injectable so tests run instantly.
    """
    if sleeper is None:
        import time

        sleeper = time.sleep
    import time as _time

    # De-dupe up front so every URL is checked exactly once.
    seen: set[str] = set()
    unique: list[LinkRef] = []
    skipped = 0
    for ref in refs:
        if ref.url in seen:
            skipped += 1
            continue
        seen.add(ref.url)
        unique.append(ref)
    if limit is not None:
        unique = unique[:limit]

    report = ScanReport(skipped_duplicate_urls=skipped)

    def _wait_while_paused() -> None:
        while should_pause is not None and should_pause():
            logger.info("link_health: pausing (a higher-priority job is running)")
            sleeper(pause_poll)

    if workers <= 1:
        last_hit: dict[str, float] = {}
        for ref in unique:
            _wait_while_paused()
            host = urlsplit(ref.url).hostname or ""
            if per_host_delay and host in last_hit:
                wait = per_host_delay - (_time.monotonic() - last_hit[host])
                if wait > 0:
                    sleeper(wait)
            category, code, detail = checker(ref.url)
            last_hit[host] = _time.monotonic()
            report.results.append(LinkResult(ref, category, code, detail))
        return report

    from concurrent.futures import ThreadPoolExecutor

    for start in range(0, len(unique), chunk_size):
        _wait_while_paused()
        chunk = unique[start : start + chunk_size]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ref, (category, code, detail) in zip(chunk, pool.map(lambda r: checker(r.url), chunk)):
                report.results.append(LinkResult(ref, category, code, detail))
    return report


# --------------------------------------------------------------------------- #
# Persistence + confirm-over-time (so transient blips don't page)
# --------------------------------------------------------------------------- #
CONFIRM_THRESHOLD = 2  # consecutive actionable sweeps before a link is "confirmed broken"


# --------------------------------------------------------------------------- #
# Layer 2: local-LLM assessment of a confirmed-broken link
# --------------------------------------------------------------------------- #
def root_url(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}/" if p.scheme and p.netloc else ""


def fetch_page_text(url: str, *, timeout: float = 15.0, max_chars: int = 6000) -> str:
    """Fetch a page and return a rough text rendering (tags stripped). '' on failure."""
    from app.contrib.url_fetcher import is_blocked_target

    blocked, _ = is_blocked_target(url)
    if blocked:
        return ""
    try:
        import re as _re

        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as c:
            resp = c.get(url)
            if resp.status_code >= 400:
                return ""
            text = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", resp.text, flags=_re.S | _re.I)
            text = _re.sub(r"<[^>]+>", " ", text)
            return _re.sub(r"\s+", " ", text).strip()[:max_chars]
    except Exception:
        return ""


def local_chat(prompt: str, *, model: str | None = None, timeout: float = 180.0) -> str:
    """One text completion against the local OpenAI-compatible endpoint. '' on failure."""
    import os

    base = (os.getenv("VISION_BASE_URL") or "").strip()
    if not base:
        return ""
    try:
        import httpx

        payload = {
            "model": model or os.getenv("VISION_MODEL") or "qwen2.5vl:3b",
            "temperature": 0,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=timeout) as c:
            resp = c.post(f"{base.rstrip('/')}/chat/completions", json=payload)
            resp.raise_for_status()
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        logger.warning("link_health: local_chat failed", exc_info=True)
        return ""


_ASSESS_PROMPT = (
    'A directory link for the business "{business}" is broken (HTTP error): {broken}\n'
    "Below is the text of that site's homepage ({root}). Decide whether the business still "
    "exists on this site, and if you can identify the correct working page for it, give that "
    "URL. Reply with STRICT JSON only: "
    '{{"present": true|false, "suggested_url": "<url or null>", "note": "<=12 words"}}.\n\n'
    "HOMEPAGE TEXT:\n{page}"
)


def assess_link(
    url: str,
    label: str,
    *,
    page_fetcher: Callable[[str], str] = fetch_page_text,
    chat: Callable[[str], str] = local_chat,
    verifier: Callable[[str], tuple[str, int | None, str]] = check_one,
) -> tuple[str, str | None]:
    """Read the broken link's root domain with the local model; return (verdict, suggested_url).

    Best-effort and side-effect-free: any failure yields a plain-text verdict and no
    suggestion. Suggestions are advisory only -- a human applies them.
    """
    import json as _json

    root = root_url(url)
    if not root:
        return ("could not derive a root domain", None)
    page = page_fetcher(root)
    if not page:
        return (f"root domain {root} also unreachable", None)
    raw = chat(_ASSESS_PROMPT.format(business=label or "(unknown)", broken=url, root=root, page=page))
    if not raw:
        return ("local model unavailable", None)
    # Models occasionally wrap JSON in prose; grab the first {...} block if so.
    snippet = raw
    if not raw.lstrip().startswith("{"):
        i, j = raw.find("{"), raw.rfind("}")
        snippet = raw[i : j + 1] if 0 <= i < j else raw
    try:
        data = _json.loads(snippet)
    except ValueError:
        return ("model reply unparseable", None)
    if not isinstance(data, dict):
        return ("model reply unparseable", None)
    present = bool(data.get("present"))
    note = str(data.get("note") or "").strip()
    sug = data.get("suggested_url")
    sug = sug.strip() if isinstance(sug, str) and sug.strip().startswith("http") else None
    # Small local models often just echo the broken URL back (seen on real data),
    # or invent one. Only keep a suggestion that is genuinely DIFFERENT and actually
    # resolves -- otherwise it's noise, not a fix.
    if sug:
        same = sug.rstrip("/") == url.rstrip("/")
        if same or verifier(sug)[0] != OK:
            sug = None
    verdict = ("business present on site; " if present else "business NOT found on site; ") + note
    return (verdict.strip()[:512], sug)


def save_assessment(db, url: str, assessment: str, suggested_url: str | None, *, now: datetime) -> None:
    from app.db.models import LinkHealth

    row = db.query(LinkHealth).filter(LinkHealth.url == url).one_or_none()
    if row is None:
        return
    row.llm_assessment = assessment
    row.llm_suggested_url = suggested_url
    row.llm_checked_at = now
    db.flush()


def persist_results(db, report: ScanReport, *, now: datetime, confirm_threshold: int = CONFIRM_THRESHOLD):
    """Upsert each result into ``link_health``; return the newly-confirmed-broken rows.

    Actionable results increment ``consecutive_failures``; once that crosses the
    threshold the row is ``confirmed_broken``. A non-actionable result (ok, or an
    inconclusive anti-bot/ssrf block) clears the streak and any prior breakage.
    Only links that *cross* the threshold this run (and weren't already notified)
    are returned, so the email summary pages once per breakage.
    """
    from app.db.models import LinkHealth

    newly_confirmed: list[LinkHealth] = []
    for r in report.results:
        row = db.query(LinkHealth).filter(LinkHealth.url == r.ref.url).one_or_none()
        if row is None:
            row = LinkHealth(url=r.ref.url, first_checked_at=now, consecutive_failures=0)
            db.add(row)
        row.kind = r.ref.kind
        row.entity_id = r.ref.entity_id
        row.label = r.ref.label
        row.category = r.category
        row.http_status = r.http_status
        row.detail = (r.detail or "")[:512]
        row.last_checked_at = now

        if r.actionable:
            row.consecutive_failures += 1
            if row.consecutive_failures >= confirm_threshold:
                if not row.confirmed_broken and not row.notified:
                    newly_confirmed.append(row)
                row.confirmed_broken = True
        else:
            if r.category == OK:
                row.last_ok_at = now
            row.consecutive_failures = 0
            row.confirmed_broken = False
            row.notified = False
    db.flush()
    return newly_confirmed
