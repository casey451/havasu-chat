"""
Upsert Provider rows from HAVASU_CHAT_MASTER.md Section 9 (business header blocks).

Idempotent: dedupe by normalized provider_name. Re-running updates metadata from the
master file without changing id, created_at, source, or is_active.

Usage (explicit invocation only — no import-time side effects):
  python -m app.db.seed_providers
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

# Project root: app/db/seed_providers.py -> parents[2] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MASTER_PATH = _REPO_ROOT / "HAVASU_CHAT_MASTER.md"

# Section 4.6 — must match exactly (no silent "other").
ALLOWED_CATEGORIES = frozenset(
    {
        "golf",
        "fitness",
        "sports",
        "swim",
        "martial_arts",
        "gymnastics",
        "cheer",
        "dance",
        "theatre",
        "art",
        "summer_camp",
        "bowling",
        "trampoline",
        "bmx",
        "soccer",
        "baseball",
        "jiu_jitsu",
        "tennis",
        "parks_rec",
        "other",
    }
)

# Keys allowed in the first ``` block of each business section (before ### Programs).
_HEADER_KEYS = frozenset(
    {
        "provider_name",
        "category",
        "address",
        "phone",
        "email",
        "website",
        "facebook",
        "hours",
        "notes",
        "draft",
        "instagram",
        "organization",
        "ages",
        "established",
        "pricing",
        "registration",
        "contact",
        "season",
        "owner",
        "tryout",
        "coach",
    }
)

_BUSINESS_START = re.compile(r"^## BUSINESS (\d+) — (.+)$", re.MULTILINE)
_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def _norm_provider_name(name: str) -> str:
    """Normalize a provider display name for comparison (dedupe + program backfill).

    Two layers:

    1. **Portable Unicode folding** — NFKC, collapse whitespace, lowercase, map en/em
       dash and minus variants to ASCII hyphen, map curly quotes and apostrophes to
       straight ASCII quotes, strip soft hyphen, replace NBSP with space. Safe for
       any locale; keeps matching stable when master vs. instructions differ only by
       typography.

    2. **Non-portable Lake Havasu §9 suffix folds** — end-anchored tails used because
       HAVASU_CHAT_SEED_INSTRUCTIONS.md program rows often use a shorter provider_name
       than the canonical business header in Section 9 (e.g. trailing (ACPA), - Sonics,
       - Lake Havasu City). Remove these once seed-data
       naming is canonicalized during **Phase 8** seed-data verification (owner phone
       review); then delete the suffix regexes here so normalization stays generic.

    Phase 1.3 uses this for Provider upsert keys; Phase 1.4 backfill imports the same
    function so exact-match keys always agree with the seed.
    """
    s = unicodedata.normalize("NFKC", (name or "").strip())
    for ch in ("\u2013", "\u2014", "\u2012", "\u2015", "\u2212"):
        s = s.replace(ch, "-")
    for old, new in (
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u201b", "'"),
        ("\u2032", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u2033", '"'),
    ):
        s = s.replace(old, new)
    s = s.replace("\u00a0", " ").replace("\u00ad", "")
    s = " ".join(s.lower().split())
    # Canonical provider headers in §9 sometimes add a subtitle or (ACPA); program rows
    # often use the shorter operating name. Fold only end-anchored tails so exact match
    # aligns without broad fuzzy matching.
    s = re.sub(r"\s*\(acpa\)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+sonics\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+-\s+lake havasu city\s*$", "", s, flags=re.IGNORECASE)
    return " ".join(s.split())


def _coerce_optional_str(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip()
    if not s or s.lower() == "null":
        return None
    upper = s.upper()
    if "NOT CONFIRMED" in upper or "DO NOT SEED PUBLIC" in upper:
        return None
    if "⚠️" in s and len(s) < 80 and "@" not in s and not any(c.isdigit() for c in s[:20]):
        # Short placeholder-only lines (e.g. unknown address) — treat as unknown
        if "UNKNOWN" in upper or "NOT CONFIRMED" in upper:
            return None
    return s


def _coerce_optional_str_lenient(val: str | None) -> str | None:
    """For notes/hours — keep content even if it contains ⚠️ (operational warnings)."""
    if val is None:
        return None
    s = val.strip()
    if not s or s.lower() == "null":
        return None
    return s


def _parse_bool(val: str | None) -> bool | None:
    if val is None:
        return None
    s = val.strip().lower()
    if s in ("true", "yes", "1"):
        return True
    if s in ("false", "no", "0", ""):
        return False
    return None


def _map_category(raw: str, provider_name: str) -> str:
    s = raw.strip().lower()
    if s not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Unknown category {raw!r} for provider {provider_name!r}. "
            f"Add an explicit mapping or fix the master file. Allowed: {sorted(ALLOWED_CATEGORIES)}"
        )
    return s


def _parse_business_fence(fence_body: str) -> dict[str, Any]:
    """Parse key: value lines; continuation lines append to the previous key."""
    lines = fence_body.strip().splitlines()
    raw: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if not line.strip():
            continue
        m = _KEY_LINE.match(line.strip())
        if m:
            key = m.group(1).strip().lower()
            rest = m.group(2).rstrip()
            if key not in _HEADER_KEYS:
                raise ValueError(f"Unknown header key {key!r} in business block.")
            current = key
            raw.setdefault(current, []).append(rest)
        else:
            if current is None:
                raise ValueError(f"Unexpected continuation line before any key: {line!r}")
            raw[current].append(line.strip())
    flat: dict[str, str] = {}
    for k, parts in raw.items():
        flat[k] = "\n".join(parts).strip()
    return flat


def _build_description(raw: dict[str, str]) -> str | None:
    parts: list[str] = []
    notes = _coerce_optional_str_lenient(raw.get("notes"))
    if notes:
        parts.append(notes)
    for extra in (
        "registration",
        "contact",
        "organization",
        "instagram",
        "ages",
        "established",
        "pricing",
        "season",
        "owner",
        "tryout",
        "coach",
    ):
        v = _coerce_optional_str_lenient(raw.get(extra))
        if v:
            parts.append(f"{extra}: {v}")
    if not parts:
        return None
    return "\n\n".join(parts)


def _header_has_verify_markers(raw: dict[str, str]) -> bool:
    blob = "\n".join(f"{k}: {v}" for k, v in sorted(raw.items()))
    return "⚠️" in blob or "NOT CONFIRMED" in blob.upper()


def _extract_first_fence_before_programs(section: str) -> str:
    """Return inner text of the first ``` block before '### Programs'."""
    cut = section.find("### Programs")
    head = section if cut < 0 else section[:cut]
    start = head.find("```")
    if start < 0:
        raise ValueError("No opening ``` in business section.")
    start += 3
    if head[start : start + 4].lower() == "yaml":
        raise ValueError("Expected plain ``` business header, found yaml fence.")
    end = head.find("```", start)
    if end < 0:
        raise ValueError("No closing ``` in business header.")
    return head[start:end]


