"""Lane B5 — conversational "/plan my day/weekend" itinerary builder.

Assembly-only: a time-sequenced, multi-stop itinerary is composed ENTIRELY from
real catalog data (providers via the intent query layer, events via
``app.events.queries.events_in_window``). No data source is added and no venue,
time, or event is ever invented — an empty slot is surfaced honestly with a
``/contribute`` nudge.
"""
