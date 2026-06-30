"""Public catalog search API (Phase 2B.3).

``GET /api/search`` composes Tier-2-style text filters, dispatches text match
through :mod:`app.search.fts` on Postgres and SQLite-compatible predicates
elsewhere, applies :mod:`app.search.ranking`, and returns entity rows with
profile URLs. No auth gate.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Float, and_, case, cast, exists, false, func, literal, or_, select
from sqlalchemy.orm import Session, aliased, joinedload

from app.chat import tier2_db_query
from app.chat.normalizer import spell_correct
from app.chat.tier2_schema import Tier2Filters
from app.chat.tier2_synonyms import _category_needle_set
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_PROGRAM,
    is_valid_entity_type,
)
from app.db.models import Entity, EntityCategory, Event, Location, Program, Provider
from app.providers import queries as provider_queries
from app.search import fts as search_fts
from app.search import ranking as search_ranking
from app.search.ranking import _verification_bonus_sql

router = APIRouter(tags=["search"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

_CURSOR_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Page-level keyword results cap (the plain crawlable list at GET /search).
_PAGE_RESULT_LIMIT = 50


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _decode_offset(cursor: str | None) -> int:
    if not cursor or not str(cursor).strip():
        return 0
    raw = str(cursor).strip()
    if not _CURSOR_RE.match(raw):
        raise HTTPException(status_code=400, detail="invalid_cursor")
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        blob = base64.urlsafe_b64decode(raw + pad)
        data = json.loads(blob.decode("utf-8"))
        o = int(data.get("o", 0))
        if o < 0:
            raise ValueError
        return o
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_cursor") from exc


def _encode_offset(offset: int) -> str:
    raw = json.dumps({"o": offset}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _like_escape(s: str) -> str:
    """Escape LIKE/ILIKE wildcards so the query matches as literal text.

    Used with an explicit ``escape='\\'`` so a name like "In-N-Out" or a query
    such as "50% off" can't behave as a wildcard pattern.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tier2_filters_for_search(
    *,
    q: str,
    category: str | None,
) -> Tier2Filters:
    return Tier2Filters(
        entity_name=q.strip(),
        category=(category.strip() if category and category.strip() else None),
        parser_confidence=1.0,
        fallback_to_tier3=False,
    )


def _search_needles(q_raw: str) -> tuple[str, ...]:
    """Category needles for a search query, with domain spell-correction.

    Expands the raw query AND its spell-corrected form (``spell_correct`` —
    the same domain typo layer the chat concierge uses, whose vocab is built
    from the leaf/synonym dicts) so a misspelled or loosely-phrased category
    query ("pool cleaining", "golf coarse") still reaches the right providers.
    Union of both needle sets, deduped + sorted.
    """
    q_norm = (q_raw or "").strip().lower()
    if not q_norm:
        return ()
    needles: set[str] = set(_category_needle_set(q_norm))
    corrected = spell_correct(q_norm)
    if corrected and corrected != q_norm:
        needles |= set(_category_needle_set(corrected))
    needles.discard("")
    return tuple(sorted(needles))


def _provider_synonym_exists_predicate(
    *,
    q_raw: str,
    entity_type_filter: str | None,
) -> Any | None:
    """OR-branch for commercial providers: Tier-2-style taxonomy ILIKE needles.

    Mirrors the recall slice in ``tier2_db_query._query_providers_orm`` so
    ``q=barbershop`` can reach ``google_primary_category=barber_shop`` rows
    without bypassing the FTS stack for the primary name/description match.
    """
    if entity_type_filter is not None and entity_type_filter != ENTITY_TYPE_COMMERCIAL:
        return None
    needles = _search_needles(q_raw)
    if not needles:
        return None
    P = aliased(Provider)
    norm_primary = func.replace(func.coalesce(P.google_primary_category, ""), "_", " ")
    conds: list[Any] = []
    for n in needles:
        n_like = tier2_db_query._text_needle(n)
        if n_like is None:
            continue
        conds.append(P.category.ilike(n_like))
        conds.append(norm_primary.ilike(n_like))
    if not conds:
        return None
    return exists(
        select(literal(1))
        .select_from(P)
        .where(
            P.entity_id == Entity.id,
            P.is_active.is_(True),
            P.draft.is_(False),
            P.is_local.isnot(False),  # Lake Havasu-local only (drop out-of-area)
            or_(*conds),
        )
    )