def parse_businesses_from_master(text: str) -> list[tuple[int, str, dict[str, Any]]]:
    """
    Parse all ## BUSINESS N — blocks. Returns list of
    (business_number, header_title, parsed_row_dict).
    """
    matches = list(_BUSINESS_START.finditer(text))
    if len(matches) != 25:
        raise ValueError(f"Expected 25 ## BUSINESS headers, found {len(matches)}")
    out: list[tuple[int, str, dict[str, Any]]] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]
        fence_inner = _extract_first_fence_before_programs(section)
        raw_flat = _parse_business_fence(fence_inner)
        pn = raw_flat.get("provider_name", "").strip()
        if not pn:
            raise ValueError(f"BUSINESS {n} ({title}) has no provider_name.")
        cat_raw = raw_flat.get("category", "").strip()
        if not cat_raw:
            raise ValueError(f"BUSINESS {n} ({pn!r}) has no category.")
        category = _map_category(cat_raw, pn)
        draft_parsed = _parse_bool(raw_flat.get("draft"))
        draft = draft_parsed if draft_parsed is not None else False
        if "elite cheer athletics" in pn.lower() and not draft:
            draft = True
        verified = False
        row = {
            "provider_name": pn,
            "category": category,
            "address": _coerce_optional_str(raw_flat.get("address")),
            "phone": _coerce_optional_str(raw_flat.get("phone")),
            "email": _coerce_optional_str(raw_flat.get("email")),
            "website": _coerce_optional_str(raw_flat.get("website")),
            "facebook": _coerce_optional_str(raw_flat.get("facebook")),
            "hours": _coerce_optional_str_lenient(raw_flat.get("hours")),
            "description": _build_description(raw_flat),
            "draft": draft,
            "verified": verified,
            "_raw_for_flags": raw_flat,
        }
        out.append((n, title, row))
    out.sort(key=lambda x: x[0])
    return out


