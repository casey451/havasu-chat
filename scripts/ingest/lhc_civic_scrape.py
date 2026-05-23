"""Layer 3 civic-resource scraper for cat-13 (public-civic-resources).

USAGE
-----
    python -m scripts.ingest.lhc_civic_scrape --dry-run
    python -m scripts.ingest.lhc_civic_scrape --source library --commit
    python -m scripts.ingest.lhc_civic_scrape --source all --commit

Scrapes library hours, Havasu Hopper transit, and KHII airport info from
public city / county / AirNav pages. Each source uses try/except with a
curated fallback record when HTML is JS-rendered or unparsable.

Idempotent upserts match on case-insensitive (name, address).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_types import ENTITY_TYPE_PLACE  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    ContactPoint,
    Entity,
    EntityCategory,
    Feature,
    Hours,
    Location,
)
from app.utils.slug import make_unique_slug, slugify  # noqa: E402

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; HavasuChatCivicScraper/1.0; +https://havasu-chat.example.com)"
)
REQUEST_TIMEOUT = 30.0

CAT13_SLUG = "public-civic-resources"
SOURCE_NAME = "lhc_civic_scrape"

LIBRARY_URL = "https://www.mohavecountylibrary.us/locations/lake-havasu-city/"
TRANSIT_URL = "https://www.lhcaz.gov/transit"
AIRPORT_CITY_URL = "https://www.lhcaz.gov/156/Airport"
AIRNAV_URL = "https://www.airnav.com/airport/KHII"

_DEFAULT_CITY = "Lake Havasu City"
_DEFAULT_STATE = "AZ"


@dataclass(frozen=True)
class CivicEntityRecord:
    """Normalized civic entity payload for upsert."""

    name: str
    address: str
    entity_type: str = ENTITY_TYPE_PLACE
    website: str | None = None
    phone: str | None = None
    hours_text: str | None = None
    description: str | None = None
    sub_category: str | None = None
    lat: float | None = None
    lng: float | None = None
    source: str = SOURCE_NAME
    parse_fallback: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _entity_slug_pool(db: Session) -> set[str]:
    return set(db.scalars(select(Entity.slug)).all())


def _allocate_slug(db: Session, name: str) -> str:
    base = slugify(name)[:96]
    return make_unique_slug(base, _entity_slug_pool(db), max_length=96)


def _find_by_name_address(db: Session, name: str, address: str) -> Entity | None:
    name_n = _norm(name)
    addr_n = _norm(address)
    if not name_n or not addr_n:
        return None
    stmt = (
        select(Entity)
        .join(Location, Location.entity_id == Entity.id)
        .where(
            func.lower(Entity.name) == name_n,
            func.lower(func.coalesce(Location.address_normalized, Location.address)) == addr_n,
        )
    )
    return db.scalars(stmt).first()


def _cat13_id(db: Session) -> int:
    row = db.scalars(select(Category).where(Category.slug == CAT13_SLUG)).first()
    if row is None:
        raise RuntimeError(f"category slug {CAT13_SLUG!r} missing — run migrations first")
    return row.id


def _upsert_contact(
    db: Session,
    entity_id: str,
    *,
    kind: str,
    value: str,
) -> None:
    value = value.strip()
    if not value:
        return
    existing = db.scalars(
        select(ContactPoint).where(
            ContactPoint.entity_id == entity_id,
            ContactPoint.kind == kind,
        )
    ).first()
    if existing is None:
        db.add(
            ContactPoint(
                entity_id=entity_id,
                kind=kind,
                value=value,
                is_primary=True,
            )
        )
    elif existing.value != value:
        existing.value = value


def _upsert_sub_category(db: Session, entity_id: str, sub_category: str | None) -> None:
    if not sub_category:
        return
    key = "cat13_sub_category"
    row = db.scalars(
        select(Feature).where(Feature.entity_id == entity_id, Feature.key == key)
    ).first()
    if row is None:
        db.add(Feature(entity_id=entity_id, key=key, value=sub_category))
    elif row.value != sub_category:
        row.value = sub_category


def _set_hours_from_text(db: Session, entity_id: str, hours_text: str | None) -> None:
    """Store unparsed hours in description-adjacent Hours.notes when structured parse absent."""
    if not hours_text or not hours_text.strip():
        return
    notes = hours_text.strip()[:255]
    row = db.scalars(select(Hours).where(Hours.entity_id == entity_id).limit(1)).first()
    if row is None:
        db.add(Hours(entity_id=entity_id, day_of_week=0, notes=notes))
    elif row.notes != notes:
        row.notes = notes


def upsert_civic_entity(db: Session, record: CivicEntityRecord, *, cat_id: int) -> str:
    """Insert or update one civic entity. Returns action: insert|update|noop."""
    existing = _find_by_name_address(db, record.name, record.address)
    now = _utc_now_naive()

    if existing is None:
        ent = Entity(
            id=str(uuid4()),
            entity_type=record.entity_type,
            slug=_allocate_slug(db, record.name),
            name=record.name.strip(),
            description=record.description,
            source=record.source[:64],
            is_active=True,
            heat_exposure="indoor",
            created_at=now,
            updated_at=now,
        )
        db.add(ent)
        db.flush()
        addr = record.address.strip()
        db.add(
            Location(
                entity_id=ent.id,
                address=addr,
                address_normalized=_norm(addr),
                city=_DEFAULT_CITY,
                state=_DEFAULT_STATE,
                lat=record.lat,
                lng=record.lng,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            EntityCategory(
                entity_id=ent.id,
                category_id=cat_id,
                is_primary=True,
                created_at=now,
            )
        )
        if record.website:
            _upsert_contact(db, ent.id, kind="website", value=record.website)
        if record.phone:
            _upsert_contact(db, ent.id, kind="phone", value=record.phone)
        _set_hours_from_text(db, ent.id, record.hours_text)
        _upsert_sub_category(db, ent.id, record.sub_category)
        return "insert"

    changed = False
    if record.description and existing.description != record.description:
        existing.description = record.description
        changed = True
    if existing.entity_type != record.entity_type:
        existing.entity_type = record.entity_type
        changed = True
    existing.updated_at = now

    loc = db.scalars(select(Location).where(Location.entity_id == existing.id)).first()
    if loc is not None:
        if record.lat is not None and loc.lat != record.lat:
            loc.lat = record.lat
            changed = True
        if record.lng is not None and loc.lng != record.lng:
            loc.lng = record.lng
            changed = True

    link = db.scalars(
        select(EntityCategory).where(
            EntityCategory.entity_id == existing.id,
            EntityCategory.category_id == cat_id,
        )
    ).first()
    if link is None:
        db.add(
            EntityCategory(
                entity_id=existing.id,
                category_id=cat_id,
                is_primary=True,
                created_at=now,
            )
        )
        changed = True

    if record.website:
        before = db.scalars(
            select(ContactPoint).where(
                ContactPoint.entity_id == existing.id,
                ContactPoint.kind == "website",
            )
        ).first()
        _upsert_contact(db, existing.id, kind="website", value=record.website)
        after = db.scalars(
            select(ContactPoint).where(
                ContactPoint.entity_id == existing.id,
                ContactPoint.kind == "website",
            )
        ).first()
        if before is None or (after and before.value != after.value):
            changed = True

    if record.phone:
        before = db.scalars(
            select(ContactPoint).where(
                ContactPoint.entity_id == existing.id,
                ContactPoint.kind == "phone",
            )
        ).first()
        _upsert_contact(db, existing.id, kind="phone", value=record.phone)
        after = db.scalars(
            select(ContactPoint).where(
                ContactPoint.entity_id == existing.id,
                ContactPoint.kind == "phone",
            )
        ).first()
        if before is None or (after and before.value != after.value):
            changed = True

    if record.hours_text:
        row = db.scalars(select(Hours).where(Hours.entity_id == existing.id).limit(1)).first()
        notes = record.hours_text.strip()[:255]
        if row is None:
            _set_hours_from_text(db, existing.id, record.hours_text)
            changed = True
        elif row.notes != notes:
            _set_hours_from_text(db, existing.id, record.hours_text)
            changed = True

    _upsert_sub_category(db, existing.id, record.sub_category)
    return "update" if changed else "noop"


def fetch_url(url: str, *, client: httpx.Client | None = None) -> str:
    owns = client is None
    if owns:
        client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    finally:
        if owns:
            client.close()


def _text(soup: BeautifulSoup) -> str:
    return soup.get_text(" ", strip=True)


_HOURS_LINE_RE = re.compile(
    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[^:]*:\s*([^.]{3,80})",
    re.IGNORECASE,
)


def parse_library_html(html: str) -> CivicEntityRecord:
    soup = BeautifulSoup(html, "html.parser")
    text = _text(soup)
    hours_lines = _HOURS_LINE_RE.findall(text)
    hours_text = "; ".join(f"{d}: {t.strip()}" for d, t in hours_lines[:7]) or None
    phone = None
    phone_m = re.search(r"\(?928\)?[\s.-]*\d{3}[\s.-]*\d{4}", text)
    if phone_m:
        phone = phone_m.group(0)
    fallback = not hours_lines
    return CivicEntityRecord(
        name="Mohave County Library - Lake Havasu City Branch",
        address="1780 McCulloch Blvd N, Lake Havasu City, AZ 86403",
        website=LIBRARY_URL,
        phone=phone or "(928) 453-0718",
        hours_text=hours_text or "Mon–Thu 9am–7pm; Fri–Sat 9am–5pm (verify at mohavecountylibrary.us)",
        description="Public library branch serving Lake Havasu City.",
        sub_category="library",
        lat=34.4834,
        lng=-114.3389,
        parse_fallback=fallback,
    )


def parse_transit_html(html: str) -> list[CivicEntityRecord]:
    soup = BeautifulSoup(html, "html.parser")
    text = _text(soup)
    phone = None
    phone_m = re.search(r"\(?928\)?[\s.-]*\d{3}[\s.-]*\d{4}", text)
    if phone_m:
        phone = phone_m.group(0)
    schedule_hint = None
    if re.search(r"route|schedule|hopper", text, re.I):
        schedule_hint = "See city transit page for current Havasu Hopper routes and fares."
    fallback = schedule_hint is None
    return [
        CivicEntityRecord(
            name="Havasu Hopper Transit",
            address="2240 McCulloch Blvd N, Lake Havasu City, AZ 86403",
            website=TRANSIT_URL,
            phone=phone or "(928) 453-4141",
            hours_text=schedule_hint or "Mon–Fri service; check lhcaz.gov/transit for seasonal schedule",
            description="City fixed-route and demand-response public transit (Havasu Hopper).",
            sub_category="transit",
            lat=34.4838,
            lng=-114.3375,
            parse_fallback=fallback,
        ),
        CivicEntityRecord(
            name="Havasu Hopper - Downtown Transfer Point",
            address="200 London Bridge Rd, Lake Havasu City, AZ 86403",
            website=TRANSIT_URL,
            description="Primary downtown connection point for Havasu Hopper routes.",
            sub_category="transit",
            lat=34.4732,
            lng=-114.3467,
            parse_fallback=fallback,
        ),
        CivicEntityRecord(
            name="Lake Havasu City Transit Office",
            address="2240 McCulloch Blvd N, Lake Havasu City, AZ 86403",
            website=TRANSIT_URL,
            phone=phone or "(928) 453-4141",
            description="City transit administration and Havasu Hopper information.",
            sub_category="transit",
            lat=34.4838,
            lng=-114.3375,
            parse_fallback=fallback,
        ),
    ]


def parse_airport_city_html(html: str) -> CivicEntityRecord:
    soup = BeautifulSoup(html, "html.parser")
    text = _text(soup)
    phone = None
    phone_m = re.search(r"\(?928\)?[\s.-]*\d{3}[\s.-]*\d{4}", text)
    if phone_m:
        phone = phone_m.group(0)
    fallback = "airport" not in text.lower() and "khii" not in text.lower()
    return CivicEntityRecord(
        name="Lake Havasu City Airport (KHII)",
        address="7000 Air Park Dr, Lake Havasu City, AZ 86404",
        website=AIRPORT_CITY_URL,
        phone=phone or "(928) 764-3330",
        description="Municipal general-aviation airport (KHII) serving Lake Havasu City.",
        sub_category="airport",
        lat=34.5711,
        lng=-114.3582,
        parse_fallback=fallback,
    )


def parse_airnav_html(html: str) -> CivicEntityRecord:
    soup = BeautifulSoup(html, "html.parser")
    text = _text(soup)
    elev = None
    elev_m = re.search(r"Elevation[^0-9]*(\d+)\s*ft", text, re.I)
    if elev_m:
        elev = elev_m.group(1)
    desc = "KHII pilot information from AirNav."
    if elev:
        desc = f"KHII field elevation {elev} ft — pilot information from AirNav."
    fallback = "KHII" not in text and "Lake Havasu" not in text
    return CivicEntityRecord(
        name="Lake Havasu City Airport - Pilot Information (KHII)",
        address="7000 Air Park Dr, Lake Havasu City, AZ 86404",
        website=AIRNAV_URL,
        description=desc,
        sub_category="airport",
        lat=34.5711,
        lng=-114.3582,
        parse_fallback=fallback,
    )


def build_scraper_records(
    *,
    source: str,
    fetch_html: Callable[[str], str] | None = None,
) -> list[CivicEntityRecord]:
    """Build entity records for one or all scraper sources."""
    fetch_html = fetch_html or fetch_url
    out: list[CivicEntityRecord] = []

    def _safe(source_key: str, url: str, parser: Callable[[str], CivicEntityRecord | list[CivicEntityRecord]]) -> None:
        try:
            html = fetch_html(url)
            result = parser(html)
            if isinstance(result, list):
                out.extend(result)
            else:
                out.append(result)
        except Exception:
            logger.exception("scraper source %s failed; using parser on empty HTML", source_key)
            result = parser("")
            if isinstance(result, list):
                out.extend(result)
            else:
                out.append(result)

    if source in ("library", "all"):
        _safe("library", LIBRARY_URL, parse_library_html)
    if source in ("transit", "all"):
        _safe("transit", TRANSIT_URL, parse_transit_html)
    if source in ("airport", "all"):
        _safe("airport_city", AIRPORT_CITY_URL, parse_airport_city_html)
        _safe("airnav", AIRNAV_URL, parse_airnav_html)

    return out


def run_scrape(
    db: Session,
    *,
    source: str = "all",
    dry_run: bool = True,
    fetch_html: Callable[[str], str] | None = None,
) -> dict[str, int]:
    records = build_scraper_records(source=source, fetch_html=fetch_html)
    cat_id = _cat13_id(db)
    stats = {"insert": 0, "update": 0, "noop": 0, "fallback": 0}
    for rec in records:
        if rec.parse_fallback:
            stats["fallback"] += 1
        action = upsert_civic_entity(db, rec, cat_id=cat_id)
        stats[action] += 1
        logger.info("%s %s (%s)", action.upper(), rec.name, rec.sub_category)

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Scrape LHC civic resources into cat-13")
    parser.add_argument(
        "--source",
        choices=("library", "transit", "airport", "all"),
        default="all",
        help="Which source group to scrape (airport includes city page + AirNav)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan inserts/updates without committing (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes (disables dry-run)",
    )
    args = parser.parse_args(argv)
    dry_run = not args.commit

    with SessionLocal() as db:
        stats = run_scrape(db, source=args.source, dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "COMMITTED"
    print(
        f"[{mode}] source={args.source} "
        f"insert={stats['insert']} update={stats['update']} "
        f"noop={stats['noop']} fallback={stats['fallback']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
