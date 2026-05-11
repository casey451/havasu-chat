"""Phase 1B — copy legacy Provider/Event/Program rows into ENTITY tables.

Invoked from Alembic migration ``b2c3d4e5f6a7``. Idempotent: skips any legacy row
whose ``entity_id`` is already set.

See outputs/cursor_brief_phase_1_entity_schema.md §6.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.entity_types import (
    ENTITY_TYPE_COMMERCIAL,
    ENTITY_TYPE_EVENT,
    ENTITY_TYPE_PROGRAM,
)
from app.utils.slug import make_unique_slug, slugify

_DEFAULT_CITY = "Lake Havasu City"
_DEFAULT_STATE = "AZ"

_WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _parse_hours_time(value: str | None) -> time | None:
    """Parse structured-hours strings into time (mirrors providers/queries.py)."""
    if not value:
        return None
    text_v = value.strip().upper().replace(".", "")
    suffix = None
    if text_v.endswith("AM") or text_v.endswith("PM"):
        suffix = text_v[-2:]
        text_v = text_v[:-2].strip()
    try:
        if ":" in text_v:
            h_str, m_str = text_v.split(":", 1)
            hour = int(h_str)
            minute = int(m_str)
        else:
            hour = int(text_v)
            minute = 0
    except ValueError:
        return None
    if suffix == "PM" and hour < 12:
        hour += 12
    elif suffix == "AM" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sql_time(value: time | str | None) -> str | None:
    """SQLite pysqlite bind params do not accept ``datetime.time`` — store ISO time."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def run_entity_backfill(connection: Connection) -> None:
    """Populate ``entities`` + extensions from legacy rows; set legacy ``entity_id``.

    Safe to call twice: only processes rows with ``entity_id IS NULL``.
    """
    used_slugs: set[str] = set(
        r[0]
        for r in connection.execute(text("SELECT slug FROM entities")).fetchall()
        if r[0]
    )

    _backfill_providers(connection, used_slugs)
    _backfill_programs(connection, used_slugs)
    _backfill_events(connection, used_slugs)
    connection.execute(
        text("UPDATE sponsors SET entity_type = :etype WHERE entity_type IS NULL"),
        {"etype": ENTITY_TYPE_COMMERCIAL},
    )


