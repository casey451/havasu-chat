"""Altitude Trampoline Park (Lake Havasu) — ROLLER booking platform (WS12).

Altitude's first-party ticketing runs on ROLLER. Its public storefront JSON API
gives us the day-camp product + its bookable dates + price directly — better
than any scrape, and the booking URL doubles as the registration link on our
event pages.

Discovery (2026-07-10, via a one-shot Playwright capture of the SPA's XHR):
  base   : https://api.roller.app/api/checkout/{slug}
  slug   : "activitycamps"
  headers: x-api-key: altitudelakehavasu   (public storefront key = the
           subdomain; shipped to every browser), x-cell-id: a
  GET {base}/products                       -> product catalog (list)
  GET {base}/availability?dateIndex=YYYYMMDD&days=N -> [{date, availability}]

The only event-worthy product is "Activity Camp- Full Day" (ages 5–12, 9 AM–4 PM,
member $26.99 / non-member $36.99). Memberships / socks / cups are filtered out.
The venue's weekly Glow / Junior Jump *open-jump* sessions are NOT on this
storefront (sibling slugs return empty), so the havasu_youth fixtures stay
authoritative for those; this connector is authority for the camps (booking
platform > hand fixture, the WebTrac>flyer pattern).

Rollout: review-queue-first (not auto-approved). Each occurrence carries a
distinct ``?date=`` booking URL so it lands as its own contribution and is
idempotent via the runner's find_duplicate.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

API_BASE = "https://api.roller.app/api/checkout"
CHECKOUT_SLUG = "activitycamps"
API_KEY = "altitudelakehavasu"  # public storefront key (subdomain), not a secret
CELL_ID = "a"
BOOKING_URL = (
    "https://lakehavasu.altitudetrampolinepark.com/activitycamps/en-us/home"
)
VENUE_NAME = "Altitude Trampoline Park"
VENUE_ADDRESS = "5601 Highway 95 N Unit 404-D, Lake Havasu City, AZ 86404"
HORIZON_DAYS = 42
_MAX_AVAIL_DAYS = 31  # the availability endpoint rejects days > 31 (400)
# The "Activity Camp- Full Day" runs 9 AM–4 PM (from the product shortDescription).
CAMP_START = time(9, 0)
CAMP_END = time(16, 0)
_TAGS = ("family", "kids", "camp", "all ages")

_MEMBERSHIP_MARKERS = ("membership", "pass", "sock", "cup", "add on", "add-on")


def _is_camp(product: dict[str, Any]) -> bool:
    """A bookable camp product (not a membership / merch add-on)."""
    name = str(product.get("name") or "").lower()
    if str(product.get("type") or "").lower() == "addon":
        return False
    if any(m in name for m in _MEMBERSHIP_MARKERS):
        return False
    return "camp" in name


def _min_cost(product: dict[str, Any]) -> float | None:
    costs = [
        c.get("cost")
        for c in (product.get("products") or [])
        if isinstance(c.get("cost"), (int, float)) and c.get("cost")
    ]
    return round(min(costs), 2) if costs else None


class AltitudeBookingClient(EventIngestClient):
    source_name = "altitude_booking"
    scrape_source = "altitude_booking"

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AskHavaBot/1.0)",
                "x-api-key": API_KEY,
                "x-cell-id": CELL_ID,
                "Accept": "application/json",
            },
        )

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today")
        if not isinstance(today, date):
            today = date.today()
        with self._client() as client:
            products = json.loads(
                self.fetch_text(f"{API_BASE}/{CHECKOUT_SLUG}/products", client=client)
            )
            # The availability endpoint caps ``days`` at 31, so page the horizon.
            avail: list[dict[str, Any]] = []
            start = today
            end = today + timedelta(days=HORIZON_DAYS)
            while start <= end:
                span = min(_MAX_AVAIL_DAYS, (end - start).days + 1)
                page = json.loads(
                    self.fetch_text(
                        f"{API_BASE}/{CHECKOUT_SLUG}/availability"
                        f"?dateIndex={start.strftime('%Y%m%d')}&days={span}",
                        client=client,
                    )
                )
                if isinstance(page, list):
                    avail.extend(x for x in page if isinstance(x, dict))
                start += timedelta(days=span)
        camps = [p for p in products if isinstance(p, dict) and _is_camp(p)]
        # Camps run on weekdays; availability is storefront-level so we keep the
        # Mon–Fri "available" dates (an honest heuristic — review-queue-gated).
        horizon = today + timedelta(days=HORIZON_DAYS)
        dates = sorted(
            {
                str(a["date"])
                for a in (avail or [])
                if isinstance(a, dict)
                and str(a.get("availability")) == "available"
                and a.get("date")
            }
        )
        hits: list[RawHit] = []
        for camp in camps:
            price = _min_cost(camp)
            for ds in dates:
                try:
                    d = date.fromisoformat(str(ds))
                except ValueError:
                    continue
                if d < today or d > horizon or d.weekday() >= 5:
                    continue
                occ_url = f"{BOOKING_URL}?product={camp.get('id')}&date={d.isoformat()}"
                hits.append(
                    RawHit(
                        source=self.source_name,
                        source_stable_id=occ_url,
                        name=str(camp.get("name") or "Activity Camp"),
                        raw={
                            "name": str(camp.get("name") or "Activity Camp").strip(),
                            "short": str(camp.get("shortDescription") or ""),
                            "date": d.isoformat(),
                            "price": price,
                            "url": occ_url,
                        },
                    )
                )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        d = datetime.fromisoformat(str(raw["date"])).date()
        name = str(raw["name"]).replace("- ", " — ").strip()
        price = raw.get("price")
        short = str(raw.get("short") or "").strip()
        price_line = f"From ${price:.2f} per day." if isinstance(price, (int, float)) else ""
        desc = "\n\n".join(
            p
            for p in (
                short,
                price_line,
                "Register on Altitude's booking site (link below). Ages 5–12; "
                "early check-in and late pickup available.",
            )
            if p
        )
        return EventPayload(
            name=name,
            entity_type="event",
            source=self.scrape_source,
            start_date=d,
            start_time=CAMP_START,
            end_time=CAMP_END,
            venue_name=VENUE_NAME,
            address=VENUE_ADDRESS,
            description=desc,
            event_url=hit.raw_hit.source_stable_id,
            source_stable_url=hit.raw_hit.source_stable_id,
            category_slug="events",
            tags=list(_TAGS),
        )
