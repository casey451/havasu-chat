"""
Load golakehavasu.com partner directory listings into providers + ENTITY graph,
via the cross-source ingest reconciler.

Mirrors :mod:`scripts.osm_overpass_load`: each listing becomes an
:class:`~app.contrib.ingest_base.EntityPayload` with ``source="go_lake_havasu"``,
then :func:`~app.contrib.ingest_reconciler.reconcile_hit` decides insert vs
merge. A partner that already exists as a Google Places provider updates the
existing row (CVB fills gaps; Google identity wins); a genuinely new attraction
is inserted; an ambiguous name-only match is skipped for human review.

Usage:
    python -m scripts.golakehavasu_partners_load --dry-run
    python -m scripts.golakehavasu_partners_load --limit 25 --category-slug things-to-do
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.golakehavasu import REQUEST_TIMEOUT, USER_AGENT  # noqa: E402
from app.contrib.golakehavasu_partners import (  # noqa: E402
    fetch_and_parse_partner,
    fetch_partner_sitemap_urls,
    partner_to_entity_payload,
)
from app.contrib.ingest_base import EntityPayload  # noqa: E402
from app.contrib.ingest_reconciler import (  # noqa: E402
    log_ambiguous_reconcile,
    reconcile_hit,
    slugify,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Entity, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402

logger = logging.getLogger(__name__)


def _norm_web(url: str | None) -> str | None:
    """Normalize a website URL into a stable idempotency key (scheme/www/slash-insensitive)."""
    if not url:
        return None
    s = str(url).strip().lower()
    for pre in ("https://", "http://"):
        if s.startswith(pre):
            s = s[len(pre) :]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/") or None


def _pick_canonical(rows: list[Provider]) -> Provider:
    """Choose the row to keep when a CVB listing already has >1 provider:
    a live (non-draft, active) row first, else any non-draft, else the first."""
    live = [r for r in rows if not r.draft and r.is_active]
    if live:
        return live[0]
    nondraft = [r for r in rows if not r.draft]
    if nondraft:
        return nondraft[0]
    return rows[0]


def _provider_kwargs(
    payload: EntityPayload,
    *,
    category_slug: str,
    category_id: int | None,
) -> dict[str, Any]:
    return {
        "provider_name": payload.name,
        "category": category_slug,
        "category_id": category_id,
        "address": payload.address,
        "phone": payload.phone,
        "website": payload.website,
        "description": payload.description,
        "google_place_id": None,
        "lat": payload.lat,
        "lng": payload.lng,
        "zip": None,
        "source": "go_lake_havasu",
        "enrichment_version": None,
        "is_active": True,
        "verified": False,
        "draft": False,
        "pending_review": False,
        "tier": "free",
    }


def _fill_gaps(
    prov: Provider,
    kwargs: dict[str, Any],
    *,
    fields: tuple[str, ...] = ("phone", "website", "address", "description"),
) -> None:
    """CVB supplements empty contact fields but never clobbers richer data."""
    for f in fields:
        incoming = kwargs.get(f)
        if incoming is None or incoming == "":
            continue
        current = getattr(prov, f)
        if current is None or current == "":
            setattr(prov, f, incoming)


def ingest_partners(
    *,
    category_slug: str,
    dry_run: bool,
    limit: int | None,
    http_client: httpx.Client | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "urls": 0,
        "parsed": 0,
        "skipped_unnamed": 0,
        "inserted": 0,
        "inserted_pending": 0,
        "updated": 0,
        "idempotent_updated": 0,
        "retired_duplicates": 0,
        "reconcile_skipped_ambiguous": 0,
    }

    def _run(client: httpx.Client) -> dict[str, int]:
        urls = fetch_partner_sitemap_urls(client=client)
        if limit is not None:
            urls = urls[:limit]
        counts["urls"] = len(urls)

        payloads: list[EntityPayload] = []
        for url in urls:
            url = (url or "").strip()
            if not url:
                continue
            try:
                listing = fetch_and_parse_partner(url, client=client)
            except Exception as e:  # noqa: BLE001
                logger.warning("parse failed %s: %s", url, e)
                continue
            if listing is None:
                counts["skipped_unnamed"] += 1
                continue
            counts["parsed"] += 1
            payloads.append(partner_to_entity_payload(listing, category_slug=category_slug))

        if dry_run or not payloads:
            return counts

        with SessionLocal() as session:
            cat_id = session.scalars(
                select(Category.id).where(Category.slug == category_slug)
            ).first()

            # Idempotency snapshot: existing CVB providers keyed by name + website
            # so a re-run UPDATES the prior row (and retires any duplicates)
            # instead of relying on flaky geo+name reconcile against neighbours.
            existing_cvb = session.scalars(
                select(Provider).where(Provider.source.like("%go_lake_havasu%"))
            ).all()
            cvb_by_name: dict[str, list[Provider]] = {}
            cvb_by_web: dict[str, Provider] = {}
            for prov in existing_cvb:
                cvb_by_name.setdefault(slugify(prov.provider_name or ""), []).append(prov)
                w = _norm_web(prov.website)
                if w:
                    cvb_by_web.setdefault(w, prov)

            for payload in payloads:
                kwargs = _provider_kwargs(payload, category_slug=category_slug, category_id=cat_id)

                # CVB-to-CVB idempotency: already ingested this listing?
                name_slug = slugify(payload.name)
                web_key = _norm_web(payload.website)
                cvb_matches = list(cvb_by_name.get(name_slug) or [])
                if not cvb_matches and web_key and web_key in cvb_by_web:
                    cvb_matches = [cvb_by_web[web_key]]
                if cvb_matches:
                    canonical = _pick_canonical(cvb_matches)
                    _fill_gaps(canonical, kwargs)
                    sync_provider_entity_from_legacy(session, canonical)
                    for other in cvb_matches:
                        if other is not canonical and other.is_active:
                            other.is_active = False
                            counts["retired_duplicates"] += 1
                    counts["idempotent_updated"] += 1
                    continue

                rec = reconcile_hit(session, payload)
                if rec.action == "ambiguous":
                    # Don't drop the listing and don't silently merge: the
                    # reconciler saw a nearby/name-similar provider but couldn't
                    # confidently match (e.g. CVB title vs Google Places name).
                    # Land it held (draft + pending_review) so the data is
                    # captured and a human can confirm dup-vs-distinct later.
                    log_ambiguous_reconcile(rec, context="golakehavasu_partners_load")
                    pend = dict(kwargs)
                    pend["draft"] = True
                    pend["pending_review"] = True
                    slug = derive_provider_slug(session, pend["provider_name"])
                    provider = Provider(**pend, slug=slug, last_google_scraped_at=None)
                    session.add(provider)
                    create_provider_and_entity(session, provider)
                    counts["inserted_pending"] += 1
                    continue
                if rec.action == "update" and rec.existing_id:
                    prov = session.scalars(
                        select(Provider).where(Provider.entity_id == rec.existing_id).limit(1)
                    ).first()
                    if prov is None:
                        counts["reconcile_skipped_ambiguous"] += 1
                        continue
                    _fill_gaps(prov, kwargs)
                    sync_provider_entity_from_legacy(session, prov)
                    if rec.merge_fields:
                        ent = session.get(Entity, rec.existing_id)
                        if ent is not None and "source" in rec.merge_fields:
                            ent.source = str(rec.merge_fields["source"])[:64]
                    counts["updated"] += 1
                    continue
                slug = derive_provider_slug(session, kwargs["provider_name"])
                provider = Provider(**kwargs, slug=slug, last_google_scraped_at=None)
                session.add(provider)
                create_provider_and_entity(session, provider)
                counts["inserted"] += 1
            session.commit()
        return counts

    if http_client is not None:
        return _run(http_client)
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        return _run(client)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest golakehavasu partner listings")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="Cap number of listings")
    p.add_argument(
        "--category-slug",
        default="things-to-do",
        help="Tier-1 slug for new Provider.category + EntityCategory FK",
    )
    args = p.parse_args()

    counts = ingest_partners(
        category_slug=args.category_slug,
        dry_run=bool(args.dry_run),
        limit=args.limit,
    )
    print("--- golakehavasu_partners_load summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    if args.dry_run:
        print("[golakehavasu_partners_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
