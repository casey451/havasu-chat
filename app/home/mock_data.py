"""Mocked home-page data for BUILD.md step 1.

Step 2 will replace each builder with a live DB read. Structure mirrors what
the live read will produce — keep the keys stable, only the source changes.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.timezone import now_lake_havasu

# ─────────── helpers ───────────

# Voice rule: only [name](url) markdown is allowed in Hava's voice text.
# We render it server-side to anchor tags; the front-end never sees raw
# markdown. Same convention will apply when the SWR pullquote (step 4)
# replaces this mock.
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_voice_links(text: str) -> str:
    """Render `[label](url)` into safe `<a>` tags. Strips other markdown.

    Voice text comes from the LLM (step 4) which is constrained to this
    single markdown form; the regex is permissive enough to handle the
    short link grammar without dragging in a markdown parser.
    """
    out: list[str] = []
    last = 0
    for m in _LINK_RE.finditer(text):
        out.append(_html_escape(text[last : m.start()]))
        label = _html_escape(m.group(1))
        url = m.group(2).strip()
        if url.startswith(("http://", "https://", "/")):
            out.append(
                f'<a href="{_html_escape(url)}" rel="noopener">{label}</a>'
            )
        else:
            # Defensive: don't render arbitrary schemes.
            out.append(label)
        last = m.end()
    out.append(_html_escape(text[last:]))
    return "".join(out)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_phone(digits: str) -> str:
    """Pretty-print a 10-digit US number; raw stays unformatted for tel:."""
    d = "".join(ch for ch in digits if ch.isdigit())
    if len(d) == 10:
        return f"({d[0:3]}) {d[3:6]}-{d[6:10]}"
    return digits


# ─────────── builders ───────────


def build_context(now: datetime | None = None) -> dict[str, Any]:
    """Return the full home-page Jinja context. All data mocked for step 1."""
    today = now or now_lake_havasu()
    today_label = today.strftime("%A, %B ") + str(today.day) if hasattr(today, "strftime") else "Thursday, May 7"

    return {
        "today_label": today_label,
        "tonight_label": "Tonight" if today.hour >= 16 else "Today",
        "added_month": today.strftime("%B"),
        "chips": [
            "find a plumber",
            "date night",
            "open right now",
            "tonight",
            "junk removal",
            "kid-friendly",
            "on the water",
        ],
        "categories": _build_categories(),
        "hava_read": _build_hava_read(today),
        "tonight": _build_tonight(),
        "sponsor": _build_sponsor(),
        "spotlights": _build_spotlights(),
        "this_week": _build_this_week(),
        "this_week_total": 24,
        "new_on_hava": _build_new_on_hava(),
    }


def _build_categories() -> list[dict[str, Any]]:
    """Pros & services pill row. Tap → chat with category as the query.

    `query` is what gets URL-encoded into the chat link. `warm` flips the
    icon tint (used sparingly to differentiate restaurants from services).
    """
    return [
        {"name": "Plumbers", "query": "find a plumber"},
        {"name": "Electricians", "query": "find an electrician"},
        {"name": "HVAC", "query": "find HVAC service"},
        {"name": "Pool service", "query": "pool service in Havasu"},
        {"name": "Contractors", "query": "find a contractor"},
        {"name": "Restaurants", "query": "where should I eat", "warm": True},
        {"name": "Cleaning", "query": "house cleaning service"},
        {"name": "Auto", "query": "auto repair in Havasu"},
        {"name": "Junk removal", "query": "junk removal"},
        {"name": "Salons", "query": "hair salons in Havasu"},
    ]


def _build_hava_read(today: datetime) -> dict[str, str]:
    """Hava's read pullquote. Step 4 swaps this for the SWR LLM generator."""
    quote_text = (
        "It's a quiet Thursday — but the lake is glass, and "
        "[Channel Brewing](/chat?q=Channel+Brewing) has acoustic on the patio at 8."
    )
    return {
        "quote": quote_text,
        "quote_html": render_voice_links(quote_text),
        "byline": "posted 4:12 pm · refreshed every hour",
    }