def _backfill_providers(connection: Connection, used_slugs: set[str]) -> None:
    rows = connection.execute(
        text(
            """
            SELECT id, slug, provider_name, description, last_verified_at, source,
                   is_active, created_at, updated_at, category_id, address, zip,
                   lat, lng, google_place_id, district, phone, email, website, facebook,
                   hours_structured, verification_method
            FROM providers
            WHERE entity_id IS NULL
            ORDER BY id
            """
        )
    ).fetchall()

    for row in rows:
        (
            pid,
            pslug,
            pname,
            pdesc,
            last_verified_at,
            psource,
            is_active,
            created_at,
            updated_at,
            category_id,
            address,
            zip_code,
            lat,
            lng,
            gpid,
            district,
            phone,
            email,
            website,
            facebook,
            hours_structured,
            verification_method,
        ) = row

        slug_base = ((pslug or "").strip() or slugify(pname))[:120]
        if slug_base not in used_slugs:
            ent_slug = slug_base
            used_slugs.add(ent_slug)
        else:
            ent_slug = make_unique_slug(slugify(pname)[:96], used_slugs, max_length=96)

        eid = str(uuid4())
        lv = last_verified_at
        connection.execute(
            text(
                """
                INSERT INTO entities (
                    id, entity_type, slug, name, description, last_verified_at,
                    source, is_active, created_at, updated_at
                ) VALUES (
                    :id, :etype, :slug, :name, :desc, :lv, :src, :active, :ca, :ua
                )
                """
            ),
            {
                "id": eid,
                "etype": ENTITY_TYPE_COMMERCIAL,
                "slug": ent_slug,
                "name": pname,
                "desc": pdesc,
                "lv": lv,
                "src": psource or "seed",
                "active": bool(is_active),
                "ca": created_at,
                "ua": updated_at,
            },
        )

        if category_id is not None:
            connection.execute(
                text(
                    """
                    INSERT INTO entity_categories (entity_id, category_id, is_primary, created_at)
                    VALUES (:eid, :cid, 1, :ca)
                    """
                ),
                {"eid": eid, "cid": category_id, "ca": _now_naive_utc()},
            )

        addr_norm = (address or "").strip().lower() if address else None
        connection.execute(
            text(
                """
                INSERT INTO locations (
                    entity_id, address, address_normalized, city, state, zip,
                    lat, lng, google_place_id, district, created_at, updated_at
                ) VALUES (
                    :eid, :addr, :anorm, :city, :state, :zip, :lat, :lng, :gpid, :dist, :ca, :ua
                )
                """
            ),
            {
                "eid": eid,
                "addr": address,
                "anorm": addr_norm,
                "city": _DEFAULT_CITY,
                "state": _DEFAULT_STATE,
                "zip": zip_code,
                "lat": lat,
                "lng": lng,
                "gpid": gpid,
                "dist": district,
                "ca": _now_naive_utc(),
                "ua": _now_naive_utc(),
            },
        )

        hs = hours_structured
        if isinstance(hs, str):
            try:
                hs = json.loads(hs)
            except json.JSONDecodeError:
                hs = None
        if isinstance(hs, dict):
            for di, day_key in enumerate(_WEEKDAY_KEYS):
                spans = hs.get(day_key)
                if not isinstance(spans, list):
                    continue
                for span in spans:
                    if not isinstance(span, dict):
                        continue
                    open_raw = span.get("open") or span.get("opens")
                    close_raw = span.get("close") or span.get("closes") or span.get("closes_at")
                    ot = _parse_hours_time(str(open_raw) if open_raw is not None else None)
                    ct = _parse_hours_time(str(close_raw) if close_raw is not None else None)
                    if ot is None and ct is None:
                        continue
                    connection.execute(
                        text(
                            """
                            INSERT INTO hours (
                                entity_id, day_of_week, opens_at, closes_at,
                                is_24h, notes, created_at
                            ) VALUES (:eid, :dow, :o, :c, 0, NULL, :ca)
                            """
                        ),
                        {
                            "eid": eid,
                            "dow": di,
                            "o": _sql_time(ot),
                            "c": _sql_time(ct),
                            "ca": _now_naive_utc(),
                        },
                    )

        _insert_contact_if(connection, eid, "phone", phone, is_primary=True)
        _insert_contact_if(connection, eid, "email", email, is_primary=False)
        _insert_contact_if(connection, eid, "website", website, is_primary=False)
        _insert_contact_if(connection, eid, "facebook", facebook, is_primary=False)

        connection.execute(
            text(
                """
                INSERT INTO source_evidence (
                    entity_id, field_path, source_type, source_url,
                    verified_at, verification_method, notes, created_at
                ) VALUES (
                    :eid, '(provider_record)', :stype, NULL, :va, :vm, NULL, :ca
                )
                """
            ),
            {
                "eid": eid,
                "stype": psource or "seed",
                "va": lv,
                "vm": verification_method,
                "ca": _now_naive_utc(),
            },
        )

        connection.execute(
            text("UPDATE providers SET entity_id = :eid WHERE id = :pid"),
            {"eid": eid, "pid": pid},
        )


def _insert_contact_if(
    connection: Connection,
    entity_id: str,
    kind: str,
    value: str | None,
    *,
    is_primary: bool,
    label: str | None = None,
) -> None:
    if not value or not str(value).strip():
        return
    connection.execute(
        text(
            """
            INSERT INTO contact_points (
                entity_id, kind, value, label, display_order, is_primary, created_at
            ) VALUES (:eid, :kind, :val, :lbl, 0, :prim, :ca)
            """
        ),
        {
            "eid": entity_id,
            "kind": kind,
            "val": str(value).strip()[:512],
            "lbl": label,
            "prim": bool(is_primary),
            "ca": _now_naive_utc(),
        },
    )


