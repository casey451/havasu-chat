"""Unit tests for :mod:`app.eval.confabulation_detector` (spec section 5.1 tests 1–7, 12)."""

from __future__ import annotations

from app.eval.confabulation_detector import (
    InvocationResult,
    LAYER2,
    detect,
)


def _h1(r: InvocationResult, f: str) -> list:
    return [h for h in detect(r) if h.layer == f]  # use "1_advisory", "2", or "3"


def test_layer1_hits_tagged_1_advisory() -> None:
    row = {
        "type": "provider",
        "name": "Aqua Beginnings",
        "description": "Max 3 swimmers per group.",
        "category": "swim",
    }
    resp = "Aqua Beginnings has private heated outdoor pool sessions."
    r = InvocationResult(response_text=resp, evidence_row_dicts=[row])
    for h in detect(r):
        assert h.layer in ("1_advisory", "2", "3")
    assert "1" not in {h.layer for h in detect(r)}


def test_layer1_aqua_beginnings_hits_private_heated_outdoor() -> None:
    row = {
        "type": "provider",
        "name": "Aqua Beginnings",
        "description": "Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified).",
        "category": "swim",
    }
    resp = (
        "Aqua Beginnings has private heated outdoor pool sessions, though you would need to book directly."
    )
    r = InvocationResult(response_text=resp, evidence_row_dicts=[row])
    h1 = {h.token for h in _h1(r, "1_advisory")}
    h2 = {h.token for h in _h1(r, "2")}
    # Layer 1: confab tokens (lemmatized; "heated" may be "heat")
    assert {"private", "outdoor"}.issubset(h1) or "private" in h1
    assert "heat" in h1 or "heated" in h1 or "outdoor" in h1
    # Layer 2: wordlist
    assert "private" in h2 or "heated" in h2 or "outdoor" in h2 or "book directly" in h2


def test_layer1_aqua_clean_no_hits() -> None:
    row = {
        "type": "provider",
        "name": "Aqua Beginnings",
        "description": "Max 3 swimmers per group. Free initial assessment. Coach Rick (Swim America® certified).",
        "category": "swim",
    }
    resp = "Aqua Beginnings offers swim assessment with Coach Rick as described in the listing."
    r = InvocationResult(response_text=resp, evidence_row_dicts=[row])
    h1 = _h1(r, "1_advisory")
    bad = {h.token for h in h1} & {"private", "outdoor", "heat", "heated", "indoor", "book"}
    assert not bad, bad


def test_layer2_indoor_in_response_not_in_evidence() -> None:
    ev = {
        "type": "provider",
        "name": "Test Pool",
        "description": "A community pool. Hours vary.",
        "category": "pool",
    }
    r_ok = InvocationResult("They have a nice outdoor deck.", [ev])
    r_bad = InvocationResult("They have an indoor lap pool and outdoor deck.", [ev])
    assert "indoor" not in (b.lower() for b in (ev.get("description") or "").split())
    l2b = {h.token for h in _h1(r_bad, "2") if h.token == "indoor"}
    l2a = {h.token for h in _h1(r_ok, "2") if h.token == "indoor"}
    assert "indoor" in l2b and "indoor" not in l2a


def test_layer1_phone_stripped_no_hit_when_digits_in_evidence_phone() -> None:
    ev = {
        "type": "provider",
        "name": "Lake Havasu City Aquatic Center",
        "description": "Indoor facility.",
        "category": "swim",
        "address": "100 Park Ave, Lake Havasu City, AZ 86403",
        "phone": "(928) 453-8686",
    }
    resp = "Call (928) 453-8686 for the desk."
    r = InvocationResult(response_text=resp, evidence_row_dicts=[ev])
    l1 = {h.token for h in _h1(r, "1_advisory")}
    assert "453-8686" not in l1
    assert "928" not in l1


def test_layer3_usd_decimal_matches_whole_dollar() -> None:
    ev = {
        "type": "program",
        "name": "Lap Swim",
        "description": "Heated pool.",
        "category": "swim",
        "provider_name": "Aquatic",
        "cost": "$5.00",
    }
    r = InvocationResult("Lap swim is $5 per session.", [ev])
    assert not [h for h in detect(r) if h.layer == "3" and h.token == "usd:5"]


def test_layer3_phone_invented_number_diff() -> None:
    ev = {
        "type": "provider",
        "name": "P",
        "description": "Call us.",
        "category": "x",
        "phone": "(928) 453-8686",
    }
    r = InvocationResult("Instead call (602) 555-1212 for reservations.", [ev])
    h3 = {h.token for h in detect(r) if h.layer == "3"}
    assert "ph:6025551212" in h3


def test_layer3_usd_cents_mismatch_vs_whole() -> None:
    ev = {
        "type": "program",
        "name": "Lap Swim",
        "description": "Heated pool.",
        "category": "swim",
        "provider_name": "Aquatic",
        "cost": "$5.00",
    }
    r = InvocationResult("Lap swim is $5.99 per session.", [ev])
    h3 = [h for h in detect(r) if h.layer == "3" and h.token == "usd:5.99"]
    assert h3


def test_layer3_invented_price() -> None:
    ev = {"type": "provider", "name": "P", "description": "It costs $19 to enter.", "category": "x"}
    r = InvocationResult("It now costs $25 to enter the same day.", [ev])
    h3 = [h for h in detect(r) if h.layer == "3" and h.token == "usd:25"]
    assert h3, [h.token for h in detect(r) if h.layer == "3"]


