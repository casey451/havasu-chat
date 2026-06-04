"""wildfire — NIFC WFIGS current Arizona wildfire incidents (ArcGIS REST).

source-expansion #16. Live AZ fire incidents (name, acres, % contained,
discovery date), geo-queried to ~100 mi of Lake Havasu. Free, no key:

    https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/
    WFIGS_Incident_Locations_Current/FeatureServer/0/query

Spatial filter is done server-side (point + distance buffer) and double-checked
client-side via haversine. Conditions-style short TTL (~5 min) when wired.

INERT build-only module: fetch + parse only, no DB writes, no orchestrator
registration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.conditions.constants import LHC_LAT, LHC_LON
from app.contrib.ingest_reconciler import haversine_m
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

SOURCE = "wildfire"
ARCGIS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Incident_Locations_Current/FeatureServer/0/query"
)
DEFAULT_RADIUS_MI = 100
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_OUT_FIELDS = "IncidentName,IncidentSize,PercentContained,FireDiscoveryDateTime,POOState"
_LIMITER = SourceLimiter("wildfire", qps=0.5)


@dataclass
class WildfireIncident:
    name: str
    size_acres: float | None
    percent_contained: float | None
    discovered_at: datetime | None
    lat: float | None
    lon: float | None
    distance_mi: float | None = None
    raw: dict = field(default_factory=dict)


def _epoch_ms_to_dt(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=UTC).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        return None


def parse_incidents(payload: Any, *, radius_mi: float | None = DEFAULT_RADIUS_MI) -> list[WildfireIncident]:
    """Map an ArcGIS query payload to WildfireIncident records (radius-filtered)."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return []
    out: list[WildfireIncident] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        attrs = feat.get("attributes") or {}
        name = (attrs.get("IncidentName") or "").strip()
        if not name:
            continue
        geom = feat.get("geometry") or {}
        lat = geom.get("y") if isinstance(geom, dict) else None
        lon = geom.get("x") if isinstance(geom, dict) else None
        distance_mi = None
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            distance_mi = round(haversine_m(LHC_LAT, LHC_LON, float(lat), float(lon)) / 1609.34, 1)
            if radius_mi is not None and distance_mi > radius_mi:
                continue
        size = attrs.get("IncidentSize")
        pct = attrs.get("PercentContained")
        out.append(
            WildfireIncident(
                name=name,
                size_acres=float(size) if isinstance(size, (int, float)) else None,
                percent_contained=float(pct) if isinstance(pct, (int, float)) else None,
                discovered_at=_epoch_ms_to_dt(attrs.get("FireDiscoveryDateTime")),
                lat=float(lat) if isinstance(lat, (int, float)) else None,
                lon=float(lon) if isinstance(lon, (int, float)) else None,
                distance_mi=distance_mi,
            )
        )
    out.sort(key=lambda i: (i.distance_mi if i.distance_mi is not None else 9999))
    return out


def fetch_incidents(*, radius_mi: int = DEFAULT_RADIUS_MI, client: httpx.Client | None = None) -> list[WildfireIncident]:
    params = {
        "where": "POOState='US-AZ'",
        "outFields": _OUT_FIELDS,
        "f": "json",
        "outSR": "4326",
        "geometry": f"{LHC_LON},{LHC_LAT}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": str(radius_mi),
        "units": "esriSRUnit_StatuteMile",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(ARCGIS_URL, params=params, timeout=30.0))
        if resp is None:
            raise RuntimeError("wildfire fetch failed")
        resp.raise_for_status()
        return parse_incidents(resp.json(), radius_mi=radius_mi)
    finally:
        if owns:
            c.close()


def incident_sample(i: WildfireIncident) -> dict:
    return {
        "name": i.name,
        "acres": i.size_acres,
        "contained_pct": i.percent_contained,
        "distance_mi": i.distance_mi,
        "discovered_at": i.discovered_at.isoformat() if i.discovered_at else None,
    }
