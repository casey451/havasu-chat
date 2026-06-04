"""az511 — ADOT/AZ511 road conditions: events API + keyless WZDx work-zones.

source-expansion #17. Answers "is SR-95 closed?". Two feeds:

* **Event API** (key required): ``https://az511.gov/api/v2/get/event?key=...``
  — incidents/closures/construction. Free key, **10 calls / 60s** throttle.
* **WZDx** (keyless secondary): ``https://az511.com/api/wzdx`` — work-zone data
  exchange GeoJSON.

Both are filtered to Havasu-relevant corridors (SR-95 / US-95 / I-40) and
Mohave & La Paz counties.

Key handling (rule 5): the key is read from ``AZ511_API_KEY``; with no key the
event fetcher logs once and returns ``[]`` (the keyless WZDx feed still works).
Never types/fetches a real key value. Inert build-only module: fetch + parse
only, no DB writes, no orchestrator registration. NEEDS_PROD_VERIFY: response
shapes parsed defensively (Casey registers the key; sandbox could not exercise).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "az511"
EVENT_API_URL = "https://az511.gov/api/v2/get/event"
WZDX_URL = "https://az511.com/api/wzdx"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
RELEVANT_COUNTIES = ("mohave", "la paz")
RELEVANT_ROAD_TOKENS = ("sr-95", "sr 95", "us-95", "us 95", "i-40", "i 40", "state route 95")
# 10 calls / 60s -> ~0.16 qps.
_LIMITER = SourceLimiter("az511", qps=0.15)


@dataclass
class Az511Event:
    event_id: str | None
    roadway: str | None
    direction: str | None
    description: str | None
    event_type: str | None
    is_full_closure: bool
    county: str | None
    feed: str
    raw: dict = field(default_factory=dict)


def _api_key() -> str:
    return (os.environ.get("AZ511_API_KEY") or "").strip()


def _is_relevant(roadway: str | None, county: str | None, description: str | None) -> bool:
    blob = " ".join(p for p in (roadway, county, description) if p).lower()
    if county and county.strip().lower() in RELEVANT_COUNTIES:
        return True
    return any(tok in blob for tok in RELEVANT_ROAD_TOKENS)


def parse_events(payload: Any) -> list[Az511Event]:
    """Parse the AZ511 event API array, filtered to relevant roads/counties."""
    rows = payload if isinstance(payload, list) else (payload.get("events") if isinstance(payload, dict) else None)
    if not isinstance(rows, list):
        return []
    out: list[Az511Event] = []
    for ev in rows:
        if not isinstance(ev, dict):
            continue
        roadway = ev.get("RoadwayName") or ev.get("roadwayName")
        county = ev.get("County") or ev.get("county")
        description = ev.get("Description") or ev.get("description")
        if not _is_relevant(roadway, county, description):
            continue
        out.append(
            Az511Event(
                event_id=str(ev.get("ID") or ev.get("id") or "") or None,
                roadway=roadway,
                direction=ev.get("DirectionOfTravel") or ev.get("direction"),
                description=description,
                event_type=ev.get("EventType") or ev.get("eventType"),
                is_full_closure=bool(ev.get("IsFullClosure") or ev.get("isFullClosure")),
                county=county,
                feed="event_api",
                raw={"id": ev.get("ID") or ev.get("id")},
            )
        )
    return out


def parse_wzdx(geojson: Any) -> list[Az511Event]:
    """Parse the keyless WZDx GeoJSON work-zone feed, filtered to relevant roads."""
    features = geojson.get("features") if isinstance(geojson, dict) else None
    if not isinstance(features, list):
        return []
    out: list[Az511Event] = []
    for feat in features:
        props = feat.get("properties") if isinstance(feat, dict) else None
        if not isinstance(props, dict):
            continue
        core = props.get("core_details") or props
        road_names = core.get("road_names") or core.get("road_name")
        if isinstance(road_names, list):
            roadway = ", ".join(str(r) for r in road_names)
        else:
            roadway = str(road_names) if road_names else None
        description = core.get("description")
        if not _is_relevant(roadway, None, description):
            continue
        out.append(
            Az511Event(
                event_id=str(props.get("id") or core.get("data_source_id") or "") or None,
                roadway=roadway,
                direction=core.get("direction"),
                description=description,
                event_type="work-zone",
                is_full_closure=False,
                county=None,
                feed="wzdx",
                raw={"id": props.get("id")},
            )
        )
    return out


def fetch_events(*, client: httpx.Client | None = None) -> list[Az511Event]:
    key = _api_key()
    if not key:
        logger.info("az511.no_api_key — skipping event API (set AZ511_API_KEY); WZDx still works")
        return []
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(EVENT_API_URL, params={"key": key}, timeout=30.0))
        if resp is None:
            raise RuntimeError("az511 event fetch failed")
        resp.raise_for_status()
        return parse_events(resp.json())
    finally:
        if owns:
            c.close()


def fetch_wzdx(*, client: httpx.Client | None = None) -> list[Az511Event]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(WZDX_URL, timeout=30.0))
        if resp is None:
            raise RuntimeError("az511 wzdx fetch failed")
        resp.raise_for_status()
        return parse_wzdx(resp.json())
    finally:
        if owns:
            c.close()


def event_sample(e: Az511Event) -> dict:
    return {
        "roadway": e.roadway,
        "type": e.event_type,
        "full_closure": e.is_full_closure,
        "county": e.county,
        "feed": e.feed,
        "description": (e.description or "")[:160],
    }
