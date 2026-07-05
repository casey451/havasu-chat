"""Filter and load enriched Google Places rows into the providers table.

Phase 5 of the LHC business pull. Reads
scripts/output/places_pull/enrichment_enriched.jsonl, optionally narrows to
one Tier-1 category via ``--category`` (the enrichment file may carry rows
from several domains' scrapes), filters by LHC ZIP codes per the locked list
(86403/86404/86405/86406), and upserts each survivor into the providers table.

Upsert key: `google_place_id`. Matches existing rows by Place ID and
UPDATEs them; inserts new rows otherwise. Stamps `last_google_scraped_at`
on every write.

Idempotent — re-running on the same input produces the same DB state.

Usage:
    python -m scripts.places_load --dry-run                      # parse + filter only, no DB writes
    python -m scripts.places_load --category eat-drink --dry-run # preview one Tier-1 slice
    python -m scripts.places_load --category eat-drink           # load one Tier-1 slice
    python -m scripts.places_load                                # filter + load every domain

Environment:
    Uses whatever DB the app is configured against (DATABASE_URL or local
    SQLite). Run `alembic upgrade head` first if you haven't already.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.google_places_scraper import (  # noqa: E402
    DISCOVERY_CATEGORY_TO_DOMAINS,
    enrichment_row_to_entity_payload,
)
from app.contrib.google_types_mapping import (  # noqa: E402
    map_google_types_to_slug_and_place_type,
)
from app.contrib.hours_helper import places_hours_to_structured  # noqa: E402
from app.contrib.ingest_reconciler import (  # noqa: E402
    log_ambiguous_reconcile,
    reconcile_hit,
)
from app.contrib.ingest_suppression import is_suppressed_business  # noqa: E402
from app.contrib.leaf_type_mapping import (  # noqa: E402
    map_google_types_to_leaf_slug,
)
from app.contrib.name_leaf_rules import leaf_for_name  # noqa: E402
from app.contrib.scraper_ingest import decide_ingest  # noqa: E402
from app.core.liveness import compute_liveness  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.entity_dual_write import (  # noqa: E402
    create_provider_and_entity,
    sync_provider_entity_from_legacy,
)
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402
from app.db.seed_helpers import derive_provider_slug  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PATH = Path(__file__).parent / "output" / "places_pull" / "enrichment_enriched.jsonl"
LHC_ZIPS = {"86403", "86404", "86405", "86406"}
ENRICHMENT_VERSION = "places_api_new_2026-05-06"


def load_enriched(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def filter_by_category(rows: list[dict[str, Any]], category_slug: str) -> list[dict[str, Any]]:
    """Keep only rows whose discovery domain maps to the given Tier-1 slug.

    Mirrors ``places_discovery``'s ``--category`` behaviour: the slug is
    resolved through ``DISCOVERY_CATEGORY_TO_DOMAINS`` to one or more
    ``_first_seen_domain`` values, and rows outside those domains are dropped.
    This keeps a per-category load scoped to its category even when
    ``enrichment_enriched.jsonl`` carries rows from other domains' scrapes.
    """
    domains = DISCOVERY_CATEGORY_TO_DOMAINS.get(category_slug)
    if domains is None:
        known = ", ".join(sorted(DISCOVERY_CATEGORY_TO_DOMAINS))
        raise SystemExit(f"Unknown --category {category_slug!r}. Expected one of: {known}")
    return [r for r in rows if r.get("_first_seen_domain", "") in domains]


def filter_by_zip(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep only rows in LHC ZIPs. Return (kept, drop_reason_counts).

    Normalizes ZIP+4 codes (with or without the standard dash) to the
    5-digit prefix before comparison. Google Places API occasionally
    returns ZIP+4 with the dash stripped — e.g. ``864035889`` for
    ``86403-5889`` — and the bare-string match would otherwise
    misclassify those LHC addresses as non-LHC. Phase 5.4 dispatch
    surfaced this with 3 real LHC health-wellness-care rows being
    dropped at load time.
    """
    kept: list[dict[str, Any]] = []
    drops: Counter[str] = Counter()
    for row in rows:
        zip_code = row.get("zip")
        if zip_code is None:
            drops["no_zip"] += 1
            continue
        # Normalize ZIP+4 (with or without dash) to 5-digit prefix.
        zip5 = str(zip_code).replace("-", "")[:5]
        if zip5 in LHC_ZIPS:
            kept.append(row)
        else:
            drops[f"non_lhc:{zip_code}"] += 1
    return kept, dict(drops)


def _local_photo_urls(raw_urls: Any) -> list[str] | None:
    """Accept only already-self-hosted local static paths.

    ``places_load`` must stay fully offline from Google APIs; photo URL resolution
    happens in the one-time photo backfill, not during category loads.
    """
    if not isinstance(raw_urls, list):
        return None
    kept: list[str] = []
    for candidate in raw_urls:
        if not isinstance(candidate, str):
            continue
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if cleaned.startswith("/static/"):
            kept.append(cleaned)
    return kept or None


