"""Runs the 120-query battery against production. Produces JSON output.

Diagnostic only — do not import from app. Hits HTTP endpoint directly.
"""
from __future__ import annotations

import json
import time
import uuid
from urllib import request, error

BASE = "https://web-production-bbe17.up.railway.app"


def chat(session_id: str, message: str, timeout: float = 15.0) -> dict:
    payload = json.dumps({"session_id": session_id, "message": message}).encode("utf-8")
    req = request.Request(
        f"{BASE}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            elapsed = time.monotonic() - t0
            return {"ok": True, "status": r.status, "body": json.loads(body), "elapsed": elapsed}
    except error.HTTPError as e:
        elapsed = time.monotonic() - t0
        return {"ok": False, "status": e.code, "body": e.read().decode("utf-8", "replace"), "elapsed": elapsed}
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {"ok": False, "status": None, "body": str(e), "elapsed": elapsed}


def classify(resp: dict) -> str:
    """Classify chat response body into category string."""
    if not resp.get("ok"):
        return f"ERROR({resp.get('status')})"
    body = resp["body"]
    intent = body.get("intent")
    data = body.get("data") or {}
    text = (body.get("response") or "").lower()

    if intent == "OUT_OF_SCOPE":
        cat = data.get("category")
        return f"OUT_OF_SCOPE({cat})" if cat else "OUT_OF_SCOPE"
    if intent in ("GREETING", "ADD_EVENT", "SERVICE_REQUEST", "DEAL_SEARCH",
                  "HARD_RESET", "SOFT_CANCEL", "UNCLEAR"):
        return intent
    if intent in ("SEARCH_EVENTS", "LISTING_INTENT", "REFINEMENT"):
        count = data.get("count")
        if isinstance(count, int) and count >= 1:
            return "EVENTS"
        if "permanent spot in havasu" in text:
            return "VENUE_REDIRECT"
        return "NO_MATCH"
    return f"OTHER({intent})"


def fresh_sid() -> str:
    return f"batt-{uuid.uuid4().hex[:10]}"


# (query, expected_label, severity_bucket, extra_notes)
# expected_label is a set of acceptable classification prefixes.
SINGLE_SHOT = [
    # Section 1 — Events that should match (20)
    (1,  "boat race",                      {"EVENTS"},                          "Section 1"),
    (2,  "poker run",                      {"EVENTS"},                          "Section 1"),
    (3,  "regatta",                        {"EVENTS"},                          "Section 1"),
    (4,  "live music",                     {"EVENTS"},                          "Section 1"),
    (5,  "concert",                        {"EVENTS"},                          "Section 1"),
    (6,  "band",                           {"EVENTS"},                          "Section 1"),
    (7,  "kids activities",                {"EVENTS"},                          "Section 1"),
    (8,  "family fun",                     {"EVENTS"},                          "Section 1"),
    (9,  "things to do",                   {"EVENTS"},                          "Section 1"),
    (10, "whats happening",                {"EVENTS"},                          "Section 1"),
    (11, "things to do next month",        {"EVENTS"},                          "Section 1"),
    (12, "events in may",                  {"EVENTS"},                          "Section 1"),
    (13, "events in june",                 {"EVENTS"},                          "Section 1"),
    (14, "events in july",                 {"EVENTS"},                          "Section 1"),
    (15, "farmers market",                 {"EVENTS"},                          "Section 1"),
    (16, "sunset market",                  {"EVENTS"},                          "Section 1"),
    (17, "first friday",                   {"EVENTS"},                          "Section 1"),
    (18, "fireworks",                      {"EVENTS"},                          "Section 1"),
    (19, "4th of july",                    {"EVENTS"},                          "Section 1"),
    (20, "country music",                  {"EVENTS"},                          "Section 1"),

    # Section 2 — Specific nouns, NO_MATCH (20)
    (21, "trampoline",                     {"NO_MATCH", "VENUE_REDIRECT"},      "Section 2"),
    (22, "trampoline tonight",             {"NO_MATCH"},                        "Section 2"),
    (23, "bowling",                        {"NO_MATCH", "VENUE_REDIRECT"},      "Section 2"),
    (24, "bowling this week",              {"NO_MATCH", "VENUE_REDIRECT"},      "Section 2"),
    (25, "rodeo",                          {"NO_MATCH"},                        "Section 2"),
    (26, "comedy show",                    {"NO_MATCH"},                        "Section 2"),
    (27, "karaoke",                        {"NO_MATCH"},                        "Section 2"),
    (28, "trivia night",                   {"NO_MATCH"},                        "Section 2"),
    (29, "wine tasting",                   {"NO_MATCH"},                        "Section 2"),
    (30, "brewery tour",                   {"NO_MATCH"},                        "Section 2"),
    (31, "paint night",                    {"NO_MATCH"},                        "Section 2"),
    (32, "book club",                      {"NO_MATCH"},                        "Section 2"),
    (33, "tennis tournament",              {"NO_MATCH"},                        "Section 2"),
    (34, "pickleball",                     {"EVENTS"},                          "Section 2"),
    (35, "5k run",                         {"NO_MATCH"},                        "Section 2"),
    (36, "marathon",                       {"NO_MATCH"},                        "Section 2"),
    (37, "bingo",                          {"NO_MATCH"},                        "Section 2"),
    (38, "poetry reading",                 {"NO_MATCH"},                        "Section 2"),
    (39, "film screening",                 {"NO_MATCH"},                        "Section 2"),
    (40, "dog show",                       {"NO_MATCH"},                        "Section 2"),

    # Section 3 — Known venues (12)
    (41, "altitude trampoline park",       {"VENUE_REDIRECT"},                  "Section 3"),
    (42, "havasu lanes",                   {"VENUE_REDIRECT"},                  "Section 3"),
    (43, "sara park",                      {"VENUE_REDIRECT"},                  "Section 3"),
    (44, "london bridge",                  {"VENUE_REDIRECT"},                  "Section 3"),
    (45, "rotary park",                    {"VENUE_REDIRECT"},                  "Section 3"),
    (46, "lake havasu state park",         {"VENUE_REDIRECT"},                  "Section 3"),
    (47, "cattail cove",                   {"VENUE_REDIRECT"},                  "Section 3"),
    (48, "english village",                {"VENUE_REDIRECT"},                  "Section 3"),
    (49, "aquatic center",                 {"VENUE_REDIRECT"},                  "Section 3"),
    (50, "scooter's",                      {"VENUE_REDIRECT"},                  "Section 3"),
    (51, "bridgewater links",              {"VENUE_REDIRECT"},                  "Section 3"),
    (52, "copper still distillery",        {"VENUE_REDIRECT"},                  "Section 3"),

    # Section 4 — OUT_OF_SCOPE (21)
    (53, "whats the weather",              {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (54, "weather this weekend",           {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (55, "is it going to rain",            {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (56, "how hot is it",                  {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (57, "temperature today",              {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (58, "forecast",                       {"OUT_OF_SCOPE(weather)"},           "Section 4"),
    (59, "where should i stay",            {"OUT_OF_SCOPE(lodging)"},           "Section 4"),
    (60, "hotels in havasu",               {"OUT_OF_SCOPE(lodging)"},           "Section 4"),
    (61, "best motel",                     {"OUT_OF_SCOPE(lodging)"},           "Section 4"),
    (62, "airbnb near me",                 {"OUT_OF_SCOPE(lodging)"},           "Section 4"),
    (63, "place to sleep",                 {"OUT_OF_SCOPE(lodging)"},           "Section 4"),
    (64, "where do i park",                {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (65, "parking downtown",               {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (66, "directions to london bridge",    {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (67, "how far is phoenix",             {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (68, "is there uber here",             {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (69, "rent a car",                     {"OUT_OF_SCOPE(transportation)"},    "Section 4"),
    (70, "best restaurants",               {"OUT_OF_SCOPE(dining)"},            "Section 4"),
    (71, "top restaurants in havasu",      {"OUT_OF_SCOPE(dining)"},            "Section 4"),
    (72, "where to eat",                   {"OUT_OF_SCOPE(dining)"},            "Section 4"),
    (73, "best breakfast",                 {"OUT_OF_SCOPE(dining)"},            "Section 4"),

    # Section 5 — Event-indicator overrides (5)
    (74, "hotel grand opening event",      {"EVENTS", "NO_MATCH"},              "Section 5"),
    (75, "restaurant week",                {"EVENTS", "NO_MATCH"},              "Section 5"),
    (76, "food festival",                  {"EVENTS", "NO_MATCH"},              "Section 5"),
    (77, "car show",                       {"EVENTS", "NO_MATCH"},              "Section 5"),
    (78, "weather station tour",           {"EVENTS", "NO_MATCH"},              "Section 5"),

    # Section 6 — Date phrase parsing (11)
    (79, "events today",                   {"EVENTS", "NO_MATCH"},              "Section 6"),
    (80, "events tonight",                 {"EVENTS", "NO_MATCH"},              "Section 6"),
    (81, "events tomorrow",                {"EVENTS", "NO_MATCH"},              "Section 6"),
    (82, "this week",                      {"EVENTS", "NO_MATCH"},              "Section 6"),
    (83, "this weekend",                   {"EVENTS", "NO_MATCH"},              "Section 6"),
    (84, "next weekend",                   {"EVENTS", "NO_MATCH"},              "Section 6"),
    (85, "this month",                     {"EVENTS", "NO_MATCH"},              "Section 6"),
    (86, "next month",                     {"EVENTS", "NO_MATCH"},              "Section 6"),
    (87, "in may",                         {"EVENTS", "NO_MATCH"},              "Section 6"),
    (88, "memorial day",                   {"EVENTS", "NO_MATCH"},              "Section 6"),
    (89, "july 4",                         {"EVENTS", "NO_MATCH"},              "Section 6"),

    # Section 8 — Edge cases (13)
    (98,  "",                               {"*"},                              "Section 8 — empty string"),
    (99,  "a",                              {"*"},                              "Section 8 — single char"),
    (100, "!@#$%^",                         {"*"},                              "Section 8 — symbols"),
    (101, "bowling alley near me",          {"VENUE_REDIRECT", "NO_MATCH"},     "Section 8"),
    (102, "cheap boat rental",              {"OUT_OF_SCOPE*", "NO_MATCH"},      "Section 8"),
    (103, "is there parking at the festival",
                                            {"OUT_OF_SCOPE(transportation)", "EVENTS", "NO_MATCH"},
                                            "Section 8 — ambiguous"),
    (104, "kids birthday party venue",      {"OUT_OF_SCOPE*", "VENUE_REDIRECT", "NO_MATCH"}, "Section 8"),
    (105, "date night ideas",               {"EVENTS"},                         "Section 8"),
    (106, "romantic things to do",          {"EVENTS"},                         "Section 8"),
    (107, "senior activities",              {"EVENTS"},                         "Section 8"),
    (108, "dog friendly events",            {"EVENTS", "NO_MATCH"},             "Section 8"),
    (109, "free events",                    {"EVENTS"},                         "Section 8"),
    (110, "indoor activities when its hot", {"EVENTS", "NO_MATCH"},             "Section 8"),

    # Section 9 — Adversarial (10)
    (111, "add an event",                  {"ADD_EVENT"},                       "Section 9"),
    (112, "help",                          {"GREETING", "UNCLEAR", "*"},        "Section 9 — meta"),
    (113, "what can you do",               {"GREETING", "UNCLEAR", "*"},        "Section 9 — meta"),
    (114, "hi",                            {"GREETING"},                        "Section 9"),
    (115, "thanks",                        {"*"},                               "Section 9 — graceful"),
    (116, "i love this app",               {"*"},                               "Section 9 — graceful"),
    (117, "this is broken",                {"*"},                               "Section 9 — graceful"),
    (118, "tell me a joke",                {"OUT_OF_SCOPE*", "*"},              "Section 9 — decline"),
    (119, "book me a table",               {"OUT_OF_SCOPE*", "NO_MATCH"},       "Section 9"),
    (120, "buy tickets to the concert",    {"EVENTS", "OUT_OF_SCOPE*"},         "Section 9"),
]

# Section 7 — Multi-turn sequences. Each shares a session across queries.
SEQUENCES = [
    ("A", [
        (90, "this weekend",              {"NO_MATCH", "EVENTS"},               "Seq A step 1"),
        (91, "any boat events",           {"EVENTS"},                           "Seq A step 2 — date_range must clear"),
        (92, "what about next week",      {"NO_MATCH", "EVENTS"},               "Seq A step 3"),
    ]),
    ("B", [
        (93, "whats happening this weekend", {"NO_MATCH", "EVENTS"},            "Seq B step 1"),
        (94, "concerts in july",             {"EVENTS"},                        "Seq B step 2 — date_range must be July"),
    ]),
    ("C", [
        (95, "this weekend",              {"NO_MATCH", "EVENTS"},               "Seq C step 1"),
        (96, "the week after that",       {"NO_MATCH", "EVENTS"},               "Seq C step 2"),
        (97, "how about the week after",  {"NO_MATCH", "EVENTS"},               "Seq C step 3"),
    ]),
]


def matches(actual: str, accept: set[str]) -> bool:
    if "*" in accept:
        return True
    if actual in accept:
        return True
    # Wildcard suffix matches like OUT_OF_SCOPE* or OUT_OF_SCOPE(weather)*
    for a in accept:
        if a.endswith("*") and actual.startswith(a[:-1]):
            return True
    return False


def run_all() -> dict:
    results = []
    total = 0

    # Section 7 sequences first (so later single-shot queries don't share)
    for label, steps in SEQUENCES:
        sid = fresh_sid()
        for (num, query, expected, note) in steps:
            total += 1
            resp = chat(sid, query)
            actual = classify(resp)
            body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
            record = {
                "num": num,
                "section": f"Section 7 / Seq {label}",
                "query": query,
                "expected": sorted(expected),
                "actual": actual,
                "match": matches(actual, expected),
                "intent": body.get("intent"),
                "count": (body.get("data") or {}).get("count"),
                "category": (body.get("data") or {}).get("category"),
                "elapsed": round(resp.get("elapsed", 0), 2),
                "note": note,
                "response_snippet": (body.get("response") or "")[:200],
                "status": resp.get("status"),
            }
            results.append(record)
            time.sleep(0.4)

    # Single-shot queries — fresh session each
    for (num, query, expected, note) in SINGLE_SHOT:
        total += 1
        sid = fresh_sid()
        resp = chat(sid, query)
        actual = classify(resp)
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        record = {
            "num": num,
            "section": note.split(" — ")[0] if " — " in note else note,
            "query": query,
            "expected": sorted(expected),
            "actual": actual,
            "match": matches(actual, expected),
            "intent": body.get("intent"),
            "count": (body.get("data") or {}).get("count"),
            "category": (body.get("data") or {}).get("category"),
            "elapsed": round(resp.get("elapsed", 0), 2),
            "note": note,
            "response_snippet": (body.get("response") or "")[:200],
            "status": resp.get("status"),
        }
        results.append(record)
        time.sleep(0.4)

    return {"total": total, "results": results}


if __name__ == "__main__":
    out = run_all()
    print(json.dumps(out, indent=2))
