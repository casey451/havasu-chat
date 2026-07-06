"""Street-address validation + normalization (S2).

Ingest sometimes stores a string in the address field that is not a real street
address: a Google plus-code (``CMVH+9G``), a PO box, an entity name (``25 Riviera
Blvd Llc``), a leading placeholder (``THE SHOPS AT, …``, ``Inside 21Glam …``),
``Online Only``, or a bare city (``Lake Havasu City, AZ 86403`` with no street).
These render as a broken pin / misleading location.

:func:`is_valid_street_address` is the guard: ``False`` for the patterns above so
the ingest path (and a cleanup pass) can store ``None`` instead of the garbage.
:func:`normalize_address` does light cleanup (trailing ``, USA`` drop, whitespace
fold) without changing a real address. Kept deliberately CONSERVATIVE — a plausible
street address (has a number + a street word) always validates, so a real address
is never blanked.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")

# Google Open Location Code (plus-code): a 4+ char cluster, a '+', then 2+ chars.
_PLUS_CODE = re.compile(r"\b[A-Z0-9]{4,}\+[A-Z0-9]{2,}\b")
_PO_BOX = re.compile(r"\bp\.?\s*o\.?\s*box\b|\bpost\s*office\s*box\b", re.IGNORECASE)
# Leading placeholders — the string starts with a non-address token.
_LEADING_PLACEHOLDER = re.compile(
    r"^\s*(the shops at\b|inside\b|online only\b|online\b|by appointment\b|"
    r"n/?a\b|tbd\b|see website\b|various\b|multiple\b)",
    re.IGNORECASE,
)
# Entity suffix standing in for the street line (e.g. "25 Riviera Blvd Llc").
_ENTITY_SUFFIX_STREET = re.compile(r"\b(l\.?l\.?c|inc|incorporated|co|corp)\.?\s*$", re.IGNORECASE)
# A "<number> <street name>" segment — the street line can be the 1st comma
# segment ("2400 Clubhouse Dr, …") or a later one when the address leads with a
# building/landmark name ("London Bridge Resort, 1477 Queens Bay, …").
_STREET_NUM_SEG = re.compile(r"^\s*\d+\s+[A-Za-z]")


def _street_segment(address: str) -> str:
    """The part before the first comma — where an entity-suffix street shows up."""
    return address.split(",", 1)[0].strip()


def normalize_address(address: str | None) -> str | None:
    """Light cleanup: fold whitespace, drop a trailing ``, USA``. Never rewrites a
    real address; returns ``None`` for empty input."""
    if not address:
        return None
    s = _WS.sub(" ", address.strip())
    s = re.sub(r",\s*USA\s*$", "", s, flags=re.IGNORECASE).strip().rstrip(",").strip()
    return s or None


def is_valid_street_address(address: str | None) -> bool:
    """True when ``address`` looks like a real street address.

    False for plus-codes, PO boxes, leading placeholders, entity-suffix streets,
    and bare-city strings. Conservative: a string whose street segment has a digit
    and is not one of those patterns is accepted.
    """
    norm = normalize_address(address)
    if not norm:
        return False
    if _PLUS_CODE.search(norm) or _PO_BOX.search(norm):
        return False
    if _LEADING_PLACEHOLDER.search(norm):
        return False
    if _ENTITY_SUFFIX_STREET.search(_street_segment(norm)):
        return False  # "25 Riviera Blvd Llc" — entity name where the street should end
    # A real street address carries a "<number> <street name>" segment somewhere.
    if not any(_STREET_NUM_SEG.match(seg) for seg in norm.split(",")):
        return False
    return True


def clean_street_address(address: str | None) -> str | None:
    """Return the normalized address when valid, else ``None`` — so ingest stores a
    real street address or nothing, never a plus-code / PO box / placeholder."""
    return normalize_address(address) if is_valid_street_address(address) else None
