"""Admin: provider approval queue (draft + pending_review providers).

Companion to the event approval flow in ``app/admin/router.py``. Scraper
ingestion (e.g. golakehavasu partners) lands uncertain reconciler matches as
``draft=True`` + ``pending_review=True`` so they are captured without being
surfaced. Every consumption query filters ``draft=False``, so these rows are
invisible until a human approves them here.

Self-contained module (its own APIRouter, same ``/admin`` prefix) so it does not
have to edit the large existing admin router. Mounted in ``app/main.py`` next to
the other admin routers. Auth uses the same cookie guard as the rest of the admin
console (``verify_admin_cookie`` / ``COOKIE_NAME``); server-rendered HTML;
POST-redirect-GET.
"""

from __future__ import annotations

import html as html_lib

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.db.database import get_db
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> RedirectResponse | None:
    """Mirror app.admin.router._guard: cookie OR request.state admin user."""
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


def _pending_providers(db: Session) -> list[Provider]:
    """Active providers held for review (draft + pending_review)."""
    return list(
        db.scalars(
            select(Provider)
            .where(
                Provider.draft.is_(True),
                Provider.pending_review.is_(True),
                Provider.is_active.is_(True),
            )
            .order_by(Provider.provider_name.asc())
        ).all()
    )


def pending_provider_count(db: Session) -> int:
    """Count of providers awaiting review (for the admin dashboard funnel)."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Provider)
            .where(
                Provider.draft.is_(True),
                Provider.pending_review.is_(True),
                Provider.is_active.is_(True),
            )
        )
        or 0
    )


def _row_html(p: Provider) -> str:
    bits = [
        ("Category", p.category or "-"),
        ("Address", p.address or "-"),
        ("Phone", p.phone or "-"),
        ("Website", p.website or "-"),
        ("Source", p.source or "-"),
    ]
    meta = " &middot; ".join(f"{_esc(k)}: {_esc(v)}" for k, v in bits)
    pid = _esc(p.id)
    return f"""
    <article class="queue-card" data-approve-url="/admin/provider/{pid}/approve"
             data-deny-url="/admin/provider/{pid}/reject">
      <h3>{_esc(p.provider_name or "(unnamed)")}</h3>
      <p class="meta">{meta}</p>
      <form method="post" action="/admin/provider/{pid}/approve" style="display:inline">
        <button type="submit">Approve</button>
      </form>
      <form method="post" action="/admin/provider/{pid}/reject" style="display:inline">
        <button type="submit">Reject</button>
      </form>
    </article>
    """


@router.get("/providers/pending", response_class=HTMLResponse, response_model=None)
def admin_providers_pending(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    rows = _pending_providers(db)
    cards = "\n".join(_row_html(p) for p in rows) or "<p>No providers awaiting review.</p>"
    body = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Provider review queue</title></head><body>
<h1>Provider review queue ({len(rows)})</h1>
<p>Draft + pending_review providers. Approve to make live (visible in chat,
category pages, search); reject to deactivate.</p>
{cards}
<p class="shortcut-hint">Desktop shortcuts: <b>A</b> approve first card, <b>D</b> reject it.</p>
</body></html>"""
    return HTMLResponse(body)


@router.post("/provider/{provider_id}/approve", response_model=None)
def admin_provider_approve(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    prov = db.get(Provider, provider_id)
    if prov is None:
        raise HTTPException(status_code=404, detail="provider not found")
    # Make the row live + visible. Entity normally already exists (dual-write at
    # insert), but ensure it before clearing draft so nothing surfaces orphaned.
    if not prov.entity_id:
        create_provider_and_entity(db, prov)
    prov.draft = False
    prov.pending_review = False
    prov.is_active = True
    db.add(prov)
    db.commit()
    return RedirectResponse(url="/admin/providers/pending", status_code=303)


@router.post("/provider/{provider_id}/reject", response_model=None)
def admin_provider_reject(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    redir = _guard(request)
    if redir:
        return redir
    prov = db.get(Provider, provider_id)
    if prov is None:
        raise HTTPException(status_code=404, detail="provider not found")
    prov.is_active = False
    prov.pending_review = False
    db.add(prov)
    db.commit()
    return RedirectResponse(url="/admin/providers/pending", status_code=303)
