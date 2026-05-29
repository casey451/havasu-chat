"""Analytics events for sponsor + chat-card surfaces (v54 Track B).

One row per render or click written to the ``analytics_events`` table by
:func:`app.analytics.events.record_event`. Sibling to the v52 atomic
``Sponsor.impressions`` / ``Sponsor.clicks`` counters — the counters give
fast roll-ups; this table gives per-event detail (rank, surface, time)
the counters can't reconstruct.

Emit sites:

* ``app/home/sponsor_store.py:active_spotlights`` — one
  ``home.spotlight.impression`` per spotlight rendered.
* ``app/home/router.py:sponsor_click`` — one ``home.spotlight.click``
  (when ``slot=spotlight``) or ``home.sponsor.click`` (any slot) per
  click attribution.
* ``app/chat/component_builders.py:build_card_row`` — one
  ``chat.card_row.impression`` per row render.
* ``app/chat/component_builders.py:build_single_business_card`` — one
  ``chat.single_card.open`` per business card render.

Analytics is best-effort and never raises into the request — see the
try/except wrapper in :func:`record_event`.
"""

from app.analytics.events import record_event

__all__ = ["record_event"]
