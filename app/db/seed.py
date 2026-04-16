"""
Seed the database with sample Lake Havasu City community events.
Idempotent: each event is tagged with __seed__:lhc_XXX; re-running skips existing seeds.
"""
from __future__ import annotations

import sys
from datetime import date, time, timedelta

from dotenv import load_dotenv

from app.core.extraction import _embedding_input
from app.core.search import generate_query_embedding
from app.db.database import SessionLocal, init_db
from app.db.models import Event
from app.schemas.event import EventCreate

load_dotenv()

SEED_TAG_PREFIX = "__seed__:lhc_"


def _seed_tag(index: int) -> str:
    return f"{SEED_TAG_PREFIX}{index:03d}"


def _existing_seed_indices(db) -> set[int]:
    found: set[int] = set()
    for event in db.query(Event).all():
        for tag in event.tags or []:
            if isinstance(tag, str) and tag.startswith(SEED_TAG_PREFIX):
                try:
                    idx = int(tag.replace(SEED_TAG_PREFIX, ""))
                    found.add(idx)
                except ValueError:
                    continue
    return found


def _build_seed_rows(today: date) -> list[dict]:
    """15 rows: title, days_ahead, start_t, location, description, extra_tags."""
    return [
        {
            "title": "Little Kickers Youth Soccer Clinic",
            "days": 3,
            "t": time(9, 0),
            "location": "Rotary Community Park, Lake Havasu City",
            "description": "Intro soccer skills for ages 5–8 with local volunteer coaches. Cleats optional; bring water and sunscreen.",
            "tags": ["kids", "sports", "soccer"],
            "event_url": "https://example.com/lhc-seed-01-soccer",
            "contact_name": "Alex Rivera",
            "contact_phone": "928-855-1001",
        },
        {
            "title": "Morning Pickleball Open Play",
            "days": 4,
            "t": time(7, 30),
            "location": "Kenyon Field Courts, Lake Havasu City",
            "description": "All skill levels welcome for doubles round-robin. Paddles available to borrow while supplies last.",
            "tags": ["fitness", "pickleball", "adults"],
            "event_url": "https://example.com/lhc-seed-02-pickleball",
            "contact_name": "Jordan Lee",
            "contact_phone": "928-855-1002",
        },
        {
            "title": "London Bridge Beach Farmers Market",
            "days": 5,
            "t": time(8, 0),
            "location": "London Bridge Beach, Lake Havasu City",
            "description": "Local produce, baked goods, and handmade crafts along the waterfront every Saturday morning.",
            "tags": ["community", "family", "outdoors"],
            "event_url": "https://example.com/lhc-seed-03-market",
            "contact_name": "Farmers Market Booth",
            "contact_phone": "928-855-1003",
        },
        {
            "title": "Sunrise Yoga by the Channel",
            "days": 6,
            "t": time(6, 30),
            "location": "Channel Walk, Lake Havasu City",
            "description": "Gentle flow yoga as the sun comes up over the water. Bring a mat or towel; donations appreciated.",
            "tags": ["fitness", "yoga", "wellness"],
            "event_url": "https://example.com/lhc-seed-04-yoga",
            "contact_name": "Sam Chen",
            "contact_phone": "928-855-1004",
        },
        {
            "title": "Havasu Youth Basketball Skills Night",
            "days": 8,
            "t": time(18, 0),
            "location": "Lake Havasu Aquatic Center Gym, Lake Havasu City",
            "description": "Dribbling, shooting, and scrimmages for middle school players with certified trainers.",
            "tags": ["kids", "sports", "basketball"],
            "event_url": "https://example.com/lhc-seed-05-basketball",
            "contact_name": "Coach Morgan",
            "contact_phone": "928-855-1005",
        },
        {
            "title": "Community Theater Open Auditions",
            "days": 9,
            "t": time(19, 0),
            "location": "Performing Arts Center, Lake Havasu City",
            "description": "Spring musical auditions for teens and adults. Prepare a one-minute song; callbacks posted online.",
            "tags": ["arts", "theater", "community"],
            "event_url": "https://example.com/lhc-seed-06-theater",
            "contact_name": "Riley Brooks",
            "contact_phone": "928-855-1006",
        },
        {
            "title": "Tadpole Swim Lessons (Level 1)",
            "days": 10,
            "t": time(10, 0),
            "location": "Lake Havasu Aquatic Center, Lake Havasu City",
            "description": "Small-group beginner swim lessons for ages 4–6 with certified instructors in the shallow pool.",
            "tags": ["kids", "swim", "aquatic"],
            "event_url": "https://example.com/lhc-seed-07-swim",
            "contact_name": "Aquatic Desk",
            "contact_phone": "928-855-1007",
        },
        {
            "title": "Sara Park Trail Group Hike",
            "days": 12,
            "t": time(7, 0),
            "location": "Sara Park Trailhead, Lake Havasu City",
            "description": "Moderate desert hike with ranger tips on local plants and wildlife. Bring 2 liters of water and a hat.",
            "tags": ["outdoors", "hiking", "family"],
            "event_url": "https://example.com/lhc-seed-08-hike",
            "contact_name": "Trail Host",
            "contact_phone": "928-855-1008",
        },
        {
            "title": "Preschool Story & Craft Hour",
            "days": 14,
            "t": time(10, 30),
            "location": "Lake Havasu City Library",
            "description": "Stories, songs, and a simple craft for ages 2–5 with caregivers. Free; no registration required.",
            "tags": ["kids", "education", "library"],
            "event_url": "https://example.com/lhc-seed-09-library",
            "contact_name": "Youth Librarian",
            "contact_phone": "928-855-1009",
        },
        {
            "title": "Silver Sneakers Strength Class",
            "days": 15,
            "t": time(11, 0),
            "location": "Havasu Community Center, Lake Havasu City",
            "description": "Low-impact strength and balance for active adults 65+. Chair modifications available for every exercise.",
            "tags": ["fitness", "seniors", "community"],
            "event_url": "https://example.com/lhc-seed-10-silver",
            "contact_name": "Community Center Front Desk",
            "contact_phone": "928-855-1010",
        },
        {
            "title": "Watercolor Desert Landscapes Workshop",
            "days": 18,
            "t": time(17, 30),
            "location": "Arts & Culture Hub, Lake Havasu City",
            "description": "Two-hour painting class inspired by local desert vistas; materials included for the first twelve sign-ups.",
            "tags": ["arts", "workshop", "adults"],
            "event_url": "https://example.com/lhc-seed-11-watercolor",
            "contact_name": "Studio Lead",
            "contact_phone": "928-855-1011",
        },
        {
            "title": "Bridge City 5K & Fun Walk",
            "days": 20,
            "t": time(7, 15),
            "location": "London Bridge Resort Area, Lake Havasu City",
            "description": "Chip-timed 5K plus untimed family walk benefiting local schools. Strollers welcome on the walk route.",
            "tags": ["community", "running", "charity"],
            "event_url": "https://example.com/lhc-seed-12-5k",
            "contact_name": "Race Director",
            "contact_phone": "928-855-1012",
        },
        {
            "title": "Youth Karate Belt Review",
            "days": 22,
            "t": time(16, 30),
            "location": "Desert Sun Karate Dojo, Lake Havasu City",
            "description": "Color-belt testing and demonstration for youth students; friends and family invited to watch.",
            "tags": ["kids", "martial arts", "karate"],
            "event_url": "https://example.com/lhc-seed-13-karate",
            "contact_name": "Sensei Kim",
            "contact_phone": "928-855-1013",
        },
        {
            "title": "Acoustic Sunset at the Channel",
            "days": 25,
            "t": time(18, 30),
            "location": "Channel Waterfront Stage, Lake Havasu City",
            "description": "Local singer-songwriters and light bites from food trucks; lawn seating—bring a blanket or low chair.",
            "tags": ["music", "community", "outdoors"],
            "event_url": "https://example.com/lhc-seed-14-sunset",
            "contact_name": "Waterfront Events",
            "contact_phone": "928-855-1014",
        },
        {
            "title": "STEM Robotics Saturday Lab",
            "days": 27,
            "t": time(13, 0),
            "location": "Mohave Community College — Lake Havasu Campus",
            "description": "Hands-on LEGO robotics challenges for ages 10–14; mentors from the high school robotics club assist teams.",
            "tags": ["education", "stem", "teens"],
            "event_url": "https://example.com/lhc-seed-15-stem",
            "contact_name": "MCC Outreach",
            "contact_phone": "928-855-1015",
        },
    ]


