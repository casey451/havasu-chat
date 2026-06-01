"""Runs the 120-query battery against production. Produces JSON output.

Diagnostic only — do not import from app. Hits POST /api/chat directly.

Retargeted in Slice 16 (Backlog #12 close): now POSTs to /api/chat with
the concierge payload shape ({query, session_id}) and parses the new
ConciergeChatResponse fields (mode, sub_intent, entity, tier_used,
latency_ms, llm_tokens_used, chat_log_id).

Slice 23 (Backlog #25 close): rebuilt expected labels from a captured
production baseline. Each tuple's expected set holds the tier_used
value(s) (TIER1/TIER2/TIER3/CHAT/GAP_TEMPLATE/PLACEHOLDER) recorded
when the query was last run against production. matches() helper
restored; run_all() reports matched/mismatched counts so the battery
functions as a tier-drift regression detector.
"""

from __future__ import annotations

import json
import time
import uuid
from urllib import error, request

BASE = "https://havasu-chat-production.up.railway.app"


def chat(session_id: str, query: str, timeout: float = 15.0) -> dict:
    payload = json.dumps({"query": query, "session_id": session_id}).encode("utf-8")
    req = request.Request(
        f"{BASE}/api/chat",
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
        return {
            "ok": False,
            "status": e.code,
            "body": e.read().decode("utf-8", "replace"),
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {"ok": False, "status": None, "body": str(e), "elapsed": elapsed}


def classify(resp: dict) -> str:
    """Categorize chat response by tier_used (or error code)."""
    if not resp.get("ok"):
        return f"ERROR({resp.get('status')})"
    body = resp["body"]
    tier_used = body.get("tier_used")
    if tier_used in ("1", "2", "3"):
        return f"TIER{tier_used}"
    if tier_used:
        return tier_used.upper()  # 'chat', 'gap_template', 'placeholder', etc.
    return "UNKNOWN"


def matches(actual: str, accept: set[str]) -> bool:
    if "*" in accept:
        return True
    if actual in accept:
        return True
    for a in accept:
        if a.endswith("*") and actual.startswith(a[:-1]):
            return True
    return False


def fresh_sid() -> str:
    return f"batt-{uuid.uuid4().hex[:10]}"


# (num, query, expected_set, note)
# expected_set holds the tier_used value(s) captured from a production baseline run
# (Slice 23, Backlog #25). Drift from these values flags a regression.
SINGLE_SHOT = [
    # Section 1 — Events that should match (20)
    (1, "boat race", {"TIER3"}, "Section 1"),
    (2, "poker run", {"TIER3"}, "Section 1"),
    (3, "regatta", {"TIER3"}, "Section 1"),
    (4, "live music", {"TIER3"}, "Section 1"),
    (5, "concert", {"TIER3"}, "Section 1"),
    (6, "band", {"TIER3"}, "Section 1"),
    (7, "kids activities", {"TIER2"}, "Section 1"),
    (8, "family fun", {"TIER3"}, "Section 1"),
    (9, "things to do", {"TIER3"}, "Section 1"),
    (10, "whats happening", {"TIER2"}, "Section 1"),
    (11, "things to do next month", {"TIER2"}, "Section 1"),
    (12, "events in may", {"TIER2"}, "Section 1"),
    (13, "events in june", {"TIER2"}, "Section 1"),
    (14, "events in july", {"TIER2"}, "Section 1"),
    (15, "farmers market", {"TIER2"}, "Section 1"),
    (16, "sunset market", {"TIER3"}, "Section 1"),
    (17, "first friday", {"TIER2"}, "Section 1"),
    (18, "fireworks", {"TIER2"}, "Section 1"),
    (19, "4th of july", {"TIER2"}, "Section 1"),
    (20, "country music", {"TIER3"}, "Section 1"),
    # Section 2 — Specific nouns, NO_MATCH (20)
    (21, "trampoline", {"TIER3"}, "Section 2"),
    (22, "trampoline tonight", {"TIER3"}, "Section 2"),
    (23, "bowling", {"TIER3"}, "Section 2"),
    (24, "bowling this week", {"TIER3"}, "Section 2"),
    (25, "rodeo", {"TIER3"}, "Section 2"),
    (26, "comedy show", {"TIER3"}, "Section 2"),
    (27, "karaoke", {"TIER3"}, "Section 2"),
    (28, "trivia night", {"TIER3"}, "Section 2"),
    (29, "wine tasting", {"TIER3"}, "Section 2"),
    (30, "brewery tour", {"TIER3"}, "Section 2"),
    (31, "paint night", {"TIER3"}, "Section 2"),
    (32, "book club", {"TIER3"}, "Section 2"),
    (33, "tennis tournament", {"TIER3"}, "Section 2"),
    (34, "pickleball", {"TIER3"}, "Section 2"),
    (35, "5k run", {"TIER3"}, "Section 2"),
    (36, "marathon", {"TIER3"}, "Section 2"),
    (37, "bingo", {"TIER2"}, "Section 2"),
    (38, "poetry reading", {"TIER3"}, "Section 2"),
    (39, "film screening", {"TIER3"}, "Section 2"),
    (40, "dog show", {"TIER3"}, "Section 2"),
    # Section 3 — Known venues (12)
    (41, "altitude trampoline park", {"TIER3"}, "Section 3"),
    (42, "havasu lanes", {"TIER3"}, "Section 3"),
    (43, "sara park", {"TIER3"}, "Section 3"),
    (44, "london bridge", {"TIER2"}, "Section 3"),
    (45, "rotary park", {"TIER2"}, "Section 3"),
    (46, "lake havasu state park", {"TIER2"}, "Section 3"),
    (47, "cattail cove", {"TIER3"}, "Section 3"),
    (48, "english village", {"TIER3"}, "Section 3"),
    (49, "aquatic center", {"TIER2"}, "Section 3"),
    (50, "scooter's", {"TIER3"}, "Section 3"),
    (51, "bridgewater links", {"TIER2"}, "Section 3"),
    (52, "copper still distillery", {"TIER3"}, "Section 3"),
    # Section 4 — OUT_OF_SCOPE (21)
    (53, "whats the weather", {"CHAT"}, "Section 4"),
    (54, "weather this weekend", {"CHAT"}, "Section 4"),
    (55, "is it going to rain", {"CHAT"}, "Section 4"),
    (56, "how hot is it", {"CHAT"}, "Section 4"),
    (57, "temperature today", {"CHAT"}, "Section 4"),
    (58, "forecast", {"CHAT"}, "Section 4"),
    (59, "where should i stay", {"CHAT"}, "Section 4"),
    (60, "hotels in havasu", {"CHAT"}, "Section 4"),
    (61, "best motel", {"CHAT"}, "Section 4"),
    (62, "airbnb near me", {"CHAT"}, "Section 4"),
    (63, "place to sleep", {"CHAT"}, "Section 4"),
    (64, "where do i park", {"CHAT"}, "Section 4"),
    (65, "parking downtown", {"CHAT"}, "Section 4"),
    (66, "directions to london bridge", {"CHAT"}, "Section 4"),
    (67, "how far is phoenix", {"CHAT"}, "Section 4"),
    (68, "is there uber here", {"CHAT"}, "Section 4"),
    (69, "rent a car", {"CHAT"}, "Section 4"),
    (70, "best restaurants", {"CHAT"}, "Section 4"),
    (71, "top restaurants in havasu", {"CHAT"}, "Section 4"),
    (72, "where to eat", {"CHAT"}, "Section 4"),
    (73, "best breakfast", {"CHAT"}, "Section 4"),
    # Section 5 — Event-indicator overrides (5)
    (74, "hotel grand opening event", {"PLACEHOLDER"}, "Section 5"),
    (75, "restaurant week", {"TIER3"}, "Section 5"),
    (76, "food festival", {"TIER3"}, "Section 5"),
    (77, "car show", {"TIER3"}, "Section 5"),
    (78, "weather station tour", {"TIER3"}, "Section 5"),
    # Section 6 — Date phrase parsing (11)
    (79, "events today", {"TIER3"}, "Section 6"),
    (80, "events tonight", {"TIER3"}, "Section 6"),
    (81, "events tomorrow", {"TIER3"}, "Section 6"),
    (82, "this week", {"TIER2"}, "Section 6"),
    (83, "this weekend", {"TIER2"}, "Section 6"),
    (84, "next weekend", {"TIER2"}, "Section 6"),
    (85, "this month", {"TIER2"}, "Section 6"),
    (86, "next month", {"TIER2"}, "Section 6"),
    (87, "in may", {"TIER2"}, "Section 6"),
    (88, "memorial day", {"TIER3"}, "Section 6"),
    (89, "july 4", {"TIER2"}, "Section 6"),
    # Section 8 — Edge cases (13)
    (98, "", {"ERROR(422)"}, "Section 8 — empty string"),
    (99, "a", {"TIER3"}, "Section 8 — single char"),
    (100, "!@#$%^", {"TIER3"}, "Section 8 — symbols"),
    (101, "bowling alley near me", {"TIER3"}, "Section 8"),
    (102, "cheap boat rental", {"CHAT"}, "Section 8"),
    (103, "is there parking at the festival", {"TIER3"}, "Section 8 — ambiguous"),
    (104, "kids birthday party venue", {"CHAT"}, "Section 8"),
    (105, "date night ideas", {"GAP_TEMPLATE"}, "Section 8"),
    (106, "romantic things to do", {"TIER3"}, "Section 8"),
    (107, "senior activities", {"TIER3"}, "Section 8"),
    (108, "dog friendly events", {"TIER3"}, "Section 8"),
    (109, "free events", {"TIER3"}, "Section 8"),
    (110, "indoor activities when its hot", {"GAP_TEMPLATE"}, "Section 8"),
    # Section 9 — Adversarial (10)
    (111, "add an event", {"TIER3"}, "Section 9"),
    (112, "help", {"TIER3"}, "Section 9 — meta"),
    (113, "what can you do", {"TIER3"}, "Section 9 — meta"),
    (114, "hi", {"CHAT"}, "Section 9"),
    (115, "thanks", {"CHAT"}, "Section 9 — graceful"),
    (116, "i love this app", {"TIER3"}, "Section 9 — graceful"),
    (117, "this is broken", {"TIER3"}, "Section 9 — graceful"),
    (118, "tell me a joke", {"TIER3"}, "Section 9 — decline"),
    (119, "book me a table", {"CHAT"}, "Section 9"),
    (120, "buy tickets to the concert", {"TIER3"}, "Section 9"),
]

# Section 7 — Multi-turn sequences. Each shares a session across queries.
SEQUENCES = [
    (
        "A",
        [
            (90, "this weekend", {"TIER2"}, "Seq A step 1"),
            (91, "any boat events", {"TIER3"}, "Seq A step 2 — date_range must clear"),
            (92, "what about next week", {"TIER2"}, "Seq A step 3"),
        ],
    ),
    (
        "B",
        [
            (93, "whats happening this weekend", {"TIER2"}, "Seq B step 1"),
            (94, "concerts in july", {"TIER3"}, "Seq B step 2 — date_range must be July"),
        ],
    ),
    (
        "C",
        [
            (95, "this weekend", {"TIER2"}, "Seq C step 1"),
            (96, "the week after that", {"TIER3"}, "Seq C step 2"),
            (97, "how about the week after", {"TIER3"}, "Seq C step 3"),
        ],
    ),
]


def run_all() -> dict:
    results = []
    total = 0

    # Section 7 sequences first (so later single-shot queries don't share)
    for label, steps in SEQUENCES:
        sid = fresh_sid()
        for num, query, expected, note in steps:
            total += 1
            resp = chat(sid, query)
            actual = classify(resp)
            body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
            record = {
                "num": num,
                "section": f"Section 7 / Seq {label}",
                "query": query,
                "actual": actual,
                "expected": sorted(list(expected)),
                "match": matches(actual, expected),
                "mode": body.get("mode"),
                "sub_intent": body.get("sub_intent"),
                "entity": body.get("entity"),
                "tier_used": body.get("tier_used"),
                "latency_ms": body.get("latency_ms"),
                "llm_tokens_used": body.get("llm_tokens_used"),
                "chat_log_id": body.get("chat_log_id"),
                "elapsed_seconds": round(resp.get("elapsed", 0), 2),
                "note": note,
                "response_snippet": (body.get("response") or "")[:200],
                "status": resp.get("status"),
            }
            results.append(record)
            time.sleep(0.4)

    # Single-shot queries — fresh session each
    for num, query, expected, note in SINGLE_SHOT:
        total += 1
        sid = fresh_sid()
        resp = chat(sid, query)
        actual = classify(resp)
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        record = {
            "num": num,
            "section": note.split(" — ")[0] if " — " in note else note,
            "query": query,
            "actual": actual,
            "expected": sorted(list(expected)),
            "match": matches(actual, expected),
            "mode": body.get("mode"),
            "sub_intent": body.get("sub_intent"),
            "entity": body.get("entity"),
            "tier_used": body.get("tier_used"),
            "latency_ms": body.get("latency_ms"),
            "llm_tokens_used": body.get("llm_tokens_used"),
            "chat_log_id": body.get("chat_log_id"),
            "elapsed_seconds": round(resp.get("elapsed", 0), 2),
            "note": note,
            "response_snippet": (body.get("response") or "")[:200],
            "status": resp.get("status"),
        }
        results.append(record)
        time.sleep(0.4)

    matched = sum(1 for r in results if r.get("match"))
    return {"total": total, "matched": matched, "mismatched": total - matched, "results": results}


if __name__ == "__main__":
    out = run_all()
    print(json.dumps(out, indent=2))
