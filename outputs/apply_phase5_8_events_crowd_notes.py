"""Apply long-form crowd_notes to the top-10 events (cat-2) entities.

Closes Phase 5.8 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` — per the 5.4
close-out §4 source-path correction). Top-10 surfaced via
``outputs/phase5_8_top10_discovery.py`` against
``Provider.google_review_count`` desc, taken post-§2-apply (so the
15 NEW Slice A entries + Slice B-2 Altitude Trampoline + Slice C
Simply Savage are eligible; the 2 pre-existing 5.7 FLIPs are also in
the pool but fell out of top-10 by review_count).

Mirrors ``apply_phase5_7_parks_crowd_notes.py`` shape exactly:
id-prefix-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in
5.4/5.5/5.6/5.7):** ``Entity.crowd_notes`` is mapped as JSON;
SQLAlchemy serializes dicts on write. Pass the dict directly —
do NOT ``json.dumps()`` first.

Snippet coverage in the post-§2-apply top-10 was **100% (5 snippets
each)** — abundant raw signal for hand-curating. The notes focus on
events-specific themes (venue character, frequency of programming,
food + drink amenities, family-friendliness, seasonal-vs-recurring,
named-staff callouts) per kickoff §4 rubric.

Usage:
    python outputs/apply_phase5_8_events_crowd_notes.py --dry-run
    python outputs/apply_phase5_8_events_crowd_notes.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, select  # noqa: E402

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory  # noqa: E402

# entity_id 8-char prefix -> {"short": str, "long": str}
# Drafted from Provider.google_review_snippets per entity. Operator
# edits inline before live apply if any text needs adjustment.
# Ordering matches the post-§2-apply top-10 by review_count desc.
CROWD_NOTES_TOP10: dict[str, dict[str, str]] = {
    "75a43cf1": {  # Star Cinemas — 814 reviews, 4.4★, movie_theater
        "short": (
            "LHC's main movie theater — ~10 viewing screens, big-screen "
            "comfort with cupholder seats, reasonably priced. Senior "
            "combo deal on Wednesdays draws regulars."
        ),
        "long": (
            "814 reviews at 4.4★ — LHC's primary multiplex. Reviewers "
            "consistently praise the big screens, comfortable cupholder "
            "seats, buttered popcorn, and clean bathrooms. The senior "
            "combo on Wednesdays is a notable value draw. Casual food + "
            "drink option: patrons can bring beer in from the adjacent "
            "Buffalo Wild Wings (a common pre-show pairing). Recurring "
            "1-star complaints flag occasional issues with screen "
            "brightness (dim picture) and inconsistent concession "
            "quality (cold theater, rancid butter mentioned in one "
            "extensive update review). Overall a reliable indoor "
            "entertainment option, particularly for seniors and "
            "families."
        ),
    },
    "250a6f40": {  # Lake Havasu Elks Lodge #2399 — 388 reviews, 4.6★
        "short": (
            "Active community lodge with an attached RV park (full "
            "hookups, friendly camp hosts) plus on-site bar and dining "
            "hall. Cheap drinks ($2.50 PBR on tap), daily events, "
            "members-only but accepts prospective members."
        ),
        "long": (
            "388 reviews at 4.6★ — community lodge with an attached RV "
            "park (sites with full hookups + distant lake views). "
            "Camp-host couples (Elmer + Jewls, more recently Mike + "
            "Tracy) get repeated praise; reservation recommended. Daily "
            "meals + events keep the lodge active most evenings. Bar is "
            "cash-only ($2.50 PBR on tap, $9 pitchers; food + events "
            "accept credit/debit/cash). LHC's official Dark Sky "
            "designation makes campsite stargazing a notable amenity — "
            "one reviewer brought a telescope and shared views with "
            "fellow campers. Negative signal: one 1-star review "
            "describes a hostile interaction with a then-camp-host and "
            "non-responsive lodge management; reviewer also noted the "
            "RV area is sharp crushed gravel (rough on dogs' paws). "
            "Otherwise consistently strong feedback."
        ),
    },
    "b3fc8e9b": {  # Altitude Trampoline Park — 224 reviews, 4.6★
        "short": (
            "Indoor trampoline park with multiple activities, music, "
            "food + drinks, and birthday party rooms. Well-supervised "
            "and clean per reviewers; monthly pass available for daily "
            "jumping during the summer."
        ),
        "long": (
            "224 reviews at 4.6★ — indoor trampoline facility with "
            "variety beyond basic jump areas (under-6 play area, dodge "
            "lanes, slam-dunk zones, music, food/drinks, party rooms). "
            "Reviewers consistently praise staff supervision (older "
            "kids called out for unsafe behavior, younger kids assisted) "
            "and cleanliness. Monthly pass for daily jumping is a value "
            "option for summer. Two recurring criticisms: the 6-and-"
            "under play area structures are tall (climbing slides hard "
            "for 3-and-under without adult assistance, but adults can't "
            "easily fit in to help) and one notable 1-star complaint "
            "about being charged for a 1-year-old who could only stand "
            "against the wall (membership policy enforced regardless "
            "of mobility)."
        ),
    },
    "82295ffa": {  # LH Museum of History & Havasu Rocks — 213 reviews, 4.7★
        "short": (
            "Free LHC history museum (donation appreciated) covering "
            "McCulloch, the London Bridge, Parker Dam, Native "
            "populations, and local wildlife. Includes a kids' corner "
            "with magnetic sand + live animals, plus a Havasu Rocks "
            "lapidary annex."
        ),
        "long": (
            "213 reviews at 4.7★ — small community museum, ~1-hour "
            "visit. Covers the McCulloch / London Bridge origin story, "
            "Parker Dam construction, Native populations who lived in "
            "the area before, steamboats, and local wildlife. Free "
            "admission with donations appreciated. Children's corner "
            "is a draw — magnetic sand, coloring, and live animals (a "
            "gecko, lizard, and spider) keep toddlers engaged. The "
            "'Havasu Rocks' lapidary display is the recently-added "
            "gem/mineral wing (the suffix in the renamed Google "
            "listing). Outside the museum sits a small replica jail "
            "(1970s era) noted by reviewers as a fun-but-jarring "
            "touch. Friendly staff, clean facility, widely recommended "
            "as a worthwhile stop for visitors with an hour to spare."
        ),
    },
    "9654aab2": {  # American Legion — 140 reviews, 4.7★
        "short": (
            "Active veterans post with daily events — $3 beer, $9 "
            "pitchers, Friday taco lunch + fish fry, Wii bowling "
            "nights, ALR riders chapter. Smoking restricted to patio "
            "(vote-passed; main building cleaned + repainted)."
        ),
        "long": (
            "140 reviews at 4.7★ — active LHC veterans post. Open "
            "7 days a week with daily programming: Friday tacos for "
            "lunch + fish fry for dinner, Wii bowling on some "
            "evenings, occasional live entertainment, ALR (American "
            "Legion Riders) Auxiliary chapter active on weekends. Bar "
            "is cash-only with $3 beer on tap and $9 pitchers. "
            "Friendly atmosphere, welcoming to newcomers (with active "
            "winter-snowbird member base). Recent membership vote "
            "moved smoking to the patio (which has been built out "
            "nicely); main building was repainted to clear smoke "
            "residue. Patio area + multiple TVs round out the social "
            "space."
        ),
    },
    "b9ade64f": {  # Quest Realm — 100 reviews, 4.7★
        "short": (
            "Trading-card-game and hobby shop — Magic singles, sealed "
            "product, vintage tees + collectibles, board games to play "
            "on site. Standout customer service (ask for Sam)."
        ),
        "long": (
            "100 reviews at 4.7★ — LHC's trading-card-game / hobby "
            "shop. Magic singles at fair prices with high condition "
            "standards (\"we have high standards\" per the owner). "
            "Sealed product, vintage t-shirts + clothing, and a "
            "card-sorting service. On-site board / card games available "
            "for casual play (good way to kill time). Customer service "
            "is the standout — Sam gets repeated callouts for asking "
            "the right questions, recommending personalized gifts for "
            "spouses, and shipping to out-of-town customers who can't "
            "make the drive. Negative signal: one 1-star review pegging "
            "the singles-buyback offer at 31% of card value (lower "
            "than the 40-60% industry norm) and a ~week-long appraisal "
            "turnaround. Best for fair-priced purchase + play, less so "
            "for selling."
        ),
    },
    "c4a93c74": {  # Four Quarters Amusements — 46 reviews, 5.0★
        "short": (
            "In-home repair service for pinball, video poker, and "
            "arcade machines (LHC + surrounding area). Owner James "
            "gets uniform praise for on-time arrivals, fair pricing, "
            "and phone-help."
        ),
        "long": (
            "46 reviews at 5.0★ — perfect rating across the board. "
            "In-home arcade-machine repair service: pinball, video "
            "poker, classic multi-game video machines. Owner James "
            "handles all jobs personally — reviewers consistently "
            "note he calls ahead, arrives on time, prices fairly, and "
            "shares enough phone troubleshooting to save a service "
            "call when possible. Standout differentiator: he'll help "
            "walk newcomers through buying a pinball machine before "
            "they purchase, not just after they have a problem. "
            "Strong recurring reviewer signal across years of "
            "testimonials (2021-2025). Not a storefront — phone "
            "consultation + house calls only. Best fit for collectors "
            "of older mechanical / electronic games who need expert "
            "service."
        ),
    },
    "343cd08a": {  # Ru Art Gallery and Boutique — 18 reviews, 4.4★
        "short": (
            "Boutique + art gallery combo on the restaurant level of "
            "The Barley Brewery / Shugrue's. Upscale clothing, "
            "jewelry, unique art — friendly owner Tatyana, "
            "affordable."
        ),
        "long": (
            "18 reviews at 4.4★ — small boutique + art gallery "
            "co-located on the restaurant level of The Barley Brewery "
            "and Shugrue's fine dining. Mix of upscale jewelry, "
            "sparkly clothing, accessories, and original artwork. "
            "Owner Tatyana gets repeated mentions for warm greetings "
            "and personal styling help (one reviewer credits her with "
            "making the visit-of-the-day). Sister store: Barracuda. "
            "Prices described as 'reasonable' for the boutique tier. "
            "One 1-star review flags rudeness in response to "
            "criticism — likely one-off but worth flagging. Best "
            "discovered after dinner at the adjacent restaurants."
        ),
    },
    "432ac703": {  # Buses By The Bridge — 14 reviews, 4.9★
        "short": (
            "Annual VW Bus + classic-car festival held by the London "
            "Bridge each January. Camping, music, food, raffles. $5 "
            "entry; profits support local Sea Scouts."
        ),
        "long": (
            "14 reviews at 4.9★ — annual VW Bus + classic-car "
            "rendezvous held by the London Bridge in LHC, typically "
            "January. Hosted by London Bridge Bullis (Sea Scouts "
            "beneficiary). Multi-day event includes overnight camping, "
            "music, raffles, vendors, food selection, and 'plenty of "
            "conversation' — reviewers describe it as one of the top "
            "West Coast VW gatherings. $5 entry. Profits donated back "
            "to the community. Friendly culture around the VW Bus "
            "collector scene — reviewers note diverse buses + a few "
            "other classics (#BBB and #busesbythebridge hashtags by "
            "year). Outdoor event by design."
        ),
    },
    "90bfcf92": {  # AZ Party Express — 11 reviews, 4.7★
        "short": (
            "Event-rental service for parties + weddings (tables, "
            "chairs, tents). Reps Michaela + Anne known for meeting "
            "at the venue to help plan. Prompt delivery + pickup."
        ),
        "long": (
            "11 reviews at 4.7★ — LHC event-rental service for "
            "parties + weddings. Tables, chairs, tents. Standout "
            "reviewer signal: rep Michaela meets clients at their "
            "venue to walk through layout decisions before booking. "
            "Anne also gets called out for clutch-saves in "
            "last-minute event rescues (quinceañeras, weddings). "
            "Provided service during COVID with social-distancing "
            "accommodations. Negative signal: one 2-star review "
            "describes a communication mismatch with rep Darleen "
            "(wrong tables delivered, little remediation help) — "
            "pre-book carefully and confirm specifics in writing. "
            "Otherwise prompt delivery + pickup, friendly crew."
        ),
    },
}


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _resolve_entity_by_prefix(session, prefix: str) -> Entity | None:
    """Resolve Entity by id-prefix (first 8 chars). Asserts exactly one
    active match."""
    rows = session.scalars(
        select(Entity).where(Entity.id.like(prefix + "%"), Entity.is_active == 1)
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError(
            f"prefix-resolution collision: {len(rows)} active entities match "
            f"id LIKE {prefix!r}; expected exactly 1."
        )
    return rows[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; roll back; no DB writes.",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        applied = 0
        skipped = 0
        for prefix, notes in CROWD_NOTES_TOP10.items():
            ent = _resolve_entity_by_prefix(session, prefix)
            if ent is None:
                print(f"  [skip] not found: id LIKE {prefix!r}")
                skipped += 1
                continue
            # JSON column — pass dict directly per 5.3 f35d5e4 gotcha.
            ent.crowd_notes = notes
            ent.updated_at = _utc_now_naive()
            short_preview = notes["short"][:60].replace("\n", " ")
            print(
                f"  [apply] {ent.name!r:55s}  {short_preview!r}..."
            )
            applied += 1

        print(f"\n=== Summary ===\n  applied: {applied}\n  skipped: {skipped}")

        # Self-verify: count cat-2 entities with long-form crowd_notes.
        cat2 = session.scalars(
            select(Category).where(Category.slug == "events")
        ).one()
        all_cat2 = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                and_(
                    EntityCategory.category_id == cat2.id,
                    Entity.is_active == 1,
                )
            )
        ).all()
        with_long = sum(
            1
            for e in all_cat2
            if isinstance(e.crowd_notes, dict) and e.crowd_notes.get("long")
        )
        print(
            f"  cat-2 entities with long-form crowd_notes: "
            f"{with_long} (gate-4 target: ≥10)"
        )

        if args.dry_run:
            print("\n[dry-run] rolling back; no DB writes.")
            session.rollback()
        else:
            session.commit()
            print("\n[apply] committed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