def _build_tonight() -> list[dict[str, Any]]:
    """Tonight feature row: 1 big card + 2 stacked cards."""
    return [
        {
            "name": "Channel Brewing Co.",
            "blurb": (
                "Patio over the water, full kitchen till 10. Three-piece "
                "acoustic kicks off at 8 — the regulars start showing up "
                "around 7:30."
            ),
            "meta_text": "Live music · 8 pm",
            "footer_text": "Bridgewater Channel",
            "image_url": "https://images.unsplash.com/photo-1518176258769-f227c798150e?w=1200&q=80&auto=format&fit=crop",
            "image_alt": "Channel Brewing patio over the water at dusk",
            "url": "/chat?q=Channel+Brewing",
            "is_pick": True,
            "feature": True,
            "dot": "accent",
        },
        {
            "name": "Aquatic Center",
            "blurb": "Lap lanes and the family pool. Last entry 7:30, $4 adults.",
            "meta_text": "Open swim · until 8",
            "footer_text": "Register",
            "image_url": "https://images.unsplash.com/photo-1530870110042-98b2cb110834?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Pool lanes at the Lake Havasu Aquatic Center",
            "url": "/chat?q=Aquatic+Center+open+swim",
            "is_pick": False,
            "feature": False,
            "dot": "warm",
        },
        {
            "name": "Yoga at the Library",
            "blurb": "Beginner-friendly, mats provided. $10 cash, no signup.",
            "meta_text": "Drop-in · 6:30",
            "footer_text": "Library, room 2",
            "image_url": "https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Yoga mats laid out in a library room",
            "url": "/chat?q=yoga+at+the+library",
            "is_pick": False,
            "feature": False,
            "dot": "accent",
        },
    ]


def _build_sponsor() -> dict[str, Any] | None:
    """Editorial sponsor record. Returns None to render the fallback card.

    Step 3 will replace this mock with a query against the new `sponsors`
    table. Toggle to None locally to preview the fallback ("This slot is
    open · Sponsor a slot →").
    """
    return {
        "name": "Havasu Outdoor Co.",
        "eyebrow": "Local sponsor · on the water",
        "line": (
            "Kayaks, SUPs, and tubes — picked up on the channel, returned "
            "wherever you finish. Locals get 20% off through May."
        ),
        "cta_label": "Reserve",
        "cta_url": "https://example.com",
        "image_url": "https://images.unsplash.com/photo-1463694775559-eea25ae0a2bd?w=600&q=80&auto=format&fit=crop",
    }


def _build_spotlights() -> list[dict[str, Any]]:
    """Local pros row — three businesses with paid spotlight placement.

    Step 7.5 will source these from `Provider WHERE tier = 'spotlight'
    AND sponsored_until > now()`. Disclosure (the row eyebrow + the
    Spotlight badge on each card) is part of the design contract — see
    BUILD.md "Spotlight architecture".
    """
    return [
        {
            "name": "Aqua Bros Plumbing",
            "category": "Plumbing",
            "blurb": (
                "Family-run, on McCulloch since '04. After-hours line "
                "through Saturday."
            ),
            "image_url": "https://images.unsplash.com/photo-1607400201515-c2c41c07d307?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Plumber tools and pipe fittings",
            "phone_raw": "9285550112",
            "phone": _format_phone("9285550112"),
            "status": "open",
            "status_text": "Open · until 6",
            "url": "/chat?q=Aqua+Bros+Plumbing",
            "dot": "accent",
        },
        {
            "name": "Bridgewater Electric",
            "category": "Electrical",
            "blurb": (
                "Service calls, panels, ceiling fans. Same-week scheduling, "
                "real pickup."
            ),
            "image_url": "https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Electrical panel with breakers",
            "phone_raw": "9285550144",
            "phone": _format_phone("9285550144"),
            "status": "open",
            "status_text": "Open · until 5",
            "url": "/chat?q=Bridgewater+Electric",
            "dot": "warm",
        },
        {
            "name": "Desert Blue Pools",
            "category": "Pool service",
            "blurb": (
                "Weekly maintenance and acid-wash specialists. Insured, in "
                "town since '11."
            ),
            "image_url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Backyard pool with cleaning equipment",
            "phone_raw": "9285550178",
            "phone": _format_phone("9285550178"),
            "status": "closed",
            "status_text": "Closed · opens 8 am",
            "url": "/chat?q=Desert+Blue+Pools",
            "dot": "accent",
        },
    ]