def _backfill_programs(connection: Connection, used_slugs: set[str]) -> None:
    rows = connection.execute(
        text(
            """
            SELECT id, title, description, source, is_active, created_at, updated_at,
                   category_id, location_address, contact_phone, contact_email, contact_url,
                   schedule_days, schedule_start_time, schedule_end_time, schedule_note, cost
            FROM programs
            WHERE entity_id IS NULL
            ORDER BY id
            """
        )
    ).fetchall()

    for row in rows:
        (
            prid,
            title,
            description,
            psource,
            is_active,
            created_at,
            updated_at,
            category_id,
            location_address,
            cphone,
            cemail,
            curl,
            schedule_days,
            st_time,
            et_time,
            schedule_note,
            cost,
        ) = row

        base = slugify(title)
        ent_slug = make_unique_slug(base, used_slugs, max_length=96)

        eid = str(uuid4())
        connection.execute(
            text(
                """
                INSERT INTO entities (
                    id, entity_type, slug, name, description, last_verified_at,
                    source, is_active, created_at, updated_at
                ) VALUES (
                    :id, :etype, :slug, :name, :desc, NULL, :src, :active, :ca, :ua
                )
                """
            ),
            {
                "id": eid,
                "etype": ENTITY_TYPE_PROGRAM,
                "slug": ent_slug,
                "name": title,
                "desc": description,
                "src": psource or "admin",
                "active": bool(is_active),
                "ca": created_at,
                "ua": updated_at,
            },
        )

        if category_id is not None:
            connection.execute(
                text(
                    """
                    INSERT INTO entity_categories (entity_id, category_id, is_primary, created_at)
                    VALUES (:eid, :cid, 1, :ca)
                    """
                ),
                {"eid": eid, "cid": category_id, "ca": _now_naive_utc()},
            )

        if location_address and str(location_address).strip():
            la = str(location_address).strip()
            connection.execute(
                text(
                    """
                    INSERT INTO locations (
                        entity_id, address, address_normalized, city, state, zip,
                        lat, lng, google_place_id, district, created_at, updated_at
                    ) VALUES (
                        :eid, :addr, :anorm, NULL, NULL, NULL, NULL, NULL, NULL, NULL, :ca, :ua
                    )
                    """
                ),
                {
                    "eid": eid,
                    "addr": la[:255],
                    "anorm": la.lower(),
                    "ca": _now_naive_utc(),
                    "ua": _now_naive_utc(),
                },
            )

        _insert_contact_if(connection, eid, "phone", cphone, is_primary=True)
        _insert_contact_if(connection, eid, "email", cemail, is_primary=False)
        _insert_contact_if(connection, eid, "website", curl, is_primary=False)

        dow_json = _json_or_none(schedule_days)
        connection.execute(
            text(
                """
                INSERT INTO schedules (
                    entity_id, schedule_type, start_date, end_date, start_time, end_time,
                    recurrence_rule, days_of_week, capacity, capacity_label, notes,
                    created_at, updated_at
                ) VALUES (
                    :eid, 'recurring', NULL, NULL, :st, :et, NULL, :dow, NULL, NULL, :note,
                    :ca, :ua
                )
                """
            ),
            {
                "eid": eid,
                "st": _sql_time(st_time),
                "et": _sql_time(et_time),
                "dow": dow_json,
                "note": (schedule_note or "")[:255] if schedule_note else None,
                "ca": _now_naive_utc(),
                "ua": _now_naive_utc(),
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO offerings (
                    entity_id, name, description, price_text, price_min_cents,
                    price_max_cents, duration_minutes, url, display_order, created_at, updated_at
                ) VALUES (
                    :eid, :name, :desc, :pt, NULL, NULL, NULL, NULL, 0, :ca, :ua
                )
                """
            ),
            {
                "eid": eid,
                "name": title[:255],
                "desc": description,
                "pt": (cost or "")[:64] if cost else None,
                "ca": _now_naive_utc(),
                "ua": _now_naive_utc(),
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO source_evidence (
                    entity_id, field_path, source_type, source_url,
                    verified_at, verification_method, notes, created_at
                ) VALUES (
                    :eid, '(program_record)', :stype, NULL, NULL, NULL, NULL, :ca
                )
                """
            ),
            {"eid": eid, "stype": psource or "admin", "ca": _now_naive_utc()},
        )

        connection.execute(
            text("UPDATE programs SET entity_id = :eid WHERE id = :pid"),
            {"eid": eid, "pid": prid},
        )


