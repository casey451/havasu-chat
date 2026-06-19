"""GET /lake-styleguide — the Lake Ink & Brass component gallery (Phase 0).

A self-contained, ``noindex`` sample page rendered on the new ``base_lake.html``
that exercises every component in the redesign library. It is the foundation
phase's deliverable proof and the target the CI a11y/SEO gates run against
before any customer-facing page is migrated. Always renders the lake skin
regardless of the THEME flag, so QA can eyeball the system at any time.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu

router = APIRouter(tags=["lake-redesign"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

# Static sample conditions so the live-conditions band renders in the gallery.
# Real wiring to GET /api/conditions lands in Phase 1; nothing here is fabricated
# product data — it is clearly labelled demo content on a noindex page.
_SAMPLE_CHIPS = [
    {"value": "78°F", "label": "Water"},
    {"value": "4–8 mph", "label": "Wind SW"},
    {"value": "$3.92", "label": "Gas avg", "href": "/gas"},
    {"value": "AQI 42", "label": "Air"},
]


@router.get("/lake-styleguide", response_class=HTMLResponse, include_in_schema=False)
def lake_styleguide(request: Request) -> HTMLResponse:
    now = now_lake_havasu()
    today_label = now.strftime("%A, %B ") + str(now.day)
    response = templates.TemplateResponse(
        request=request,
        name="lake_styleguide.html",
        context={"utility_chips": _SAMPLE_CHIPS, "today_label": today_label},
    )
    # Belt-and-suspenders with the template's <meta name="robots">: keep the
    # internal gallery out of the index even if a crawler ignores the meta tag.
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