def _leaf_link_exists_predicate(
    db: Session,
    *,
    q_raw: str,
    entity_type_filter: str | None,
) -> Any | None:
    """OR-branch: entities whose canonical taxonomy leaf matches the query's intent.

    The legacy ``Provider.category`` / ``google_primary_category`` columns are
    generic for trades ("home_services" / "general_contractor"), so a category
    query like "ac repair", "roofer", or "nursing home" cannot reach the right
    providers through the synonym needles alone — the specific trade lives only in
    the entity name and the canonical ``EntityCategory`` leaf link (what the leaf
    pages render). This branch resolves the query to its leaf via the existing
    query→leaf routing (:mod:`app.categories.leaf_query`) and matches providers
    whose PRIMARY ``EntityCategory`` is that leaf, closing the intent gap.

    Commercial entities only; returns ``None`` when the query resolves to no leaf
    (so non-category queries are unaffected).
    """
    if entity_type_filter is not None and entity_type_filter != ENTITY_TYPE_COMMERCIAL:
        return None
    from app.categories import leaf_query  # lazy: avoid an import cycle

    leaf = leaf_query.match_leaf_query(db, q_raw) or leaf_query.match_leaf_service_intent(
        db, q_raw
    )
    if leaf is None:
        return None
    return exists(
        select(literal(1))
        .select_from(EntityCategory)
        .where(
            EntityCategory.entity_id == Entity.id,
            EntityCategory.category_id == leaf.id,
            EntityCategory.is_primary.is_(True),
        )
    )


def _sqlite_entity_text_and(
    filters: Tier2Filters,
    *,
    entity_type: str | None,
) -> Any:
    """AND of name + category text dimensions (same shape as sqlite_fallback)."""
    parts: list[Any] = []
    if filters.entity_name and filters.entity_name.strip():
        needle = f"%{filters.entity_name.strip()}%"
        parts.append(or_(Entity.name.ilike(needle), Entity.description.ilike(needle)))
    if filters.category and filters.category.strip():
        needles = _category_needle_set(filters.category)
        if needles:
            cat_conds: list[Any] = []
            for n in needles:
                n_like = f"%{n}%"
                cat_conds.append(Entity.name.ilike(n_like))
                cat_conds.append(Entity.description.ilike(n_like))
            if cat_conds:
                parts.append(or_(*cat_conds))
    if not parts:
        return literal(False)
    if len(parts) == 1:
        return parts[0]
    return and_(*parts)


def _featured_case_expr() -> Any:
    return case(
        (Entity.entity_type == ENTITY_TYPE_COMMERCIAL, func.coalesce(Provider.featured, false())),
        (Entity.entity_type == ENTITY_TYPE_EVENT, func.coalesce(Event.featured, false())),
        (Entity.entity_type == ENTITY_TYPE_PROGRAM, func.coalesce(Program.featured, false())),
        else_=false(),
    )