def _parse_google_publish_time(value: Any) -> datetime | None:
    """Parse a Google review ``publishTime`` into a UTC-aware datetime.

    Google emits RFC-3339 with a trailing ``Z`` and up to **9** fractional-second
    digits (e.g. ``2026-02-22T03:04:41.102809936Z``). ``datetime.fromisoformat``
    accepts at most 6, so truncate the fraction to microseconds first. Returns
    ``None`` for missing / unparseable values.
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Keep the first 6 fractional digits; drop any extra (Google's 7–9).
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _newest_review_at(row: dict[str, Any]) -> datetime | None:
    """Max ``publish_time`` across the row's ``review_snippets`` (or None)."""
    times: list[datetime] = []
    for snippet in row.get("review_snippets") or []:
        if not isinstance(snippet, dict):
            continue
        dt = _parse_google_publish_time(snippet.get("publish_time"))
        if dt is not None:
            times.append(dt)
    return max(times) if times else None


def row_to_provider_kwargs(row: dict[str, Any], *, ref_now: datetime | None = None) -> dict[str, Any]:
    """Map an enriched row to the kwargs for Provider construction.

    `category` is NOT NULL on the providers table. Use the domain label
    from the discovery sweep (e.g. food_drink, lake_recreation) as a
    coarse-grained value; finer Google taxonomy lives in
    google_primary_category and google_categories.

    ``newest_review_at`` (max review publishTime) and ``liveness_score`` (the
    0–1 staleness blend, computed against ``ref_now``) are populated here so the
    rank dampener can bury stale listings. ``ref_now`` defaults to now(UTC).
    """
    domain = row.get("_first_seen_domain") or "uncategorized"
    ref_now = ref_now or datetime.now(UTC)
    newest_review_at = _newest_review_at(row)
    liveness_score = compute_liveness(
        row.get("rating"), row.get("review_count"), newest_review_at, ref_now
    )
    return {
        "provider_name": row["display_name"],
        "category": domain,
        "address": row.get("formatted_address"),
        "phone": row.get("phone"),
        "website": row.get("website"),
        "google_place_id": row["place_id"],
        "google_primary_category": row.get("primary_type"),
        "google_categories": row.get("types") or None,
        "google_rating": row.get("rating"),
        "google_review_count": row.get("review_count"),
        "google_review_snippets": row.get("review_snippets") or None,
        "google_photo_refs": row.get("photo_refs") or None,
        "google_photo_urls": _local_photo_urls(row.get("photo_urls")),
        "google_hours": row.get("regular_opening_hours") or None,
        # Also populate the structured column so future loads keep the
        # ``hours_structured`` / ``Hours`` table consistent with ``google_hours``
        # (the dual-write materializes ``Hours`` rows from it). NULL when Google
        # returned no parseable hours.
        "hours_structured": places_hours_to_structured(row.get("regular_opening_hours") or {}) or None,
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "zip": row.get("zip"),
        "newest_review_at": newest_review_at,
        "liveness_score": liveness_score,
        "source": "google_places",
        "enrichment_version": ENRICHMENT_VERSION,
        "is_active": True,
        "verified": False,
        "draft": False,
        "pending_review": False,
        "tier": "free",
    }


# Sustainability layer post-Phase-5.2 audit (commit chain ending at 452c44e).
# The Phase 5.2 §1 Layer 1 load surfaced two recurring routing gaps that the
# pure types-map fix at efd193a didn't close:
#
#   (1) Google tags many Havasu boat businesses with vehicle types
#       (``car_dealer``, ``car_rental``, ``car_repair``, ``car_wash``)
#       because its taxonomy doesn't distinguish boats from cars well in
#       sparse markets. Without intervention, every future scrape would
#       re-route ~30+ boat businesses to ``auto-rv-fuel`` and require
#       operator audit + apply_phase5_2_on_the_water_audit.py re-run.
#
#   (2) ~71 lake_recreation rows had primary_type in {``service``,
#       ``tour_agency``, ``tourist_attraction``, ``point_of_interest``,
#       ``<none>``} which the narrow types-map left as ``category_id=None``.
#       apply_on_the_water_promote_unmapped.py promoted them once today;
#       future scrapes would re-create the same operator-queue pile.
#
# Two enhancements below close both gaps automatically on every load:
#
#   (A) Name override — when discovered via lake_recreation, vehicle-typed
#       rows whose name contains a boat keyword route to on-the-water.
#       Runs BEFORE the types-map so it can override car_dealer etc.
#
#   (B) Discovery-domain fallback — for known (primary_type, domain) pairs
#       (or (None, domain) when primary_type is missing), use the domain's
#       Tier-1 mapping when types[] doesn't resolve. Runs AFTER the
#       types-map so it doesn't override explicit type matches.
#
# Both layers are deliberately conservative: only fire for lake_recreation
# domain in Phase 5.2 scope. Phase 5.3 (home_services) and beyond extend
# the tables as their audits surface similar gaps.