@dataclass
class SeedProvidersResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    draft_flagged: int = 0
    verify_marker_headers: int = 0
    total_in_db: int = 0


def _find_provider_by_norm(db: Session, norm: str) -> Any | None:
    from app.db.models import Provider

    for p in db.query(Provider).all():
        if _norm_provider_name(p.provider_name) == norm:
            return p
    return None


def seed_providers(
    db: Session,
    *,
    master_path: Path | None = None,
) -> SeedProvidersResult:
    """
    Parse HAVASU_CHAT_MASTER.md Section 9 and upsert Provider rows.

    Dedupe key: normalized provider_name (case-insensitive, collapsed whitespace).
    On match: updates address, phone, email, website, facebook, hours, description,
    category, draft, verified, updated_at — never id, created_at, source, or is_active.
    """
    from app.db.models import Provider

    path = master_path or DEFAULT_MASTER_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Master file not found: {path}")

    text = path.read_text(encoding="utf-8")
    businesses = parse_businesses_from_master(text)
    now = datetime.now(UTC).replace(tzinfo=None)
    result = SeedProvidersResult()

    for _n, _title, row in businesses:
        raw = row.pop("_raw_for_flags")
        if row["draft"]:
            result.draft_flagged += 1
        if _header_has_verify_markers(raw):
            result.verify_marker_headers += 1

        norm = _norm_provider_name(row["provider_name"])
        existing = _find_provider_by_norm(db, norm)
        if existing is None:
            p = Provider(
                id=str(uuid4()),
                provider_name=row["provider_name"],
                category=row["category"],
                address=row["address"],
                phone=row["phone"],
                email=row["email"],
                website=row["website"],
                facebook=row["facebook"],
                hours=row["hours"],
                description=row["description"],
                tier="free",
                sponsored_until=None,
                featured_description=None,
                draft=row["draft"],
                verified=row["verified"],
                is_active=True,
                pending_review=False,
                admin_review_by=None,
                source="seed",
                created_at=now,
                updated_at=now,
            )
            db.add(p)
            result.created += 1
        else:
            existing.category = row["category"]
            existing.address = row["address"]
            existing.phone = row["phone"]
            existing.email = row["email"]
            existing.website = row["website"]
            existing.facebook = row["facebook"]
            existing.hours = row["hours"]
            existing.description = row["description"]
            existing.draft = row["draft"]
            existing.verified = row["verified"]
            existing.updated_at = now
            result.updated += 1

    db.commit()
    result.total_in_db = db.query(Provider).count()
    return result


def print_seed_summary(result: SeedProvidersResult, master_path: Path) -> None:
    print("=== Provider seed summary ===")
    print(f"master file: {master_path.resolve()}")
    print(f"providers created: {result.created}")
    print(f"providers updated: {result.updated}")
    print(f"providers skipped: {result.skipped}")
    if result.skip_reasons:
        for r in result.skip_reasons:
            print(f"  skip reason: {r}")
    print(f"draft providers (draft=true in DB): {result.draft_flagged}")
    print(
        "business headers with VERIFY markers (U+26A0 or NOT CONFIRMED): "
        f"{result.verify_marker_headers}"
    )
    print(f"total rows in providers table: {result.total_in_db}")


def main(argv: list[str] | None = None) -> int:
    from app.bootstrap_env import ensure_dotenv_loaded
    from app.db.database import SessionLocal, init_db

    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Seed providers from HAVASU_CHAT_MASTER.md")
    parser.add_argument(
        "--master",
        type=Path,
        default=DEFAULT_MASTER_PATH,
        help="Path to HAVASU_CHAT_MASTER.md",
    )
    args = parser.parse_args(argv)

    init_db()
    with SessionLocal() as db:
        result = seed_providers(db, master_path=args.master)
    print_seed_summary(result, args.master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
