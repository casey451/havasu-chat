"""Phase 9b event source scrapers."""

from app.events.scrapers.altitude_booking import AltitudeBookingClient
from app.events.scrapers.base import EventIngestClient, EventPayload
from app.events.scrapers.chamber import ChamberClient
from app.events.scrapers.facebook_pages import FacebookPagesClient
from app.events.scrapers.go_lake_havasu import GoLakeHavasuClient
from app.events.scrapers.havasu_youth import HavasuYouthClient
from app.events.scrapers.lhc_bmx import LhcBmxClient
from app.events.scrapers.lhc_library import LhcLibraryClient
from app.events.scrapers.lhc_parks_rec import LhcParksRecClient
from app.events.scrapers.river_scene_v2 import RiverSceneV2Client
from app.events.scrapers.split_finger import SplitFingerClient
from app.events.scrapers.squarespace_events import (
    HavasuMuseumClient,
    SquarespaceEventsClient,
)

SOURCE_REGISTRY: dict[str, type[EventIngestClient]] = {
    "chamber": ChamberClient,
    "go_lake_havasu": GoLakeHavasuClient,
    "river_scene": RiverSceneV2Client,
    "lhc_library": LhcLibraryClient,
    "lhc_parks_rec": LhcParksRecClient,
    "lhc_bmx": LhcBmxClient,
    "havasu_youth": HavasuYouthClient,
    "havasu_museum": HavasuMuseumClient,
    "facebook": FacebookPagesClient,
    "altitude_booking": AltitudeBookingClient,
    "split_finger": SplitFingerClient,
}

__all__ = [
    "AltitudeBookingClient",
    "ChamberClient",
    "EventIngestClient",
    "EventPayload",
    "FacebookPagesClient",
    "GoLakeHavasuClient",
    "HavasuMuseumClient",
    "HavasuYouthClient",
    "LhcBmxClient",
    "LhcLibraryClient",
    "LhcParksRecClient",
    "RiverSceneV2Client",
    "SOURCE_REGISTRY",
    "SplitFingerClient",
    "SquarespaceEventsClient",
]
