"""Live crawl + DB indexes + ledger persistence for source reconciliation.

The network/DB layer under ``scripts/reconcile_sources.py``. Pure classification
lives in ``app.contrib.reconcile_core``; this module builds the provider/event
indexes from our DB, crawls the two sources, and (optionally) upserts the
source_listings / source_events ledger tables. Kept thin and out of the unit-test
path (the crawl hits live sites); the testable logic is in reconcile_core.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.contrib.reconcile_core import (
    ReconcileRow,
    classify_business,
    classify_event,
    norm_web,
    slugify_name,
)
from app.db.database import SessionLocal
from app.db.models import Category, Event, Provider, SourceEvent, SourceListing

BUSINESS_SOURCE = "go_lake_havasu"
EVENT_SOURCE = "river_scene"


def _leaf_slug_map(session) -> dict[int, str]:
    """category_id -> slug for level-1 (leaf) categories only."""
    return {
        cid: slug
        for cid, slug in session.execute(
            select(Category.id, Category.slug).where(Category.level == 1)
        )
    }


def _provider_indexes(
    session,
) -> tuple[dict[str, tuple[str, str | None]], dict[str, tuple[str, str | None]]]:
    leaves = _leaf_slug_map(session)
    by_name: dict[str, tuple[str, str | None]] = {}
    by_web: dict[str, tuple[str, str | None]] = {}
    rows = session.scalars(
        select(Provider).where(Provider.is_active.is_(True), Provider.draft.is_(False))
    ).all()
    for p in rows:
        leaf = leaves.get(p.category_id) if p.category_id else None
        key = slugify_name(p.provider_name)
        if key:
            by_name.setdefault(key, (p.id, leaf))
        w = norm_web(p.website)
        if w:
            by_web.setdefault(w, (p.id, leaf))
    return by_name, by_web


def _event_index(session) -> dict[tuple[str, str], str]:
    idx: dict[tuple[str, str], str] = {}
    for ev in session.scalars(select(Event)).all():
        title = ev.normalized_title or ev.title
        key = (slugify_name(title), ev.date.isoformat() if ev.date else "")
        idx.setdefault(key, ev.id)
    return idx


def crawl_business_rows(*, limit: int | None = None) -> list[ReconcileRow]:
    import httpx

    from app.contrib.golakehavasu import USER_AGENT
    from app.contrib.golakehavasu_partners import (
        PARTNER_PAGE_HTTP_TIMEOUT,
        fetch_and_parse_partner,
        fetch_partner_sitemap_urls,
    )

    with SessionLocal() as session:
        by_name, by_web = _provider_indexes(session)

    rows: list[ReconcileRow] = []
    with httpx.Client(
        timeout=PARTNER_PAGE_HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        urls = fetch_partner_sitemap_urls(client=client)
        if limit is not None:
            urls = urls[:limit]
        for url in urls:
            listing = fetch_and_parse_partner(url, client=client)
            if listing is None:
                continue
            rows.append(
                classify_business(
                    source=BUSINESS_SOURCE,
                    source_url=url,
                    name=listing.name,
                    address=listing.address,
                    source_category=listing.category,
                    providers_by_name=by_name,
                    providers_by_web=by_web,
                    website=listing.website,
                )
            )
    return rows


def crawl_event_rows(*, limit: int | None = None) -> list[ReconcileRow]:
    from app.contrib.river_scene import (
        EVENT_PAGE_HTTP_TIMEOUT,
        build_river_scene_client,
        fetch_and_parse_event,
        fetch_sitemap_urls,
    )

    with SessionLocal() as session:
        idx = _event_index(session)

    rows: list[ReconcileRow] = []
    with build_river_scene_client(timeout=EVENT_PAGE_HTTP_TIMEOUT) as client:
        # early start_date so the sitemap lookback includes history
        urls = fetch_sitemap_urls(client=client, start_date=date(2000, 1, 1))
        if limit is not None:
            urls = urls[:limit]
        for url in urls:
            # today=date.min keeps past events (reconciliation needs full history)
            rse = fetch_and_parse_event(url, client=client, today=date.min)
            if rse is None:
                continue
            cats = list(getattr(rse, "category_slugs", None) or [])
            rows.append(
                classify_event(
                    source=EVENT_SOURCE,
                    source_url=url,
                    title=rse.title,
                    event_date=rse.start_date,
                    venue=rse.venue_name,
                    source_category=cats[0] if cats else None,
                    events_by_key=idx,
                )
            )
    return rows


def persist_ledger(rows: list[ReconcileRow]) -> int:
    """Upsert ledger rows keyed by (source, source_url). Additive bookkeeping —
    does NOT touch providers/events."""
    now = datetime.now(UTC)
    n = 0
    with SessionLocal() as session:
        for r in rows:
            if r.source == EVENT_SOURCE:
                existing = session.scalar(
                    select(SourceEvent).where(
                        SourceEvent.source == r.source, SourceEvent.source_url == r.source_url
                    )
                )
                if existing is None:
                    session.add(
                        SourceEvent(
                            source=r.source, source_url=r.source_url,
                            source_category=r.source_category, title=r.name, venue=r.address,
                            region=r.region, mapped_category=r.mapped,
                            match_status=r.match_status, matched_event_id=r.matched_id,
                            exclusion_reason=r.exclusion_reason, first_seen=now, last_seen=now,
                        )
                    )
                else:
                    existing.match_status = r.match_status
                    existing.mapped_category = r.mapped
                    existing.region = r.region
                    existing.matched_event_id = r.matched_id
                    existing.exclusion_reason = r.exclusion_reason
                    existing.last_seen = now
            else:
                existing = session.scalar(
                    select(SourceListing).where(
                        SourceListing.source == r.source, SourceListing.source_url == r.source_url
                    )
                )
                if existing is None:
                    session.add(
                        SourceListing(
                            source=r.source, source_url=r.source_url,
                            source_category=r.source_category, name=r.name, address=r.address,
                            region=r.region, mapped_leaf=r.mapped,
                            match_status=r.match_status, matched_provider_id=r.matched_id,
                            exclusion_reason=r.exclusion_reason, first_seen=now, last_seen=now,
                        )
                    )
                else:
                    existing.match_status = r.match_status
                    existing.mapped_leaf = r.mapped
                    existing.region = r.region
                    existing.matched_provider_id = r.matched_id
                    existing.exclusion_reason = r.exclusion_reason
                    existing.last_seen = now
            n += 1
        session.commit()
    return n
