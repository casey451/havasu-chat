"""Admin "miscategorized?" review list (category patrol, 2026-06-04).

Read-only list of providers the category patrol (scripts/category_patrol.py)
flagged as likely-miscategorized, highest-confidence first, plus a one-click
"Resolve" that clears the flag. The patrol writes ``category_confidence`` +
``category_flagged_at``; this is the human review surface for those flags. No new
review machinery -- it reuses the same auth/nav/shell as the other Phase 5 admin
pages.

The patrol stores a confidence, not its suggested category (that lives in the
patrol's JSON run artifact). So this list routes attention -- "these rows look
wrong, sorted by how sure the model is" -- and the admin opens the provider to
re-categorize. Resolving only clears the flag; it never changes the listing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.shell import admin_shell
from app.admin.shell import esc as _esc
from app.admin.shell import fmt_dt as _fmt_dt
from app.db.database import get_db
from app.db.models import Provider

# Page-specific CSS layered over the shared admin_shell base (confidence cell,
# resolve button, kind pill).
_CATEGORY_FLAGS_CSS = """    .conf { font-variant-numeric: tabular-nums; font-weight: 600; }
    .btn { display: inline-block; padding: 6px 12px; border: none; border-radius: 8px; background: #198754;
      color: #fff; font-weight: 600; font-size: 0.85rem; cursor: pointer; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.78rem;
      background: #e2e3e5; color: #41464b; }"""


def flagged_provider_count(db: Session) -> int:
    """Number of providers currently flagged as possibly miscategorized."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(Provider)
            .where(Provider.category_flagged_at.is_not(None))
        )
        or 0
    )


def register_category_flags_html_routes(router: APIRouter) -> None:
    @router.get("/providers/miscategorized", response_class=HTMLResponse, response_model=None)
    def miscategorized_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir

        rows = db.scalars(
            select(Provider)
            .where(Provider.category_flagged_at.is_not(None))
            .order_by(desc(Provider.category_confidence), desc(Provider.category_flagged_at))
            .limit(200)
        ).all()

        if not rows:
            table = '<p class="empty">No providers flagged as miscategorized. Clean catalog.</p>'
        else:
            body = ""
            for p in rows:
                conf = p.category_confidence
                conf_s = f"{conf:.2f}" if conf is not None else "—"
                slug = (p.slug or "").strip()
                name_cell = _esc(p.provider_name)
                if slug:
                    name_cell = (
                        f'<a href="/provider/{_esc(slug)}" target="_blank" rel="noopener">'
                        f"{_esc(p.provider_name)}</a>"
                    )
                body += (
                    "<tr>"
                    f"<td>{name_cell}</td>"
                    f'<td><span class="pill">{_esc(p.primary_category or "(none)")}</span></td>'
                    f'<td class="conf">{conf_s}</td>'
                    f"<td>{_esc(_fmt_dt(p.category_flagged_at))}</td>"
                    "<td>"
                    f'<form method="post" action="/admin/providers/{_esc(p.id)}/resolve-category-flag" '
                    'style="display:inline">'
                    '<button type="submit" class="btn">Resolve</button>'
                    "</form>"
                    "</td>"
                    "</tr>"
                )
            table = (
                "<table><thead><tr>"
                "<th>Provider</th><th>Current category</th><th>Confidence wrong</th>"
                "<th>Flagged</th><th></th>"
                f"</tr></thead><tbody>{body}</tbody></table>"
            )

        inner = f"""<h1>Possibly miscategorized</h1>
<p class="sub">Flagged by the category patrol, most-confident first. Open a provider to
re-categorize, then Resolve to clear the flag. Confidence is how sure the model is the
current category is <em>wrong</em>.</p>
{table}
"""
        return HTMLResponse(
            admin_shell("Miscategorized", inner, css=_CATEGORY_FLAGS_CSS, max_width="980px")
        )

    @router.post("/providers/{provider_id}/resolve-category-flag", response_model=None)
    def resolve_flag(
        request: Request,
        provider_id: str,
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        prov = db.get(Provider, provider_id)
        if prov is not None:
            prov.category_flagged_at = None
            db.commit()
        return RedirectResponse(url="/admin/providers/miscategorized", status_code=303)
