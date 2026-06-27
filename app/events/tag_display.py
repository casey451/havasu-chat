"""Display-time filtering of event tags (site review §5).

``Event.tags`` mixes two kinds of strings:

* **User-facing tags** — friendly bare words (``music``, ``family``,
  ``sports``, ``aquatics``) meant to be shown to visitors.
* **Internal taxonomy keys** — namespaced ``KEY:value`` tokens
  (``activity:golf``, ``facet:special``, ``audience:youth``, and legacy
  upper-case ``ACTIVITY:TRAMPOLINE``) stamped by
  :mod:`app.events.activity_taxonomy` purely for routing/classification.

The namespaced keys are not meant for human eyes; they leaked onto the event
detail page and into chat category labels. ``public_event_tags`` strips them,
leaving only the friendly tags in their original order.
"""

from __future__ import annotations


def _is_internal_tag(tag: str) -> bool:
    """True for namespaced taxonomy keys like ``activity:golf`` / ``FACET:SPECIAL``.

    Every internal key is of the form ``namespace:value``; user-facing tags are
    bare words with no colon, so the colon is a reliable discriminator.
    """
    return ":" in tag


def public_event_tags(tags: object) -> list[str]:
    """Return only the user-facing tags, dropping internal ``KEY:value`` keys.

    Order is preserved. Non-string, blank, and namespaced entries are removed.
    Accepts any iterable (or ``None``) so callers can pass ``event.tags`` raw.
    """
    if not tags:
        return []
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        s = t.strip()
        if not s or _is_internal_tag(s):
            continue
        out.append(s)
    return out
