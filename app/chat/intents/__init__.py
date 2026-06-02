"""Intent-routing layer (Ask Hava intent catalog, Phase 1).

Sits at the front of the Tier-2 path inside ``unified_router._handle_ask``:

    user msg
      -> L0 normalize (reuse app.chat.normalizer.normalize)
      -> L1 rule match  (regex / keyword -> intent + obvious slots)
      -> L2 slot-fill   (service / cuisine / area / age / symptom dicts)
      -> query template (parameterized query over the REAL models)
      -> Hava-voice answer  (or honest "not in the catalog yet" + /contribute)
      -> (no confident intent) -> None -> existing Tier 2 / Tier 3 path

Grounding (verified against the live schema, 2026-06-01):

* Service granularity lives in ``Provider.subcategory`` groups
  (``app/categories/subcategories.py``), NOT a per-trade ``Provider.category``.
  ``plumber`` -> ``home-services`` group + a ``plumb`` name token, never a
  ``plumbing`` category.
* Providers rank by ``google_rating`` / ``google_review_count`` (there is no
  ``rating`` / ``review_count`` column).
* Events use ``date`` + ``start_time`` with ``status == 'live'`` (no
  ``start_at``, no ``cost``, no ``category`` column) -- queried via
  ``app.events.queries.events_in_window``.
* Class ``cost`` and ``age_min`` / ``age_max`` live on ``Program``, not Event.
* Gas reads ``external_conditions_cache`` source ``gas_prices_lhc``.

The whole layer is gated behind the ``USE_INTENT_LAYER`` env flag (default
off) so the production router is unchanged until the layer is enabled.
"""

from __future__ import annotations

from app.chat.intents.resolver import ResolvedIntent, resolve
from app.chat.intents.runtime import IntentAnswer, try_intent_layer

__all__ = ["ResolvedIntent", "resolve", "IntentAnswer", "try_intent_layer"]