def _build_this_week() -> list[dict[str, Any]]:
    """This week row — 3 events. Step 2 wires to live event queries."""
    return [
        {
            "name": "Bridgewater 5K",
            "blurb": (
                "Annual run along the channel. Family wave at 8. Registration "
                "closes Friday — last year sold out."
            ),
            "meta_text": "Saturday · 7 am",
            "footer_text": "Sign up",
            "image_url": "https://images.unsplash.com/photo-1530549387789-4c1017266635?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Runners at a Lake Havasu 5K",
            "url": "/chat?q=Bridgewater+5K",
            "is_pick": True,
            "dot": "warm",
        },
        {
            "name": "Saturday Art Lab",
            "blurb": "Kids 6–12 — watercolor and collage at the Library. Drop in, free with a library card.",
            "meta_text": "Saturday · 10 am",
            "footer_text": "Library",
            "image_url": "https://images.unsplash.com/photo-1617791160588-241658c0f566?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Watercolor paints and brushes laid out for a kids art class",
            "url": "/chat?q=Saturday+Art+Lab",
            "is_pick": False,
            "dot": "accent",
        },
        {
            "name": "Farmers Market downtown",
            "blurb": "Produce, hot food, crafts. Live music after 10. Closes at 2 sharp.",
            "meta_text": "Sunday · 8 am – 2 pm",
            "footer_text": "Main Street",
            "image_url": "https://images.unsplash.com/photo-1488459716781-31db52582fe9?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Farmers market stalls with fresh produce",
            "url": "/chat?q=Farmers+Market",
            "is_pick": False,
            "dot": "accent",
        },
    ]


def _build_new_on_hava() -> list[dict[str, Any]]:
    """New on Hava row — mix of new businesses and new events.

    The mix is deliberate: the catalog is everything in town, not just
    events. A new Mexican restaurant, a new pickleball league, and a new
    pottery studio side by side reads as the actual breadth Hava covers.
    """
    return [
        {
            "name": "Sunset Cantina",
            "blurb": "Coastal Mexican, opened on the bluff in April. Back patio faces the lake — best after 7.",
            "meta_text": "Restaurant",
            "footer_text": "McCulloch Blvd",
            "image_url": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Lakeside Mexican restaurant patio at sunset",
            "url": "/chat?q=Sunset+Cantina",
            "is_pick": True,
            "is_business": False,
            "dot": "accent",
        },
        {
            "name": "Beginner pickleball",
            "blurb": "Tuesday evenings at the Rec Center, starts May 20. Sign-ups close in 9 days.",
            "meta_text": "Program · 8 weeks",
            "footer_text": "Register",
            "image_url": "https://images.unsplash.com/photo-1554068865-24cecd4e34cd?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Pickleball paddle and ball on a court",
            "url": "/chat?q=Beginner+pickleball",
            "is_pick": False,
            "is_business": False,
            "dot": "warm",
        },
        {
            "name": "Desert Clay Studio",
            "blurb": "Drop-in pottery wheel, Thursday + Saturday. Walk-ins welcome till they fill.",
            "meta_text": "Studio",
            "footer_text": "Off Acoma",
            "image_url": "https://images.unsplash.com/photo-1565193298357-c5b46b0ff68b?w=900&q=80&auto=format&fit=crop",
            "image_alt": "Pottery wheel with clay being shaped",
            "url": "/chat?q=Desert+Clay+Studio",
            "is_pick": False,
            "is_business": True,
            "phone_raw": "9285550199",
            "phone": _format_phone("9285550199"),
            "status": "open",
            "status_text": "Open · until 9",
            "dot": "accent",
        },
    ]
