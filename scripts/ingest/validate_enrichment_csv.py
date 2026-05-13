"""Validate a filled enrichment CSV before any DB write.

Operator workflow tool. Takes the path to a filled
``templates/enrichment/business_enrichment_template.csv`` and runs every
row through a fixed set of rules. Prints a structured PASS / FAIL report
to stdout and exits non-zero if anything fails.

USAGE
-----
    python scripts/ingest/validate_enrichment_csv.py path/to/filled.csv

Validation rules (kept terse — one short sentence each):

* All required columns must be present in the header.
* ``provider_name`` is non-empty.
* ``category`` is one of the **new-taxonomy** slugs in ``CATEGORY_LABELS``;
  legacy slugs (deleted / renamed) are rejected with an explicit error.
* ``address`` is non-empty.
* ``phone`` digit-only is exactly 10 chars and is NOT a NANP 555-01XX
  placeholder (the same regex used in ``app/home/queries.py``).
* ``owner_email`` matches a basic ``name@host.tld`` regex.
* ``hava_voice_description`` is between 80 and 400 chars (rough 2-3
  sentence band).
* ``last_verified_at`` parses via ``datetime.fromisoformat`` and is
  not in the future (compared in UTC).
* ``verification_method`` is one of ``ALLOWED_VERIFICATION_METHODS``.

This module exposes a small library API (``validate_row``,
``validate_csv``) so the ingest script can call into it without
re-implementing the rules.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

# Project-root on sys.path so this script can be invoked either as
#   python scripts/ingest/validate_enrichment_csv.py ...
# or as
#   python -m scripts.ingest.validate_enrichment_csv ...
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ─────────── shared with operator-facing README ───────────

REQUIRED_COLUMNS: tuple[str, ...] = (
    "provider_name",
    "category",
    "address",
    "phone",
    "owner_email",
    "hava_voice_description",
    "last_verified_at",
    "verification_method",
)

# website + hours are accepted but not required.
OPTIONAL_COLUMNS: tuple[str, ...] = ("website", "hours")

ALLOWED_VERIFICATION_METHODS: tuple[str, ...] = (
    "phone_call",
    "in_person",
    "web_form_submission",
    "email_confirmation",
)

# Mirrors `app/home/queries.py::_PLACEHOLDER_PHONE_RE`.
_PLACEHOLDER_PHONE_RE = re.compile(r"^\d{3}55501\d{2}$")

# Basic email shape — local@host.tld with at least one dot in the host.
# Intentionally loose; we're catching typos, not RFC-compliance.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DESCRIPTION_MIN_CHARS = 80
DESCRIPTION_MAX_CHARS = 400


# ─────────── allowed categories (read from app.home.queries) ───────────


# Legacy CSV slugs — must not pass validation (Phase 3.2 taxonomy rewrite).
_REJECTED_ENRICHMENT_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "family",
        "community",
        "eat-and-drink",
        "home-services",
        "health",
        "outdoors-and-parks",
        "shopping",
        "auto-and-gas",
        "lodging",
    }
)


def _allowed_categories() -> set[str]:
    """Return canonical category slugs accepted for enrichment CSV ``category``."""
    from app.home.queries import CATEGORY_LABELS  # local import — see docstring

    return set(CATEGORY_LABELS.keys())


# ─────────── result types ───────────


@dataclass
class RowResult:
    row_number: int  # 1-indexed, header is row 1, first data row is row 2
    provider_name: str
    passed: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    csv_path: Path
    total_rows: int
    passed: int
    failed: int
    rows: list[RowResult] = field(default_factory=list)
    fatal: list[str] = field(default_factory=list)  # header / file-level errors

    @property
    def ok(self) -> bool:
        return self.failed == 0 and not self.fatal


# ─────────── per-field validators ───────────


def _check_phone(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return f"phone must be 10 NANP digits; got {len(digits)} digit(s)"
    if _PLACEHOLDER_PHONE_RE.match(digits):
        return "phone is a reserved 555-01XX placeholder — use a real number"
    return None


def _check_email(raw: str) -> str | None:
    if not _EMAIL_RE.match(raw):
        return "owner_email does not look like a valid email"
    return None


def _check_description(raw: str) -> str | None:
    n = len(raw.strip())
    if n < DESCRIPTION_MIN_CHARS:
        return (
            f"hava_voice_description is {n} chars; "
            f"must be at least {DESCRIPTION_MIN_CHARS}"
        )
    if n > DESCRIPTION_MAX_CHARS:
        return (
            f"hava_voice_description is {n} chars; "
            f"must be at most {DESCRIPTION_MAX_CHARS}"
        )
    return None


def _check_last_verified_at(raw: str) -> tuple[datetime | None, str | None]:
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None, "last_verified_at must be ISO-8601 (e.g. 2026-05-08T09:30:00-07:00)"
    # Compare in UTC. If naive, treat as UTC for the future-check.
    cmp = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    now_utc = datetime.now(UTC)
    if cmp > now_utc:
        return dt, "last_verified_at is in the future"
    return dt, None


def _check_verification_method(raw: str) -> str | None:
    if raw not in ALLOWED_VERIFICATION_METHODS:
        allowed = ", ".join(ALLOWED_VERIFICATION_METHODS)
        return f"verification_method {raw!r} not in: {allowed}"
    return None


def _check_category(raw: str, allowed: set[str]) -> str | None:
    if raw in _REJECTED_ENRICHMENT_CATEGORY_SLUGS:
        return (
            f"category {raw!r} is a legacy slug removed or renamed in the Phase 3.2 "
            f"taxonomy; use a current slug (e.g. eat-drink, home-property-services)"
        )
    if raw not in allowed:
        return f"category {raw!r} is not in the allowed set"
    return None


# ─────────── row-level validation ───────────


def validate_row(
    row: dict[str, str],
    *,
    row_number: int,
    allowed_categories: set[str] | None = None,
) -> RowResult:
    """Run every rule against one CSV row and collect errors."""
    if allowed_categories is None:
        allowed_categories = _allowed_categories()

    name = (row.get("provider_name") or "").strip()
    errors: list[str] = []

    if not name:
        errors.append("provider_name is empty")

    category = (row.get("category") or "").strip()
    if not category:
        errors.append("category is empty")
    else:
        e = _check_category(category, allowed_categories)
        if e:
            errors.append(e)

    address = (row.get("address") or "").strip()
    if not address:
        errors.append("address is empty")

    phone = (row.get("phone") or "").strip()
    if not phone:
        errors.append("phone is empty")
    else:
        e = _check_phone(phone)
        if e:
            errors.append(e)

    email = (row.get("owner_email") or "").strip()
    if not email:
        errors.append("owner_email is empty")
    else:
        e = _check_email(email)
        if e:
            errors.append(e)

    desc = row.get("hava_voice_description") or ""
    if not desc.strip():
        errors.append("hava_voice_description is empty")
    else:
        e = _check_description(desc)
        if e:
            errors.append(e)

    lva = (row.get("last_verified_at") or "").strip()
    if not lva:
        errors.append("last_verified_at is empty")
    else:
        _dt, e = _check_last_verified_at(lva)
        if e:
            errors.append(e)

    method = (row.get("verification_method") or "").strip()
    if not method:
        errors.append("verification_method is empty")
    else:
        e = _check_verification_method(method)
        if e:
            errors.append(e)

    return RowResult(
        row_number=row_number,
        provider_name=name or "(no name)",
        passed=not errors,
        errors=errors,
    )


# ─────────── file-level validation ───────────


def _iter_data_rows(reader: csv.DictReader) -> Iterable[tuple[int, dict[str, str]]]:
    """Yield (row_number, row_dict) skipping comment rows.

    Treats any row whose ``provider_name`` cell starts with ``#`` as a
    comment line (the example row in the template). Header is row 1, so
    the first data row is row 2.
    """
    for idx, row in enumerate(reader, start=2):
        first_val = (row.get("provider_name") or "").lstrip()
        if first_val.startswith("#"):
            continue
        # Skip wholly-empty rows (trailing blank lines).
        if not any((v or "").strip() for v in row.values()):
            continue
        yield idx, row


def validate_csv(csv_path: Path) -> ValidationReport:
    report = ValidationReport(csv_path=csv_path, total_rows=0, passed=0, failed=0)

    if not csv_path.is_file():
        report.fatal.append(f"file not found: {csv_path}")
        return report

    try:
        allowed = _allowed_categories()
    except Exception as exc:  # pragma: no cover — defensive import guard
        report.fatal.append(f"could not load CATEGORY_LABELS: {exc!r}")
        return report

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            report.fatal.append("CSV has no header row")
            return report
        present = set(reader.fieldnames)
        missing = [c for c in REQUIRED_COLUMNS if c not in present]
        if missing:
            report.fatal.append(f"missing required column(s): {', '.join(missing)}")
            return report

        for row_number, row in _iter_data_rows(reader):
            result = validate_row(row, row_number=row_number, allowed_categories=allowed)
            report.rows.append(result)
            report.total_rows += 1
            if result.passed:
                report.passed += 1
            else:
                report.failed += 1

    return report


# ─────────── stdout reporter ───────────


def print_report(report: ValidationReport) -> None:
    print(f"validating: {report.csv_path}")
    print("-" * 64)

    if report.fatal:
        for msg in report.fatal:
            print(f"  FATAL  {msg}")
        print("-" * 64)
        print("validation aborted — file/header level error")
        return

    for r in report.rows:
        if r.passed:
            print(f"  PASS  row {r.row_number:>3}  {r.provider_name}")
        else:
            print(f"  FAIL  row {r.row_number:>3}  {r.provider_name}")
            for err in r.errors:
                print(f"          - {err}")

    print("-" * 64)
    print(
        f"summary: {report.passed} passed, {report.failed} failed "
        f"out of {report.total_rows} data row(s)"
    )


# ─────────── CLI ───────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a filled enrichment CSV before ingest.",
    )
    parser.add_argument("csv_path", type=Path, help="path to filled enrichment CSV")
    args = parser.parse_args(argv)

    report = validate_csv(args.csv_path)
    print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
