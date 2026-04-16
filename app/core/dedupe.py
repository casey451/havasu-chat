from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Event


def find_duplicate(candidate_event: dict[str, Any], db: Session) -> Event | None:
    candidate_embedding = candidate_event.get("embedding")
    if not candidate_embedding:
        return None

    candidate_date = _coerce_date(candidate_event.get("date"))
    candidate_location = _normalize_text(candidate_event.get("location_name", ""))

    best_match: Event | None = None
    best_score = 0.0

    for existing_event in db.query(Event).all():
        if not existing_event.embedding:
            continue

        similarity = cosine_similarity(candidate_embedding, existing_event.embedding)
        if similarity < 0.85:
            continue

        if not _dates_within_one_day(candidate_date, existing_event.date):
            continue

        if not _locations_similar(candidate_location, existing_event.location_normalized):
            continue

        if similarity > best_score:
            best_score = similarity
            best_match = existing_event

    return best_match


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_mag = math.sqrt(sum(a * a for a in left))
    right_mag = math.sqrt(sum(b * b for b in right))

    if left_mag == 0 or right_mag == 0:
        return 0.0
    return dot / (left_mag * right_mag)


def _dates_within_one_day(left: date, right: date) -> bool:
    return abs((left - right).days) <= 1


def _locations_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