def _json_or_none(val: Any) -> str | None:
    if val is None:
        return None
    return json.dumps(val)


def _backfill_events(connection: Connection, used_slugs: set[str]) -> None:
    rows = connection.execute(
        text(
            """
            SELECT id, title, description, source, status, date, end_date,
                   start_time, end_time, location_name, contact_phone, contact_name,
                   event_url, last_verified_at, created_at
            FROM events
            WHERE entity_id IS NULL
            ORDER BY id
            """
        )
    ).fetchall()

    for row in rows:
        (
            evid,
            title,
            description,
            esource,
            status,
            start_d,
            end_d,
            st_time,
            et_time,
            loc_name,
            cphone,
            cname,
            event_url,
            last_verified_at,
            ev_created_at,
        ) = row

        base = slugify(title)
        ent_slug = make_unique_slug(base, used_slugs, max_length=96)

        eid = str(uuid4())
        is_live = (status or "").lower() == "live"
        ev_ca = ev_created_at or _now_naive_utc()
        connection.execute(
            text(
                """
                INSERT INTO entities (
                    id, entity_type, slug, name, description, last_verified_at,
                    source, is_active, created_at, updated_at
                ) VALUES (
                    :id, :etype, :slug, :name, :desc, :lv, :src, :active, :ca, :ua
                )
                """
            ),
            {
                "id": eid,
                "etype": ENTITY_TYPE_EVENT,
                "slug": ent_slug,
                "name": title,
                "desc": description,
                "lv": last_verified_at,
                "src": esource or "admin",
                "active": is_live,
                "ca": ev_ca,
                "ua": ev_ca,
            },
        )

        ln = (loc_name or "").strip()
        if ln:
            connection.execute(
                text(
                    """
                    INSERT INTO locations (
                        entity_id, address, address_normalized, city, state, zip,
                        lat, lng, google_place_id, district, created_at, updated_at
                    ) VALUES (
                        :eid, :addr, :anorm, NULL, NULL, NULL, NULL, NULL, NULL, NULL, :ca, :ua
                    )
                    """
                ),
                {
                    "eid": eid,
                    "addr": ln[:255],
                    "anorm": ln.lower(),
                    "ca": _now_naive_utc(),
                    "ua": _now_naive_utc(),
                },
            )

        connection.execute(
            text(
                """
                INSERT INTO schedules (
                    entity_id, schedule_type, start_date, end_date, start_time, end_time,
                    recurrence_rule, days_of_week, capacity, capacity_label, notes,
                    created_at, updated_at
                ) VALUES (
                    :eid, 'one_off', :sd, :ed, :st, :et, NULL, NULL, NULL, NULL, NULL,
                    :ca, :ua
                )
                """
            ),
            {
                "eid": eid,
                "sd": start_d,
                "ed": end_d,
                "st": _sql_time(st_time),
                "et": _sql_time(et_time),
                "ca": _now_naive_utc(),
                "ua": _now_naive_utc(),
            },
        )

        label = (cname or "").strip() or None
        if cphone and str(cphone).strip():
            _insert_contact_if(
                connection,
                eid,
                "phone",
                cphone,
                is_primary=True,
                label=label,
            )
        elif label:
            _insert_contact_if(connection, eid, "other", label, is_primary=False)

        eu = (event_url or "").strip()
        if eu:
            _insert_contact_if(connection, eid, "website", eu, is_primary=False)

        connection.execute(
            text(
                """
                INSERT INTO source_evidence (
                    entity_id, field_path, source_type, source_url,
                    verified_at, verification_method, notes, created_at
                ) VALUES (
                    :eid, '(event_record)', :stype, NULL, :va, NULL, NULL, :ca
                )
                """
            ),
            {
                "eid": eid,
                "stype": esource or "admin",
                "va": last_verified_at,
                "ca": _now_naive_utc(),
            },
        )

        connection.execute(
            text("UPDATE events SET entity_id = :eid WHERE id = :eid2"),
            {"eid": eid, "eid2": evid},
        )