_VEHICLE_TYPES_THAT_MIGHT_BE_BOATS: frozenset[str] = frozenset(
    {
        "car_dealer",
        "car_rental",
        "car_repair",
        "car_wash",
    }
)

_BOAT_NAME_KEYWORDS: tuple[str, ...] = (
    "marine",
    "marina",
    "boat",
    "watersports",
    "yacht",
    "kayak",
    "fishing",
)

# (primary_type, discovery_domain) -> Tier-1 slug. ``None`` matches rows
# without a Google primary_type (10 in the Phase 5.2 load).
_DISCOVERY_DOMAIN_FALLBACK: dict[tuple[str | None, str], str] = {
    # lake_recreation -> on-the-water (catches the catch-all primary types
    # for Havasu boat businesses per Phase 5.2 §1 Layer 1 + audit findings).
    (None, "lake_recreation"): "on-the-water",
    ("service", "lake_recreation"): "on-the-water",
    ("tour_agency", "lake_recreation"): "on-the-water",
    ("tourist_attraction", "lake_recreation"): "on-the-water",
    ("tourist_information_center", "lake_recreation"): "on-the-water",
    ("point_of_interest", "lake_recreation"): "on-the-water",
    ("supplier", "lake_recreation"): "on-the-water",
    ("sporting_goods_store", "lake_recreation"): "on-the-water",
    ("adventure_sports_center", "lake_recreation"): "on-the-water",
    # home_services -> home-property-services (catches the catch-all primary
    # types for Havasu trades per Phase 5.3 §1 Layer 1 findings: 282 input
    # rows, 70 landed at category_id=None with primary_type in {``service``
    # ×49, ``laundry`` ×3, ``consultant`` ×1, ``None`` ×1}. Adding these four
    # entries catches the same shape automatically on every future load —
    # no apply-script needed).
    (None, "home_services"): "home-property-services",
    ("consultant", "home_services"): "home-property-services",
    ("laundry", "home_services"): "home-property-services",
    ("service", "home_services"): "home-property-services",
    # health_medical -> health-wellness-care (catches the catch-all primary
    # types for Havasu medical/wellness venues per Phase 5.4 §1 Layer 1
    # findings: 282 input rows inserted, 111 landed at category_id=None.
    # Dominant: ``health`` ×47 (Google's generic medical catch-all) and
    # ``medical_clinic`` ×36 (surprisingly not in google_types_mapping.py),
    # plus a long tail of spa/wellness_center/non_profit/dental_clinic/
    # skin_care_clinic/apartment_building (the last is senior-living
    # facilities Google tags as residential). NOTE: ``medical_clinic`` and
    # ``dental_clinic`` arguably belong in google_types_mapping.py directly
    # — left in the fallback for the 5.3 surgical-fix shape; types-map
    # widening flagged as a soft-edge in outputs/phase5_4_*).
    (None, "health_medical"): "health-wellness-care",
    ("health", "health_medical"): "health-wellness-care",
    ("medical_clinic", "health_medical"): "health-wellness-care",
    ("dental_clinic", "health_medical"): "health-wellness-care",
    ("skin_care_clinic", "health_medical"): "health-wellness-care",
    ("wellness_center", "health_medical"): "health-wellness-care",
    ("spa", "health_medical"): "health-wellness-care",
    ("non_profit_organization", "health_medical"): "health-wellness-care",
    ("apartment_building", "health_medical"): "health-wellness-care",
    ("service", "health_medical"): "health-wellness-care",
    ("point_of_interest", "health_medical"): "health-wellness-care",
    # fitness_sports -> health-wellness-care (catches sports schools,
    # athletic fields, courts, and generic catch-alls that surfaced under
    # fitness label searches in Phase 5.4 §1).
    (None, "fitness_sports"): "health-wellness-care",
    ("sports_school", "fitness_sports"): "health-wellness-care",
    ("health", "fitness_sports"): "health-wellness-care",
    ("tennis_court", "fitness_sports"): "health-wellness-care",
    ("athletic_field", "fitness_sports"): "health-wellness-care",
    ("consultant", "fitness_sports"): "health-wellness-care",
    ("point_of_interest", "fitness_sports"): "health-wellness-care",
    # auto -> auto-rv-fuel (catches catch-all primary types for Havasu
    # auto/RV/fuel businesses per Phase 5.5 §1 Layer 1 findings: 179 input
    # rows, 18 landed at category_id=None with primary_type distribution
    # ``None`` ×5 (auto glass + mobile detailers Google tags without a
    # specific primary), ``service`` ×3 (towing operators), ``car_rental``
    # ×2 (Avis + Budget), plus ``point_of_interest`` and ``store`` as
    # safety nets per the 5.5 kickoff §1 anticipation. NOTE: ``car_rental``
    # arguably belongs in google_types_mapping.py directly — left in the
    # fallback for the surgical-fix shape, mirroring 5.4's medical_clinic
    # decision).
    (None, "auto"): "auto-rv-fuel",
    ("service", "auto"): "auto-rv-fuel",
    ("car_rental", "auto"): "auto-rv-fuel",
    ("point_of_interest", "auto"): "auto-rv-fuel",
    ("store", "auto"): "auto-rv-fuel",
    # retail -> shopping-essentials (catches catch-all primary types for
    # Havasu retail businesses per Phase 5.6 §1 Layer 1 findings: 268 input
    # rows, 21 landed at category_id=None; 10 visible as Providers with NULL
    # category_id {``service`` ×3 (IT/electronics service shops — Havasu
    # Technologies, Vertical IT, Whiz Kid Computer Services), ``None`` ×1
    # (Havasu Computers)}. 6 edge cases intentionally LEFT in operator queue
    # for per-row review: ``corporate_office`` ×1 (wholesale beverage
    # distributor — B2B), ``manufacturer`` ×1 (B2B electronics assembly),
    # ``garden`` ×1 (community garden — not retail), ``farm`` ×1 (Serrano's
    # Nursery — IS retail but ``farm`` type also covers actual farms),
    # ``health`` ×1 (hospice — wrong category), ``community_center`` ×1
    # (Clothes Closet thrift). The other 11 operator-queue rows are inside
    # the 181-row ambig-skip pool. ``store`` is defensive (already in
    # google_types_mapping → shopping-essentials so this never fires unless
    # the mapping changes); ``shopping_mall`` covers The Shops at Lake
    # Havasu and similar.
    (None, "retail"): "shopping-essentials",
    ("service", "retail"): "shopping-essentials",
    ("supplier", "retail"): "shopping-essentials",
    ("point_of_interest", "retail"): "shopping-essentials",
    ("establishment", "retail"): "shopping-essentials",
    ("store", "retail"): "shopping-essentials",
    ("shopping_mall", "retail"): "shopping-essentials",
    # entertainment_attractions -> outdoors-parks-trails (catches catch-all
    # primary types for Havasu parks/golf businesses per Phase 5.7 §1
    # anticipation; Narrow scope = 3 labels (parks, golf courses, mini
    # golf), all from the entertainment_attractions domain — fitness_sports
    # labels deferred to V1.5 per kickoff §1 to avoid collision with the
    # existing ``(None, "fitness_sports") -> "health-wellness-care"``
    # fallback). The 6 pre-existing outdoors-parks-trails entries (Avalon
    # Park, Cattail Cove SP, Dick Samp Memorial, Lake Havasu SP, Rotary
    # Community Park, SARA Park) all sit as ``entity_type='commercial'``
    # because Google often primary-types state parks as
    # ``tourist_attraction`` rather than ``park`` — the
    # ``("tourist_attraction", "entertainment_attractions")`` entry catches
    # that pattern. ``amusement_park`` is the Google primary type for mini
    # golf venues. ``point_of_interest`` and ``establishment`` are the
    # generic safety nets seen across 5.3-5.6 fallback shapes. NOTE:
    # ``golf_course`` is added directly to
    # ``app/contrib/google_types_mapping._PRIMARY_TYPE_MAP`` in this same
    # commit so golf courses route correctly regardless of discovery
    # domain — the fallback here only fires for ambiguous fall-through
    # cases.
    (None, "entertainment_attractions"): "outdoors-parks-trails",
    ("tourist_attraction", "entertainment_attractions"): "outdoors-parks-trails",
    ("amusement_park", "entertainment_attractions"): "outdoors-parks-trails",
    ("point_of_interest", "entertainment_attractions"): "outdoors-parks-trails",
    ("establishment", "entertainment_attractions"): "outdoors-parks-trails",
    # childcare_education -> classes-sports-recreation (Phase 5.9 §1
    # sustainability). NEW domain — no prior phase populated the
    # childcare_education catch-all. Pairs with the 5 direct
    # ``_PRIMARY_TYPE_MAP`` entries shipped this commit for
    # child_care_agency / preschool / music_school / driving_school /
    # tutor (per kickoff §1 Option A); this fallback covers any
    # unmapped childcare_education primary_types that Google emits for
    # the 5 in-scope labels. The 4 cat-12-native fitness_sports
    # primary_types (personal_trainer + swimming_pool + tennis_court +
    # pickleball_court) route via direct ``_PRIMARY_TYPE_MAP`` entries
    # (which beat the existing 5.4 ``(None, "fitness_sports") ->
    # "health-wellness-care"`` catch-all per resolver order); the 7
    # HWC-absorbed fitness types (gym/yoga/pilates/crossfit/martial/
    # jiu_jitsu/dance) stay in HWC via that same 5.4 catch-all.
    (None, "childcare_education"): "classes-sports-recreation",
    # lodging -> lodging-vacation-rentals (Phase 5.10 §1 sustainability).
    # NEW catch-all — no prior phase populated the lodging domain in
    # the fallback. Pairs with the 5 direct ``_PRIMARY_TYPE_MAP``
    # entries shipped this commit for hotel / motel / resort_hotel /
    # extended_stay_hotel / bed_and_breakfast (per kickoff §1 Option
    # A); this fallback covers any unmapped lodging primary_types that
    # Google emits for the 5 in-scope labels (hotels, motels, resorts,
    # vacation rentals, bed and breakfast). The 5.10 §1 load surfaced
    # one such case: Vanderpump Rules Lake Havasu Luxury Villa
    # (primary=``service``, _first_seen_domain=``lodging``, types[]
    # without the ``lodging`` secondary that would otherwise catch it
    # via the existing ``"lodging": ("lodging-vacation-rentals",
    # "commercial")`` direct mapping in google_types_mapping.py:134).
    # The new catch-all routes that edge case + any future similar
    # cases to cat-10 instead of operator queue.
    #
    # The 5.2 ``(None, "lake_recreation") -> "on-the-water"`` catch-all
    # stays in place for the lake_recreation domain (the OTHER half of
    # the lodging-vacation-rentals two-domain bundle); RV parks already
    # in cat-10 via the pre-Phase-5 ``rv_park`` direct mapping in
    # _PRIMARY_TYPE_MAP, campgrounds + mobile_home_park + camping_cabin
    # also already in cat-10 via the secondary-types[] first-match on
    # the existing ``lodging`` direct mapping. The 11 (of 24)
    # lake_recreation labels deferred to V1.5 per kickoff §1 Narrow
    # scope: marina/boat shape already absorbed by 5.2; campgrounds +
    # RV dealers/rentals re-evaluable per-label in V1.5.
    (None, "lodging"): "lodging-vacation-rentals",
    # pets -> pets (Phase 5.11 -- 1 sustainability). NEW catch-all --
    # no prior phase populated the pets domain in the fallback. Pairs
    # with the 4 direct ``_PRIMARY_TYPE_MAP`` entries shipped this
    # commit for pet_care / dog_groomer / pet_boarding / dog_trainer
    # (per kickoff 1 Option A); this fallback covers any unmapped
    # pets-domain primary_types Google emits for the 4 in-scope
    # labels (pet stores / dog groomers / dog boarding / dog
    # trainers). The 5.11 1 load surfaced 3 such cases: 3 entities
    # with primary=``service`` (Google's generic catch-all type)
    # discovered under the pets domain -- same shape as 5.10's
    # Vanderpump villa case where primary=``service`` discovered
    # under the lodging domain got routed by the new ``(None,
    # "lodging") -> "lodging-vacation-rentals"`` catch-all. The 4
    # ``pet_care``-primary entries from the same load are caught by
    # the direct ``pet_care`` mapping above (which beats the catch-
    # all per resolver order); this fallback documents intent for the
    # ``service`` shape + provides future-proofing for any other
    # unmapped pets primary_types Google emits.
    #
    # No prior phase populated the pets domain in _PRIMARY_TYPE_MAP
    # either, beyond the pre-Phase-5 ``veterinary_care`` +
    # ``pet_store`` direct mappings (which cover vets + pet retail).
    # The 5.4 ``medical_clinic`` direct mapping in
    # google_types_mapping.py routes vet clinics with primary=
    # ``medical_clinic`` to cat-5 HWC (out of 5.11 scope by design);
    # the pre-Phase-5 ``dog_park`` direct mapping continues to route
    # dog parks to cat-7 outdoors-parks-trails. The 5.11 1 scrape
    # used 4 pets-domain labels (pet stores / dog groomers / dog
    # boarding / dog trainers) -- none of those labels would match
    # ``medical_clinic`` or ``dog_park`` primaries (different label
    # search surface), so no cross-cat collision.
    (None, "pets"): "pets",
    # Phase 5.8+ entries land here as their per-category audits surface gaps.
}


