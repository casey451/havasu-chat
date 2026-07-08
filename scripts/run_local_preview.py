"""Local preview harness — boot the app against a throwaway SQLite DB.

Why this exists: the repo ``.env`` points ``DATABASE_URL`` at the **production**
Railway Postgres, and serving pages writes to the conditions cache / analytics.
Booting uvicorn normally would therefore talk to prod. This launcher forces an
isolated local SQLite file (so visual QA via the preview tools never touches
prod), runs migrations, seeds a tiny fixture set, and serves with the v4
redesign flag on.

Run via the ``havasu-local`` launch profile (.claude/launch.json) or directly:

    .venv\\Scripts\\python.exe scripts/run_local_preview.py

Dev-only tooling — not imported by the app, not used in CI or prod.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, time
from pathlib import Path

# Run-as-a-file puts scripts/ on sys.path, not the repo root; add it so ``app``
# imports resolve regardless of the launcher's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Force an isolated, NON-prod environment BEFORE any app import. ---------
# get_database_url() falls back to SQLite when DATABASE_URL is blank, but we set
# an explicit throwaway file so there is zero chance of hitting prod. python-
# dotenv (load_dotenv, override=False) will NOT clobber an already-set var, so
# the prod .env line is ignored.
_DB_FILE = Path(tempfile.gettempdir()) / "havasu_local_preview.sqlite"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.resolve().as_posix()}"
os.environ["HOME_REDESIGN"] = "1"  # serve the v4 redesign homepage
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("AUTH_DEV_MODE", "1")
os.environ.setdefault("AUTH_MAGIC_LINK_BASE_URL", "http://localhost:8099")
os.environ.setdefault("R2_ACCESS_KEY_ID", "local")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "local")
os.environ.setdefault("R2_ENDPOINT_URL", "https://local.r2.cloudflarestorage.com")
os.environ.setdefault("R2_BUCKET_NAME", "local-bucket")
os.environ.setdefault("R2_PUBLIC_URL_BASE", "https://local.r2.dev")

PROVIDER_SLUG = "havasu-preview-lanes"


def _seed() -> None:
    """Idempotently seed the few rows the Phase-1 visual checks need.

    Deliberately small: a Provider with 24h-format structured hours (place-page
    hours render) and two MovieShowtimes today (home "At the movies" strip
    spacing). The curated family venues render straight from
    ``app.home.family_venues`` with no DB rows, so the events-feed noon-range /
    redundant-category checks need no seeding.
    """
    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import Entity, Event, MovieShowtime, Provider

    weekday_hours = [{"open": "12:00", "close": "21:00"}]
    structured = {
        "monday": weekday_hours,
        "tuesday": weekday_hours,
        "wednesday": weekday_hours,
        "thursday": weekday_hours,
        "friday": [{"open": "12:00", "close": "23:00"}],
        "saturday": [{"open": "12:00", "close": "23:00"}],
        "sunday": [{"open": "12:00", "close": "21:00"}],
    }
    with SessionLocal() as db:
        if not db.scalars(select(Provider).where(Provider.slug == PROVIDER_SLUG)).first():
            ent = Entity(
                entity_type="commercial",
                slug="havasu-preview-lanes-ent",
                name="Havasu Preview Lanes",
                source="local-preview",
            )
            db.add(ent)
            db.flush()
            db.add(
                Provider(
                    provider_name="Havasu Preview Lanes",
                    category="Bowling",
                    primary_category="things-to-do",
                    slug=PROVIDER_SLUG,
                    address="123 Preview Dr, Lake Havasu City, AZ",
                    hours_structured=structured,
                    is_active=True,
                    draft=False,
                    source="local-preview",
                    entity_id=ent.id,
                )
            )
            # A dated event AT that venue, so the event detail can link back to
            # the provider profile (§1 event->venue backlink), plus a midnight /
            # Time-TBD event for the chat-agenda check (§1 "12 am" dump).
            db.add(
                Event(
                    id="preview-event-1",
                    title="Cosmic Bowling Night",
                    normalized_title="cosmic bowling night",
                    date=date.today(),
                    start_time=time(21, 0),
                    end_time=time(23, 59),
                    location_name="Havasu Preview Lanes",
                    location_normalized="havasu preview lanes",
                    description="Glow-in-the-dark bowling with music. $20 per lane.",
                    tags=["family", "music"],
                    status="live",
                    source="local-preview",
                    created_by="seed",
                    entity_id=ent.id,
                )
            )
            db.add(
                Event(
                    id="preview-event-tbd",
                    title="Lake Havasu Farmers Market",
                    normalized_title="lake havasu farmers market",
                    date=date.today(),
                    start_time=time(0, 0),  # unknown time -> renders "Time TBD"
                    end_time=None,
                    location_name="Main Street Plaza",
                    location_normalized="main street plaza",
                    description="Local produce and crafts.",
                    tags=["family"],
                    status="live",
                    source="local-preview",
                    created_by="seed",
                    entity_id=ent.id,
                )
            )
        # WS10 hub QA seed: an Eat & Drink venue open past 10 PM (so /night's
        # "Late-night kitchens" list renders) and a live-music event today (so
        # /night's "Live music tonight" section renders). Idempotent by slug/id.
        if not db.scalars(
            select(Provider).where(Provider.slug == "havasu-preview-cantina")
        ).first():
            cant = Entity(
                entity_type="commercial",
                slug="havasu-preview-cantina-ent",
                name="Havasu Preview Cantina",
                source="local-preview",
            )
            db.add(cant)
            db.flush()
            late = [{"open": "16:00", "close": "23:30"}]
            db.add(
                Provider(
                    provider_name="Havasu Preview Cantina",
                    category="restaurant",
                    google_primary_category="restaurant",
                    # subcategory drives derive_primary_category → "eat-drink"
                    # (the route_provider_filter primary), matching real data.
                    subcategory="restaurants",
                    slug="havasu-preview-cantina",
                    address="500 Preview Blvd, Lake Havasu City, AZ",
                    hours_structured={d: late for d in (
                        "monday", "tuesday", "wednesday", "thursday",
                        "friday", "saturday", "sunday",
                    )},
                    is_active=True,
                    draft=False,
                    source="local-preview",
                    entity_id=cant.id,
                )
            )
            db.add(
                Event(
                    id="preview-event-music",
                    title="Live Music: The Preview Band",
                    normalized_title="live music: the preview band",
                    date=date.today(),
                    start_time=time(20, 0),
                    end_time=time(23, 0),
                    location_name="Havasu Preview Cantina",
                    location_normalized="havasu preview cantina",
                    description="Live band on the patio. No cover.",
                    tags=["music"],
                    status="live",
                    source="local-preview",
                    created_by="seed",
                    entity_id=cant.id,
                )
            )
        if not db.scalars(
            select(MovieShowtime).where(MovieShowtime.source == "local-preview")
        ).first():
            today = date.today()
            # "Toy Story 5" deliberately plays at BOTH theaters so the home-strip
            # dedup (§4e) is exercised — it must appear once, not twice.
            films = [
                ("Star Cinemas", "star-cinemas", "Disclosure Day", time(19, 0)),
                ("Movies Havasu", "movies-havasu", "Toy Story 5", time(18, 30)),
                ("Star Cinemas", "star-cinemas", "Toy Story 5", time(20, 0)),
            ]
            for i, (theater, tslug, film, t) in enumerate(films):
                db.add(
                    MovieShowtime(
                        source="local-preview",
                        source_stable_id=f"local-{i}",
                        theater_slug=tslug,
                        theater_name=theater,
                        film_title=film,
                        show_date=today,
                        show_time=t,
                    )
                )
        db.commit()


def main() -> None:
    from app.db.database import init_db

    init_db()
    _seed()

    import uvicorn

    print(f"[local-preview] DB: {os.environ['DATABASE_URL']}")
    print(f"[local-preview] provider profile: /provider/{PROVIDER_SLUG}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8099, reload=False, log_level="info")


if __name__ == "__main__":
    main()
