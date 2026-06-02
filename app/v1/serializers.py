"""JSON shapes for master-spec public API (§4.1)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from app.db.models import Event, Provider
from app.v1.categories import bucket_for_legacy_category


def _provider_status(provider: Provider) -> str:
    if provider.draft or provider.pending_review:
        return "pending"
    if not provider.is_active:
        return "hidden"
    return "published"


def business_from_provider(provider: Provider) -> dict[str, Any]:
    bucket = bucket_for_legacy_category(provider.category)
    hours = provider.hours_structured or provider.google_hours
    return {
        "id": provider.id,
        "name": provider.provider_name,
        "category": bucket,
        # Canonical second level (master spec §3.1). Falls back to the raw Google
        # primary type when a row hasn't been classified yet (subcategory NULL).
        "subcategory": provider.subcategory or provider.google_primary_category,
        "phone": provider.phone,
        "address": provider.address,
        "lat": provider.lat,
        "lng": provider.lng,
        "hours": hours,
        "website": provider.website or provider.facebook,
        "rating": provider.google_rating,
        "review_count": provider.google_review_count,
        "source": provider.source if provider.google_place_id else provider.source,
        "tier": provider.tier or "free",
        "description": provider.description or provider.featured_description,
        "photos": provider.google_photo_urls or [],
        "slug": provider.slug,
        "status": _provider_status(provider),
        "profile_url": f"/provider/{provider.slug}" if provider.slug else None,
    }


def event_from_row(event: Event, *, occurrence_date: date | None = None) -> dict[str, Any]:
    occ = occurrence_date or event.date
    start_at = datetime.combine(occ, event.start_time)
    end_at = None
    if event.end_time:
        end_d = event.end_date or occ
        end_at = datetime.combine(end_d, event.end_time)
    return {
        "id": event.id,
        "title": event.title,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat() if end_at else None,
        "all_day": event.start_time == time(0, 0) and event.end_time is None,
        "venue": event.location_name,
        "address": event.location_name,
        "lat": None,
        "lng": None,
        "category": "events",
        "cost": None,
        "host": event.contact_name,
        "organizer_url": event.event_url or event.source_url,
        "description": event.description,
        "image_url": None,
        "recurrence": {"rrule": event.rrule} if event.is_recurring and event.rrule else None,
        "boosted": False,
        "source": event.source,
        "slug": getattr(event, "slug", None),
        "status": "published" if event.status == "live" else event.status,
    }
