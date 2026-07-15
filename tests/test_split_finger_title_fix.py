"""Root fix for the RunSwift "Stength" -> "Strength" source typo.

The vendor misspells the class name; the connector must correct it at ingest so a
re-scrape never reintroduces it (the paired backfill repairs already-landed rows).
"""

from __future__ import annotations

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.split_finger import SplitFingerClient, _clean_source_name


def test_clean_source_name_fixes_stength() -> None:
    assert _clean_source_name("Stength/Conditioning/Agility") == "Strength/Conditioning/Agility"


def test_clean_source_name_whole_word_and_idempotent() -> None:
    # Already-correct text is untouched (idempotent), and it is a whole-word fix.
    assert _clean_source_name("Strength/Conditioning/Agility") == "Strength/Conditioning/Agility"
    assert _clean_source_name("TRX & Tabata w/Toree") == "TRX & Tabata w/Toree"


def _class_hit(name: str) -> EnrichedHit:
    raw = {
        "kind": "class",
        "item": {"name": name, "prices": {"basePrice": {"cost": 10}},
                 "minAgeLimit": 10, "maxAgeLimit": 18},
        "start_date": "2026-07-20",
        "start_time": "15:30",
        "end_time": "16:30",
        "url": "https://book.runswiftapp.com/facilities/split-finger-athletics/classes?classId=1&date=2026-07-20",
    }
    return EnrichedHit(raw_hit=RawHit(source="split_finger", source_stable_id=raw["url"], name=name), enriched=raw)


def test_class_payload_title_is_corrected() -> None:
    payload = SplitFingerClient().to_event_payload(_class_hit("Stength/Conditioning/Agility"))
    assert payload.name == "Strength/Conditioning/Agility"


def test_non_typo_class_title_unchanged() -> None:
    payload = SplitFingerClient().to_event_payload(_class_hit("Team Speed & Agility"))
    assert payload.name == "Team Speed & Agility"
