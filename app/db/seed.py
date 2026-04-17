# TODO: Verify recurring-event dates and placeholder phones against venues before major launch
"""
Seed the database with real Lake Havasu City community events.
Idempotent: each event is tagged with __seed__:lhc_XXX; re-running skips existing seeds.
"""
from __future__ import annotations

import sys
from datetime import date, time

from app.bootstrap_env import ensure_dotenv_loaded
from app.core.extraction import _embedding_input
from app.core.search import generate_query_embedding
from app.db.database import SessionLocal, init_db
from app.db.models import Event
from app.schemas.event import EventCreate

ensure_dotenv_loaded()

SEED_TAG_PREFIX = "__seed__:lhc_"

# LAKE HAVASU CITY — REAL SEED DATA (next ~30 days + listed anchor dates)
# Sourced from: golakehavasu.com, lhcaz.gov, riverscenemagazine.com,
# downtownlakehavasu.com, allevents.in, desertstormlhc.com, heathotel.com,
# thekawslhc.com, lakehavasufarmersmarket.com
#
# Reference date for copy: April 16, 2026
# Date range intent: April 16 – May 16, 2026 (some entries extend slightly per source list)
REAL_SEED_EVENTS: list[dict[str, str | list[str]]] = [
    {
        "title": "Desert Storm Poker Run & Shootout",
        "date": "2026-05-20",
        "start_time": "14:00",
        "end_time": "20:00",
        "location_name": "Bridgewater Channel, Lake Havasu City",
        "description": (
            "The largest performance boating event in the Western US. A world-class collection "
            "of the most prestigious performance boats from across the nation. Free to watch "
            "from the shoreline. Runs April 22–25 with daily events."
        ),
        "tags": ["outdoor", "boats", "racing", "spectator", "free", "family", "signature"],
        "event_url": "https://www.desertstormlhc.com",
        "contact_name": "Desert Storm",
        "contact_phone": "928-453-3444",
    },
    {
        "title": "Country Divas at Havasu Landing Casino",
        "date": "2026-05-02",
        "start_time": "19:00",
        "end_time": "22:00",
        "location_name": "Havasu Landing Casino, Lake Havasu City",
        "description": (
            "Country Divas live concert at Havasu Landing Casino. A night of country music "
            "tribute performances. Tickets available through the casino. Must be 21+."
        ),
        "tags": ["music", "adults", "concert", "country", "evening"],
        "event_url": "https://www.allevents.in/lake-havasu-city",
        "contact_name": "Havasu Landing Casino",
        "contact_phone": "928-855-0777",
    },
    {
        "title": "Sky Lantern Festival by Lights Over America",
        "date": "2026-05-30",
        "start_time": "18:00",
        "end_time": "22:00",
        "location_name": "Lake Havasu, AZ",
        "description": (
            "A magical evening where thousands of biodegradable sky lanterns light up the night "
            "sky over Lake Havasu. Family-friendly festival with food, music, and lantern launch. "
            "Tickets required."
        ),
        "tags": ["family", "evening", "festival", "outdoor", "lights", "kids"],
        "event_url": "https://www.lightsoveramerica.com",
        "contact_name": "Lights Over America",
        "contact_phone": "928-555-0110",
    },
    {
        "title": "Desert Island Tiki Night",
        "date": "2026-05-16",
        "start_time": "17:00",
        "end_time": "22:00",
        "location_name": "Heat Hotel, 1420 McCulloch Blvd N",
        "description": (
            "Tropical tiki-themed evening at Heat Hotel with signature cocktails, island vibes, "
            "and live music. Dress code encouraged. 21 and over."
        ),
        "tags": ["adults", "nightlife", "cocktails", "music", "evening"],
        "event_url": "https://www.heathotel.com",
        "contact_name": "Heat Hotel",
        "contact_phone": "928-854-2833",
    },
    {
        "title": "Motor Madness Cruise-In",
        "date": "2026-06-07",
        "start_time": "13:00",
        "end_time": "17:00",
        "location_name": "Lighthouse Lounge, Lake Havasu City",
        "description": (
            "Classic car cruise-in event at Lighthouse Lounge. Come show your ride or just enjoy "
            "looking at the beautiful cars and bikes on display. Food and drinks available."
        ),
        "tags": ["cars", "outdoor", "community", "weekend", "family"],
        "event_url": "https://www.allevents.in/lake-havasu-city",
        "contact_name": "Lighthouse Lounge",
        "contact_phone": "928-555-0111",
    },
    {
        "title": "Crosscutt Live at The Office Cocktail Lounge",
        "date": "2026-06-19",
        "start_time": "20:00",
        "end_time": "23:00",
        "location_name": "The Office Cocktail Lounge & Grill, Lake Havasu City",
        "description": (
            "Live music with Crosscutt at The Office Cocktail Lounge. Rock and classic covers. "
            "Full bar and grill menu available. 21+."
        ),
        "tags": ["music", "adults", "nightlife", "live music", "rock", "evening"],
        "event_url": "https://www.allevents.in/lake-havasu-city",
        "contact_name": "The Office Cocktail Lounge",
        "contact_phone": "928-855-6263",
    },
    {
        "title": "Legends Tattoo Show 2026",
        "date": "2026-07-15",
        "start_time": "10:00",
        "end_time": "18:00",
        "location_name": "London Bridge, Lake Havasu City",
        "description": (
            "Hosted by Lakeside Tattoo Art Collective. Tattoo artists from across the region, "
            "live tattooing, vendors, art, and community. Three-day event at the London Bridge."
        ),
        "tags": ["art", "adults", "tattoo", "festival", "culture"],
        "event_url": "https://www.allevents.in/lake-havasu-city",
        "contact_name": "Lakeside Tattoo Art Collective",
        "contact_phone": "928-555-0112",
    },
    {
        "title": "Lake Havasu Farmers Market",
        "date": "2026-06-13",
        "start_time": "08:00",
        "end_time": "12:00",
        "location_name": "The KAWS, 2144 McCulloch Blvd N",
        "description": (
            "Every 2nd and 4th Saturday — fresh produce, cheese, bread, eggs, baked goods, "
            "fresh fish, soaps, honey, teas, plants, microgreens, coffee, candles, art, "
            "crafts, jewelry, pottery and more. Downtown community favorite."
        ),
        "tags": ["market", "food", "family", "community", "weekend", "outdoor", "shopping"],
        "event_url": "https://www.lakehavasufarmersmarket.com",
        "contact_name": "The KAWS",
        "contact_phone": "928-555-0113",
    },
    {
        "title": "Havasu Sunset Market",
        "date": "2026-06-20",
        "start_time": "17:00",
        "end_time": "21:00",
        "location_name": "London Bridge Beach walkway, Lake Havasu City",
        "description": (
            "Evening sunset market along the channel — local makers, street food, and live acoustic "
            "music as the sun goes down. Free entry; family friendly."
        ),
        "tags": ["market", "sunset", "shopping", "family", "evening", "outdoor"],
        "event_url": "https://www.golakehavasu.com/events",
        "contact_name": "Havasu Sunset Market",
        "contact_phone": "928-555-0116",
    },
    {
        "title": "First Friday Downtown Lake Havasu",
        "date": "2026-06-05",
        "start_time": "18:00",
        "end_time": "21:00",
        "location_name": "Downtown Lake Havasu, Main Street",
        "description": (
            "First Friday of every month — art scene event in downtown Havasu. Galleries open, "
            "local artists, live music, food trucks, and community vibes. Family friendly and free."
        ),
        "tags": ["art", "music", "family", "free", "community", "evening", "downtown"],
        "event_url": "https://downtownlakehavasu.com/events/",
        "contact_name": "Downtown Lake Havasu",
        "contact_phone": "928-555-0114",
    },
    {
        "title": "July 4th Fireworks & Celebration",
        "date": "2026-07-04",
        "start_time": "21:00",
        "end_time": "22:30",
        "location_name": "London Bridge / Bridgewater Channel, Lake Havasu City",
        "description": (
            "Independence Day fireworks over the lake with viewing along the channel and London Bridge. "
            "Arrive early for parking; family-friendly."
        ),
        "tags": ["fireworks", "july 4", "4th of july", "family", "holiday", "evening"],
        "event_url": "https://www.golakehavasu.com/events",
        "contact_name": "City of Lake Havasu City",
        "contact_phone": "928-855-2115",
    },
    {
        "title": "Open Swim — Aquatic Center",
        "date": "2026-06-06",
        "start_time": "12:00",
        "end_time": "16:00",
        "location_name": "Lake Havasu City Aquatic Center, 100 Park Ave",
        "description": (
            "Every Saturday year-round. Indoor wave pool, waterslide, kiddie lagoon, splash pad, "
            "and hot tubs. $6 adults, $3 seniors/kids, under 3 free. Additional days in June and July."
        ),
        "tags": ["kids", "family", "swimming", "water", "indoor", "weekend"],
        "event_url": "https://www.lhcaz.gov/parks-recreation/aquatic-center",
        "contact_name": "Aquatic Center",
        "contact_phone": "928-453-8686",
    },
    {
        "title": "Swim Lessons for Kids — Aquatic Center",
        "date": "2026-05-11",
        "start_time": "09:00",
        "end_time": "10:00",
        "location_name": "Lake Havasu City Aquatic Center, 100 Park Ave",
        "description": (
            "Swim lessons for children ages 6 months and up. Certified instructors, classes "
            "tailored to skill level. Sessions run Monday through Thursday over two-week blocks. "
            "Call to register."
        ),
        "tags": ["kids", "swimming", "lessons", "toddler", "youth", "weekdays"],
        "event_url": "https://www.lhcaz.gov/parks-recreation/open-swim-schedule",
        "contact_name": "Aquatic Center",
        "contact_phone": "928-453-8686",
    },
    {
        "title": "Aqua Aerobics — Aquatic Center",
        "date": "2026-05-08",
        "start_time": "08:00",
        "end_time": "09:00",
        "location_name": "Lake Havasu City Aquatic Center, 100 Park Ave",
        "description": (
            "Shallow and deep water fitness class — full body workout, all levels. "
            "Improves aerobic fitness and builds endurance. Drop-in $5. "
            "Other classes include Ai-Chi, water walking, and aqua Zumba."
        ),
        "tags": ["fitness", "adults", "water", "exercise", "seniors", "weekdays"],
        "event_url": "https://www.lhcaz.gov/parks-recreation/open-swim-schedule",
        "contact_name": "Aquatic Center",
        "contact_phone": "928-453-8686",
    },
    {
        "title": "Havasu Stingrays Swim Team Tryouts",
        "date": "2026-06-21",
        "start_time": "09:00",
        "end_time": "11:00",
        "location_name": "Lake Havasu City Aquatic Center, 100 Park Ave",
        "description": (
            "Tryouts for the Havasu Stingrays competitive swim team. Open to youth swimmers. "
            "Contact the Aquatic Center ahead of time to register."
        ),
        "tags": ["kids", "youth", "sports", "swimming", "competitive"],
        "event_url": "https://www.golakehavasu.com/events",
        "contact_name": "Havasu Stingrays",
        "contact_phone": "928-453-8686",
    },
    {
        "title": "CrossFit Classes — Havasu CrossFit",
        "date": "2026-05-29",
        "start_time": "06:00",
        "end_time": "07:00",
        "location_name": "Havasu CrossFit, 1050 Lake Havasu Ave N #C",
        "description": (
            "Coach-led CrossFit classes for all fitness levels. Experienced certified trainers. "
            "Multiple class times daily. Registration required. Check website for weekly schedule. "
            "Daily, weekly, monthly rates available."
        ),
        "tags": ["fitness", "adults", "crossfit", "gym", "strength", "classes"],
        "event_url": "https://havasucrossfit.com",
        "contact_name": "Havasu CrossFit",
        "contact_phone": "928-680-9348",
    },
    {
        "title": "Yoga & Pilates — Ben Hicks Yoga",
        "date": "2026-05-22",
        "start_time": "08:00",
        "end_time": "09:00",
        "location_name": "Ben Hicks Yoga, 2000 McCulloch Blvd N #A",
        "description": (
            "Daily studio and online yoga classes for all levels. Also offers Pilates reformer "
            "private, duet, and trio sessions. A popular local studio in the heart of Havasu."
        ),
        "tags": ["fitness", "yoga", "pilates", "adults", "wellness", "classes"],
        "event_url": "https://benhicksyoga.com",
        "contact_name": "Ben Hicks Yoga",
        "contact_phone": "928-680-6392",
    },
    {
        "title": "Group Fitness Classes — FitLab 928",
        "date": "2026-06-12",
        "start_time": "05:00",
        "end_time": "06:00",
        "location_name": "FitLab 928, 537 Lake Havasu Ave N #101",
        "description": (
            "Community-based functional fitness gym with coach-led group classes. "
            "Mon–Fri 5am–5:45pm, Sat 8am. No contracts — daily, weekly, monthly rates. "
            "Personal training also offered."
        ),
        "tags": ["fitness", "adults", "gym", "group", "functional", "classes"],
        "event_url": "https://fitlab928.com",
        "contact_name": "FitLab 928",
        "contact_phone": "928-900-7989",
    },
    {
        "title": "Pilates & Spa Treatments — Bella Faccia",
        "date": "2026-07-10",
        "start_time": "09:00",
        "end_time": "18:00",
        "location_name": "Bella Faccia Skincare, Lake Havasu City",
        "description": (
            "Yoga classes, private/duet/trio Pilates reformer classes, plus massage and "
            "other spa treatments. By appointment only."
        ),
        "tags": ["fitness", "adults", "wellness", "pilates", "yoga", "spa"],
        "event_url": "https://bellafacciaskincare.com",
        "contact_name": "Bella Faccia",
        "contact_phone": "928-555-0115",
    },
    {
        "title": "Junior Ranger Program — Lake Havasu State Park",
        "date": "2026-07-11",
        "start_time": "09:00",
        "end_time": "12:00",
        "location_name": "Lake Havasu State Park, Windsor Beach, 171 London Bridge Rd",
        "description": (
            "Kids ages 6–12 can become a Junior Ranger! Complete activity booklets, learn about "
            "the Colorado River, and earn a Junior Ranger badge. Free with park entry. "
            "Available year-round at the Visitor Center."
        ),
        "tags": ["kids", "outdoor", "nature", "free", "family", "state park", "educational"],
        "event_url": "https://azstateparks.com/lake-havasu/explore/for-kids",
        "contact_name": "Lake Havasu State Park",
        "contact_phone": "928-855-2784",
    },
    {
        "title": "Kayaking & Paddleboard Rentals",
        "date": "2026-07-04",
        "start_time": "08:00",
        "end_time": "17:00",
        "location_name": "Lake Havasu Shoreline",
        "description": (
            "Kayak, paddleboard, and watercraft rentals on beautiful Lake Havasu. "
            "Great for families, beginners, and experienced paddlers. Guided tours also available. "
            "Open daily weather permitting."
        ),
        "tags": ["outdoor", "kayaking", "water", "family", "rental", "paddleboard", "daily"],
        "event_url": "https://www.golakehavasu.com/things-to-do/water-sports/",
        "contact_name": "Southwest Kayaks",
        "contact_phone": "928-855-6459",
    },
    {
        "title": "Crack in the Mountain Hiking Trail",
        "date": "2026-07-05",
        "start_time": "07:00",
        "end_time": "12:00",
        "location_name": "SARA Park Trailhead, 7260 Sara Pkwy",
        "description": (
            "Popular local hiking trail — moderate difficulty with incredible slot canyon views. "
            "Approximately 5 miles round trip to the shoreline and back. Best done early morning "
            "or late afternoon. Bring water, sturdy shoes, and sun protection."
        ),
        "tags": ["outdoor", "hiking", "free", "family", "adults", "nature"],
        "event_url": "https://www.lhcaz.gov/parks-recreation",
        "contact_name": "SARA Park",
        "contact_phone": "928-453-8686",
    },
    {
        "title": "Pickleball Open Play — LHCPBA",
        "date": "2026-07-18",
        "start_time": "07:00",
        "end_time": "10:00",
        "location_name": "Lake Havasu City Pickleball Courts",
        "description": (
            "The Lake Havasu City Pickleball Association hosts regular open play sessions for "
            "all skill levels. One of the fastest-growing sports in Havasu. "
            "Check their Facebook page for current schedule."
        ),
        "tags": ["sports", "adults", "pickleball", "outdoor", "community", "social"],
        "event_url": "https://www.facebook.com/search/top?q=lake+havasu+pickleball+association",
        "contact_name": "LHCPBA",
        "contact_phone": "928-555-0103",
    },
    {
        "title": "Havasu 95 Speedway Race Night",
        "date": "2026-07-25",
        "start_time": "18:00",
        "end_time": "22:00",
        "location_name": "Havasu 95 Speedway, 7260 Sara Pkwy",
        "description": (
            "Dirt track racing at Havasu 95 Speedway. Exciting local motorsports action. "
            "Concessions, family seating, and exciting races all night. Check schedule for "
            "race classes and ticket pricing."
        ),
        "tags": ["sports", "racing", "family", "outdoor", "evening", "spectator"],
        "event_url": "https://www.havasu95speedway.com",
        "contact_name": "Havasu 95 Speedway",
        "contact_phone": "928-855-2257",
    },
    {
        "title": "Mohave County Library Story Time",
        "date": "2026-05-13",
        "start_time": "10:30",
        "end_time": "11:15",
        "location_name": "Mohave County Library, 1770 McCulloch Blvd N",
        "description": (
            "Free weekly story time for toddlers and preschoolers. Stories, songs, and simple "
            "crafts. A favorite for local parents. Check library calendar for current weekly "
            "schedule and age groups."
        ),
        "tags": ["kids", "toddler", "free", "library", "family", "educational", "weekdays"],
        "event_url": "https://www.mohavecountylibrary.us",
        "contact_name": "Mohave County Library",
        "contact_phone": "928-453-0718",
    },
    {
        "title": "Hollywood Knights Dinner & Silent Auction",
        "date": "2026-06-14",
        "start_time": "17:00",
        "end_time": "21:00",
        "location_name": "Aquatic Center, 100 Park Ave",
        "description": (
            "Community fundraiser dinner with a silent auction. Hollywood Knights benefit event. "
            "Tickets required. Check Go Lake Havasu events for details."
        ),
        "tags": ["community", "charity", "adults", "evening", "dinner", "fundraiser"],
        "event_url": "https://www.golakehavasu.com/events",
        "contact_name": "Hollywood Knights",
        "contact_phone": "928-555-0116",
    },
    {
        "title": "Iron Wolf Golf & Country Club Open Play",
        "date": "2026-07-12",
        "start_time": "07:00",
        "end_time": "18:00",
        "location_name": "Iron Wolf Golf & Country Club, Lake Havasu City",
        "description": (
            "Beautiful 18-hole golf course open to the public. Pavilion, pro shop, and "
            "restaurant on site. Tee times recommended. Also hosts regular tribute band "
            "nights and special events."
        ),
        "tags": ["sports", "golf", "adults", "outdoor", "recreation"],
        "event_url": "https://www.ironwolfgolf.com",
        "contact_name": "Iron Wolf Golf Club",
        "contact_phone": "928-681-5900",
    },
]

