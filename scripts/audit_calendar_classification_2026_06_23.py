"""READ-ONLY prod audit for the calendar-classification fix-up (2026-06-23).

Enumerates the live catalog across upcoming dates and reports the ground truth:
  1. Class occurrences landing in "Other classes" — with provider + the provider's
     directory category fields (so we can design provider-aware classification).
  2. Events sitting in the Fitness & classes bucket that are really social/music
     (open mic, trivia, karaoke, bingo, live music, comedy).
  3. Duplicate candidate pairs (same normalized title + date) across times/sources.
  4. Placeholder / implausible times (pre-dawn, bare-noon-no-end) + title-as-venue.

READ-ONLY: queries only, ends with rollback. Repo .env points DATABASE_URL at
prod by default (override=False), matching prior audit workers.

    .venv\\Scripts\\python.exe scripts\\audit_calendar_classification_2026_06_23.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date, time, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emoji-safe console
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Event, Provider  # noqa: E402
from app.events.activity_taxonomy import (  # noqa: E402
    FALLBACK_LABEL,
    classify_class_subgroup,
)
from app.events.class_occurrences import class_occurrences_in_window  # noqa: E402
from app.home.events_views import _group_for  # noqa: E402

_SOCIAL_HINTS = (
    "open mic", "trivia", "karaoke", "bingo", "live music", "comedy",
    "open jam", "jam session", "quiz",
)


def _is_social(title: str) -> bool:
    low = (title or "").lower()
    return any(h in low for h in _SOCIAL_HINTS)


def _provider_cat_fields(db, slug: str) -> dict:
    if not slug:
        return {}
    prov = db.query(Provider).filter(Provider.slug == slug).first()
    if prov is None:
        return {}
    cat_slugs = []
    if prov.entity_id:
        rows = (
            db.query(Category.slug, EntityCategory.is_primary)
            .join(EntityCategory, EntityCategory.category_id == Category.id)
            .filter(EntityCategory.entity_id == prov.entity_id)
            .all()
        )
        cat_slugs = [f"{s}{'*' if p else ''}" for s, p in rows]
    return {
        "name": prov.provider_name,
        "subcategory": prov.subcategory,
        "primary_category": prov.primary_category,
        "category": prov.category,
        "entity_categories": cat_slugs,
    }


def run() -> None:
    today = date.today()
    db = SessionLocal()
    try:
        print(f"=== CALENDAR CLASSIFICATION AUDIT — {today} ===\n")

        # --- 1. CLASS OCCURRENCES: subgroup census + "Other classes" detail ----
        occs = class_occurrences_in_window(
            db, window_start=today, window_end=today + timedelta(days=60)
        )
        # Dedupe to one row per (title, venue, provider) series for readability.
        seen_series = {}
        for o in occs:
            seen_series.setdefault((o.title, o.venue, o.provider_slug), o)
        series = list(seen_series.values())

        sub_counts = Counter(classify_class_subgroup(o.title, o.venue) for o in series)
        print(f"CLASS SERIES (distinct title+venue) in next 60d: {len(series)}")
        print("By subgroup:")
        for label, n in sub_counts.most_common():
            print(f"  {label:20} {n}")

        other = [o for o in series if classify_class_subgroup(o.title, o.venue) == FALLBACK_LABEL]
        print(f"\n--- 'Other classes' series: {len(other)} (with provider category) ---")
        # group by provider to design the mapping
        by_prov = defaultdict(list)
        for o in other:
            by_prov[o.provider_slug or "(no provider)"].append(o.title)
        prov_cache = {}
        for slug, titles in sorted(by_prov.items(), key=lambda kv: -len(kv[1])):
            if slug not in prov_cache:
                prov_cache[slug] = _provider_cat_fields(db, slug if slug != "(no provider)" else "")
            cf = prov_cache[slug]
            print(f"\n  PROVIDER slug={slug}  name={cf.get('name')!r}")
            print(f"    subcat={cf.get('subcategory')!r} primary={cf.get('primary_category')!r} "
                  f"cat={cf.get('category')!r} entity_cats={cf.get('entity_categories')}")
            for t in sorted(set(titles))[:25]:
                print(f"      - {t!r}")

        # --- 2. EVENTS mis-routed into the classes bucket ----------------------
        events = (
            db.query(Event)
            .filter(Event.status == "live", Event.date >= today)
            .all()
        )
        print(f"\n\n=== UPCOMING LIVE EVENTS: {len(events)} ===")
        ev_bucket = Counter()
        social_in_classes = []
        for ev in events:
            gkey = _group_for(
                title=ev.title or "", tags=ev.tags,
                featured=bool(getattr(ev, "featured", False)),
                recurring=bool(ev.is_recurring),
            )
            ev_bucket[gkey] += 1
            if gkey == "classes" and _is_social(ev.title):
                social_in_classes.append((ev.title, ev.location_name, ev.is_recurring, ev.tags))
        print("By bucket:")
        for k, n in ev_bucket.most_common():
            print(f"  {k:10} {n}")
        print(f"\n--- SOCIAL/MUSIC events stuck in Fitness & classes: {len(social_in_classes)} ---")
        for title, loc, rec, tags in social_in_classes[:60]:
            print(f"  {title!r} @ {loc!r} recurring={rec} tags={tags}")

        # --- 3. DUPLICATE candidates: same normalized title + date -------------
        from app.events.dedup import normalize_event_title

        by_key = defaultdict(list)
        for ev in events:
            key = (normalize_event_title(ev.normalized_title or ev.title or ""), ev.date)
            by_key[key].append(ev)
        dups = {k: v for k, v in by_key.items() if len(v) > 1}
        print(f"\n\n=== DUPLICATE CANDIDATES (same title+date): {len(dups)} groups ===")
        for (tnorm, d), rows in sorted(dups.items(), key=lambda kv: -len(kv[1]))[:50]:
            times = [(r.start_time.strftime('%H:%M') if r.start_time else 'TBD', r.source) for r in rows]
            print(f"  {d} {tnorm!r}  x{len(rows)}  -> {times}")

        # --- 4. PLACEHOLDER / implausible times + title-as-venue ---------------
        odd_times = []
        title_as_venue = []
        for ev in events:
            st = ev.start_time
            if st is not None and (st.hour < 6 or (st == time(12, 0) and ev.end_time is None)):
                odd_times.append((ev.title, ev.date, st.strftime('%H:%M'), ev.source))
            if ev.location_name and ev.title and ev.location_name.strip().lower() == ev.title.strip().lower():
                title_as_venue.append((ev.title, ev.source))
        print(f"\n\n=== PLACEHOLDER/ODD TIMES (pre-6am or bare-noon-no-end): {len(odd_times)} ===")
        for t, d, st, src in odd_times[:50]:
            print(f"  {d} {st}  {t!r}  [{src}]")
        print(f"\n=== TITLE-AS-VENUE rows: {len(title_as_venue)} ===")
        for t, src in title_as_venue[:30]:
            print(f"  {t!r}  [{src}]")

    finally:
        db.rollback()  # READ-ONLY guarantee
        db.close()


if __name__ == "__main__":
    run()
