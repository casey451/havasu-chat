"""Admin: cross-source duplicate merge review (Item C UI).

Companion to ``app/admin/provider_approval.py``. Where that surface approves
draft providers, this one resolves DUPLICATES: pairs of already-live providers
that the cross-source dedup audit flagged as the same real-world business.

Pairs are computed LIVE on page load by reusing the audit's pure scoring core
(``scripts.cross_source_dedup_audit.find_provider_pairs``) over current live
provider rows -- no new table, always fresh. The workflow is deliberately
human-gated (dry-run preview -> confirm), because after the shared-key fix the
real worklist is ``needs_review`` (exact-name-at-0m is usually a dup but
occasionally two real units at one address), and the ``website`` auto pairs are
soft (a shared booking/brokerage domain at small N). Merging is NOT batched.

Routes (all under /admin, same cookie guard as the rest of the console):
  GET  /admin/providers/duplicates                -> ranked pair list
  POST /admin/providers/duplicates/preview        -> dry-run plan for one pair
  POST /admin/providers/duplicates/merge          -> commit merge_providers()

The merge itself is the tested primitive ``app.contrib.provider_merge``; this
module only renders and calls it. POST-redirect-GET; server-rendered HTML.
"""

from __future__ import annotations

import html as html_lib
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.contrib.provider_merge import merge_providers
from app.db.database import get_db
from app.db.models import DedupeResolution, Provider, dedupe_pair_key

router = APIRouter(prefix="/admin", tags=["admin"])

# Cap pairs rendered per page so a noisy catalog cannot produce a runaway page.
_MAX_PAIRS = 200

# Resolutions a reviewer can pick from the queue card. ``merged`` is written by
# the merge endpoint itself (via merge_providers), never directly here.
_REVIEW_RESOLUTIONS = ("not_duplicate", "multi_location", "parent_child")



def _esc(value: object) -> str:
    return html_lib.escape(str(value if value is not None else ""))


def _live_provider_rows(db: Session):
    """Load live providers into the audit's ProvRow shape (is_active, not draft)."""
    from scripts.cross_source_dedup_audit import ProvRow

    out = []
    for p in db.query(Provider).filter(Provider.is_active.is_(True), Provider.draft.is_(False)):
        out.append(
            ProvRow(
                id=p.id,
                name=p.provider_name or "",
                source=p.source,
                website=p.website,
                phone=p.phone,
                lat=p.lat,
                lng=p.lng,
                google_place_id=p.google_place_id,
                verified=bool(p.verified),
                created_at=p.created_at,
            )
        )
    return out


def _resolved_pair_keys(db: Session) -> set[str]:
    """pair_keys a human already resolved — filtered out of the live queue."""
    return {k for (k,) in db.execute(select(DedupeResolution.pair_key)).all()}


def _candidate_pairs(db: Session):
    from scripts.cross_source_dedup_audit import find_provider_pairs

    rows = _live_provider_rows(db)
    pairs, _shared = find_provider_pairs(rows)
    resolved = _resolved_pair_keys(db)
    pairs = [c for c in pairs if dedupe_pair_key(c.keep_id, c.dup_id) not in resolved]
    return pairs[:_MAX_PAIRS]


def duplicate_pair_count(db: Session) -> int:
    """Count of live duplicate-candidate pairs (for the admin dashboard funnel)."""
    return len(_candidate_pairs(db))


def _resolve_form_html(c, resolution: str, label: str, parent_id: str | None = None) -> str:
    parent_field = (
        f'<input type="hidden" name="parent_id" value="{_esc(parent_id)}">' if parent_id else ""
    )
    return f"""
      <form method="post" action="/admin/providers/duplicates/resolve" style="display:inline">
        <input type="hidden" name="keep_id" value="{_esc(c.keep_id)}">
        <input type="hidden" name="dup_id" value="{_esc(c.dup_id)}">
        <input type="hidden" name="resolution" value="{_esc(resolution)}">
        <input type="hidden" name="reason" value="{_esc(c.reason)}">
        {parent_field}
        <button type="submit">{_esc(label)}</button>
      </form>"""


def _pair_card_html(c) -> str:
    dist = "" if c.distance_m is None else f" &middot; {_esc(c.distance_m)}m"
    resolve_buttons = "\n".join(
        (
            _resolve_form_html(c, "not_duplicate", "Not a duplicate"),
            _resolve_form_html(c, "multi_location", "Same business, 2 locations"),
            _resolve_form_html(c, "parent_child", "Dup is dept of keep", parent_id=c.keep_id),
            _resolve_form_html(c, "parent_child", "Keep is dept of dup", parent_id=c.dup_id),
        )
    )
    return f"""
    <article class="queue-card">
      <h3>{_esc(c.keep_name)} &larr; {_esc(c.dup_name)}</h3>
      <p class="meta">reason: {_esc(c.reason)} &middot; score: {_esc(c.score)}
         &middot; action: {_esc(c.action)}{dist}</p>
      <p class="meta">keep: {_esc(c.keep_id)} [{_esc(c.keep_source)}]<br>
         dup:&nbsp; {_esc(c.dup_id)} [{_esc(c.dup_source)}]</p>
      <form method="post" action="/admin/providers/duplicates/preview"
            style="display:inline">
        <input type="hidden" name="keep_id" value="{_esc(c.keep_id)}">
        <input type="hidden" name="dup_id" value="{_esc(c.dup_id)}">
        <button type="submit">Preview merge</button>
      </form>
      {resolve_buttons}
    </article>
    """


