"""Static trust pages -- ``/about``, ``/help``, ``/contact`` (WP-1, DL-18).

Three server-rendered Lake Light pages that extend ``lake_light_base.html``.
They take no DB and no dynamic context, so they render fast and never 500 on a
cold database. Registered in ``app/main.py`` via ``include_router`` (see the
``include_router`` block alongside ``home_router``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templates import make_templates
from app.events import senior_center as _sc

templates = make_templates()

router = APIRouter(tags=["static-pages"])


def _t(request: Request, name: str) -> str:
    """Map a ``foo.html`` page name to its Lake template ``foo_lake.html``.

    Lake is the only theme (desert lineage deleted 2026-06-24); always the lake
    variant. ``request`` kept so call sites are unchanged."""
    del request
    return f"{name[:-5]}_lake.html"


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request) -> HTMLResponse:
    """Static About page."""
    return templates.TemplateResponse(request=request, name=_t(request, "about.html"), context={})


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request) -> HTMLResponse:
    """Static Help / FAQ page."""
    return templates.TemplateResponse(request=request, name=_t(request, "help.html"), context={})


@router.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request) -> HTMLResponse:
    """Static Contact page."""
    return templates.TemplateResponse(
        request=request, name=_t(request, "contact.html"), context={}
    )


_DAY_LABEL = {"MO": "Mon", "TU": "Tue", "WE": "Wed", "TH": "Thu", "FR": "Fri",
              "SA": "Sat", "SU": "Sun"}


def _fmt_time(t: object) -> str:
    if t is None:
        return ""
    hour = t.hour % 12 or 12  # type: ignore[attr-defined]
    ampm = "AM" if t.hour < 12 else "PM"  # type: ignore[attr-defined]
    minute = t.minute  # type: ignore[attr-defined]
    return f"{hour}:{minute:02d} {ampm}" if minute else f"{hour} {ampm}"


def _activity_row(a: "_sc.RecurringActivity") -> dict:
    days = "/".join(_DAY_LABEL[d] for d in a.byday)
    span = _fmt_time(a.start) + (f"\u2013{_fmt_time(a.end)}" if a.end else "")
    return {"title": a.title, "when": f"{days} \u00b7 {span}",
            "cost": a.cost, "description": a.description}


_MONTHS = ("January February March April May June July August September October "
           "November December").split()


def _fmt_day(d: object) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}"  # type: ignore[attr-defined]


def _special_row(e: "_sc.SpecialEvent") -> dict:
    when = _fmt_day(e.start_date)
    if e.end_date and e.end_date != e.start_date:
        when += f"\u2013{e.end_date.day}"
    times = _fmt_time(e.start) + (f"\u2013{_fmt_time(e.end)}" if e.end else "")
    if times.strip("\u2013"):
        when += f", {times}"
    return {"title": e.title, "when": when, "description": e.description}


@router.get("/seniors", response_class=HTMLResponse)
def seniors_page(request: Request) -> HTMLResponse:
    """Static Seniors hub -- Lake Havasu Senior Center info, meal program, the
    two monthly calendars, and the recurring weekly activity schedule. No DB, so
    it renders fast and never 500s on a cold database (static constants only)."""
    ctx = {
        "address": _sc.VENUE_ADDRESS,
        "phone": _sc.PHONE,
        "source_url": _sc.EVENTS_URL,
        "home_url": _sc.HOME_URL,
        "menu_image": _sc.CALENDAR_IMAGES["lunch_menu"],
        "activities_image": _sc.CALENDAR_IMAGES["activities"],
        "lunch": _activity_row(_sc.COMMUNITY_LUNCH),
        "activities": [_activity_row(a) for a in _sc.RECURRING_ACTIVITIES],
        "specials": [_special_row(e) for e in _sc.CURATED_SPECIAL_EVENTS],
    }
    return templates.TemplateResponse(
        request=request, name=_t(request, "seniors.html"), context=ctx
    )