def _name_signals_boat(name: str) -> bool:
    """Lowercased substring check against ``_BOAT_NAME_KEYWORDS``."""
    n = name.lower()
    return any(kw in n for kw in _BOAT_NAME_KEYWORDS)


def _resolve_category_id(row: dict[str, Any], category_id_by_slug: dict[str, int]) -> int | None:
    """Resolve a Tier-1 ``Category.id`` for a Google Places enriched row.

    Three-layer resolution (in priority order):

      1. **Name override** — when discovered via ``lake_recreation`` and
         primary_type is vehicle-like (``car_dealer`` etc.) but the name
         contains a boat keyword, route to on-the-water. Catches Havasu
         boat dealers Google tags as ``car_dealer``.

      1.5 **Leaf-map** — ``map_google_types_to_leaf_slug`` (single source of
         truth, ``app/contrib/leaf_type_mapping.py``) routes a google type
         straight to an A.3 *leaf* so a fresh scrape lands on the correct leaf
         page. Its non-directory guardrail returns ``None`` for calendar-event
         venue types (``event_venue`` …) so they never hit a directory leaf.

      2. **Types-map** (legacy fallback) — ``map_google_types_to_slug_
         and_place_type`` consults the operator-maintained
         ``app/contrib/google_types_mapping.py`` table.

      3. **Discovery-domain fallback** — for ``(primary_type, domain)``
         pairs registered in ``_DISCOVERY_DOMAIN_FALLBACK``, use the
         domain's Tier-1 mapping. Catches catch-all primary_types
         (``service``, ``tour_agency``, etc.) that Google uses for
         specialty lake businesses.

    Returns ``None`` only when none of the three layers match — that's
    the operator-queue fallback per Phase 5 design.

    Without this resolution + a downstream ``EntityCategory`` row, entities
    do not appear at ``/category/<slug>`` (route filters strictly via
    ``EntityCategory`` join — see
    ``app/api/routes/category_pages.py:_select_entities_for_category``).
    """
    domain = row.get("_first_seen_domain") or ""
    primary_type = row.get("primary_type")
    name = row.get("display_name") or ""

    # Layer 1 — name override for vehicle-typed boat businesses.
    if (
        domain == "lake_recreation"
        and primary_type in _VEHICLE_TYPES_THAT_MIGHT_BE_BOATS
        and _name_signals_boat(name)
    ):
        cat_id = category_id_by_slug.get("on-the-water")
        if cat_id is not None:
            return cat_id

    # Layer 1a — name override for martial-arts / dance. Google has no precise
    # primary type for dojos or dance studios (they carry gym / school /
    # point_of_interest), so a confident NAME signal routes the leaf and must beat
    # the generic-type leaf map below — otherwise a dojo typed ``gym`` would file
    # under gyms-and-fitness-centers (the 2026-06-17 Phase 4 misfile class). The
    # matcher (``name_leaf_rules``) is conservative; an unmatched name falls
    # through untouched.
    name_leaf = leaf_for_name(name)
    if name_leaf is not None:
        cat_id = category_id_by_slug.get(name_leaf)
        if cat_id is not None:
            return cat_id

    types = row.get("types") or []
    if not types and primary_type:
        types = [primary_type]

    # Layer 1.5 — direct google-type -> A.3 leaf (app/contrib/leaf_type_mapping).
    # Preferred over the legacy 13-category map (Layer 2) so a fresh scrape
    # auto-files onto the correct *leaf* page, single-sourced and consistent.
    # The non-directory guardrail keeps calendar-event venue types
    # (``event_venue`` etc.) OFF every directory leaf — they belong to the
    # events feed (entity_type='event'). This is the fix for the 2026-06-11
    # ``event_venue`` -> Family Fun & Arcades misfile: returning ``None`` here
    # leaves the row unmapped (operator-queue) instead of dropping an annual
    # event onto an arcade leaf.
    leaf_slug, non_directory = map_google_types_to_leaf_slug(list(types))
    if non_directory:
        return None
    if leaf_slug is not None:
        cat_id = category_id_by_slug.get(leaf_slug)
        if cat_id is not None:
            return cat_id

    # Layer 2 — Google types[] -> Tier-1 slug (legacy fallback).
    slug, _ = map_google_types_to_slug_and_place_type(list(types))
    if slug is not None:
        return category_id_by_slug.get(slug)

    # Layer 3 — discovery-domain fallback for unmapped primary types.
    fallback_slug = _DISCOVERY_DOMAIN_FALLBACK.get((primary_type, domain))
    if fallback_slug is None:
        # Also accept (None, domain) for rows without any primary_type.
        fallback_slug = _DISCOVERY_DOMAIN_FALLBACK.get((None, domain))
    if fallback_slug is not None:
        return category_id_by_slug.get(fallback_slug)

    return None