@router.get("/providers/duplicates", response_class=HTMLResponse, response_model=None)
def admin_duplicates(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    pairs = _candidate_pairs(db)
    cards = "\n".join(_pair_card_html(c) for c in pairs) or "<p>No duplicate candidates.</p>"
    body = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Duplicate merge review</title></head><body>
<h1>Duplicate merge review ({len(pairs)})</h1>
<p>Live provider pairs the cross-source audit flags as the same business.
Preview shows what the merge would change before you commit. Merging folds the
second row into the first and retires the second; it cannot be undone from here.</p>
{cards}
</body></html>"""
    return HTMLResponse(body)


def _provider_label(db: Session, pid: str) -> str:
    p = db.get(Provider, pid)
    if p is None:
        return f"(missing {pid})"
    return f"{p.provider_name} [{p.source}] addr={p.address or '-'} web={p.website or '-'}"


@router.post("/providers/duplicates/preview", response_class=HTMLResponse, response_model=None)
def admin_duplicates_preview(
    request: Request,
    keep_id: str = Form(...),
    dup_id: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    try:
        plan = merge_providers(db, keep_id=keep_id, dup_id=dup_id, dry_run=True)
    except ValueError as e:
        return HTMLResponse(
            f"<p>Cannot merge: {_esc(str(e))}</p>"
            f"<p><a href='/admin/providers/duplicates'>Back</a></p>",
            status_code=400,
        )
    gap = ", ".join(plan.gap_filled) or "(none)"
    repoint = "<br>".join(f"{_esc(k)}: {_esc(v)}" for k, v in plan.repointed.items()) or "(none)"
    body = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Confirm merge</title></head><body>
<h1>Confirm merge</h1>
<p><b>Keep:</b> {_esc(_provider_label(db, keep_id))}</p>
<p><b>Retire:</b> {_esc(_provider_label(db, dup_id))}</p>
<p><b>Fields gap-filled onto keeper:</b> {_esc(gap)}</p>
<p><b>Combined source:</b> {_esc(plan.combined_source)}</p>
<p><b>References repointed:</b><br>{repoint}</p>
<form method="post" action="/admin/providers/duplicates/merge">
  <input type="hidden" name="keep_id" value="{_esc(keep_id)}">
  <input type="hidden" name="dup_id" value="{_esc(dup_id)}">
  <button type="submit">Confirm merge</button>
</form>
<p><a href="/admin/providers/duplicates">Cancel</a></p>
</body></html>"""
    return HTMLResponse(body)


@router.post("/providers/duplicates/merge", response_model=None)
def admin_duplicates_merge(
    request: Request,
    keep_id: str = Form(...),
    dup_id: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    redir = _guard(request)
    if redir:
        return redir
    try:
        merge_providers(db, keep_id=keep_id, dup_id=dup_id, dry_run=False)
    except ValueError as e:
        db.rollback()
        return HTMLResponse(
            f"<p>Cannot merge: {_esc(str(e))}</p>"
            f"<p><a href='/admin/providers/duplicates'>Back</a></p>",
            status_code=400,
        )
    db.commit()
    return RedirectResponse(url="/admin/providers/duplicates", status_code=303)


def _upsert_resolution(
    db: Session, *, id_a: str, id_b: str, resolution: str, reason: str | None
) -> None:
    """Insert-or-update the pair's DedupeResolution (re-resolving is allowed)."""
    key = dedupe_pair_key(id_a, id_b)
    existing = db.scalar(select(DedupeResolution).where(DedupeResolution.pair_key == key))
    if existing is not None:
        existing.resolution = resolution
        existing.reason = (reason or existing.reason or "")[:40] or None
        return
    lo, hi = sorted((id_a, id_b))
    db.add(
        DedupeResolution(
            pair_key=key,
            provider_id_a=lo,
            provider_id_b=hi,
            resolution=resolution,
            reason=(reason or "")[:40] or None,
        )
    )


@router.post("/providers/duplicates/resolve", response_model=None)
def admin_duplicates_resolve(
    request: Request,
    keep_id: str = Form(...),
    dup_id: str = Form(...),
    resolution: str = Form(...),
    reason: str = Form(""),
    parent_id: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    """Resolve a candidate pair WITHOUT merging (Track B1 resolution paths).

    * ``not_duplicate``  — record only; the pair stops surfacing.
    * ``multi_location`` — stamp both rows with one ``location_group_id``
      (reusing either side's existing group so chains coalesce), record.
    * ``parent_child``   — ``parent_id`` picks the parent of the two; the
      other row gets ``parent_provider_id`` and renders on the parent's
      profile, record.
    """
    redir = _guard(request)
    if redir:
        return redir

    def _fail(msg: str, code: int = 400) -> HTMLResponse:
        db.rollback()
        return HTMLResponse(
            f"<p>Cannot resolve: {_esc(msg)}</p>"
            f"<p><a href='/admin/providers/duplicates'>Back</a></p>",
            status_code=code,
        )

    if resolution not in _REVIEW_RESOLUTIONS:
        return _fail(f"unknown resolution {resolution!r}")
    if keep_id == dup_id:
        return _fail("pair ids are identical")
    a = db.get(Provider, keep_id)
    b = db.get(Provider, dup_id)
    if a is None or b is None:
        return _fail("provider not found", code=404)

    if resolution == "multi_location":
        group = a.location_group_id or b.location_group_id or str(uuid4())
        a.location_group_id = group
        b.location_group_id = group
    elif resolution == "parent_child":
        if parent_id not in (keep_id, dup_id):
            return _fail("parent_id must be one of the pair")
        parent, child = (a, b) if parent_id == keep_id else (b, a)
        if parent.parent_provider_id == child.id:
            return _fail("would create a parent cycle")
        child.parent_provider_id = parent.id

    _upsert_resolution(db, id_a=keep_id, id_b=dup_id, resolution=resolution, reason=reason)
    db.commit()
    return RedirectResponse(url="/admin/providers/duplicates", status_code=303)