SEED_EVENT_COUNT = len(REAL_SEED_EVENTS)


def _parse_hhmm(s: str) -> time:
    parts = s.strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    sec = int(parts[2]) if len(parts) > 2 else 0
    return time(h, m, sec)


def _normalized_seed_rows() -> list[dict]:
    rows: list[dict] = []
    for raw in REAL_SEED_EVENTS:
        end_raw = raw.get("end_time")
        rows.append(
            {
                "title": str(raw["title"]),
                "date": date.fromisoformat(str(raw["date"])),
                "start_time": _parse_hhmm(str(raw["start_time"])),
                "end_time": _parse_hhmm(str(end_raw)) if end_raw else None,
                "location_name": str(raw["location_name"]),
                "description": str(raw["description"]),
                "tags": list(raw["tags"]),
                "event_url": str(raw["event_url"]),
                "contact_name": str(raw["contact_name"]),
                "contact_phone": str(raw["contact_phone"]),
            }
        )
    return rows


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


def run_seed(skip_init: bool = False) -> tuple[int, int]:
    """
    Insert missing seed events. Returns (inserted_count, skipped_count).
    """
    if not skip_init:
        init_db()
    rows = _normalized_seed_rows()

    inserted = 0
    skipped = 0

    with SessionLocal() as db:
        existing = _existing_seed_indices(db)
        for i, row in enumerate(rows, start=1):
            if i in existing:
                skipped += 1
                continue

            event_date = row["date"]
            tags = row["tags"] + [_seed_tag(i)]
            payload_dict = {
                "title": row["title"],
                "date": event_date,
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "location_name": row["location_name"],
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
                start_time=row["start_time"],
                end_time=row["end_time"],
                location_name=row["location_name"],
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


def run_seed_if_empty() -> None:
    """If there are no events (e.g. fresh production DB), run the full seed once.

    Intended to be called from app startup on Railway (`RAILWAY_ENVIRONMENT` set in main.py).
    """
    with SessionLocal() as db:
        if db.query(Event).count() > 0:
            return
    run_seed(skip_init=True)


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
    if total_seed < SEED_EVENT_COUNT:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
