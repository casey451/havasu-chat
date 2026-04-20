"""Fetch public URLs and extract lightweight metadata (Phase 5.2)."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "HavasuChat/0.1 (+https://havasu-chat-production.up.railway.app)"
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def _naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class UrlFetchResult:
    status: str  # "success" | "error" | "timeout" | "not_attempted"
    title: str | None = None
    description: str | None = None
    final_url: str | None = None
    error_message: str | None = None
    fetched_at: datetime = field(default_factory=_naive_utc_now)


def _is_blocked_target(url: str) -> tuple[bool, str | None]:
    """Return (blocked, reason). Blocks private/reserved hosts (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True, "unsupported_scheme"
    host = parsed.hostname
    if not host:
        return True, "missing_host"
    host_l = host.strip().lower()
    if host_l == "localhost" or host_l.endswith(".local"):
        return True, "blocked_host"
    try:
        ip = ipaddress.ip_address(host_l)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            return True, "blocked_ip_literal"
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as e:
        return True, f"dns_error:{e}"
    for info in infos:
        addr = info[4]
        if not addr:
            continue
        ip_s = addr[0]
        try:
            ip = ipaddress.ip_address(ip_s)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                return True, "blocked_resolved_ip"
        except ValueError:
            continue
    return False, None


def _normalize_url(url: str) -> str:
    u = url.strip()
    if not u:
        return u
    parsed = urlparse(u)
    if not parsed.scheme:
        u = "https://" + u
    return u


def _content_type_ok(ct: str | None) -> bool:
    if not ct:
        return False
    base = ct.split(";", 1)[0].strip().lower()
    return any(base == a or base.startswith(a + "+") for a in ALLOWED_CONTENT_TYPES)


def _extract_meta(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    title = None
    desc = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    if not title and soup.title and soup.title.string:
        title = re.sub(r"\s+", " ", soup.title.string).strip()
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = str(og_desc["content"]).strip()
    if not desc:
        md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if md and md.get("content"):
            desc = str(md["content"]).strip()
    if title:
        title = title[:300]
    if desc:
        desc = desc[:1000]
    return title or None, desc or None


def fetch_url_metadata(url: str, timeout_seconds: int = 10) -> UrlFetchResult:
    """Fetch URL, extract title + description. Returns structured result."""
    now = _naive_utc_now()
    if not (url or "").strip():
        return UrlFetchResult(
            status="error",
            error_message="empty_url",
            fetched_at=now,
        )

    current = _normalize_url(url)
    redirects = 0
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            while True:
                blocked, reason = _is_blocked_target(current)
                if blocked:
                    return UrlFetchResult(
                        status="error",
                        final_url=current,
                        error_message=f"blocked:{reason}",
                        fetched_at=_naive_utc_now(),
                    )
                try:
                    with client.stream("GET", current, headers=headers) as resp:
                        ct = resp.headers.get("content-type")
                        cl = resp.headers.get("content-length")
                        if cl is not None:
                            try:
                                if int(cl) > MAX_BODY_BYTES:
                                    return UrlFetchResult(
                                        status="error",
                                        final_url=current,
                                        error_message="content_length_exceeds_cap",
                                        fetched_at=_naive_utc_now(),
                                    )
                            except ValueError:
                                pass
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in resp.iter_bytes():
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > MAX_BODY_BYTES:
                                return UrlFetchResult(
                                    status="error",
                                    final_url=current,
                                    error_message="body_exceeds_cap",
                                    fetched_at=_naive_utc_now(),
                                )
                            chunks.append(chunk)
                        body = b"".join(chunks)
                except httpx.TimeoutException:
                    return UrlFetchResult(
                        status="timeout",
                        final_url=current,
                        error_message="timeout",
                        fetched_at=_naive_utc_now(),
                    )
                except httpx.RequestError as e:
                    return UrlFetchResult(
                        status="error",
                        final_url=current,
                        error_message=f"request_error:{e!s}",
                        fetched_at=_naive_utc_now(),
                    )

                if resp.status_code in (301, 302, 303, 307, 308):
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        return UrlFetchResult(
                            status="error",
                            final_url=current,
                            error_message="too_many_redirects",
                            fetched_at=_naive_utc_now(),
                        )
                    loc = resp.headers.get("location")
                    if not loc:
                        return UrlFetchResult(
                            status="error",
                            final_url=current,
                            error_message="redirect_missing_location",
                            fetched_at=_naive_utc_now(),
                        )
                    current = urljoin(current, loc)
                    continue

                final_url = str(resp.url)
                if resp.status_code < 200 or resp.status_code >= 300:
                    return UrlFetchResult(
                        status="error",
                        final_url=final_url,
                        error_message=f"http_{resp.status_code}",
                        fetched_at=_naive_utc_now(),
                    )
                if not _content_type_ok(ct):
                    return UrlFetchResult(
                        status="error",
                        final_url=final_url,
                        error_message=f"bad_content_type:{ct!r}",
                        fetched_at=_naive_utc_now(),
                    )
                try:
                    text = body.decode(resp.encoding or "utf-8", errors="replace")
                except Exception:
                    text = body.decode("utf-8", errors="replace")
                soup = BeautifulSoup(text, "html.parser")
                title, description = _extract_meta(soup)
                return UrlFetchResult(
                    status="success",
                    title=title,
                    description=description,
                    final_url=final_url,
                    fetched_at=_naive_utc_now(),
                )
    except Exception as e:  # pragma: no cover — defensive
        logger.exception("url_fetcher unexpected failure")
        return UrlFetchResult(
            status="error",
            error_message=f"unexpected:{e!s}",
            fetched_at=_naive_utc_now(),
        )
