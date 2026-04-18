"""
Populate concierge columns on programs from HAVASU_CHAT_MASTER.md Section 9.

Reads YAML program blocks under each ## BUSINESS header, matches DB rows by
(normalized provider_name, normalized title), then fills show_pricing_cta,
cost_description, schedule_note, draft only when those fields are still at
defaults (safe re-run). Does not touch provider_id or legacy columns.

Usage:
  python -m app.db.populate_program_concierge_fields
  python -m app.db.populate_program_concierge_fields --master path/to/HAVASU_CHAT_MASTER.md
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.db.seed_providers import DEFAULT_MASTER_PATH, _norm_provider_name

_YAML_FENCE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_BUSINESS_SPLIT = re.compile(r"\n## BUSINESS\s+\d+\s+—\s+", re.IGNORECASE)
_HEADER_FENCE = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


def _norm_program_title(title: str) -> str:
    """NFKC + dash/quote folding + whitespace collapse (no provider-specific suffix strips)."""
    s = unicodedata.normalize("NFKC", (title or "").strip())
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
    return " ".join(s.lower().split())


def _parse_business_header_meta(head: str) -> dict[str, str]:
    """First ``` ... ``` in chunk before ### Programs — plain key: value lines."""
    m = _HEADER_FENCE.search(head)
    if not m:
        return {}
    body = m.group(1).strip()
    if body.lower().startswith("yaml"):
        return {}
    meta: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, rest = line.partition(":")
        key = k.strip().lower()
        meta[key] = rest.strip()
    return meta


def _extract_yaml_program_sections(tail: str) -> list[str]:
    return [m.group(1) for m in _YAML_FENCE.finditer(tail)]


def _cost_is_contact_for_pricing(val: Any) -> bool:
    if val is None:
        return False
    return "CONTACT_FOR_PRICING" in str(val).upper()


def _draft_explicit_true(val: Any) -> bool:
    if val is True:
        return True
    if isinstance(val, str) and val.strip().lower() in ("true", "yes", "1"):
        return True
    return False


def _desired_cost_description(item: dict[str, Any]) -> str | None:
    if _cost_is_contact_for_pricing(item.get("cost")):
        return None
    raw = item.get("cost_description")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _desired_schedule_note(item: dict[str, Any]) -> str | None:
    raw = item.get("schedule_note")
    if raw is None:
        return None
    s = str(raw)
    if not s.strip():
        return None
    return s


def _concierge_intervention(prog: Any) -> bool:
    """True if any concierge column was set away from defaults — do not overwrite."""
    if prog.show_pricing_cta:
        return True
    cd = prog.cost_description
    if cd is not None and str(cd).strip():
        return True
    sn = prog.schedule_note
    if sn is not None and str(sn).strip():
        return True
    if prog.draft:
        return True
    if prog.pending_review:
        return True
    if prog.admin_review_by is not None:
        return True
    return False