def _ensure_entity_category(session: Any, entity_id: str, category_id: int | None) -> bool:
    """Idempotent EntityCategory upsert on the UPDATE branch.

    The Phase 1D dual-write hook only creates an ``EntityCategory`` on
    fresh ``Provider`` INSERT. The UPDATE branch (re-running the load
    after the fix landed; or matching an existing ``google_place_id``)
    needs to ensure the link exists when ``Provider.category_id`` is
    populated. Returns ``True`` if a new row was inserted.
    """
    if category_id is None:
        return False
    existing = session.scalars(
        select(EntityCategory).where(
            EntityCategory.entity_id == entity_id,
            EntityCategory.category_id == category_id,
        )
    ).first()
    if existing is not None:
        return False
    session.add(
        EntityCategory(
            entity_id=entity_id,
            category_id=category_id,
            is_primary=True,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    return True


def upsert(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Bulk upsert keyed on google_place_id.

    Strategy:
      1. Fetch all existing rows by google_place_id IN (...) — one query.
      2. UPDATE matched rows in place.
      3. INSERT the rest as new rows.
    Both branches stamp `last_google_scraped_at = now()` and
    `updated_at` (auto via onupdate).
    """
    skipped_no_name = 0
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("display_name"):
            skipped_no_name += 1
            continue
        if not row.get("place_id"):
            skipped_no_name += 1
            continue
        valid_rows.append(row)

    counts: dict[str, int] = {
        "input": len(rows),
        "skipped_no_name": skipped_no_name,
        "inserted": 0,
        "inserted_pending": 0,
        "updated": 0,
        "reconcile_skipped_ambiguous": 0,
        "reconcile_merged_geo": 0,
        "category_id_set": 0,
        "category_id_unmapped": 0,
        "entity_category_inserted": 0,
    }

    if not valid_rows:
        return counts

    place_ids = [row["place_id"] for row in valid_rows]
    now = datetime.now(UTC)

    with SessionLocal() as session:
        # One-shot Category lookup for the run — Tier-1 slug -> id table is
        # tiny + immutable during a load. Used by ``_resolve_category_id``
        # to translate Google ``types[]`` to ``Provider.category_id`` so
        # the dual-write hook (or ``_ensure_entity_category`` on UPDATE)
        # creates the EntityCategory link the ``/category/<slug>`` route
        # filters by. Pre-fix, all newly-loaded Providers landed with
        # ``category_id=None`` and never appeared at the route — surfaced
        # by the Phase 5.2 §0 + diagnose_category_id_gap.py finding.
        category_id_by_slug: dict[str, int] = {
            c.slug: c.id for c in session.scalars(select(Category)).all()
        }

        # Phase 1C: match upsert keys on legacy ``google_place_id`` or ENTITY
        # ``locations.google_place_id`` (backfilled Places rows).
        existing_by_pid: dict[str, Provider] = {}
        for p in session.query(Provider).filter(Provider.google_place_id.in_(place_ids)).all():
            if p.google_place_id:
                existing_by_pid[p.google_place_id] = p
        for p, loc_pid in (
            session.query(Provider, Location.google_place_id)
            .join(Entity, Provider.entity_id == Entity.id)
            .join(Location, Location.entity_id == Entity.id)
            .filter(Location.google_place_id.in_(place_ids))
            .all()
        ):
            existing_by_pid[loc_pid] = p

        for row in valid_rows:
            pid = row["place_id"]
            kwargs = row_to_provider_kwargs(row, ref_now=now)
            # Durable blocklist check covers BOTH branches: the place_id-match
            # update branch below sets is_active=True and never runs the
            # decide_ingest funnel, so without this a suppressed identity would
            # be reactivated by the next Places re-pull (the exact failure
            # ingest_suppression exists to stop).
            if is_suppressed_business(kwargs.get("provider_name")):
                counts["suppressed"] = counts.get("suppressed", 0) + 1
                continue
            cat_id = _resolve_category_id(row, category_id_by_slug)
            kwargs["category_id"] = cat_id
            if cat_id is not None:
                counts["category_id_set"] += 1
            else:
                counts["category_id_unmapped"] += 1
            if pid in existing_by_pid:
                provider = existing_by_pid[pid]
                # Preserve operator-set category_id on UPDATE so apply-
                # script decisions (audit re-routes, promote-unmapped)
                # survive future re-pulls. Only auto-set when the existing
                # row has no category — this keeps the resolver effective
                # for backfilling NULLs without clobbering curation.
                if provider.category_id is not None:
                    kwargs.pop("category_id", None)
                # cat_id used downstream for _ensure_entity_category — fall
                # back to provider's existing category for the link check
                # when we're preserving the operator's choice.
                effective_cat_id = (
                    provider.category_id if provider.category_id is not None else cat_id
                )
                payload = enrichment_row_to_entity_payload(row)
                rec = reconcile_hit(session, payload)
                log_ambiguous_reconcile(rec, context=f"places_load update branch place_id={pid}")
                for field, value in kwargs.items():
                    setattr(provider, field, value)
                provider.last_google_scraped_at = now
                sync_provider_entity_from_legacy(session, provider)
                if _ensure_entity_category(session, provider.entity_id, effective_cat_id):
                    counts["entity_category_inserted"] += 1
                if rec.action == "update" and rec.merge_fields:
                    ent = session.get(Entity, provider.entity_id)
                    if ent is not None:
                        if "name" in rec.merge_fields:
                            ent.name = str(rec.merge_fields["name"])[:255]
                        if "description" in rec.merge_fields:
                            ent.description = rec.merge_fields["description"]
                        if "source" in rec.merge_fields:
                            ent.source = str(rec.merge_fields["source"])[:64]
                counts["updated"] += 1
            else:
                payload = enrichment_row_to_entity_payload(row)
                # Funnel: normalize + reconcile + hide-on-doubt via decide_ingest.
                # ``should_hide`` (ambiguous) now lands the row HELD (draft +
                # pending_review) for admin review instead of dropping it, so an
                # uncertain Google row is captured rather than silently lost.
                decision = decide_ingest(session, payload)
                rec = decision.reconcile
                if decision.action == "skip":
                    counts["suppressed"] = counts.get("suppressed", 0) + 1
                    continue
                if decision.should_hide:
                    log_ambiguous_reconcile(
                        rec, context=f"places_load insert branch place_id={pid}"
                    )
                    pend = dict(kwargs)
                    pend["draft"] = True
                    pend["pending_review"] = True
                    slug = derive_provider_slug(session, pend["provider_name"])
                    provider = Provider(**pend, slug=slug, last_google_scraped_at=now)
                    session.add(provider)
                    create_provider_and_entity(session, provider)
                    if cat_id is not None:
                        counts["entity_category_inserted"] += 1
                    counts["inserted_pending"] += 1
                    continue
                if rec.action == "update" and rec.existing_id:
                    prov = session.scalars(
                        select(Provider).where(Provider.entity_id == rec.existing_id).limit(1)
                    ).first()
                    if prov is None:
                        logger.warning(
                            "places_load reconcile update without provider row entity_id=%s",
                            rec.existing_id,
                        )
                        counts["reconcile_skipped_ambiguous"] += 1
                        continue
                    for field, value in kwargs.items():
                        setattr(prov, field, value)
                    prov.last_google_scraped_at = now
                    sync_provider_entity_from_legacy(session, prov)
                    if _ensure_entity_category(session, rec.existing_id, cat_id):
                        counts["entity_category_inserted"] += 1
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
                provider = Provider(**kwargs, slug=slug, last_google_scraped_at=now)
                session.add(provider)
                create_provider_and_entity(session, provider)
                # Dual-write hook auto-inserts EntityCategory when
                # ``provider.category_id is not None``; count it here for
                # the load summary.
                if cat_id is not None:
                    counts["entity_category_inserted"] += 1
                counts["inserted"] += 1

        session.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument(
        "--category",
        default=None,
        metavar="SLUG",
        help="Tier-1 taxonomy slug (e.g. eat-drink). Filters enriched rows by "
        "their discovery domain (via DISCOVERY_CATEGORY_TO_DOMAINS) before the "
        "ZIP filter. Omit to load every domain in the enrichment file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + filter only. No DB writes.",
    )
    args = parser.parse_args()

    rows = load_enriched(args.input)
    print(f"[load] enriched rows: {len(rows)}")

    if args.category:
        rows = filter_by_category(rows, args.category)
        print(f"[load] after --category {args.category} filter: {len(rows)} rows")

    kept, drops = filter_by_zip(rows)
    print(f"[load] after ZIP filter: {len(kept)} kept, {sum(drops.values())} dropped")

    if drops:
        print("[load] drop reason breakdown:")
        no_zip = drops.pop("no_zip", 0)
        if no_zip:
            print(f"    no_zip: {no_zip}")
        # Group spillover ZIPs together for readability.
        sorted_drops = sorted(drops.items(), key=lambda kv: -kv[1])
        for reason, count in sorted_drops[:20]:
            print(f"    {reason}: {count}")
        if len(sorted_drops) > 20:
            other = sum(c for _, c in sorted_drops[20:])
            print(f"    other ({len(sorted_drops) - 20} more reasons): {other}")

    if args.dry_run:
        print("[load] dry-run complete; no DB writes")
        return 0

    counts = upsert(kept)
    print()
    print("--- load summary ---")
    print(f"input rows:         {counts['input']}")
    print(f"skipped (no name):  {counts['skipped_no_name']}")
    print(f"inserted (new):     {counts['inserted']}")
    print(f"updated (existing): {counts['updated']}")
    print(f"reconcile skipped (ambiguous): {counts['reconcile_skipped_ambiguous']}")
    print(f"reconcile merged (geo):        {counts['reconcile_merged_geo']}")
    print(f"category_id resolved (Tier 1): {counts['category_id_set']}")
    print(f"category_id unmapped (operator queue): {counts['category_id_unmapped']}")
    print(f"EntityCategory rows inserted:  {counts['entity_category_inserted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
