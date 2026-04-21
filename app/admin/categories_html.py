"""Admin category discovery dashboard (Phase 5.6)."""

from __future__ import annotations

import html

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.db.database import get_db
from app.db.models import Contribution, Program, Provider


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


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
    .wrap {{ max-width: 920px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.05rem; margin: 28px 0 10px; color: #343a40; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }}
    .nav {{ margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .nav a {{ color: #0d6efd; font-weight: 600; text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 8px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .empty {{ color: #6c757d; padding: 12px 0; font-size: 0.92rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="nav">
      <a href="/admin?tab=queue">Admin home</a>
      <a href="/admin/contributions">Contributions</a>
      <a href="/admin/mentioned-entities">Mentioned entities</a>
      <a href="/admin/categories">Categories</a>
    </nav>
    {inner}
  </div>
</body>
</html>"""


def register_categories_html_routes(router: APIRouter) -> None:
    @router.get("/categories", response_class=HTMLResponse, response_model=None)
    def categories_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir

        p_rows = db.execute(
            select(Provider.category, func.count())
            .where(Provider.is_active.is_(True), Provider.draft.is_(False))
            .group_by(Provider.category)
            .order_by(func.count().desc())
        ).all()
        pr_rows = db.execute(
            select(Program.activity_category, func.count())
            .where(Program.is_active.is_(True), Program.draft.is_(False))
            .group_by(Program.activity_category)
            .order_by(func.count().desc())
        ).all()
        c_rows = db.execute(
            select(Contribution.submission_category_hint, func.count())
            .where(
                Contribution.status == "pending",
                Contribution.submission_category_hint.isnot(None),
                Contribution.submission_category_hint != "",
            )
            .group_by(Contribution.submission_category_hint)
            .order_by(func.count().desc())
        ).all()

        def table(rows: list, col: str) -> str:
            if not rows:
                return f'<p class="empty">No data in this section yet.</p>'
            body = "".join(
                f"<tr><td>{_esc(str(a))}</td><td>{int(b)}</td></tr>"
                for a, b in rows
            )
            return (
                f"<table><thead><tr><th>{_esc(col)}</th><th>Count</th></tr></thead>"
                f"<tbody>{body}</tbody></table>"
            )

        inner = f"""<h1>Category discovery</h1>
<p class="sub">Read-only frequencies: live catalog vs. pending contribution hints.</p>

<h2>Provider categories</h2>
{table([(r[0], r[1]) for r in p_rows], "Category")}

<h2>Program activity categories</h2>
{table([(r[0], r[1]) for r in pr_rows], "Activity category")}

<h2>Pending contribution category hints</h2>
{table([(r[0], r[1]) for r in c_rows], "submission_category_hint")}
"""
        return HTMLResponse(_nav_shell("Categories", inner))