def run_seed() -> tuple[int, int]:
    """
    Insert missing seed events. Returns (inserted_count, skipped_count).
    """
    init_db()
    today = date.today()
    rows = _build_seed_rows(today)

    inserted = 0
    skipped = 0

    with SessionLocal() as db:
        existing = _existing_seed_indices(db)
        for i, row in enumerate(rows, start=1):
            if i in existing:
                skipped += 1
                continue

            event_date = today + timedelta(days=min(row["days"], 30))
            if event_date < today:
                event_date = today + timedelta(days=1)

            tags = row["tags"] + [_seed_tag(i)]
            payload_dict = {
                "title": row["title"],
                "date": event_date,
                "start_time": row["t"],
                "end_time": None,
                "location_name": row["location"],
                "description": row["description"],
                "event_url": row["event_url"],
                "contact_name": row["contact_name"],
                "contact_phone": row["contact_phone"],
                "tags": tags,
                "embedding": None,
                "status": "live",
                "created_by": "seed",
                "admin_review_by": None,
            }
            emb_input = _embedding_input(payload_dict)
            embedding = generate_query_embedding(emb_input)

            payload = EventCreate(
                title=row["title"],
                date=event_date,
                start_time=row["t"],
                end_time=None,
                location_name=row["location"],
                description=row["description"],
                event_url=row["event_url"],
                contact_name=row["contact_name"],
                contact_phone=row["contact_phone"],
                tags=tags,
                embedding=embedding,
                status="live",
                created_by="seed",
                admin_review_by=None,
            )
            ev = Event.from_create(payload)
            db.add(ev)
            inserted += 1

        db.commit()

    return inserted, skipped


def main() -> None:
    inserted, skipped = run_seed()
    print(f"Seed complete: inserted={inserted}, skipped (already present)={skipped}")
    with SessionLocal() as db:
        total_seed = sum(
            1
            for e in db.query(Event).all()
            if any(isinstance(t, str) and t.startswith(SEED_TAG_PREFIX) for t in (e.tags or []))
        )
        total_live = db.query(Event).filter(Event.status == "live").count()
        print(f"Events with seed tags in DB: {total_seed}")
        print(f"Total live events: {total_live}")
    if total_seed < 15:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
