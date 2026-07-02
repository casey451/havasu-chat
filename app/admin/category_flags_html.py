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

import html
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.nav_html import admin_phase5_nav_html
from app.db.database import get_db
from app.db.models import Provider


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


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


def _nav_shell(title: str, inner: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }}
    .nav {{ margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .nav a {{ color: #0d6efd; font-weight: 600; text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 8px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .empty {{ color: #6c757d; padding: 12px 0; font-size: 0.92rem; }}
    .conf {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
    .btn {{ display: inline-block; padding: 6px 12px; border: none; border-radius: 8px; background: #198754;
      color: #fff; font-weight: 600; font-size: 0.85rem; cursor: pointer; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.78rem;
      background: #e2e3e5; color: #41464b; }}
  </style>
</head>
<body>
  <div class="wrap">
{admin_phase5_nav_html()}
    {inner}
  </div>
</body>
</html>"""


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
        return HTMLResponse(_nav_shell("Miscategorized", inner))

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
