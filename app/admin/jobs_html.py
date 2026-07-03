"""HTML admin UI for the Jobs portal (one-click scraper pipeline).

Casey's only involvement is clicking a button: each button POSTs to
``/admin/jobs/create`` which queues a job; worker agents pick it up via the
ingest API. The page lists recent jobs and meta-refreshes so status updates
appear without a manual reload. A button is disabled while a job of the same
type is already queued/claimed/running. See docs/scraper/ADMIN_JOBS_SPEC.md.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin.auth import admin_guard as _guard
from app.admin.shell import admin_shell
from app.admin.shell import esc as _esc
from app.admin.shell import fmt_compact_ts as _fmt_ts
from app.db.database import get_db
from app.db.jobs_store import VALID_JOB_TYPES, active_job_types, create_job, list_jobs
from app.db.models import Job

# Page-specific CSS layered over the shared admin_shell base (buttons + status
# pills). The jobs page auto-refreshes via the extra_head meta below.
_JOBS_CSS = """    .flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.92rem; }
    .flash-ok { background: #d1e7dd; color: #0f5132; }
    .buttons { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
    .buttons form { margin: 0; }
    .btn { min-height: 48px; padding: 12px 18px; font-size: 1rem; font-weight: 600; border: none;
      border-radius: 10px; cursor: pointer; background: #0d6efd; color: #fff; }
    .btn:disabled { background: #ced4da; color: #6c757d; cursor: not-allowed; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .pill-pending { background: #fff3cd; color: #664d03; }
    .pill-approved { background: #d1e7dd; color: #0f5132; }
    .pill-rejected { background: #f8d7da; color: #842029; }
    .pill-ok { background: #cfe2ff; color: #084298; }
    .pill-muted { background: #e2e3e5; color: #41464b; }
    .muted { color: #6c757d; }"""

# Button label per job type, in display order (kickoff addition 1a adds the 5th).
_JOB_BUTTONS: tuple[tuple[str, str], ...] = (
    ("schedule_hunt", "Hunt schedules (websites)"),
    ("fb_capture_sweep", "Capture Facebook (OpenClaw)"),
    ("capture_review", "Review captures"),
    ("publish_approved", "Publish approved"),
    ("discovery_audit", "Discovery audit (find new venues)"),
)

_STATUS_PILL = {
    "queued": "pill-pending",
    "claimed": "pill-ok",
    "running": "pill-ok",
    "done": "pill-approved",
    "failed": "pill-rejected",
}



def _status_pill(status: str) -> str:
    cls = _STATUS_PILL.get(status, "pill-muted")
    return f'<span class="pill {cls}">{_esc(status)}</span>'


def _buttons_html(active: set[str]) -> str:
    forms: list[str] = []
    for job_type, label in _JOB_BUTTONS:
        busy = job_type in active
        disabled = " disabled" if busy else ""
        suffix = " (in progress)" if busy else ""
        forms.append(
            f'<form method="post" action="/admin/jobs/create">'
            f'<input type="hidden" name="job_type" value="{_esc(job_type)}"/>'
            f'<button type="submit" class="btn"{disabled}>{_esc(label)}{suffix}</button>'
            f"</form>"
        )
    return f'<div class="buttons">{"".join(forms)}</div>'


def _table_html(jobs: list[Job]) -> str:
    if not jobs:
        return '<p class="empty">No jobs yet. Click a button above to queue one.</p>'
    rows: list[str] = []
    for j in jobs:
        when = _fmt_ts(j.created_at)
        if j.finished_at:
            when += f' <span class="muted">· done {_fmt_ts(j.finished_at)}</span>'
        elif j.claimed_at:
            when += f' <span class="muted">· claimed {_fmt_ts(j.claimed_at)}</span>'
        summary = (j.result_summary or "").strip()
        if len(summary) > 160:
            summary = summary[:160] + "…"
        worker = _esc(j.claimed_by) if j.claimed_by else "—"
        rows.append(
            "<tr>"
            f"<td>{_esc(j.job_type)}</td>"
            f"<td>{_status_pill(j.status)}</td>"
            f"<td>{worker}</td>"
            f"<td>{when}</td>"
            f"<td>{_esc(summary) or '—'}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Type</th><th>Status</th><th>Worker</th><th>When</th><th>Result</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def register_jobs_html_routes(router: APIRouter) -> None:
    @router.get("/jobs", response_class=HTMLResponse, response_model=None)
    def jobs_page(
        request: Request,
        db: Session = Depends(get_db),
        flash: str | None = None,
    ) -> HTMLResponse | RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        active = active_job_types(db)
        jobs = list_jobs(db, limit=50)
        flash_html = f'<div class="flash flash-ok">{_esc(flash)}</div>' if flash else ""
        inner = f"""{flash_html}
<h1>Jobs</h1>
<p class="sub">Click a button to queue work for the scraper pipeline. Workers poll a few
times a day and report back here. This page refreshes every 15 seconds.</p>
{_buttons_html(active)}
{_table_html(jobs)}"""
        return HTMLResponse(
            admin_shell(
                "Jobs",
                inner,
                css=_JOBS_CSS,
                extra_head='<meta http-equiv="refresh" content="15"/>',
            )
        )

    @router.post("/jobs/create", response_model=None)
    def jobs_create(
        request: Request,
        db: Session = Depends(get_db),
        job_type: str = Form(...),
    ) -> RedirectResponse:
        redir = _guard(request)
        if redir:
            return redir
        if job_type not in VALID_JOB_TYPES:
            msg = quote(f"Unknown job type: {job_type}")
            return RedirectResponse(url=f"/admin/jobs?flash={msg}", status_code=303)
        # Don't double-queue a type that's already in flight (mirrors the disabled
        # button — but the button could be stale between refreshes).
        if job_type in active_job_types(db):
            msg = quote(f"{job_type} is already in progress — not queued again.")
            return RedirectResponse(url=f"/admin/jobs?flash={msg}", status_code=303)
        create_job(db, job_type, requested_by="admin")
        msg = quote(f"Queued: {job_type}")
        return RedirectResponse(url=f"/admin/jobs?flash={msg}", status_code=303)