def test_layer3_normalization_free() -> None:
    a = "Admission is free today."
    b = "Price is $0.00 and free."
    ra = InvocationResult("Same day $0.00 and no charge here.", [{"type": "p", "name": "E", "description": a, "category": "x"}])
    rb = InvocationResult("Same as listed.", [{"type": "p", "name": "E", "description": b, "category": "x"}])
    d3a = {h.token for h in _h1(ra, "3")}
    d3b = {h.token for h in _h1(rb, "3")}
    assert d3a == set() and d3b == set(), (d3a, d3b)


def test_safe_framing_worth_no_layer1() -> None:
    r = InvocationResult("It is worth checking out. Nothing in evidence about worth.", [{"type": "provider", "name": "Q", "description": "A place.", "category": "c"}])
    toks = {h.token for h in _h1(r, "1_advisory")}
    assert "worth" not in toks


def test_grace_arts_event_youth_theatre_scoping() -> None:
    p = {
        "type": "provider",
        "name": "Grace Arts Live",
        "description": "Nonprofit. Affiliated with ACPA. established: 2006.",
        "category": "theatre",
    }
    e = {
        "type": "event",
        "name": "Youth show",
        "date": "2025-01-10",
        "start_time": "10:00",
        "end_time": "12:00",
        "location_name": "GAL",
        "description": "youth theatre performance evening.",
    }
    resp = "indoor option, air-conditioned, family-friendly, youth theatre next week."
    r = InvocationResult(response_text=resp, evidence_row_dicts=[p, e])
    all_h = detect(r)
    t1 = {h.token for h in all_h if h.layer == "1_advisory"}
    assert "youth" not in t1
    assert "theatre" not in t1
    assert "air" in t1 or "air-conditioned" in {h.token for h in all_h if h.layer == "2"}


def test_l2_phrase_list_matches_closure() -> None:
    assert "book directly" in LAYER2
    assert "family-friendly" in LAYER2
    assert "AV" not in LAYER2


def test_layer3_time_symmetry_schedule_range_vs_12h_response() -> None:
    ev = {
        "type": "program",
        "name": "Open Jump",
        "description": "Session daily 09:00-10:00; cost on file is $19.00.",
        "category": "x",
    }
    r = InvocationResult(
        "Runs daily 9:00 to 10:00 AM, seven days a week. As listed, $19.00.",
        [ev],
    )
    h3 = {h.token for h in _h1(r, "3")}
    assert "t:09:00" not in h3 and "t:10:00" not in h3, h3


def test_layer3_time_symmetry_24h_two_digit() -> None:
    ev = {
        "type": "program",
        "name": "P",
        "description": "Hours: 10:00-11:00 weekdays.",
        "category": "x",
    }
    r = InvocationResult("The desk opens 10:00 and 11:00 for staff.", [ev])
    h3 = {h.token for h in _h1(r, "3")}
    assert "t:10:00" not in h3 and "t:11:00" not in h3, h3


def test_l3_90_min_matches() -> None:
    ev = {"type": "provider", "name": "G", "description": "90 min class.", "category": "x"}
    r0 = InvocationResult("Same 90 min format.", [ev])
    r1 = InvocationResult("Same 90-minute format.", [ev])
    assert not _h1(r0, "3")
    assert not _h1(r1, "3")


def test_l2_av_not_matched_inside_available() -> None:
    ev = {"type": "provider", "name": "P", "description": "No A/V listed.", "category": "x"}
    r = InvocationResult("Availability is available now.", [ev])
    toks = {h.token for h in _h1(r, "2")}
    assert "AV" not in toks


def test_em_dash_split_no_glued_tokens() -> None:
    ev = {"type": "provider", "name": "P", "description": "max 3 swimmers per group", "category": "x"}
    r = InvocationResult("Groups stay small—max 3 swimmers per session—and start quickly.", [ev])
    l1 = {h.token for h in _h1(r, "1_advisory")}
    assert all("—" not in t for t in l1)
    assert "small—max" not in l1
    assert "session—and" not in l1


def test_contraction_fragments_not_content_tokens() -> None:
    ev = {"type": "provider", "name": "P", "description": "desc", "category": "x"}
    r = InvocationResult("You're welcome and we aren't open.", [ev])
    l1 = {h.token for h in _h1(r, "1_advisory")}
    assert "'re" not in l1
    assert "n't" not in l1


def test_outdoor_outdoors_normalization() -> None:
    ev = {"type": "provider", "name": "P", "description": "outdoor swim lessons", "category": "x"}
    r = InvocationResult("They host lessons outdoors.", [ev])
    l1 = {h.token for h in _h1(r, "1_advisory")}
    assert "outdoor" not in l1
    assert "outdoors" not in l1


def test_safe_framing_expansion_words_not_l1_hits() -> None:
    ev = {"type": "provider", "name": "P", "description": "desc", "category": "x"}
    r = InvocationResult(
        "Current details are specific and listed in the directory with contact info and phone number.",
        [ev],
    )
    l1 = {h.token for h in _h1(r, "1_advisory")}
    for tok in ("current", "detail", "specific", "list", "directory", "contact", "info", "phone", "number"):
        assert tok not in l1
