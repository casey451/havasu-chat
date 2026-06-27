"""Provider display name normalization for matching and deduplication.

Also hosts the shared Jinja template-extension helpers
(``register_template_filters`` and ``register_template_globals``) — both
sit here because every ``Jinja2Templates`` site already imports this
module for ``register_template_filters``, so co-locating
``register_template_globals`` keeps the per-router boilerplate to one
import line. If a third extension lands and this module starts feeling
overloaded, factor the two registrars into ``app/core/templates.py``.
"""

from __future__ import annotations

import os
import re
import unicodedata


def clean_name(value: str | None) -> str:
    """Strip vendor marketing tails from a display name.

    Some Google Places sources return names with a pipe character followed by
    marketing copy, e.g. ``"Havasu Hills Apartment Homes | An AllThrive 365
    Affordable Housing Property"``. This helper keeps everything before the
    first ``|`` and trims trailing whitespace.

    Render-time fix only — the underlying ``Provider.name`` column is left
    untouched so the mapping is reversible. Used both as a Jinja filter
    (registered via ``register_template_filters``) and on the chat
    ``build_business_list`` server path so the API surface carries clean names.

    Idempotent: applying twice produces the same result as applying once.
    """
    if not value:
        return ""
    return value.split("|", 1)[0].rstrip()


def time12h(value: str | None) -> str:
    """Convert a 24-hour ``"HH:MM"`` string to a 12-hour label.

    ``"12:00"`` → ``"12 PM"``, ``"21:00"`` → ``"9 PM"``, ``"18:30"`` → ``"6:30 PM"``.
    Place-page hours store structured spans as 24-hour strings, but a consumer
    audience reads 12-hour (site review §6). Unparseable input is returned
    unchanged.
    """
    if not value:
        return value or ""
    s = str(value).strip()
    hh, _, mm = s.partition(":")
    if not (hh.isdigit() and mm.isdigit()):
        return s
    h, m = int(hh), int(mm)
    if not (0 <= h <= 24 and 0 <= m < 60):
        return s
    mer = "AM" if (h % 24) < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {mer}" if m == 0 else f"{h12}:{m:02d} {mer}"


def register_template_filters(templates_or_env: "object") -> None:
    """Register CLUSTER-08 Jinja filters on a ``Jinja2Templates`` or ``Environment``.

    The codebase has multiple ``Jinja2Templates`` instances (one per router
    module). Each must call this helper after construction so ``clean_name``
    (and any future shared filters) is available regardless of which router
    rendered the template. Without this, templates that work in dev (where
    the main app's instance is in scope) break under tests that import a
    subset of routers directly.

    Duck-typed argument: pass either a ``fastapi.templating.Jinja2Templates``
    (which exposes ``.env``) or a raw ``jinja2.Environment``. Tests that build
    a bare ``Environment`` for direct template rendering should call this
    helper too — see ``tests/test_phase6_hava_card.py`` for an example.
    """
    env = getattr(templates_or_env, "env", templates_or_env)
    env.filters["clean_name"] = clean_name
    env.filters["time12h"] = time12h
    # SEO P1.8: shared meta-description sanitizer (newline collapse +
    # sentence-boundary truncation) for description/og:description tags.
    from app.seo.meta import meta_description

    env.filters["meta_desc"] = meta_description


def register_template_globals(templates_or_env: "object") -> None:
    """Register shared Jinja globals (Q5 Plausible analytics, future shared
    template-wide values) on a ``Jinja2Templates`` or ``Environment``.

    Currently exposes ``plausible_domain``: the value of the
    ``PLAUSIBLE_DOMAIN`` env var (whitespace-stripped, with empty string
    coerced to ``None``). When unset, every ``_partials/plausible.html``
    include is a no-op — local dev never loads the script tag and never
    sends events, so no consent banner is required.

    **Re-reads the env var on every call** rather than caching at import
    time. That keeps tests honest: they can ``monkeypatch.setenv`` then
    re-invoke this registrar against an already-constructed ``templates``
    instance and the global will refresh. The per-call cost is one
    ``os.getenv`` lookup — negligible at app-startup time, which is when
    each router calls this.

    Duck-typed argument: pass either a ``fastapi.templating.Jinja2Templates``
    (which exposes ``.env``) or a raw ``jinja2.Environment``. Mirrors the
    contract of ``register_template_filters`` above.
    """
    env = getattr(templates_or_env, "env", templates_or_env)
    raw = (os.getenv("PLAUSIBLE_DOMAIN") or "").strip()
    env.globals["plausible_domain"] = raw or None
    # SEO P1.0/P1.3: absolute-https canonical / og:url builders, shared with the
    # base layout so every page emits one self-canonical from one origin source.
    from app.seo.urls import absolute_url, canonical_url

    env.globals["canonical_url"] = canonical_url
    env.globals["absolute_url"] = absolute_url
    # 1.6: share-safe provider og:image / JSON-LD image — coerces to an absolute
    # house-image fallback when a hero URL is missing or points at a transient
    # Google host whose URL rotates and breaks cached social-card previews.
    from app.providers.photo_urls import social_image_url

    env.globals["social_image_url"] = social_image_url
    # 1.9b: content-hash ``?v=`` fingerprinting for /static assets. Templates that
    # adopt ``static_url('/static/...')`` get the immutable 1yr cache from
    # CachedStaticFiles; the hash changes on file change so it can't go stale.
    from app.core.static_assets import static_url

    env.globals["static_url"] = static_url


def _norm_provider_name(name: str) -> str:
    """Normalize a provider display name for comparison (dedupe + program backfill).

    Two layers:

    1. **Portable Unicode folding** — NFKC, collapse whitespace, lowercase, map en/em
       dash and minus variants to ASCII hyphen, map curly quotes and apostrophes to
       straight ASCII quotes, strip soft hyphen, replace NBSP with space. Safe for
       any locale; keeps matching stable when master vs. instructions differ only by
       typography.

    2. **Non-portable Lake Havasu section 9 suffix folds** — end-anchored tails used because
       some legacy program-import rows used a shorter provider_name
       than the canonical business header in Section 9 (e.g. trailing (ACPA), - Sonics,
       - Lake Havasu City). Remove these once seed-data
       naming is canonicalized during **Phase 8** seed-data verification (owner phone
       review); then delete the suffix regexes here so normalization stays generic.

    Phase 1.3 uses this for Provider upsert keys; Phase 1.4 backfill imports the same
    function so exact-match keys always agree with the seed.
    """
    s = unicodedata.normalize("NFKC", (name or "").strip())
    for ch in ("\u2013", "\u2014", "\u2012", "\u2015", "\u2212"):
        s = s.replace(ch, "-")
    for old, new in (
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u201b", "'"),
        ("\u2032", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u2033", '"'),
    ):
        s = s.replace(old, new)
    s = s.replace("\u00a0", " ").replace("\u00ad", "")
    s = " ".join(s.lower().split())
    s = re.sub(r"\s*\(acpa\)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+sonics\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+lake havasu city\s*$", "", s, flags=re.IGNORECASE)
    return " ".join(s.split())