@router.get("/api/search/suggestions")
def api_search_suggestions(
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lightweight autocomplete for the hero/topbar ask bars.

    Returns up to 8 ``{name, type, subcategory, url}`` rows whose entity name
    matches ``q`` as a prefix or substring (active commercial/event/program
    entities only). Prefix hits rank above mid-string hits. Kept intentionally
    cheap: a single bounded query with one optional outerjoin to Provider for
    the commercial subcategory; no FTS/ranking machinery and no per-row
    hydration like :func:`api_search`.
    """
    if q is None or len(str(q).strip()) < 2:
        return []

    needle = str(q).strip()
    prefix_like = f"{needle}%"
    sub_like = f"%{needle}%"

    suggest_types = (
        ENTITY_TYPE_COMMERCIAL,
        ENTITY_TYPE_EVENT,
        ENTITY_TYPE_PROGRAM,
    )

    # Prefix matches sort first (rank 0), then mid-string matches (rank 1),
    # then alphabetically — a stable, predictable order for a dropdown.
    rank_expr = case((Entity.name.ilike(prefix_like), 0), else_=1)

    stmt = (
        select(
            Entity.id,
            Entity.entity_type,
            Entity.name,
            Entity.slug,
            Provider.slug.label("provider_slug"),
            func.coalesce(Provider.google_primary_category, Provider.category).label("subcategory"),
        )
        .outerjoin(
            Provider,
            (Provider.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
        )
        .where(
            Entity.is_active.is_(True),
            Entity.entity_type.in_(suggest_types),
            Entity.name.ilike(sub_like),
        )
        .order_by(rank_expr.asc(), Entity.name.asc(), Entity.id.asc())
        .limit(8)
    )

    out: list[dict[str, Any]] = []
    for row in db.execute(stmt).all():
        claim_url: str | None = None
        if row.entity_type == ENTITY_TYPE_COMMERCIAL:
            slug_out = row.provider_slug or row.slug
            url = f"/provider/{slug_out}"
            # Direct one-step claim link (Phase 3.1): the claim flow resolves by
            # ENTITY slug (auth.claims.get_entity_by_slug → Entity.slug, mirrored
            # by the provider page's claim CTA), so build it from row.slug — NOT
            # the provider slug used for the profile URL. Lets /portal/claim send
            # a search hit straight to /claim/<slug> instead of via the listing.
            if row.slug:
                claim_url = f"/claim/{row.slug}"
        elif row.entity_type == ENTITY_TYPE_EVENT:
            url = f"/events/{row.id}"
        elif row.entity_type == ENTITY_TYPE_PROGRAM:
            url = f"/programs/{row.id}"
        else:  # pragma: no cover - filtered out above
            url = "/home"
        subcat = row.subcategory if row.entity_type == ENTITY_TYPE_COMMERCIAL else None
        out.append(
            {
                "name": row.name,
                "type": row.entity_type,
                "subcategory": subcat,
                "url": url,
                # Only commercial rows are claimable; None for events/programs so
                # the claim page can fall back to the profile URL.
                "claim_url": claim_url,
            }
        )
    return out


@router.get("/api/search")
def api_search(
    q: str | None = Query(None),
    category: str | None = Query(None),
    district: str | None = Query(None),
    entity_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if q is None or not str(q).strip():
        raise HTTPException(status_code=400, detail="q_required")

    q_clean = str(q).strip()
    entity_type_f = None
    if entity_type is not None and str(entity_type).strip():
        et = str(entity_type).strip().lower()
        if not is_valid_entity_type(et):
            raise HTTPException(status_code=400, detail="invalid_entity_type")
        entity_type_f = et

    filters = _tier2_filters_for_search(q=q_clean, category=category)
    offset = _decode_offset(cursor)
    fetch_n = limit + 1

    prov_syn = _provider_synonym_exists_predicate(
        q_raw=q_clean,
        entity_type_filter=entity_type_f,
    )

    q_stmt = select(Entity).where(Entity.is_active.is_(True))
    if entity_type_f:
        q_stmt = q_stmt.where(Entity.entity_type == entity_type_f)
    if district and district.strip():
        d_needle = f"%{district.strip()}%"
        q_stmt = q_stmt.where(
            exists(
                select(literal(1))
                .select_from(Location)
                .where(
                    Location.entity_id == Entity.id,
                    Location.district.isnot(None),
                    Location.district.ilike(d_needle),
                )
            )
        )

    is_pg = _is_postgres(db)
    text_parts: list[Any] = []
    if is_pg:
        tsq = search_fts.build_tsquery_string(filters)
        if tsq:
            text_parts.append(search_fts.entities_search_vector_match(tsq))
    else:
        sqlite_and = _sqlite_entity_text_and(filters, entity_type=entity_type_f)
        text_parts.append(sqlite_and)

    if prov_syn is not None:
        text_parts.append(prov_syn)

    leaf_link = _leaf_link_exists_predicate(db, q_raw=q_clean, entity_type_filter=entity_type_f)
    if leaf_link is not None:
        text_parts.append(leaf_link)

    if not text_parts:
        return {"results": [], "next_cursor": None}

    q_stmt = q_stmt.where(or_(*text_parts))

    q_stmt = (
        q_stmt.outerjoin(
            Provider,
            (Provider.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
        )
        .outerjoin(
            Event, (Event.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_EVENT)
        )
        .outerjoin(
            Program,
            (Program.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_PROGRAM),
        )
    )

    # Locality (2026-06-19, Casey): Lake Havasu-local only. Drop out-of-area
    # commercial listings; non-commercial entity types are unaffected.
    q_stmt = q_stmt.where(
        or_(
            Entity.entity_type != ENTITY_TYPE_COMMERCIAL,
            Provider.is_local.isnot(False),
        )
    )

    ref_now = now_lake_havasu()

    feat = _featured_case_expr()
    order_cols: list[Any] = []
    if is_pg:
        rank_expr = search_ranking.build_rank_score_expr_for_filters(
            filters,
            last_verified_col=Entity.last_verified_at,
            featured_col=feat,  # type: ignore[arg-type]
            ref_now=ref_now,
            liveness_col=Entity.liveness_score,
        )
        if rank_expr is not None:
            order_cols.append(rank_expr.desc())
    else:
        sqlite_base = cast(_verification_bonus_sql(Entity.last_verified_at, ref_now), Float) + cast(
            case((feat.is_(True), 25.0), else_=0.0),
            Float,
        )
        # Mirror the PG liveness dampener (bury stale listings; NULL → unchanged).
        sqlite_damp = search_ranking.liveness_dampener_sql(Entity.liveness_score)
        sqlite_rank = sqlite_base if sqlite_damp is None else sqlite_base * sqlite_damp
        order_cols.append(sqlite_rank.desc())
    order_cols.extend([Entity.name.asc(), Entity.id.asc()])

    q_stmt = q_stmt.order_by(*order_cols).offset(offset).limit(fetch_n)

    rows = list(db.scalars(q_stmt).unique().all())
    has_more = len(rows) > limit
    page = rows[:limit]
    if not page:
        return {"results": [], "next_cursor": None}

    ids = [e.id for e in page]
    prov_by_ent: dict[str, Provider] = {}
    ev_by_ent: dict[str, Event] = {}
    prog_by_ent: dict[str, Program] = {}
    if ids:
        for p in db.scalars(select(Provider).where(Provider.entity_id.in_(ids))).all():
            prov_by_ent[p.entity_id] = p
        for ev in db.scalars(select(Event).where(Event.entity_id.in_(ids))).all():
            ev_by_ent[ev.entity_id] = ev
        for pr in db.scalars(select(Program).where(Program.entity_id.in_(ids))).all():
            prog_by_ent[pr.entity_id] = pr

    hydrated = (
        db.query(Entity).filter(Entity.id.in_(ids)).options(joinedload(Entity.location)).all()
    )
    ent_order = {eid: i for i, eid in enumerate(ids)}
    hydrated.sort(key=lambda e: ent_order.get(e.id, 999))

    results: list[dict[str, Any]] = []
    for ent in hydrated:
        loc = ent.location
        district_val = loc.district if loc is not None else None
        slug_out = ent.slug
        hero: str | None = None
        profile_url = "/home"
        p = prov_by_ent.get(ent.id)
        ev = ev_by_ent.get(ent.id)
        pr = prog_by_ent.get(ent.id)
        if ent.entity_type == ENTITY_TYPE_COMMERCIAL and p is not None:
            slug_out = p.slug or ent.slug
            profile_url = f"/provider/{slug_out}"
            hero = provider_queries.derive_hero_photo(p)
        elif ent.entity_type == ENTITY_TYPE_EVENT and ev is not None:
            profile_url = f"/events/{ev.id}"
        elif ent.entity_type == ENTITY_TYPE_PROGRAM and pr is not None:
            profile_url = f"/programs/{pr.id}"
        elif ent.entity_type == ENTITY_TYPE_PLACE:
            profile_url = "/home"

        results.append(
            {
                "entity_id": ent.id,
                "entity_type": ent.entity_type,
                "slug": slug_out,
                "name": ent.name,
                "description": ent.description,
                "district": district_val,
                "hero_url": hero,
                "profile_url": profile_url,
            }
        )

    next_cursor: str | None = None
    if has_more:
        next_cursor = _encode_offset(offset + limit)

    return {"results": results, "next_cursor": next_cursor}


# --- /search keyword results page (DL-6 phase 2, WP-11) --------------------


def _humanize_subtype(subcategory_slug: str | None, raw_token: str | None) -> str | None:
    """Human label for a result row's category line.

    Prefers the canonical taxonomy label for a known ``Provider.subcategory``
    slug ("bars-breweries" → "Bars & Breweries"); otherwise prettifies the raw
    Google/legacy token ("mexican_restaurant" → "Mexican Restaurant").
    """
    slug = (subcategory_slug or "").strip().lower()
    if slug:
        from app.categories.subcategories import subcategory_by_slug  # lazy: no cycle

        sub = subcategory_by_slug(slug)
        if sub is not None:
            return sub.label
    token = (raw_token or "").strip()
    if not token:
        return None
    return token.replace("_", " ").replace("-", " ").strip().title()


def _keyword_provider_rows(db: Session, *, q_clean: str, limit: int) -> list[Provider]:
    """Provider rows matching ``q`` via the same FTS/synonym path as ``/api/search``.

    Reuses :func:`_tier2_filters_for_search`, the Postgres
    ``entities.search_vector @@ to_tsquery`` predicate (or the SQLite ILIKE
    fallback :func:`_sqlite_entity_text_and`) and the commercial-synonym
    EXISTS branch, then hydrates the active, non-draft :class:`Provider` rows
    so the page can render phone / address / category directly. Ordered by
    name for a stable, crawlable list.
    """
    filters = _tier2_filters_for_search(q=q_clean, category=None)

    e_stmt = select(Entity.id).where(
        Entity.is_active.is_(True),
        Entity.entity_type == ENTITY_TYPE_COMMERCIAL,
    )

    text_parts: list[Any] = []
    if _is_postgres(db):
        tsq = search_fts.build_tsquery_string(filters)
        if tsq:
            text_parts.append(search_fts.entities_search_vector_match(tsq))
        # F13: a proper noun or punctuated name ("In-N-Out") tokenizes away in
        # to_tsquery (hyphens are dropped, then "in"/"out" are stopwords), so an
        # FTS-only path returns nothing for it. Add a direct name substring so
        # named businesses stay findable; the SQLite branch already does this.
        if q_clean.strip():
            text_parts.append(
                Entity.name.ilike(f"%{_like_escape(q_clean.strip())}%", escape="\\")
            )
    else:
        text_parts.append(_sqlite_entity_text_and(filters, entity_type=ENTITY_TYPE_COMMERCIAL))

    prov_syn = _provider_synonym_exists_predicate(
        q_raw=q_clean,
        entity_type_filter=ENTITY_TYPE_COMMERCIAL,
    )
    if prov_syn is not None:
        text_parts.append(prov_syn)

    leaf_link = _leaf_link_exists_predicate(
        db, q_raw=q_clean, entity_type_filter=ENTITY_TYPE_COMMERCIAL
    )
    if leaf_link is not None:
        text_parts.append(leaf_link)

    if not text_parts:
        return []

    e_stmt = e_stmt.where(or_(*text_parts))
    entity_ids = list(db.scalars(e_stmt).all())
    if not entity_ids:
        return []

    p_stmt = (
        select(Provider)
        .where(
            Provider.entity_id.in_(entity_ids),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Provider.is_local.isnot(False),  # Lake Havasu-local only
        )
        .order_by(func.lower(Provider.provider_name).asc(), Provider.id.asc())
        .limit(limit)
    )
    return list(db.scalars(p_stmt).unique().all())


def _keyword_event_rows(db: Session, *, q_clean: str, limit: int) -> list[Event]:
    """Event rows whose title or description match ``q`` (live status only).

    A deliberately plain keyword query (ILIKE on title/description); the event
    corpus has no FTS search_vector, so we keep this simple and dialect-neutral.
    Soonest dates first.
    """
    needle = f"%{q_clean}%"
    ev_stmt = (
        select(Event)
        .where(
            Event.status == "live",
            or_(Event.title.ilike(needle), Event.description.ilike(needle)),
        )
        .order_by(Event.date.asc(), Event.start_time.asc(), Event.id.asc())
        .limit(limit)
    )
    return list(db.scalars(ev_stmt).unique().all())


@router.get("/search", response_class=HTMLResponse)
def search_results_page(
    request: Request,
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Plain, crawlable keyword results page for the header search.

    Renders two lists (providers, events) for ``?q=``. Blank ``q`` or no
    matches shows an empty state pointing at Ask Hava. No auth gate.
    """
    q_clean = (q or "").strip()

    providers: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    if q_clean:
        for p in _keyword_provider_rows(db, q_clean=q_clean, limit=_PAGE_RESULT_LIMIT):
            # Raw Google type tokens ("mexican_restaurant", "bar_and_grill")
            # leaked onto the live page — humanize via the canonical
            # subcategory label when we have one, else prettify the token.
            subtype = _humanize_subtype(
                p.subcategory, p.google_primary_category or p.category
            )
            # Street line only — the stored address is the full Google format
            # including ", Lake Havasu City, AZ 86403, USA".
            street = (p.address or "").split(",")[0].strip()
            area = p.district or street or None
            phone_display = (p.phone or "").strip()
            providers.append(
                {
                    "name": p.provider_name,
                    "url": f"/provider/{p.slug}" if p.slug else None,
                    "subtype": subtype,
                    "phone": phone_display,
                    # tel: links want bare digits, not "(928) 555-1234".
                    "phone_tel": re.sub(r"\D", "", phone_display),
                    "address": area,
                }
            )
        for ev in _keyword_event_rows(db, q_clean=q_clean, limit=_PAGE_RESULT_LIMIT):
            events.append(
                {
                    "title": ev.title,
                    "url": f"/events/{ev.id}",
                    "date": ev.date,
                    "venue": ev.location_name,
                }
            )

    # Lake Ink & Brass: the concierge falls through here for descriptive
    # queries, so /search must follow the active theme (was desert-only).
    template = "search_lake.html"
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "q": q_clean,
            "providers": providers,
            "events": events,
            "has_results": bool(providers or events),
        },
    )
