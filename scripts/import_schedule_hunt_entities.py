"""Propose new Entity rows from the schedule-hunt candidate sweep.

Reads ``docs/scraper/schedule_hunt_candidates.csv`` and proposes, WITHOUT
writing anything by default:

  1. **New Entity rows** (+ ``Location`` / ``ContactPoint`` / ``EntityCategory``
     satellites) for candidate venues that are not already in the DB, decided by
     a fuzzy name match against existing *real* entities.
  2. A **quarantine list** of obvious test fixtures — entities whose ``source``
     contains ``test`` or whose name carries a hash suffix (e.g. the two
     ``Bridge City Combat <hash>`` rows) — EXCEPT fixtures whose (de-hashed) name
     shadows a real business present in the CSV. Those shadowing fixtures are
     reported separately as **keep & fix** so we keep the real name and repair
     the row instead of deleting it.

Schedules / Offerings are intentionally NOT imported here; those flow through the
capture-review -> contributions -> publish path once the Jobs page exists.

Usage:
    python scripts/import_schedule_hunt_entities.py            # dry-run (default)
    python scripts/import_schedule_hunt_entities.py --apply    # write (prod-data op!)

``--apply`` is a production-data operation: per CLAUDE.md, run the dry-run first,
show the counts, and get Casey's approval before applying. Applying creates the
proposed new entities and quarantines fixtures by setting ``is_active = False``
(reversible — it never deletes rows).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

# Allow ``python scripts/import_schedule_hunt_entities.py`` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    ContactPoint,
    Entity,
    EntityCategory,
    Location,
)
from app.utils.slug import make_unique_slug, slugify  # noqa: E402

_DEFAULT_CSV = Path(__file__).resolve().parents[1] / "docs" / "scraper" / "schedule_hunt_candidates.csv"
_SOURCE_TAG = "schedule_hunt:2026-06-03"
_CITY = "Lake Havasu City"
_STATE = "AZ"

# Fuzzy-match threshold (difflib ratio). Tuned to treat clear name variants as the
# same business while keeping distinct venues apart.
_MATCH_RATIO = 0.86

# Bare place names that exist as stub DB entities — never a meaningful containment
# match (they appear inside dozens of real business names). Normalized form.
_PLACE_STOPWORDS: frozenset[str] = frozenset(
    {"havasu", "lake havasu", "lake havasu city", "lake havasu city az", "lhc", "arizona"}
)

# A trailing hex-ish token (>=6 chars, at least one digit) preceded by a space or
# hyphen — the shape the tier2-test fixtures use, e.g. "Bridge City Combat 3f9a2b1c".
_HASH_SUFFIX_RE = re.compile(r"[\s\-]+(?=[0-9a-f]*[0-9])[0-9a-f]{6,}$", re.IGNORECASE)

# CSV ``type`` keyword -> live Category slug (the 17-bucket post-rewrite taxonomy;
# verified against the seeded ``categories`` table, NOT the stale directory_v1 set).
# Whole-word, first-match-wins; unmatched types are reported uncategorized so a
# reviewer can assign them. These are hints for review, not authoritative.
_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("dog training", "pets"),
    ("dog", "pets"),
    # On the water
    ("scuba", "on-the-water"),
    ("kayak", "on-the-water"),
    ("boating", "on-the-water"),
    ("swim", "on-the-water"),
    ("pool", "on-the-water"),
    # Retail (more specific shop terms before the generic class terms)
    ("bike shop", "shopping-essentials"),
    ("music store", "shopping-essentials"),
    ("quilt shop", "shopping-essentials"),
    ("fabric shop", "shopping-essentials"),
    # Civic / public
    ("library", "public-civic-resources"),
    ("museum", "public-civic-resources"),
    ("community education", "public-civic-resources"),
    ("city rec", "public-civic-resources"),
    ("senior", "public-civic-resources"),
    ("homeschool", "public-civic-resources"),
    # Everything else here is a class / lesson / sport venue -> classes bucket
    ("dance", "classes-sports-recreation"),
    ("dancing", "classes-sports-recreation"),
    ("ballet", "classes-sports-recreation"),
    ("yoga", "classes-sports-recreation"),
    ("pilates", "classes-sports-recreation"),
    ("gym", "classes-sports-recreation"),
    ("fitness", "classes-sports-recreation"),
    ("crossfit", "classes-sports-recreation"),
    ("martial arts", "classes-sports-recreation"),
    ("mma", "classes-sports-recreation"),
    ("bjj", "classes-sports-recreation"),
    ("muay thai", "classes-sports-recreation"),
    ("karate", "classes-sports-recreation"),
    ("taekwondo", "classes-sports-recreation"),
    ("kickboxing", "classes-sports-recreation"),
    ("boxing", "classes-sports-recreation"),
    ("krav maga", "classes-sports-recreation"),
    ("kung fu", "classes-sports-recreation"),
    ("tai chi", "classes-sports-recreation"),
    ("personal training", "classes-sports-recreation"),
    ("sports training", "classes-sports-recreation"),
    ("gymnastics", "classes-sports-recreation"),
    ("trampoline", "classes-sports-recreation"),
    ("golf", "classes-sports-recreation"),
    ("tennis", "classes-sports-recreation"),
    ("pickleball", "classes-sports-recreation"),
    ("shooting", "classes-sports-recreation"),
    ("riding lessons", "classes-sports-recreation"),
    ("kids", "classes-sports-recreation"),
    ("youth", "classes-sports-recreation"),
    ("tutoring", "classes-sports-recreation"),
    ("theater", "classes-sports-recreation"),
    ("art", "classes-sports-recreation"),
    ("pottery", "classes-sports-recreation"),
    ("music", "classes-sports-recreation"),
    ("voice", "classes-sports-recreation"),
    ("wellness", "classes-sports-recreation"),
    ("cpr", "classes-sports-recreation"),
)


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CsvVenue:
    name: str
    type: str
    website: str
    facebook_url: str
    address: str


@dataclass(frozen=True)
class ExistingEntity:
    id: str
    name: str
    source: str
    is_active: bool


@dataclass
class NewProposal:
    venue: CsvVenue
    slug: str
    category_slug: str | None


@dataclass
class Plan:
    new: list[NewProposal] = field(default_factory=list)
    existing_matches: list[tuple[str, str]] = field(default_factory=list)  # (csv name, db name)
    quarantine: list[ExistingEntity] = field(default_factory=list)
    keep_fix: list[tuple[ExistingEntity, str]] = field(default_factory=list)  # (fixture, csv name)


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without a DB)
# --------------------------------------------------------------------------- #
def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation/possessives, collapse whitespace for matching."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"['’]s\b", "", s)  # strip possessive 's
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_hash_suffix(name: str) -> str:
    """Drop a trailing hash token (e.g. 'Bridge City Combat 3f9a2b1c' -> base)."""
    return _HASH_SUFFIX_RE.sub("", name or "").strip()


def has_hash_suffix(name: str) -> bool:
    return bool(_HASH_SUFFIX_RE.search(name or ""))


def is_fixture(source: str, name: str) -> bool:
    """A test fixture: 'test' in source, or a hash-suffixed name."""
    return "test" in (source or "").lower() or has_hash_suffix(name)


def best_match(target: str, candidates: list[str]) -> str | None:
    """Return the candidate that best matches ``target`` (or None).

    Matches on normalized equality, multi-word containment, or a difflib ratio
    at/above the threshold — whichever fires first by score.

    Containment requires the *shorter* name to be a substring of the longer, to
    have **≥ 2 word tokens**, and to not be a bare place name. Those guards matter
    against stub entities literally named after the town: "Havasu" (1 token) and
    "Lake Havasu city" (3 tokens) both live as DB rows and otherwise match every
    venue that contains the town name, wrongly skipping real new venues. A shared
    place name must clear the difflib bar on its own to count.
    """
    nt = normalize_name(target)
    if not nt:
        return None
    best: tuple[float, str] | None = None
    for cand in candidates:
        nc = normalize_name(cand)
        if not nc:
            continue
        if nt == nc:
            return cand
        shorter, longer = (nt, nc) if len(nt) <= len(nc) else (nc, nt)
        contained = (
            shorter in longer
            and len(shorter.split()) >= 2
            and shorter not in _PLACE_STOPWORDS
        )
        ratio = SequenceMatcher(None, nt, nc).ratio()
        score = max(ratio, 0.95 if contained else 0.0)
        if score >= _MATCH_RATIO and (best is None or score > best[0]):
            best = (score, cand)
    return best[1] if best else None


def category_slug_for(venue_type: str) -> str | None:
    t = (venue_type or "").lower()
    for keyword, slug in _CATEGORY_KEYWORDS:
        # Whole-word match so e.g. "art" doesn't fire on "martial arts".
        if re.search(rf"\b{re.escape(keyword)}\b", t):
            return slug
    return None


def build_plan(venues: list[CsvVenue], existing: list[ExistingEntity]) -> Plan:
    """Classify CSV venues + existing entities into the proposed change sets."""
    fixtures = [e for e in existing if is_fixture(e.source, e.name)]
    real = [e for e in existing if not is_fixture(e.source, e.name)]
    real_names = [e.name for e in real]
    csv_names = [v.name for v in venues]

    plan = Plan()
    used_slugs: set[str] = set()  # de-dupe slugs across the proposed batch
    for v in venues:
        match = best_match(v.name, real_names)
        if match is not None:
            plan.existing_matches.append((v.name, match))
            continue
        slug = make_unique_slug(slugify(v.name), used_slugs)
        plan.new.append(NewProposal(venue=v, slug=slug, category_slug=category_slug_for(v.type)))

    for f in fixtures:
        base = strip_hash_suffix(f.name)
        shadow = best_match(base, csv_names) or best_match(f.name, csv_names)
        if shadow is not None:
            plan.keep_fix.append((f, shadow))
        else:
            plan.quarantine.append(f)
    return plan


# --------------------------------------------------------------------------- #
# CSV + DB I/O
# --------------------------------------------------------------------------- #
def load_csv(path: Path) -> list[CsvVenue]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    venues: list[CsvVenue] = []
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        venues.append(
            CsvVenue(
                name=name,
                type=(r.get("type") or "").strip(),
                website=(r.get("website") or "").strip(),
                facebook_url=(r.get("facebook_url") or "").strip(),
                address=(r.get("address") or "").strip(),
            )
        )
    return venues


def load_existing(session) -> list[ExistingEntity]:
    rows = session.query(Entity.id, Entity.name, Entity.source, Entity.is_active).all()
    return [
        ExistingEntity(id=r[0], name=r[1], source=r[2] or "", is_active=bool(r[3]))
        for r in rows
    ]


def apply_plan(session, plan: Plan) -> None:
    """Write the proposed changes. Called only under --apply (single transaction)."""
    slug_pool = {s for (s,) in session.query(Entity.slug).all()}
    category_ids = {c.slug: c.id for c in session.query(Category).all()}

    for prop in plan.new:
        slug = make_unique_slug(slugify(prop.venue.name), slug_pool)
        ent = Entity(
            id=str(uuid4()),
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=slug,
            name=prop.venue.name,
            source=_SOURCE_TAG[:64],
            is_active=True,
        )
        session.add(ent)
        if prop.venue.address:
            session.add(
                Location(
                    entity_id=ent.id,
                    address=prop.venue.address[:255],
                    address_normalized=prop.venue.address.lower()[:255],
                    city=_CITY,
                    state=_STATE,
                )
            )
        if prop.venue.website:
            session.add(
                ContactPoint(entity_id=ent.id, kind="website", value=prop.venue.website[:512])
            )
        if prop.venue.facebook_url:
            session.add(
                ContactPoint(entity_id=ent.id, kind="facebook", value=prop.venue.facebook_url[:512])
            )
        cat_id = category_ids.get(prop.category_slug) if prop.category_slug else None
        if cat_id is not None:
            session.add(EntityCategory(entity_id=ent.id, category_id=cat_id, is_primary=True))

    for fixture in plan.quarantine:
        ent = session.get(Entity, fixture.id)
        if ent is not None:
            ent.is_active = False

    session.commit()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_report(plan: Plan, *, applied: bool) -> str:
    lines: list[str] = []
    head = "APPLIED" if applied else "DRY-RUN (no changes written)"
    lines.append(f"=== Schedule-hunt entity import — {head} ===")
    lines.append("")
    lines.append("Counts:")
    lines.append(f"  New entities to create : {len(plan.new)}")
    lines.append(f"  Already in DB (skipped): {len(plan.existing_matches)}")
    lines.append(f"  Quarantine (test rows) : {len(plan.quarantine)}")
    lines.append(f"  Keep & fix (shadows)   : {len(plan.keep_fix)}")
    lines.append("")

    lines.append(f"--- NEW ENTITIES ({len(plan.new)}) ---")
    lines.append(f"{'name':<40} {'category':<20} {'address'}")
    for p in plan.new:
        lines.append(
            f"{p.venue.name[:39]:<40} {(p.category_slug or '(uncategorized)'):<20} "
            f"{p.venue.address[:40]}"
        )
    lines.append("")

    lines.append(f"--- QUARANTINE: test fixtures to deactivate ({len(plan.quarantine)}) ---")
    lines.append(f"{'id':<38} {'name':<40} source")
    for e in plan.quarantine:
        lines.append(f"{e.id:<38} {e.name[:39]:<40} {e.source}")
    lines.append("")

    lines.append(
        f"--- KEEP & FIX: fixtures shadowing a real CSV business ({len(plan.keep_fix)}) ---"
    )
    lines.append(f"{'fixture name':<40} {'shadows CSV venue':<40} source")
    for e, shadow in plan.keep_fix:
        lines.append(f"{e.name[:39]:<40} {shadow[:39]:<40} {e.source}")
    lines.append("")

    lines.append(f"--- ALREADY IN DB ({len(plan.existing_matches)}) ---")
    for csv_name, db_name in plan.existing_matches:
        suffix = "" if normalize_name(csv_name) == normalize_name(db_name) else f"  (~ {db_name})"
        lines.append(f"  {csv_name}{suffix}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=_DEFAULT_CSV, help="candidate CSV path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="WRITE the proposed changes (prod-data op — get approval first). "
        "Without this flag the script is a dry-run.",
    )
    args = parser.parse_args(argv)

    venues = load_csv(args.csv)
    session = SessionLocal()
    try:
        existing = load_existing(session)
        plan = build_plan(venues, existing)
        if args.apply:
            apply_plan(session, plan)
        print(render_report(plan, applied=args.apply))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
