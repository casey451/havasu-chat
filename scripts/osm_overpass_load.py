"""Load OSM Overpass JSONL into providers + ENTITY graph (Phase 5 on-the-water).

Each input line is JSON. Supported shapes:

1. **Feature line** — ``{"type":"node|way|relation","id":..., "tags":{...}, ...}``
   (must include ``tags``, ``name``, and coordinates).
2. **Wrapper line** — ``{"elements":[...]}`` — only elements whose ``tags``
   contain ``--tag`` = ``--value`` are ingested (e.g. ``leisure=marina``).

Elements without the requested tag are **ignored** (they may appear only as
skeleton members from a recurse — they do not count as venues).

Mirrors :mod:`scripts.places_load` reconciler integration: each hit becomes an
:class:`~app.contrib.ingest_base.EntityPayload` with ``source="osm"``, then
:func:`~app.contrib.ingest_reconciler.reconcile_hit` decides insert vs merge.

Usage:
    python -m scripts.osm_overpass_load --input path/to/osm.jsonl --dry-run
    python -m scripts.osm_overpass_load --tag leisure --value marina
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.ingest_base import EntityPayload  # noqa: E402
from app.contrib.ingest_reconciler import (  # noqa: E402
    log_ambiguous_reconcile,
)
from app.contrib.scraper_ingest import decide_ingest  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Entity, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = Path(__file__).parent / "output" / "osm_pull" / "osm_elements.jsonl"


def _element_lat_lng(el: dict[str, Any]) -> tuple[float, float] | None:
    if el.get("lat") is not None and el.get("lon") is not None:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    geom = el.get("geometry")
    if isinstance(geom, list) and geom:
        first = geom[0]
        if (
            isinstance(first, dict)
            and first.get("lat") is not None
            and first.get("lon") is not None
        ):
            return float(first["lat"]), float(first["lon"])
    return None


def _format_address(tags: dict[str, Any]) -> str | None:
    if tags.get("addr:full"):
        return str(tags["addr:full"]).strip() or None
    parts: list[str] = []
    hn = tags.get("addr:housenumber")
    st = tags.get("addr:street")
    if hn or st:
        parts.append(" ".join(str(p) for p in (hn, st) if p).strip())
    city = tags.get("addr:city") or tags.get("addr:place")
    state = tags.get("addr:state")
    pc = tags.get("addr:postcode")
    tail = ", ".join(str(p) for p in (city, state, pc) if p)
    if tail:
        parts.append(tail)
    if not parts:
        return None
    return ", ".join(parts)


def _iter_feature_elements(
    obj: dict[str, Any],
    *,
    tag: str | None,
    value: str | None,
) -> Iterator[dict[str, Any]]:
    if "elements" in obj and isinstance(obj["elements"], list):
        for el in obj["elements"]:
            if not isinstance(el, dict):
                continue
            if el.get("type") not in {"node", "way", "relation"}:
                continue
            tags = el.get("tags")
            if not isinstance(tags, dict):
                continue
            if tag is not None and value is not None:
                if tags.get(tag) != value:
                    continue
            yield el
        return
    if obj.get("type") in {"node", "way", "relation"}:
        tags = obj.get("tags")
        if not isinstance(tags, dict):
            return
        if tag is not None and value is not None and tags.get(tag) != value:
            return
        yield obj


def element_to_entity_payload(
    el: dict[str, Any],
    *,
    category_slug: str,
) -> EntityPayload | None:
    tags = el.get("tags") or {}
    if not isinstance(tags, dict):
        return None
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    coords = _element_lat_lng(el)
    if coords is None:
        return None
    lat, lng = coords
    phone_raw = tags.get("phone") or tags.get("contact:phone")
    phone = str(phone_raw).strip() if phone_raw is not None else None
    if phone == "":
        phone = None
    web_raw = tags.get("website") or tags.get("contact:website")
    website = str(web_raw).strip() if web_raw is not None else None
    if website == "":
        website = None
    desc = tags.get("description")
    if isinstance(desc, str):
        desc = desc.strip() or None
    else:
        desc = None
    return EntityPayload(
        name=name,
        entity_type="place",
        lat=lat,
        lng=lng,
        address=_format_address(tags),
        phone=phone,
        website=website,
        description=desc,
        category_slug=category_slug,
        google_place_id=None,
        source="osm",
    )


def _fill_gaps(
    prov: Provider,
    kwargs: Mapping[str, Any],
    *,
    fields: tuple[str, ...] = ("phone", "website", "address", "description"),
) -> None:
    """Copy OSM kwargs into ``prov`` only where the row is missing contact data.

    Used on reconcile ``update`` hits: OSM is lower ``SOURCE_PRIORITY`` than
    ``google_places`` / ``operator``, so we supplement empty fields but never
    clobber verified/Google identity or richer existing contact info.
    """
    for field in fields:
        incoming = kwargs.get(field)
        if incoming is None or incoming == "":
            continue
        current = getattr(prov, field)
        if current is None or current == "":
            setattr(prov, field, incoming)


def _osm_provider_kwargs(
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
        "source": "osm",
        "enrichment_version": None,
        "is_active": True,
        "verified": False,
        "draft": False,
        "pending_review": False,
        "tier": "free",
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def ingest_rows(
    rows: list[dict[str, Any]],
    *,
    tag: str | None,
    value: str | None,
    category_slug: str,
    dry_run: bool,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "lines": len(rows),
        "elements_seen": 0,
        "skipped_no_name_or_coords": 0,
        "payloads_ready": 0,
        "inserted": 0,
        "inserted_pending": 0,
        "updated": 0,
        "reconcile_skipped_ambiguous": 0,
        "reconcile_merged_geo": 0,
    }
    payloads: list[EntityPayload] = []
    for raw in rows:
        for el in _iter_feature_elements(raw, tag=tag, value=value):
            counts["elements_seen"] += 1
            p = element_to_entity_payload(el, category_slug=category_slug)
            if p is None:
                counts["skipped_no_name_or_coords"] += 1
                continue
            payloads.append(p)

    counts["payloads_ready"] = len(payloads)

    if dry_run or not payloads:
        return counts

    with SessionLocal() as session:
        cat_id = session.scalars(select(Category.id).where(Category.slug == category_slug)).first()
        for payload in payloads:
            kwargs = _osm_provider_kwargs(payload, category_slug=category_slug, category_id=cat_id)
            # Funnel: normalize + reconcile + hide-on-doubt in one place
            # (app.contrib.scraper_ingest.decide_ingest). ``should_hide`` is True
            # exactly when the reconciler is unsure (ambiguous); we honour it by
            # landing the row HELD (draft + pending_review) for admin review
            # rather than dropping it -- so an uncertain OSM element is captured,
            # never shown to a user, and never silently lost.
            decision = decide_ingest(session, payload)
            rec = decision.reconcile
            if decision.should_hide:
                log_ambiguous_reconcile(rec, context="osm_overpass_load insert branch")
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
                    logger.warning(
                        "osm_overpass_load reconcile update without provider entity_id=%s",
                        rec.existing_id,
                    )
                    counts["reconcile_skipped_ambiguous"] += 1
                    continue
                _fill_gaps(prov, kwargs)
                sync_provider_entity_from_legacy(session, prov)
                if rec.merge_fields:
                    ent = session.get(Entity, rec.existing_id)
                    if ent is not None:
                        if "name" in rec.merge_fields:
                            ent.name = str(rec.merge_fields["name"])[:255]
                        if "description" in rec.merge_fields:
                            ent.description = rec.merge_fields["description"]
                        if "source" in rec.merge_fields:
                            ent.source = str(rec.merge_fields["source"])[:64]
                counts["reconcile_merged_geo"] += 1
                counts["updated"] += 1
                continue
            slug = derive_provider_slug(session, kwargs["provider_name"])
            provider = Provider(**kwargs, slug=slug, last_google_scraped_at=None)
            session.add(provider)
            create_provider_and_entity(session, provider)
            counts["inserted"] += 1

        session.commit()

    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tag", default=None, help="Required tag key when input has wrapper lines")
    p.add_argument("--value", default=None, help="Required tag value when input has wrapper lines")
    p.add_argument(
        "--category-slug",
        default="on-the-water",
        help="Tier-1 slug for new Provider.category + EntityCategory FK",
    )
    args = p.parse_args()

    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    rows = load_jsonl(args.input)
    counts = ingest_rows(
        rows,
        tag=args.tag,
        value=args.value,
        category_slug=args.category_slug,
        dry_run=args.dry_run,
    )

    print("--- osm_overpass_load summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    if args.dry_run:
        print("[osm_overpass_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
