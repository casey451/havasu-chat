"""Sponsor lookups for the four-tier ad inventory (CRITIQUE_AND_REDESIGN.md §B5.6).

Each tier has a dedicated helper because the rules differ:

* :func:`active_marquee` — at most one row, sold daily. Returns ``None`` when
  unsold; the template renders the contracting one-line fallback.
* :func:`active_spotlights` — up to 2 rows, sold weekly, ranked by ``weight``
  then ``created_at``. Returns ``[]`` when unsold (the row hides entirely).
* :func:`active_promoted` — at most one row across the entire page (not per
  row). Returns ``None`` when unsold.
* :func:`supporters` — up to 4 logos in the footer wall, sold monthly.
  Returns ``[]`` when unsold.

The legacy :func:`get_active_sponsor` is kept for back-compat with templates
that haven't migrated to the typed partials yet — it now scopes to the marquee
slot only and is internally a thin wrapper around :func:`active_marquee`.

Active criteria for every tier:

    slot == X
    AND status == 'approved'
    AND active is True            (admin kill-switch override of FSM)
    AND (starts_at is null OR starts_at <= now)
    AND (ends_at   is null OR ends_at   >  now)

Impression counter (v52 P0): each ``active_*`` helper atomically increments
``Sponsor.impressions`` for the row(s) it returns, in the same DB transaction
as ``_to_template_dict``. The click counter is bumped in the matching
``/sponsor/click`` route handler. The clicks/impressions ratio is honest
because both numerators draw from the same approved+active+windowed
population; absolute counts include bot traffic but the ratio is what
advertisers care about. Assumes ``/home`` is not cached (true today — no CDN
headers). If page caching is added later, impressions will undercount.

Long-form telemetry (v54 Track B, extended v55): every ``active_*`` helper
emits one ``home.<tier>.impression`` row to ``analytics_events`` per row
rendered, capturing ``ranking_score`` (= ``Sponsor.weight`` at emit time)
so downstream CTR-by-rank math doesn't have to re-join to a mutable Sponsor
row. Event names: ``home.marquee.impression``, ``home.spotlight.impression``,
``home.promoted.impression``, ``home.supporter.impression``. Each is emitted
alongside (not inside) ``_bump_impressions`` — the helper only sees ids, but
we need ``weight`` for ``ranking_score``. ``record_event`` is best-effort and
swallows DB errors, so analytics never breaks a /home render.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, update
from sqlalchemy.orm import Query, Session

from app.analytics import record_event
from app.core.timezone import now_lake_havasu
from app.db.models import AdSlot, Sponsor, SponsorStatus
from app.db.sponsor_resolve import resolve_sponsor_linked_provider


def live_filter_for_slot(q: "Query[Sponsor]", slot: AdSlot) -> "Query[Sponsor]":
    """Apply the standard active-record filter to a Sponsor query for a slot."""
    now = now_lake_havasu()
    return q.filter(
        Sponsor.slot == slot.value,
        Sponsor.status == SponsorStatus.APPROVED.value,
        Sponsor.active.is_(True),
        or_(Sponsor.starts_at.is_(None), Sponsor.starts_at <= now),
        or_(Sponsor.ends_at.is_(None), Sponsor.ends_at > now),
    )


def _to_template_dict(db: Session, row: Sponsor) -> dict[str, Any]:
    """Return a Sponsor row as the dict shape the home templates expect.

    Fields prefer the new Phase-2B columns (``headline``, ``pitch``,
    ``attribution_text``) and fall back to the legacy columns (``name``,
    ``line``) so pre-Phase-2B rows still render. The fallback path is what
    keeps the old single-slot editorial sponsor working through the migration
    without a manual data backfill.
    """
    out: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "headline": row.headline or row.name,
        "pitch": row.pitch or row.line or "",
        "attribution_text": row.attribution_text or f"Sponsored by {row.name}",
        "eyebrow": row.eyebrow or "",
        "line": row.line or "",
        "cta_label": row.cta_label,
        "cta_url": row.cta_url,
        "image_url": row.image_url,
    }
    linked = resolve_sponsor_linked_provider(db, row)
    if linked is not None:
        out["linked_provider_id"] = linked.id
        out["linked_provider_name"] = linked.provider_name
    return out


def _bump_impressions(db: Session, ids: list[str]) -> None:
    """Atomic ``impressions += 1`` for the given sponsor ids; no-op if empty.

    Single SQL UPDATE (no row lock needed) keeps this safe under concurrent
    workers and cheap enough to do on every /home render.
    """
    if not ids:
        return
    db.execute(
        update(Sponsor).where(Sponsor.id.in_(ids)).values(impressions=Sponsor.impressions + 1)
    )
    db.commit()


def active_marquee(db: Session) -> dict[str, Any] | None:
    """Tier 1 — Marquee sponsor below the *Today* section. None when unsold.

    Daily inventory; the template's unsold fallback collapses the slot to a
    single eyebrow + link line so the page contracts instead of advertising
    its own failure to sell. See §B5.6 Tier 1.
    """
    row = (
        live_filter_for_slot(db.query(Sponsor), AdSlot.MARQUEE)
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .first()
    )
    if row is None:
        return None
    _bump_impressions(db, [row.id])
    record_event(
        db,
        "home.marquee.impression",
        slot=AdSlot.MARQUEE.value,
        sponsor_id=row.id,
        ranking_score=row.weight,
    )
    return _to_template_dict(db, row)


def active_spotlights(db: Session, *, limit: int = 2) -> list[dict[str, Any]]:
    """Tier 2 — Spotlight cards in *Local pros · Spotlight*. 0 to 2 rows."""
    rows = (
        live_filter_for_slot(db.query(Sponsor), AdSlot.SPOTLIGHT)
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .limit(limit)
        .all()
    )
    _bump_impressions(db, [r.id for r in rows])
    # v54 Track B — one ``analytics_events`` row per spotlight rendered.
    # Emitted alongside (not inside) ``_bump_impressions`` because the
    # helper only sees ids; we need ``weight`` for ``ranking_score`` and
    # would have to widen its signature otherwise. ``record_event`` is
    # best-effort and swallows DB errors.
    for r in rows:
        record_event(
            db,
            "home.spotlight.impression",
            slot=AdSlot.SPOTLIGHT.value,
            sponsor_id=r.id,
            ranking_score=r.weight,
        )
    return [_to_template_dict(db, r) for r in rows]


def active_promoted(db: Session) -> dict[str, Any] | None:
    """Tier 3 — single Promoted in-feed card per page. None when unsold."""
    row = (
        live_filter_for_slot(db.query(Sponsor), AdSlot.PROMOTED)
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .first()
    )
    if row is None:
        return None
    _bump_impressions(db, [row.id])
    record_event(
        db,
        "home.promoted.impression",
        slot=AdSlot.PROMOTED.value,
        sponsor_id=row.id,
        ranking_score=row.weight,
    )
    return _to_template_dict(db, row)


def supporters(db: Session, *, limit: int = 4) -> list[dict[str, Any]]:
    """Tier 4 — Supporters wall in the footer. Up to 4 logos."""
    rows = (
        live_filter_for_slot(db.query(Sponsor), AdSlot.SUPPORTER)
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .limit(limit)
        .all()
    )
    _bump_impressions(db, [r.id for r in rows])
    for r in rows:
        record_event(
            db,
            "home.supporter.impression",
            slot=AdSlot.SUPPORTER.value,
            sponsor_id=r.id,
            ranking_score=r.weight,
        )
    return [_to_template_dict(db, r) for r in rows]


# back-compat shim ---------------------------------------------------------


def get_active_sponsor(db: Session) -> dict[str, Any] | None:
    """Back-compat shim — scoped to the marquee slot.

    Pre-Phase-2B callers used this for the single editorial sponsor banner.
    All those banners are now Marquee-tier records (defaulted by the
    migration). New code should call :func:`active_marquee` directly.
    """
    return active_marquee(db)
