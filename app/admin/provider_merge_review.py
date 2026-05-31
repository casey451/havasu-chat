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

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.contrib.provider_merge import merge_providers
from app.db.database import get_db
from app.db.models import Provider

router = APIRouter(prefix="/admin", tags=["admin"])

# Cap pairs rendered per page so a noisy catalog cannot produce a runaway page.
_MAX_PAIRS = 200


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    current_user = getattr(request.state, "current_user", None)
    if current_user is not None and getattr(current_user, "role", None) == "admin":
        return None
    if current_user is not None:
        raise HTTPException(status_code=403, detail="admin_only")
    return RedirectResponse(url="/admin/login", status_code=303)


def _esc(value: object) -> str:
    return html_lib.escape(str(value if value is not None else ""))


def _live_provider_rows(db: Session):
    """Load live providers into the audit's ProvRow shape (is_active, not draft)."""
    from scripts.cross_source_dedup_audit import ProvRow

    out = []
    for p in db.query(Provider).filter(
        Provider.is_active.is_(True), Provider.draft.is_(False)
    ):
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


def _candidate_pairs(db: Session):
    from scripts.cross_source_dedup_audit import find_provider_pairs

    rows = _live_provider_rows(db)
    pairs, _shared = find_provider_pairs(rows)
    return pairs[:_MAX_PAIRS]


def duplicate_pair_count(db: Session) -> int:
    """Count of live duplicate-candidate pairs (for the admin dashboard funnel)."""
    return len(_candidate_pairs(db))


def _pair_card_html(c) -> str:
    dist = "" if c.distance_m is None else f" &middot; {_esc(c.distance_m)}m"
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
    repoint = (
        "<br>".join(f"{_esc(k)}: {_esc(v)}" for k, v in plan.repointed.items())
        or "(none)"
    )
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
