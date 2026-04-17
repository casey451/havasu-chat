"""Lake Havasu venue recognition for the no-match redirect path.

Source: ``docs/havasu-knowledge-base.md`` Section 6.
"""
from __future__ import annotations


VENUE_ALIASES: dict[str, list[str]] = {
    "Altitude Trampoline Park": [
        "altitude trampoline park",
        "altitude trampoline",
        "trampoline park",
        "trampoline",
    ],
    "Havasu Lanes": [
        "havasu lanes",
        "bowling alley",
        "bowling",
        "lanes",
    ],
    "Scooter's Family Fun Center": [
        "scooter's family fun center",
        "scooters family fun center",
        "scooter's",
        "scooters",
        "mini golf",
        "mini-golf",
        "arcade",
    ],
    "Sunshine Indoor Play": [
        "sunshine indoor play",
        "sunshine indoor",
        "indoor play",
    ],
    "Lake Havasu Aquatic Center": [
        "lake havasu aquatic center",
        "havasu aquatic center",
        "aquatic center",
    ],
    "Lake Havasu State Park": [
        "lake havasu state park",
        "havasu state park",
        "windsor beach",
    ],
    "Cattail Cove State Park": [
        "cattail cove state park",
        "cattail cove",
    ],
    "SARA Park": [
        "sara park",
        "sara pkwy",
    ],
    "Rotary Park": [
        "rotary community park",
        "rotary park",
    ],
    "London Bridge Beach": [
        "london bridge beach",
    ],
    "Crack in the Mountain Trail": [
        "crack in the mountain trail",
        "crack in the mountain",
        "crack in mountain",
    ],
    "Wet Monkey": [
        "wet monkey",
    ],
    "Havasu Rentals": [
        "havasu rentals",
    ],
    "Paradise Wild Wave Rentals": [
        "paradise wild wave rentals",
        "paradise wild wave",
        "wild wave rentals",
    ],
    "Champion Watercraft Rentals": [
        "champion watercraft rentals",
        "champion watercraft",
    ],
    "Southwest Kayaks": [
        "southwest kayaks",
    ],
    "Cruisin Tikis Havasu": [
        "cruisin tikis havasu",
        "cruising tikis havasu",
        "cruisin tikis",
        "cruising tikis",
    ],
    "Sunset Charter & Tour Co": [
        "sunset charter & tour co",
        "sunset charter and tour co",
        "sunset charter and tour",
        "sunset charter",
    ],
    "Bluewater Jet Boat Tours": [
        "bluewater jet boat tours",
        "bluewater jet boat",
    ],
    "Havasu Adventure Company": [
        "havasu adventure company",
        "havasu adventure",
    ],
    "Wanderlust Balloons": [
        "wanderlust balloons",
        "wanderlust",
    ],
    "Copper Still Distillery": [
        "copper still distillery",
        "copper still",
    ],
    "Hava Bite Taproom": [
        "hava bite taproom",
        "hava bite",
    ],
    "Kokomo": [
        "kokomo",
    ],
    "London Bridge": [
        "london bridge",
    ],
    "English Village": [
        "english village",
    ],
    "Lake Havasu Museum of History": [
        "lake havasu museum of history",
        "havasu museum of history",
        "museum of history",
        "havasu museum",
    ],
    "Replica Lighthouses": [
        "replica lighthouses",
        "lighthouses",
    ],
    "Bridgewater Links Golf Course": [
        "bridgewater links golf course",
        "bridgewater links",
    ],
    "London Bridge Resort Golf Course": [
        "london bridge resort golf course",
        "london bridge resort golf",
    ],
}


def detect_venue(query: str) -> str | None:
    """Return the canonical venue name if any alias is a substring of ``query``.

    Uses longest-alias-wins: when multiple aliases match the query, the
    alias with the greatest length determines the canonical name. This
    prevents short generic aliases (e.g. ``"lanes"``) from shadowing
    more specific ones (e.g. ``"havasu lanes"``).

    Returns ``None`` when no alias matches.
    """
    if not query:
        return None
    q = query.lower()
    best_len = 0
    best_canonical: str | None = None
    for canonical, aliases in VENUE_ALIASES.items():
        for alias in aliases:
            a = alias.lower()
            if a in q and len(a) > best_len:
                best_len = len(a)
                best_canonical = canonical
    return best_canonical
