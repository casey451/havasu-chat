"""p2c_bulletin — LHCPD daily bulletin (CentralSquare P2C). OPTIONAL / LAST.

source-expansion #24. Daily arrests/incidents/accidents at
``https://p2c.lhcaz.gov/dailybulletin.aspx`` (CentralSquare P2C, AJAX-loaded).
Per the build prompt this is time-boxed: probe the known JSON backend
``POST /jqHandler.ashx?op=s`` first; if it isn't there, document findings and
stop — do not reverse-engineer further.

The sandbox could not reach the P2C host, so this ships as a probe + defensive
parser, both NEEDS_PROD_VERIFY. :func:`probe_json_backend` returns a structured
result for the dry-run to print so Casey can decide go/no-go from a single run.

Inert build-only module: no DB writes, no orchestrator registration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "p2c_bulletin"
BASE_URL = "https://p2c.lhcaz.gov"
BULLETIN_URL = f"{BASE_URL}/dailybulletin.aspx"
JSON_BACKEND_URL = f"{BASE_URL}/jqHandler.ashx"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("p2c_bulletin", qps=0.3)


@dataclass
class P2cEntry:
    entry_type: str | None  # arrest | incident | accident
    occurred_at: str | None
    description: str | None
    raw: dict = field(default_factory=dict)


@dataclass
class ProbeResult:
    backend_present: bool
    status_code: int | None
    note: str
    entry_count: int = 0


def parse_bulletin(payload: Any) -> list[P2cEntry]:
    """Defensively parse a P2C jqHandler JSON response into entries.

    The exact shape is unknown (NEEDS_PROD_VERIFY); we tolerate a top-level list
    or a dict with a ``data``/``rows``/``Records`` array.
    """
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("rows") or payload.get("Records") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    out: list[P2cEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        desc = row.get("Description") or row.get("description") or row.get("Charge")
        out.append(
            P2cEntry(
                entry_type=(row.get("Type") or row.get("type") or row.get("Category")),
                occurred_at=(row.get("Date") or row.get("DateTime") or row.get("occurred")),
                description=(str(desc).strip() if desc else None),
            )
        )
    return out


def probe_json_backend(*, client: httpx.Client | None = None) -> tuple[ProbeResult, list[P2cEntry]]:
    """Probe POST /jqHandler.ashx?op=s. Returns (ProbeResult, parsed entries).

    Never raises on a missing/!=200 backend — returns a ProbeResult describing
    what was found so the caller can document findings and stop.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        try:
            resp = _LIMITER.call_with_retry(
                lambda: c.post(JSON_BACKEND_URL, params={"op": "s"}, data={"op": "s"}, timeout=30.0)
            )
        except httpx.RequestError as exc:
            return ProbeResult(False, None, f"request error: {exc}"), []
        if resp is None:
            return ProbeResult(False, None, "no response"), []
        if resp.status_code != 200:
            return ProbeResult(False, resp.status_code, f"backend returned {resp.status_code}"), []
        try:
            payload = resp.json()
        except ValueError:
            return ProbeResult(False, 200, "200 but non-JSON body — backend not the JSON op"), []
        entries = parse_bulletin(payload)
        return ProbeResult(True, 200, "JSON backend present", entry_count=len(entries)), entries
    finally:
        if owns:
            c.close()


def entry_sample(e: P2cEntry) -> dict:
    return {"type": e.entry_type, "occurred_at": e.occurred_at, "description": e.description}
