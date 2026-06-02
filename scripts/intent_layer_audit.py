"""Read-only Phase-0 audit for the Ask Hava intent layer.

Reports catalog counts + field-coverage for the fields the intent layer depends
on, then runs the real intent layer over a phrase battery so each Phase-1 intent
shows its live result count against the dev DB. Mutates nothing.

Run:  python scripts/intent_layer_audit.py
(uses the default DB -- data/events.db -- unless DATABASE_URL is set)
"""

from __future__ import annotations

import os

os.environ["USE_INTENT_LAYER"] = "1"

from sqlalchemy import func, select  # noqa: E402

from app.chat.intents.dicts import SERVICE_SUBCAT_GROUPS  # noqa: E402
from app.chat.intents.runtime import try_intent_layer  # noqa: E402
from app.conditions.cache import read_source  # noqa: E402
from app.conditions.constants import SOURCE_GAS  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Event, Program, Provider  # noqa: E402


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.0f}%" if d else "n/a"


def main() -> None:
    print(f"DB: {DATABASE_URL}\n")
    with SessionLocal() as db:
        active = db.query(Provider).filter(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        )
        total = active.count()
        print(f"== Providers (active, non-draft): {total} ==")
        with_hours = active.filter(Provider.hours_structured.isnot(None)).count()
        with_district = active.filter(Provider.district.isnot(None)).count()
        with_rating = active.filter(Provider.google_rating.isnot(None)).count()
        with_subcat = active.filter(Provider.subcategory.isnot(None)).count()
        print(f"  hours_structured: {with_hours} ({_pct(with_hours, total)})  "
              f"<- gates open_now intents")
        print(f"  district:         {with_district} ({_pct(with_district, total)})  "
              f"<- gates area intents")
        print(f"  google_rating:    {with_rating} ({_pct(with_rating, total)})")
        print(f"  subcategory set:  {with_subcat} ({_pct(with_subcat, total)})")

        print("\n  distinct districts:")
        rows = db.execute(
            select(Provider.district, func.count())
            .where(Provider.is_active.is_(True), Provider.district.isnot(None))
            .group_by(Provider.district)
            .order_by(func.count().desc())
        ).all()
        for label, n in rows[:25]:
            print(f"    {n:>4}  {label}")

        print("\n  providers by subcategory group (Services + others):")
        rows = db.execute(
            select(Provider.subcategory, func.count())
            .where(Provider.is_active.is_(True), Provider.subcategory.isnot(None))
            .group_by(Provider.subcategory)
            .order_by(func.count().desc())
        ).all()
        for label, n in rows:
            tag = " (service group)" if label in SERVICE_SUBCAT_GROUPS else ""
            print(f"    {n:>4}  {label}{tag}")

        print("\n  providers by legacy category (top 25):")
        rows = db.execute(
            select(Provider.category, func.count())
            .where(Provider.is_active.is_(True))
            .group_by(Provider.category)
            .order_by(func.count().desc())
        ).all()
        for label, n in rows[:25]:
            print(f"    {n:>4}  {label}")

        # Events
        ev_total = db.query(Event).count()
        ev_live = db.query(Event).filter(Event.status == "live").count()
        print(f"\n== Events: {ev_total} total, {ev_live} live ==")

        # Programs
        pr_total = db.query(Program).filter(Program.is_active.is_(True)).count()
        pr_age = (
            db.query(Program)
            .filter(Program.is_active.is_(True), Program.age_min.isnot(None))
            .count()
        )
        print(f"== Programs: {pr_total} active, {pr_age} with age_min "
              f"({_pct(pr_age, pr_total)}) <- gates kids age-band ==")

        # Gas
        gas = read_source(db, SOURCE_GAS)
        n_stations = len(gas.data.get("stations", [])) if gas and isinstance(gas.data, dict) else 0
        print(f"== Gas cache: {'present' if gas else 'MISSING'}, {n_stations} stations ==")

        # Phrase battery -- run the real intent layer.
        print("\n== Phrase battery (intent_key | layer-result_count | component) ==")
        phrases = [
            "where's the cheapest gas",
            "what events are happening this weekend",
            "things to do tonight",
            "live music this weekend",
            "i need a plumber",
            "electrician near me",
            "good mechanic",
            "dentist open now",
            "urgent care",
            "dog groomer",
            "hair salon",
            "best mexican food",
            "pizza downtown",
            "coffee shop",
            "somewhere to eat open now",
            "yoga studio",
            "gym near me",
            "karate for my 8 year old",
            "swim lessons for my 9 year old",
            "hotels near the lake",
            "where can i go shopping",
        ]
        for p in phrases:
            ans = try_intent_layer(p, db)
            if ans is None:
                print(f"  {p!r:42} -> (fell through)")
            else:
                print(
                    f"  {p!r:42} -> {ans.intent_key:18} "
                    f"n={ans.result_count:<3} [{ans.component_type}]"
                )


if __name__ == "__main__":
    main()
