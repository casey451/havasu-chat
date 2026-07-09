"""Off-site copy detection (A4): hunt canary watermark phrases on external sites.

Pure core + a paced scan, mirroring :mod:`app.monitoring.link_health`: network and
the canary set are injectable so the whole module tests offline. Read-only — it
issues outbound GETs (through the same SSRF guard + page fetcher as link_health)
and writes nothing.

If a canary's :attr:`~app.monitoring.canaries.Canary.unique_phrase` is found on a
watched external page, that's evidence the directory's data was copied. The CLI
(``scripts/canary_scan.py``) wires this to live fetching and prints a report;
scheduling it (a cron / VPS job) is an infra step.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.monitoring.canaries import CANARIES, Canary

logger = logging.getLogger(__name__)

# Watched competitor surfaces — havasu.info first, per the plan. Extend as needed.
DEFAULT_WATCH_URLS: tuple[str, ...] = (
    "https://havasu.info/",
    "https://www.havasu.info/",
)

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class CanaryHit:
    """A canary phrase found on an external page."""

    canary_slug: str
    canary_name: str
    url: str
    snippet: str


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace, so formatting differences in a copy
    (re-wrapped lines, doubled spaces) don't hide a verbatim lift."""
    return _WS.sub(" ", (text or "")).strip().lower()


def find_canary_hits(
    page_text: str, url: str, canaries: Iterable[Canary] = CANARIES
) -> list[CanaryHit]:
    """Return a CanaryHit for every canary whose unique phrase appears in ``page_text``."""
    norm = _normalize(page_text)
    if not norm:
        return []
    hits: list[CanaryHit] = []
    for c in canaries:
        phrase = _normalize(c.unique_phrase)
        if phrase and phrase in norm:
            idx = norm.find(phrase)
            lo = max(0, idx - 40)
            hi = min(len(norm), idx + len(phrase) + 40)
            hits.append(CanaryHit(c.slug, c.name, url, norm[lo:hi]))
    return hits


def scan_for_leaks(
    watch_urls: Iterable[str] = DEFAULT_WATCH_URLS,
    *,
    fetcher: Callable[[str], str] | None = None,
    canaries: Iterable[Canary] = CANARIES,
) -> list[CanaryHit]:
    """Fetch each watched URL and collect any canary hits. Never raises.

    ``fetcher`` defaults to :func:`app.monitoring.link_health.fetch_page_text`
    (SSRF-guarded, tags stripped); injected in tests so no network is touched.
    """
    if fetcher is None:
        from app.monitoring.link_health import fetch_page_text

        fetcher = fetch_page_text
    canary_list = list(canaries)
    out: list[CanaryHit] = []
    for url in watch_urls:
        try:
            text = fetcher(url)
        except Exception:
            logger.warning("canary_scan: fetch failed url=%s", url, exc_info=True)
            continue
        if text:
            out.extend(find_canary_hits(text, url, canary_list))
    return out


def format_canary_report(hits: list[CanaryHit]) -> tuple[str, str]:
    """Build a (subject, text) alert from canary hits. Empty hits → an all-clear."""
    if not hits:
        return ("[Ask Hava] canary scan: no copies detected", "No canary phrases found on the watched sites.\n")
    subject = f"[Ask Hava] ⚠ canary copy detected ({len(hits)} hit(s))"
    lines = [
        f"{len(hits)} canary watermark phrase(s) found off-site — likely a scrape "
        "of askhava.com data.",
        "",
    ]
    for h in hits:
        lines.append(f"## {h.canary_name} ({h.canary_slug})")
        lines.append(f"  found on: {h.url}")
        lines.append(f"  context:  …{h.snippet}…")
        lines.append("")
    return subject, "\n".join(lines)
