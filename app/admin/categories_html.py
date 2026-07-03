"""Admin category discovery dashboard (Phase 5.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.shell import admin_shell
from app.admin.shell import esc as _esc
from app.db.database import get_db
from app.db.models import Contribution, Program, Provider


def register_categories_html_routes(router: APIRouter) -> None:
    @router.get("/categories", response_class=HTMLResponse, response_model=None)
    def categories_page(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse | RedirectResponse:
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
                return '<p class="empty">No data in this section yet.</p>'
            body = "".join(f"<tr><td>{_esc(str(a))}</td><td>{int(b)}</td></tr>" for a, b in rows)
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
        return HTMLResponse(admin_shell("Categories", inner))
