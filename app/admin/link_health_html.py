"""Admin "broken links" review list (link sentinel, 2026-06-25).

Read-only triage surface for the links the VPS link-health sweep
(``app.monitoring.link_health``) has confirmed broken across multiple sweeps.
Highest-failure-count first, grouped by kind. There is no "resolve" button: the
sweep self-heals the list -- fix (or remove) the URL on the provider/event and
the next sweep marks it OK and it drops off here. Reuses the same auth/nav/shell
as the other admin pages.
"""

from __future__ import annotations

import html
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.admin.nav_html import admin_phase5_nav_html
from app.admin.url_safety import safe_href
from app.db.database import get_db
from app.db.models import LinkHealth, Provider


def _guard(request: Request) -> RedirectResponse | None:
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


def confirmed_broken_count(db: Session) -> int:
    """Number of links currently confirmed broken (for the nav badge / overview)."""
    return int(db.scalar(select(func.count()).select_from(LinkHealth).where(LinkHealth.confirmed_broken)))


_KIND_LABEL = {
    "provider_website": "Provider site",
    "provider_facebook": "Provider Facebook",
    "event_url": "Event link",
}


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
    .wrap {{ max-width: 1040px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    .sub {{ color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; margin-bottom: 8px; }}
    th, td {{ border: 1px solid #dee2e6; padding: 7px 9px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; font-weight: 600; }}
    tbody tr:nth-child(even) {{ background: #fcfcfc; }}
    .empty {{ color: #6c757d; padding: 12px 0; font-size: 0.92rem; }}
    .num {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
    a.ext {{ color: #0d6efd; word-break: break-all; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.76rem;
      background: #f8d7da; color: #842029; }}
    .pill.kind {{ background: #e2e3e5; color: #41464b; }}
  </style>
</head>
<body>
  <div class="wrap">
{admin_phase5_nav_html()}
    {inner}
  </div>
</body>
</html>"""


def register_link_health_html_routes(router: APIRouter) -> None:
    @router.get("/link-health", response_class=HTMLResponse, response_model=None)
    def link_health_page(
        request: Request,
        db: Session = Depends(get_db),
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir

        rows = db.scalars(
            select(LinkHealth)
            .where(LinkHealth.confirmed_broken)
            .order_by(LinkHealth.kind, desc(LinkHealth.consecutive_failures), desc(LinkHealth.last_checked_at))
            .limit(500)
        ).all()

        # Batch-resolve provider slugs so each row can deep-link to the listing.
        provider_ids = {r.entity_id for r in rows if r.kind.startswith("provider") and r.entity_id}
        slugs: dict[str, str] = {}
        if provider_ids:
            for pid, slug in db.execute(
                select(Provider.id, Provider.slug).where(Provider.id.in_(provider_ids))
            ):
                if slug:
                    slugs[pid] = slug

        if not rows:
            table = '<p class="empty">No confirmed-broken links. Every stored URL resolved on the last sweep.</p>'
        else:
            body = ""
            for r in rows:
                label = _esc(r.label) or "—"
                slug = slugs.get(r.entity_id or "")
                if slug:
                    label = f'<a href="/provider/{_esc(slug)}" target="_blank" rel="noopener">{label}</a>'
                status = _esc(r.detail or r.category)
                # Layer 2: local-LLM verdict + suggested replacement URL, if assessed.
                assess = _esc(r.llm_assessment) if r.llm_assessment else ""
                if r.llm_suggested_url:
                    # safe_href on both cells: these are scraped/LLM-produced URLs
                    # and html.escape does not neutralize javascript:/data: schemes.
                    su = _esc(r.llm_suggested_url)
                    assess += (
                        f'<br><a class="ext" href="{_esc(safe_href(r.llm_suggested_url))}"'
                        f' target="_blank" rel="noopener nofollow">→ {su}</a>'
                    )
                assess = assess or "—"
                body += (
                    "<tr>"
                    f"<td>{label}</td>"
                    f'<td><span class="pill kind">{_esc(_KIND_LABEL.get(r.kind, r.kind))}</span></td>'
                    f'<td><span class="pill">{status}</span></td>'
                    f'<td class="num">{r.consecutive_failures}</td>'
                    f"<td>{_esc(_fmt_dt(r.last_checked_at))}</td>"
                    f'<td><a class="ext" href="{_esc(safe_href(r.url))}" target="_blank" rel="noopener nofollow">{_esc(r.url)}</a></td>'
                    f"<td>{assess}</td>"
                    "</tr>"
                )
            table = (
                "<table><thead><tr>"
                "<th>Listing</th><th>Where</th><th>Status</th><th>Fails</th><th>Last checked</th>"
                "<th>URL</th><th>Suggested fix (local AI)</th>"
                f"</tr></thead><tbody>{body}</tbody></table>"
            )

        inner = f"""<h1>Broken links ({len(rows)})</h1>
<p class="sub">Outbound links the VPS sweep has confirmed broken across multiple runs. Open the
listing to fix or remove the URL — the next sweep clears it from this list automatically. Anti-bot
(403/429) links are not shown; they aren't proof a link is dead.</p>
{table}
"""
        return HTMLResponse(_nav_shell("Broken links", inner))
