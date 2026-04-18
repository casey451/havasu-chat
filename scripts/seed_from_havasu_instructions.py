"""
Import programs and events from docs/HAVASU_CHAT_SEED_INSTRUCTIONS.md.

There is no Provider table in this codebase — provider metadata from the
instruction file is denormalized onto each Program (provider_name, contacts).

Idempotency: programs get tag "havasu_instructions_seed_v1"; events get
"havasu_instructions_event_v1" in tags. Re-running skips rows that already exist.

Usage:
  py -3 scripts/seed_from_havasu_instructions.py          # run import
  py -3 scripts/seed_from_havasu_instructions.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.core.search import generate_query_embedding  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Event, Program  # noqa: E402
from app.schemas.event import EventCreate, normalize_event_url  # noqa: E402

PROG_TAG = "havasu_instructions_seed_v1"
EVT_TAG = "havasu_instructions_event_v1"

_DAY_MAP = {
    "MON": "monday",
    "TUE": "tuesday",
    "WED": "wednesday",
    "THU": "thursday",
    "FRI": "friday",
    "SAT": "saturday",
    "SUN": "sunday",
}


def _norm_days(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if not isinstance(x, str):
            continue
        k = x.strip().upper()
        if k in _DAY_MAP:
            out.append(_DAY_MAP[k])
        else:
            low = x.strip().lower()
            if low in {
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            }:
                out.append(low)
    return out


def _needs_verification(obj: dict) -> bool:
    blob = yaml.dump(obj, allow_unicode=True)
    return "⚠️" in blob or bool(obj.get("needs_verification"))


def _is_draft(obj: dict) -> bool:
    return bool(obj.get("draft"))


def _coerce_time(val: object, fallback: str) -> str:
    if val is None or val == "":
        return fallback
    s = str(val).strip()
    if s.upper() in {"TBD", "N/A"}:
        return fallback
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return fallback


def _coerce_description(text: str, schedule_note: object) -> str:
    parts: list[str] = []
    if schedule_note and str(schedule_note).strip():
        parts.append(f"Schedule: {str(schedule_note).strip()}")
    parts.append(text.strip())
    desc = "\n\n".join(parts).strip()
    if len(desc) < 20:
        desc = desc + " " * (20 - len(desc)) + "."
    return desc


def _coerce_age(val: object) -> tuple[int | None, str | None]:
    """Return (age_int_or_none, optional prefix for description)."""
    if val is None or val == "":
        return None, None
    if isinstance(val, float) and val < 1:
        return None, "Ages under 1 year (see description for months). "
    if isinstance(val, float):
        return int(val), None
    if isinstance(val, int):
        return val, None
    try:
        f = float(str(val))
        if f < 1:
            return None, "Ages under 1 year. "
        return int(f), None
    except ValueError:
        return None, None


def _coerce_cost_str(val: object) -> tuple[str | None, bool]:
    """Return (cost string for Program.cost, contact_pricing flag)."""
    if val is None or val == "":
        return None, False
    if isinstance(val, str) and "CONTACT_FOR_PRICING" in val.upper():
        return None, True
    if isinstance(val, (int, float)):
        return f"${float(val):.2f}", False
    s = str(val).strip()
    if "CONTACT_FOR_PRICING" in s.upper():
        return None, True
    return s, False


def _sanitize_phone(val: object) -> str | None:
    if val is None or not str(val).strip():
        return None
    digits = re.sub(r"\D", "", str(val))
    if len(digits) < 10:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:10]}"


def _sanitize_email(val: object) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or "⚠️" in s or "null" in s.lower():
        return None
    if "@" not in s or "." not in s.split("@", 1)[-1]:
        return None
    return s


def _sanitize_url(val: object, fallback: str) -> str:
    if val is None or not str(val).strip():
        return fallback
    s = str(val).strip()
    if "⚠️" in s or s.lower() == "null":
        return fallback
    if not s.startswith("http"):
        if "." in s:
            return normalize_event_url(s)
    return normalize_event_url(s)


def _parse_date_range(val: object) -> list[date]:
    s = str(val).strip().strip('"')
    if "through" in s.lower():
        parts = re.split(r"\s+through\s+", s, flags=re.IGNORECASE)
        if len(parts) == 2:
            try:
                d0 = date.fromisoformat(parts[0].strip())
                d1 = date.fromisoformat(parts[1].strip())
                out: list[date] = []
                cur = d0
                while cur <= d1:
                    out.append(cur)
                    cur = date.fromordinal(cur.toordinal() + 1)
                return out
            except ValueError:
                return []
    if "tbd" in s.lower() or "august 2026" in s.lower():
        return []
    try:
        return [date.fromisoformat(s[:10])]
    except ValueError:
        return []


def _extract_yaml_blocks(section: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"```yaml\s*\n(.*?)```", section, re.DOTALL | re.IGNORECASE)]


def _extract_provider_meta(header: str) -> dict:
    m = re.search(r"```\s*\n(.*?)```", header, re.DOTALL)
    if not m:
        return {}
    body = m.group(1).strip()
    if body.lower().startswith("yaml"):
        return {}
    try:
        data = yaml.safe_load(body)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _default_event_url(provider_meta: dict) -> str:
    for key in ("website", "facebook"):
        v = provider_meta.get(key)
        if v and str(v).strip() and "⚠️" not in str(v):
            return _sanitize_url(v, "https://www.golakehavasu.com")
    return "https://www.golakehavasu.com"


def _split_business_chunks(text: str) -> list[tuple[dict, str]]:
    """Return list of (provider_meta, rest_of_section_after_header_fence)."""
    parts = re.split(r"\n## BUSINESS\s+\d+\s+—\s+", text)
    out: list[tuple[dict, str]] = []
    for chunk in parts[1:]:
        sub = chunk.split("\n### Programs", 1)
        head = sub[0]
        tail = sub[1] if len(sub) > 1 else ""
        meta = _extract_provider_meta(head)
        out.append((meta, tail))
    return out


def _program_from_item(item: dict, provider_meta: dict) -> Program | None:
    if "activity_category" not in item:
        return None
    title = str(item.get("title", "")).strip()
    if len(title) < 3:
        return None

    desc = str(item.get("description", "")).strip()
    if isinstance(desc, str) and desc.endswith(">"):
        desc = desc.rstrip(">").strip()
    schedule_note = item.get("schedule_note")
    age_min, p1 = _coerce_age(item.get("age_min"))
    age_max, p2 = _coerce_age(item.get("age_max"))
    note_prefix = (p1 or "") + (p2 or "")
    desc = _coerce_description(note_prefix + desc, schedule_note)

    start_t = _coerce_time(item.get("schedule_start_time"), "09:00")
    end_t = _coerce_time(item.get("schedule_end_time"), "10:00")
    if start_t == end_t:
        end_t = "10:30"

    cost_str, contact_px = _coerce_cost_str(item.get("cost"))
    tags = [PROG_TAG]
    if contact_px:
        tags.append("contact_for_pricing")
    nv = _needs_verification(item) or _needs_verification(provider_meta)
    if nv:
        tags.append("needs_verification")
    if _is_draft(item):
        tags.append("draft")

    provider_name = str(item.get("provider_name") or provider_meta.get("provider_name") or "Local provider").strip()
    loc = str(item.get("location_name") or "Lake Havasu City").strip()
    if len(loc) < 3:
        loc = "Lake Havasu City, AZ"

    loc_addr = item.get("location_address")
    if loc_addr is not None:
        loc_addr = str(loc_addr).strip() or None

    phone = _sanitize_phone(item.get("contact_phone")) or _sanitize_phone(provider_meta.get("phone"))
    email = _sanitize_email(item.get("contact_email")) or _sanitize_email(provider_meta.get("email"))
    url = item.get("contact_url")
    fb = provider_meta.get("facebook")
    fallback = _default_event_url(provider_meta)
    contact_url = _sanitize_url(url if url else fb, fallback)

    raw_cat = str(item.get("activity_category", "sports")).strip().lower()
    cat = raw_cat.split("/")[0].strip().replace(" ", "_")
    if len(cat) < 2:
        cat = "sports"

    draft = _is_draft(item)
    source = "scraped" if (nv or draft or contact_px) else "admin"
    verified = source == "admin"
    # Scraped rows (unverified / needs_verification / contact_for_pricing / draft)
    # land inactive by default. Admin flips is_active=True via the admin UI
    # after a quick sanity check. Clean admin rows go live immediately.
    active_default = (not draft) and (source == "admin")

    emb_text = f"{title}\n{provider_name}\n{desc}\n{cat}"
    embedding = generate_query_embedding(emb_text)

    return Program(
        title=title,
        description=desc,
        activity_category=cat,
        age_min=age_min,
        age_max=age_max,
        schedule_days=_norm_days(item.get("schedule_days")),
        schedule_start_time=start_t,
        schedule_end_time=end_t,
        location_name=loc,
        location_address=loc_addr,
        cost=cost_str,
        provider_name=provider_name,
        contact_phone=phone,
        contact_email=email,
        contact_url=contact_url,
        source=source,
        verified=verified,
        is_active=active_default,
        tags=tags,
        embedding=embedding,
    )


def _event_from_item(item: dict, provider_meta: dict) -> list[Event]:
    if "date" not in item or "activity_category" in item:
        return []
    title = str(item.get("title", "")).strip()
    desc = str(item.get("description", "")).strip()
    desc = _coerce_description(desc, None)
    loc = str(item.get("location", "Lake Havasu City, AZ")).strip()
    if "⚠️" in loc or len(loc) < 3:
        loc = "Lake Havasu City, AZ — see description for venue details."
    dates = _parse_date_range(item.get("date"))
    if not dates:
        return []

    time_s = _coerce_time(item.get("time"), "18:00")
    h, m = map(int, time_s.split(":"))
    st = time(h, m)
    et = time((h + 1) % 24, m)

    provider = str(item.get("provider") or provider_meta.get("provider_name") or "Community organizer").strip()
    cost_raw = item.get("cost")
    _, contact_px = _coerce_cost_str(cost_raw)
    extra = ""
    if isinstance(cost_raw, (int, float)):
        extra = f"\n\nAdmission: ${float(cost_raw):.2f}"
    elif contact_px:
        extra = "\n\nPricing: contact organizer."
    if item.get("cost_description"):
        extra += f"\n{item.get('cost_description')}"
    desc = (desc + extra).strip()
    desc = _coerce_description(desc, None)

    tags = [EVT_TAG]
    if contact_px:
        tags.append("contact_for_pricing")
    if _needs_verification(item):
        tags.append("needs_verification")

    phone = _sanitize_phone(provider_meta.get("phone"))
    event_url = _default_event_url(provider_meta)

    out: list[Event] = []
    for d in dates:
        payload_dict = {
            "title": title,
            "date": d,
            "start_time": st,
            "end_time": et,
            "location_name": loc[:500],
            "description": desc,
            "event_url": event_url,
            "contact_name": provider[:255],
            "contact_phone": phone,
            "tags": tags,
            "embedding": None,
            "status": "live",
            "created_by": "seed_instructions",
            "admin_review_by": None,
        }
        emb_in = f"{title}\n{loc}\n{desc}"
        emb = generate_query_embedding(emb_in)
        ec = EventCreate(
            title=title,
            date=d,
            start_time=st,
            end_time=et,
            location_name=payload_dict["location_name"],
            description=desc,
            event_url=event_url,
            contact_name=payload_dict["contact_name"],
            contact_phone=phone,
            tags=tags,
            embedding=emb,
            status="live",
            created_by="seed_instructions",
            admin_review_by=None,
        )
        out.append(Event.from_create(ec))
    return out


def run_import(md_path: Path, dry_run: bool) -> dict:
    text = md_path.read_text(encoding="utf-8")
    chunks = _split_business_chunks(text)

    programs: list[Program] = []
    events: list[Event] = []
    skipped_programs = 0
    skipped_events = 0

    for provider_meta, tail in chunks:
        ev_split = tail.split("\n### Events", 1)
        prog_section = ev_split[0]
        ev_section = ev_split[1] if len(ev_split) > 1 else ""

        for raw_yaml in _extract_yaml_blocks(prog_section):
            try:
                data = yaml.safe_load(raw_yaml)
            except Exception:
                skipped_programs += 1
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "activity_category" not in item:
                    continue
                p = _program_from_item(item, provider_meta)
                if p:
                    programs.append(p)

        for raw_yaml in _extract_yaml_blocks(ev_section):
            try:
                data = yaml.safe_load(raw_yaml)
            except Exception:
                skipped_events += 1
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                evs = _event_from_item(item, provider_meta)
                events.extend(evs)

    stats = {
        "programs_built": len(programs),
        "events_built": len(events),
        "skipped_yaml_program": skipped_programs,
        "skipped_yaml_event": skipped_events,
        "programs_inserted": 0,
        "programs_skipped_idempotent": 0,
        "events_inserted": 0,
        "events_skipped_idempotent": 0,
    }

    if dry_run:
        return stats

    init_db()
    with SessionLocal() as db:
        # Match on title+provider so re-runs do not duplicate if tags differ or DB was reset.
        existing_prog_keys = {
            (p.title.strip().lower(), p.provider_name.strip().lower())
            for p in db.query(Program).all()
        }
        existing_evt = {
            (e.title.strip().lower(), e.date.isoformat()) for e in db.query(Event).all()
        }

        for p in programs:
            keyp = (p.title.strip().lower(), p.provider_name.strip().lower())
            if keyp in existing_prog_keys:
                stats["programs_skipped_idempotent"] += 1
                continue
            db.add(p)
            stats["programs_inserted"] += 1
            existing_prog_keys.add(keyp)

        for e in events:
            key = (e.title.strip().lower(), e.date.isoformat())
            if key in existing_evt:
                stats["events_skipped_idempotent"] += 1
                continue
            db.add(e)
            stats["events_inserted"] += 1
            existing_evt.add(key)

        db.commit()

    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--path",
        type=Path,
        default=ROOT / "docs" / "HAVASU_CHAT_SEED_INSTRUCTIONS.md",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.path.is_file():
        print(f"Missing file: {args.path}", file=sys.stderr)
        sys.exit(1)
    stats = run_import(args.path, args.dry_run)
    print("--- Havasu instructions seed ---")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print("\nNote: No Provider table exists; provider_name + contacts live on Program/Event rows.")
    if args.dry_run:
        print("(dry-run: no database writes)")


if __name__ == "__main__":
    main()