def parse_master_program_index(
    master_text: str,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    """
    Build (norm_provider, norm_title) -> list of raw YAML program dicts.
    Also returns all program items that have draft: true (for unmatched reporting).
    """
    text = master_text if master_text.startswith("\n") else "\n" + master_text
    parts = _BUSINESS_SPLIT.split(text)
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    draft_items: list[dict[str, Any]] = []

    for chunk in parts[1:]:
        sub = chunk.split("\n### Programs", 1)
        head = sub[0]
        tail = sub[1] if len(sub) > 1 else ""
        header_meta = _parse_business_header_meta(head)
        fallback_provider = (header_meta.get("provider_name") or "").strip()

        business_label = chunk.strip().split("\n", 1)[0].strip() if chunk.strip() else "unknown"
        for raw_yaml in _extract_yaml_program_sections(tail):
            try:
                data = yaml.safe_load(raw_yaml)
            except Exception as e:
                raise RuntimeError(
                    f"HAVASU_CHAT_MASTER.md: YAML parse failed in ### Programs block "
                    f"(business section {business_label!r}): {e}"
                ) from e
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "activity_category" not in item:
                    continue
                title = str(item.get("title", "")).strip()
                if len(title) < 3:
                    continue
                pvn = str(item.get("provider_name") or fallback_provider or "").strip()
                if not pvn:
                    continue
                np = _norm_provider_name(pvn)
                nt = _norm_program_title(title)
                index.setdefault((np, nt), []).append(item)
                if _draft_explicit_true(item.get("draft")):
                    draft_items.append(item)

    return index, draft_items


@dataclass
class PopulateConciergeResult:
    programs_scanned: int = 0
    programs_matched: int = 0
    programs_no_match: list[tuple[str, str, str]] = field(default_factory=list)  # id, provider, title
    programs_ambiguous: list[tuple[str, str, str, int]] = field(
        default_factory=list
    )  # id, provider, title, n_blocks
    programs_skipped_intervention: int = 0
    programs_skipped_matched_noop: int = 0
    programs_updated: int = 0
    set_show_pricing_cta: int = 0
    set_cost_description: int = 0
    set_schedule_note: int = 0
    set_draft: int = 0
    draft_master_items_with_no_db_match: list[tuple[str, str]] = field(
        default_factory=list
    )  # provider_name, title


def _print_report(result: PopulateConciergeResult) -> None:
    print("=== Populate program concierge fields ===")
    print(f"programs scanned: {result.programs_scanned}")
    print(f"programs matched to exactly one master block: {result.programs_matched}")
    print(f"programs skipped (concierge already touched / non-default): {result.programs_skipped_intervention}")
    print(f"programs skipped (matched, no field changes needed): {result.programs_skipped_matched_noop}")
    print(f"programs updated (>=1 concierge field written): {result.programs_updated}")
    print(f"show_pricing_cta set True this run: {result.set_show_pricing_cta}")
    print(f"cost_description set this run: {result.set_cost_description}")
    print(f"schedule_note set this run: {result.set_schedule_note}")
    print(f"draft set True this run: {result.set_draft}")
    print(f"ambiguous master key (multiple YAML rows): {len(result.programs_ambiguous)}")
    for pid, prov, title, n in result.programs_ambiguous:
        print(f"  program id={pid}  provider_name={prov!r}  title={title!r}  blocks={n}")
    print(f"no matching master block: {len(result.programs_no_match)}")
    for pid, prov, title in result.programs_no_match:
        print(f"  program id={pid}  provider_name={prov!r}  title={title!r}")
    if result.draft_master_items_with_no_db_match:
        print(
            "draft master program blocks with no matching DB program "
            f"({len(result.draft_master_items_with_no_db_match)}):"
        )
        for prov, title in result.draft_master_items_with_no_db_match:
            print(f"  master draft: provider_name={prov!r}  title={title!r}")


def populate_program_concierge_fields(
    db: Session,
    *,
    master_path: Path | None = None,
) -> PopulateConciergeResult:
    from app.db.models import Program

    path = master_path or DEFAULT_MASTER_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Master file not found: {path}")

    raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
    # Split pattern anchors on "\n## BUSINESS"; ensure a leading newline so files
    # that start with "## BUSINESS" still chunk correctly.
    index, draft_master_items = parse_master_program_index("\n" + raw)
    result = PopulateConciergeResult()
    now = datetime.now(UTC).replace(tzinfo=None)

    db_keys = {
        (_norm_provider_name(p.provider_name), _norm_program_title(p.title))
        for p in db.query(Program).all()
    }
    for item in draft_master_items:
        pvn = str(item.get("provider_name", "")).strip()
        title = str(item.get("title", "")).strip()
        if len(title) < 3:
            continue
        k = (_norm_provider_name(pvn), _norm_program_title(title))
        if k not in db_keys:
            result.draft_master_items_with_no_db_match.append((pvn, title))

    programs = db.query(Program).order_by(Program.id).all()
    result.programs_scanned = len(programs)

    for prog in programs:
        np = _norm_provider_name(prog.provider_name)
        nt = _norm_program_title(prog.title)
        key = (np, nt)
        blocks = index.get(key, [])

        if len(blocks) == 0:
            result.programs_no_match.append((prog.id, prog.provider_name, prog.title))
            continue
        if len(blocks) > 1:
            result.programs_ambiguous.append((prog.id, prog.provider_name, prog.title, len(blocks)))
            continue

        result.programs_matched += 1
        item = blocks[0]

        if _concierge_intervention(prog):
            result.programs_skipped_intervention += 1
            continue

        want_show = _cost_is_contact_for_pricing(item.get("cost"))
        want_cd = _desired_cost_description(item)
        want_sn = _desired_schedule_note(item)
        want_draft = _draft_explicit_true(item.get("draft"))

        changed = False
        if want_show != prog.show_pricing_cta:
            prog.show_pricing_cta = want_show
            changed = True
            if want_show:
                result.set_show_pricing_cta += 1
        if want_cd != prog.cost_description:
            prog.cost_description = want_cd
            changed = True
            if want_cd is not None:
                result.set_cost_description += 1
        if want_sn != prog.schedule_note:
            prog.schedule_note = want_sn
            changed = True
            if want_sn is not None:
                result.set_schedule_note += 1
        if want_draft != prog.draft:
            prog.draft = want_draft
            changed = True
            if want_draft:
                result.set_draft += 1

        if changed:
            prog.updated_at = now
            result.programs_updated += 1
        else:
            result.programs_skipped_matched_noop += 1

    db.commit()
    _print_report(result)
    if (
        result.programs_scanned >= 50
        and len(result.programs_no_match) * 100 > result.programs_scanned * 5
    ):
        print(
            "WARNING: no-match count exceeds 5% of scanned programs; "
            "check seed instructions vs HAVASU_CHAT_MASTER titles before loosening match logic."
        )
    return result


def main(argv: list[str] | None = None) -> int:
    from app.bootstrap_env import ensure_dotenv_loaded
    from app.db.database import SessionLocal, init_db

    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Populate program concierge fields from master file")
    parser.add_argument(
        "--master",
        type=Path,
        default=None,
        help="Path to HAVASU_CHAT_MASTER.md (default: repo root master)",
    )
    args = parser.parse_args(argv)
    init_db()
    with SessionLocal() as db:
        populate_program_concierge_fields(db, master_path=args.master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
