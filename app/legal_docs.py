"""Static legal/policy pages (/privacy, /terms) — the hand-rolled markdown doc
renderer extracted from app/main.py (audit 2026-07-01 decomposition).

The source docs live as markdown under repo ``docs/`` and render through
``privacy_doc_lake.html``. A tiny bespoke markdown->HTML pass (headings, wrapped
bullets, wrapped paragraphs, bold, and safe links) keeps the dependency surface
small — no third-party markdown lib on the request path. Pure move: the routes,
paths, and rendered output are unchanged; ``app.main`` re-exports the renderer +
doc-path names under their historical private names so existing callers/tests
resolve them unchanged.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.provider_name import register_template_filters, register_template_globals

_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
_PRIVACY_MD_PATH = _DOCS_DIR / "privacy.md"
_TOS_MD_PATH = _DOCS_DIR / "tos.md"

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter()


def _privacy_inline_formats(text: str) -> str:
    parts = re.split(r"(\*\*.+?\*\*)", text)
    chunks: list[str] = []
    for p in parts:
        if len(p) >= 4 and p.startswith("**") and p.endswith("**"):
            inner = html.escape(p[2:-2])
            chunks.append(f"<strong>{inner}</strong>")
        else:
            chunks.append(html.escape(p))
    s = "".join(chunks)

    def _link(m: re.Match[str]) -> str:
        u = m.group(1)
        safe = html.escape(u, quote=True)
        return f'<a href="{safe}" rel="noopener noreferrer">{html.escape(u)}</a>'

    s = re.sub(r"(https?://[^\s<>]+)", _link, s)

    def _path_link(m: re.Match[str]) -> str:
        label, path = m.group(1), m.group(2)
        p = html.escape(path, quote=True)
        return f'<a href="{p}">{html.escape(label)}</a>'

    return re.sub(r"\[([^\]]+)\]\((/[^)]+)\)", _path_link, s)


def _render_doc_markdown_to_html(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    in_ul = False
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith("<!--") and "-->" in stripped:
            # Source comments are for editors, not the public page source —
            # the live /terms shipped its "Drafted by AI … needs attorney
            # review" note to anyone who hit View Source. Drop them.
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            i += 1
            continue
        if stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            i += 1
            continue
        if stripped.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            # A markdown bullet hard-wraps across source lines; the
            # continuation lines are indented and belong to the SAME <li>.
            # The old line-by-line pass closed the list and emitted each
            # continuation as an orphan <p>, splitting every wrapped bullet
            # mid-sentence on the live /privacy page.
            item_parts = [stripped[2:].lstrip()]
            i += 1
            while i < len(lines):
                cont_raw = lines[i]
                cont = cont_raw.strip()
                if (
                    not cont
                    or not cont_raw[:1].isspace()
                    or cont.startswith("- ")
                    or cont.startswith("#")
                    or cont.startswith("<!--")
                ):
                    break
                item_parts.append(cont)
                i += 1
            out.append(f"<li>{_privacy_inline_formats(' '.join(item_parts))}</li>")
            continue
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            i += 1
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        para_parts: list[str] = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                break
            if lines[i].lstrip().startswith("- ") or lines[i].lstrip().startswith("##"):
                break
            if lines[i].strip().startswith("<!--"):
                break
            para_parts.append(nxt)
            i += 1
        out.append(f"<p>{_privacy_inline_formats(' '.join(para_parts))}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _render_static_doc(
    request: Request, *, path: Path, head_title: str, meta_description: str | None = None
) -> HTMLResponse:
    md = path.read_text(encoding="utf-8")
    body = _render_doc_markdown_to_html(md)
    return templates.TemplateResponse(
        request=request,
        name="privacy_doc_lake.html",
        context={
            "head_title": head_title,
            "body": body,
            "meta_description": meta_description,
        },
    )


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request) -> HTMLResponse:
    return _render_static_doc(
        request,
        path=_PRIVACY_MD_PATH,
        head_title="Privacy — Ask Hava",
        meta_description=(
            "How Hava handles your data: what we store, who processes it, "
            "and the choices you have. No ads, no profiles, no data sales."
        ),
    )


@router.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request) -> HTMLResponse:
    return _render_static_doc(
        request,
        path=_TOS_MD_PATH,
        head_title="Terms — Ask Hava",
        meta_description=(
            "The terms for using Ask Hava — Lake Havasu City's free local "
            "guide, directory, and AI concierge."
        ),
    )
