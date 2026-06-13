"""
Load golakehavasu.com partner directory listings into providers + ENTITY graph,
via the cross-source ingest reconciler.

Mirrors :mod:`scripts.osm_overpass_load`: each listing becomes an
:class:`~app.contrib.ingest_base.EntityPayload` with ``source="go_lake_havasu"``,
then :func:`~app.contrib.ingest_reconciler.reconcile_hit` decides insert vs
merge. A partner that already exists as a Google Places provider updates the
existing row (CVB fills gaps; Google identity wins); a genuinely new attraction
is inserted.

When reconcile_hit returns ``ambiguous`` (a nearby provider exists but the
normalized names differ -- common for CVB title vs Google Places name), a
fuzzy-name-at-geo tier (:func:`_fuzzy_geo_match`) attempts a confident merge
onto a single Google-backed row within 50m whose ``rapidfuzz`` token_sort_ratio
clears ``--fuzzy-threshold``. Only a unique high-score match promotes; anything
else is held for human review (draft + pending_review).

The ``--reconcile-pending`` mode re-runs that fuzzy match over rows previously
held pending and merges/retires the ones that now have a confident Google match.

Usage:
    python -m scripts.golakehavasu_partners_load --dry-run
    python -m scripts.golakehavasu_partners_load --limit 25 --category-slug things-to-do
    python -m scripts.golakehavasu_partners_load --fuzzy-threshold 88
    python -m scripts.golakehavasu_partners_load --reconcile-pending --dry-run --limit 25
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from rapidfuzz import fuzz
from sqlalchemy import or_, select

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
    GEO_PROXIMITY_THRESHOLD_M,
    ReconcileResult,
    _combine_sources,
    _compute_merge_fields,
    haversine_m,
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

# rapidfuzz token_sort_ratio floor (0-100) for promoting an ``ambiguous``
# geo-near reconcile into a confident merge onto a Google-backed row. CVB
# partner titles and Google Places names diverge often enough that an EXACT
# normalized-name match (what ingest_reconciler.reconcile_hit requires) misses
# real overlaps; a high fuzzy floor at <=50m recovers them without merging
# distinct neighbours. Tune via --fuzzy-threshold.
FUZZY_NAME_THRESHOLD = 88


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


def _norm_phone(phone: str | None) -> str | None:
    """Normalize a phone to its last 10 digits for exact-match comparison.

    Strips non-digits and a leading US country code so ``(702) 787-9568`` and
    ``+1 702-787-9568`` compare equal. Returns ``None`` if fewer than 10 digits
    remain (too little to be a confident identity key).
    """
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else None


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
    legacy = payload.legacy_category or "uncategorized"
    return {
        "provider_name": payload.name,
        "category": legacy,
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


def _fuzzy_geo_match(
    session: Any,
    payload: EntityPayload,
    *,
    threshold: float,
    max_distance_m: float = GEO_PROXIMITY_THRESHOLD_M,
) -> str | None:
    """Confident fuzzy-name merge target for a geo-near CVB payload.

    Called only when :func:`reconcile_hit` returned ``ambiguous`` (it found a
    nearby provider but the normalized names did not match exactly). Restrict
    candidates to GOOGLE-backed locations (``google_place_id`` set) within
    ``max_distance_m`` and score ``fuzz.token_sort_ratio`` on raw lowercased
    names. Return the entity_id only when EXACTLY ONE distinct Google entity
    clears ``threshold`` -- otherwise ``None`` so the caller keeps it pending.
    This mirrors reconcile_hit's "multiple matches -> ambiguous" conservatism.
    """
    from app.db.models import Entity, Location

    if payload.lat is None or payload.lng is None or not (payload.name or "").strip():
        return None

    target = payload.name.strip().lower()
    candidates = (
        session.query(Location)
        .filter(
            Location.lat.isnot(None),
            Location.lng.isnot(None),
            Location.google_place_id.isnot(None),
        )
        .all()
    )
    best_by_entity: dict[str, float] = {}
    for cand in candidates:
        if haversine_m(payload.lat, payload.lng, cand.lat, cand.lng) > max_distance_m:
            continue
        ent = session.get(Entity, cand.entity_id)
        if not ent or not (ent.name or "").strip():
            continue
        score = float(fuzz.token_sort_ratio(target, ent.name.strip().lower()))
        if score >= threshold:
            prev = best_by_entity.get(cand.entity_id, 0.0)
            if score > prev:
                best_by_entity[cand.entity_id] = score
    if len(best_by_entity) == 1:
        return next(iter(best_by_entity))
    return None


def _contact_match(session: Any, payload: EntityPayload) -> str | None:
    """Highest-precision merge tier: exact website or phone to a Google row.

    Runs BEFORE the fuzzy tier and needs no geo -- a shared website/phone is a
    stronger identity signal than the name. Candidates are GOOGLE-backed entities
    (a Location with ``google_place_id``). Returns the entity_id only when
    EXACTLY ONE distinct Google entity matches on normalized website or phone --
    otherwise ``None`` (stay pending), mirroring the geo/fuzzy tiers.
    """
    from app.db.models import Location
    from app.db.models import Provider as _Provider

    web = _norm_web(payload.website)
    phone = _norm_phone(payload.phone)
    if not web and not phone:
        return None
    google_ids = {
        loc.entity_id
        for loc in session.query(Location).filter(Location.google_place_id.isnot(None)).all()
    }
    if not google_ids:
        return None
    matches: set[str] = set()
    for prov in session.query(_Provider).filter(_Provider.entity_id.in_(google_ids)).all():
        if not prov.entity_id:
            continue
        if web and _norm_web(prov.website) == web:
            matches.add(prov.entity_id)
        elif phone and _norm_phone(prov.phone) == phone:
            matches.add(prov.entity_id)
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _provider_to_payload(prov: Provider) -> EntityPayload:
    """Rebuild a source-agnostic payload from a stored CVB provider row.

    Used by the --reconcile-pending cleanup pass to re-run matching against the
    current entity graph for rows that were previously held pending.
    """
    return EntityPayload(
        name=prov.provider_name or "",
        entity_type="place",
        source="go_lake_havasu",
        lat=prov.lat,
        lng=prov.lng,
        address=prov.address,
        phone=prov.phone,
        website=prov.website,
        description=prov.description,
        category_slug=prov.category or "things-to-do",
        google_place_id=None,
    )


def ingest_partners(
    *,
    category_slug: str,
    dry_run: bool,
    limit: int | None,
    fuzzy_threshold: float = FUZZY_NAME_THRESHOLD,
    http_client: httpx.Client | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "urls": 0,
        "parsed": 0,
        "skipped_unnamed": 0,
        "inserted": 0,
        "inserted_pending": 0,
        "updated": 0,
        "updated_fuzzy": 0,
        "updated_contact": 0,
        "idempotent_updated": 0,
        "reactivated": 0,
        "skipped_reactivate_live_twin": 0,
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
            # Per-slug Category.id cache (categories are per-listing now, Task C).
            _cat_id_cache: dict[str, int | None] = {}

            def _cat_id_for(slug: str | None) -> int | None:
                if not slug:
                    return None
                if slug not in _cat_id_cache:
                    _cat_id_cache[slug] = session.scalars(
                        select(Category.id).where(Category.slug == slug)
                    ).first()
                return _cat_id_cache[slug]

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

            # Live-catalog index (ALL sources, active + non-draft) keyed by the
            # same identity signals the CVB snapshot uses. Consulted only when a
            # CVB listing matches an idempotency row that is itself hidden
            # (inactive or draft): if some OTHER live row -- typically the
            # business's Google Places listing -- already represents it, we must
            # NOT reactivate the hidden CVB row, or we mint a visible duplicate.
            # Built once; the reactivate path keeps it consistent by only
            # surfacing rows that have no live twin here (see the heal block).
            live_name_idx: set[str] = set()
            live_web_idx: set[str] = set()
            for prov in session.scalars(
                select(Provider).where(
                    Provider.is_active.is_(True), Provider.draft.is_(False)
                )
            ).all():
                s = slugify(prov.provider_name or "")
                if s:
                    live_name_idx.add(s)
                w = _norm_web(prov.website)
                if w:
                    live_web_idx.add(w)

            def _register_cvb(prov: Provider) -> None:
                """Register a freshly-inserted CVB row into the in-batch
                idempotency snapshot.

                The snapshot above is built ONCE before the loop. The CVB
                sitemap lists some businesses under multiple partner URLs (e.g.
                the wildlife refuge, WACKO), so without this a later payload for
                the SAME listing in the same run would not see the row just
                inserted and would insert a second copy -- and geo can't catch
                it because both carry the visitor-center coords (0.0m apart).
                Registering here routes the later identical payload into the
                idempotent-update branch instead. Mirrors the pre-loop snapshot
                keys exactly (name slug + normalized website).
                """
                cvb_by_name.setdefault(slugify(prov.provider_name or ""), []).append(prov)
                w = _norm_web(prov.website)
                if w:
                    cvb_by_web.setdefault(w, prov)

            for payload in payloads:
                # Per-listing category (Task C): payload.category_slug carries the
                # CVB->Hava mapped slug, or the --category-slug default when the
                # CVB category had no confident mapping.
                row_slug = payload.category_slug or category_slug
                row_cat_id = _cat_id_for(row_slug)
                kwargs = _provider_kwargs(payload, category_slug=row_slug, category_id=row_cat_id)

                # CVB-to-CVB idempotency: already ingested this listing?
                name_slug = slugify(payload.name)
                web_key = _norm_web(payload.website)
                cvb_matches = list(cvb_by_name.get(name_slug) or [])
                if not cvb_matches and web_key and web_key in cvb_by_web:
                    cvb_matches = [cvb_by_web[web_key]]
                if cvb_matches:
                    canonical = _pick_canonical(cvb_matches)
                    _fill_gaps(canonical, kwargs)
                    # CVB owns these rows: re-bucket category in place on re-run
                    # when a confident per-listing mapping exists.
                    if payload.category_slug:
                        canonical.category = payload.legacy_category or "uncategorized"
                        canonical.category_id = row_cat_id
                    sync_provider_entity_from_legacy(session, canonical)
                    for other in cvb_matches:
                        if other is not canonical and other.is_active:
                            other.is_active = False
                            counts["retired_duplicates"] += 1
                    # Heal a hidden survivor. A partner still present in today's
                    # partnerDirectory sitemap is, by that presence, one the CVB
                    # still actively lists -- so if the surviving canonical is
                    # inactive or held as draft/pending, SURFACE it. Without this
                    # the loader silently routes the listing here ("idempotent")
                    # and leaves it invisible forever (the Cabana Boat Rentals
                    # no-op). Guard: skip when a live twin already represents the
                    # business (e.g. a Google Places row) so we never create a
                    # visible duplicate; merging CVB enrichment onto that twin is
                    # a separate follow-up.
                    if not (canonical.is_active and not canonical.draft):
                        has_live_twin = (name_slug and name_slug in live_name_idx) or (
                            web_key is not None and web_key in live_web_idx
                        )
                        if has_live_twin:
                            counts["skipped_reactivate_live_twin"] += 1
                        else:
                            canonical.is_active = True
                            canonical.draft = False
                            canonical.pending_review = False
                            live_name_idx.add(name_slug)
                            if web_key:
                                live_web_idx.add(web_key)
                            counts["reactivated"] += 1
                    counts["idempotent_updated"] += 1
                    continue

                # NOTE: this loader intentionally calls reconcile_hit directly
                # rather than the app.contrib.scraper_ingest.decide_ingest funnel.
                # It layers two CVB-specific confident-merge tiers (exact
                # contact match, fuzzy-name-within-50m of a Google row) ON TOP of
                # the reconciler's ambiguous result before deciding to hold -- the
                # generic funnel has no such tiers. It already honours the
                # hide-on-doubt rule (draft + pending_review) in the else branch
                # below, which is the invariant the funnel exists to enforce.
                rec = reconcile_hit(session, payload)
                if rec.action == "ambiguous":
                    # Two confident merge tiers, highest precision first:
                    #   1. contact match: exact website/phone to a unique Google
                    #      row (no geo needed -- identity beats name).
                    #   2. fuzzy name within 50m of a unique Google row.
                    contact_id = _contact_match(session, payload)
                    fuzzy_id = (
                        None
                        if contact_id is not None
                        else _fuzzy_geo_match(session, payload, threshold=fuzzy_threshold)
                    )
                    match_id = contact_id or fuzzy_id
                    if match_id is not None:
                        rec = ReconcileResult(
                            action="update",
                            existing_id=match_id,
                            merge_fields=_compute_merge_fields(session, match_id, payload),
                            reason=(
                                "exact website/phone match to Google row"
                                if contact_id is not None
                                else "fuzzy name within 50m of Google row"
                            ),
                        )
                        if contact_id is not None:
                            counts["updated_contact"] += 1
                        else:
                            counts["updated_fuzzy"] += 1
                        # fall through to the update handling below
                    else:
                        # Don't drop the listing and don't silently merge. Land
                        # it held (draft + pending_review) so the data is
                        # captured and a human can confirm dup-vs-distinct later.
                        log_ambiguous_reconcile(rec, context="golakehavasu_partners_load")
                        pend = dict(kwargs)
                        pend["draft"] = True
                        pend["pending_review"] = True
                        slug = derive_provider_slug(session, pend["provider_name"])
                        provider = Provider(**pend, slug=slug, last_google_scraped_at=None)
                        session.add(provider)
                        create_provider_and_entity(session, provider)
                        _register_cvb(provider)
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
                _register_cvb(provider)
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


def reconcile_pending(
    *,
    dry_run: bool,
    limit: int | None,
    fuzzy_threshold: float = FUZZY_NAME_THRESHOLD,
) -> dict[str, int]:
    """Cleanup pass for CVB rows held as draft + pending_review.

    Re-runs fuzzy-name-at-geo matching against the current entity graph. Where a
    single confident Google-backed match now exists, fills contact gaps onto the
    Google row, records CVB provenance on the surviving entity, and retires the
    pending CVB row (``is_active=False``, ``pending_review=False``). Rows without
    a confident match are left untouched (still pending). Idempotent and safe to
    re-run; honour ``--dry-run`` to preview without writing.
    """
    counts: dict[str, int] = {
        "scanned": 0,
        "merged": 0,
        "merged_contact": 0,
        "merged_fuzzy": 0,
        "retired": 0,
        "left_pending": 0,
    }
    with SessionLocal() as session:
        rows = session.scalars(
            select(Provider).where(
                Provider.draft.is_(True),
                Provider.pending_review.is_(True),
                Provider.is_active.is_(True),
                Provider.source.like("%go_lake_havasu%"),
            )
        ).all()
        if limit is not None:
            rows = rows[:limit]

        for prov in rows:
            counts["scanned"] += 1
            payload = _provider_to_payload(prov)
            contact_id = _contact_match(session, payload)
            match_id = contact_id or _fuzzy_geo_match(session, payload, threshold=fuzzy_threshold)
            if match_id is None:
                counts["left_pending"] += 1
                continue
            target = session.scalars(
                select(Provider).where(Provider.entity_id == match_id).limit(1)
            ).first()
            if target is None or target.id == prov.id:
                counts["left_pending"] += 1
                continue
            tier = "contact" if contact_id is not None else "fuzzy"

            kwargs = _provider_kwargs(
                payload,
                category_slug=payload.category_slug or "things-to-do",
                category_id=None,
            )
            _fill_gaps(target, kwargs)
            sync_provider_entity_from_legacy(session, target)
            ent = session.get(Entity, match_id)
            ent_name = ent.name if ent is not None else "?"
            if ent is not None:
                ent.source = _combine_sources(ent.source, "go_lake_havasu")[:64]
            prov.is_active = False
            prov.pending_review = False
            counts["merged"] += 1
            counts[f"merged_{tier}"] += 1
            counts["retired"] += 1
            print(
                f"  MERGE[{tier}] pending '{prov.provider_name}' "
                f"[{prov.address or 'no addr'}] -> entity {match_id} '{ent_name}'"
            )
        if not dry_run:
            session.commit()
    return counts


def reconcile_dormant(
    *,
    dry_run: bool,
    limit: int | None,
    fuzzy_threshold: float = FUZZY_NAME_THRESHOLD,
) -> dict[str, int]:
    """Cleanup pass for DORMANT-DUPLICATE CVB rows.

    A "dormant duplicate" is a hidden ``go_lake_havasu`` row -- inactive, or held
    as draft -- that sits beside an active twin, typically the business's Google
    Places listing. The audit found 16 of these (Lake Havasu Marina, London
    Bridge Resort, HEAT Hotel, ...): the business is visible via the Google row,
    but the CVB row's enrichment is stranded on a hidden duplicate.

    Parallels :func:`reconcile_pending` but widens the scan from draft+pending to
    EVERY hidden CVB row (``not (is_active and not draft)``). For each, if a
    single confident Google-backed twin exists (exact website/phone, or fuzzy
    name within 50m), fill contact gaps onto the twin, record CVB provenance on
    the surviving entity, and retire the hidden CVB row (``is_active=False``,
    ``pending_review=False``). Rows with NO confident twin are left untouched --
    those are the genuinely twinless partners that the ingest reactivation path
    (:func:`ingest_partners`) surfaces instead. Idempotent; honour ``--dry-run``.

    Deliberately uses the high-precision contact/fuzzy tiers (NOT the broad
    name-slug index the ingest reactivation guard uses): retiring a row is more
    consequential than declining to reactivate one, so it demands a precise twin.
    """
    counts: dict[str, int] = {
        "scanned": 0,
        "merged": 0,
        "merged_contact": 0,
        "merged_fuzzy": 0,
        "retired": 0,
        "left_alone": 0,
    }
    with SessionLocal() as session:
        rows = session.scalars(
            select(Provider).where(
                Provider.source.like("%go_lake_havasu%"),
                or_(Provider.is_active.is_(False), Provider.draft.is_(True)),
            )
        ).all()
        if limit is not None:
            rows = rows[:limit]

        for prov in rows:
            counts["scanned"] += 1
            payload = _provider_to_payload(prov)
            contact_id = _contact_match(session, payload)
            match_id = contact_id or _fuzzy_geo_match(session, payload, threshold=fuzzy_threshold)
            if match_id is None:
                counts["left_alone"] += 1
                continue
            target = session.scalars(
                select(Provider).where(Provider.entity_id == match_id).limit(1)
            ).first()
            if target is None or target.id == prov.id:
                counts["left_alone"] += 1
                continue
            tier = "contact" if contact_id is not None else "fuzzy"

            kwargs = _provider_kwargs(
                payload,
                category_slug=payload.category_slug or "things-to-do",
                category_id=None,
            )
            _fill_gaps(target, kwargs)
            sync_provider_entity_from_legacy(session, target)
            ent = session.get(Entity, match_id)
            ent_name = ent.name if ent is not None else "?"
            if ent is not None:
                ent.source = _combine_sources(ent.source, "go_lake_havasu")[:64]
            # Already-inactive rows are not re-retired (no double count); active
            # draft rows get retired now that their data is safe on the twin.
            if prov.is_active:
                prov.is_active = False
                counts["retired"] += 1
            prov.pending_review = False
            counts["merged"] += 1
            counts[f"merged_{tier}"] += 1
            print(
                f"  MERGE[{tier}] dormant '{prov.provider_name}' "
                f"[{prov.address or 'no addr'}] -> entity {match_id} '{ent_name}'"
            )
        if not dry_run:
            session.commit()
    return counts


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
    p.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=FUZZY_NAME_THRESHOLD,
        help="rapidfuzz token_sort_ratio floor (0-100) for geo-near fuzzy merge",
    )
    p.add_argument(
        "--reconcile-pending",
        action="store_true",
        help="Cleanup mode: re-match existing draft+pending CVB rows onto Google rows",
    )
    p.add_argument(
        "--reconcile-dormant",
        action="store_true",
        help="Cleanup mode: fold hidden CVB rows (inactive/draft) that have a "
        "confident Google twin onto that twin and retire them",
    )
    args = p.parse_args()

    if args.reconcile_pending:
        counts = reconcile_pending(
            dry_run=bool(args.dry_run),
            limit=args.limit,
            fuzzy_threshold=args.fuzzy_threshold,
        )
        print("--- golakehavasu_partners_load --reconcile-pending summary ---")
    elif args.reconcile_dormant:
        counts = reconcile_dormant(
            dry_run=bool(args.dry_run),
            limit=args.limit,
            fuzzy_threshold=args.fuzzy_threshold,
        )
        print("--- golakehavasu_partners_load --reconcile-dormant summary ---")
    else:
        counts = ingest_partners(
            category_slug=args.category_slug,
            dry_run=bool(args.dry_run),
            limit=args.limit,
            fuzzy_threshold=args.fuzzy_threshold,
        )
        print("--- golakehavasu_partners_load summary ---")
    for k, v in counts.items():
        print(f"{k}: {v}")
    if args.dry_run:
        print("[golakehavasu_partners_load] dry-run: no DB writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
