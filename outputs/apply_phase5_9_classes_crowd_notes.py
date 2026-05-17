"""Apply long-form crowd_notes to the top-10 classes-sports-recreation
(cat-12) entities.

Closes Phase 5.9 acceptance gate item 4 ("Top-10 by reviews have
long-form crowd_notes"). Notes follow the locked Phase 5.1 JSON shape
``{"short": str, "long": str}`` — Phase 6 consumes the absence-of-long
signal (list-blurb vs profile-section); presence of ``long`` marks
this entry as a profile-page entry.

Drafts sourced from each entity's ``Provider.google_review_snippets``
(own column on Provider, NOT inside ``attributes`` — per the 5.4
close-out §4 source-path correction). Top-10 surfaced via
``outputs/phase5_9_top10_discovery.py`` against
``Provider.google_review_count`` desc, taken post-§2-apply (so the 3
Slice E NEW creates + Slice B FLIP-in (Stormy Wade) are eligible).

Mirrors ``apply_phase5_8_events_crowd_notes.py`` shape exactly:
id-prefix-keyed dict, ``--dry-run`` first, idempotent (overwrites
existing crowd_notes), self-verifies via with-long-form count.

**JSON-column gotcha (per 5.3 ``f35d5e4``, internalized in
5.4/5.5/5.6/5.7/5.8):** ``Entity.crowd_notes`` is mapped as JSON;
SQLAlchemy serializes dicts on write. Pass the dict directly —
do NOT ``json.dumps()`` first.

Snippet coverage in the post-§2-apply top-10 was **100% (5 snippets
each, except Hilltop Learning Center with 3)** — abundant signal for
hand-curating. The notes focus on cat-12-specific themes per kickoff
§4 rubric: staff quality + safety supervision (childcare), program
variety + schedule (gyms / classes), equipment + facility condition,
member friendliness, parking + access, instructor / teacher quality,
public-hours visibility (public courts / pools), kid-friendliness,
named-staff callouts.

Usage:
    python outputs/apply_phase5_9_classes_crowd_notes.py --dry-run
    python outputs/apply_phase5_9_classes_crowd_notes.py
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
    "baf9b389": {  # Lake Havasu City Aquatic Center — 595r, 4.6★, swimming_pool (Slice E NEW)
        "short": (
            "LHC's city aquatic center — multipurpose municipal facility "
            "with outdoor pool, 4 pickleball courts ($3 / 3-hr session), "
            "and seasonal classes. Public access is limited to specific "
            "hours; check the schedule."
        ),
        "long": (
            "595 reviews at 4.6★ — the city's main aquatic complex run by "
            "LHC Parks & Rec. Reviewers consistently praise the staff: "
            "lifeguards described as plentiful and focused on the water, "
            "the director credited for running the facility well, and "
            "patrons appreciate being allowed to bring their own food + "
            "drink. Beyond the pool, the venue hosts 4 pickleball courts "
            "($3 per 3-hour session — popular but the AC reportedly "
            "struggles in summer) and seasonal community classes (a recent "
            "pumpkin painting class for ~20 attendees drew praise). The "
            "consistent friction point: public access is limited to "
            "specific hours each day — call ahead or check the schedule, "
            "and don't expect drop-in access to facilities like showers "
            "outside those windows. Outdoor pool by design; bring sun "
            "protection in summer."
        ),
    },
    "cab0c922": {  # Our Lady of the Lake Catholic School — 121r, 4.3★, church (Slice D DUAL)
        "short": (
            "Catholic K-8 school with engaged faculty + strong parent "
            "involvement; broad extracurricular offerings (music, PE, "
            "sports, religion, arts clubs). Integrated with Our Lady of "
            "the Lake parish."
        ),
        "long": (
            "121 reviews at 4.3★ — Catholic K-8 school co-located with "
            "the Our Lady of the Lake parish. Reviewers describe strong "
            "curriculum, dedicated teachers, and welcoming student "
            "culture (long-attending alumni cite 'no bullies'). The "
            "school runs broad extracurriculars: music + PE classes plus "
            "dances, fairs, plays, religious clubs, sports, and patriotic "
            "clubs; parents are described as actively involved. Small-"
            "school community feel that has grown over the decades. The "
            "review mix also includes parish-side comments — some critical "
            "of church leadership specifically (not the school) — so look "
            "at academic-focused reviews when evaluating the school. "
            "Indoor classroom setting."
        ),
    },
    "917be389": {  # Telesis Preparatory Academy — 29r, 3.8★, primary=None (§1 insert)
        "short": (
            "Preparatory K-12 school with engaged leadership (principal "
            "+ counselor visible daily) and named-staff dedication. "
            "Reviews mixed — some parents flag favoritism dynamics; "
            "visit before committing."
        ),
        "long": (
            "29 reviews at 3.8★ — preparatory school in LHC with positive "
            "signals on leadership communication: the principal, counselor, "
            "and office staff are described as visible, welcoming students "
            "in the morning and available throughout the day. Multiple "
            "5-star reviews call out 'dedicated educators' and 'deep "
            "commitment to student success.' Counter-signal: critical "
            "reviews describe a 'reputation for snootiness,' teachers who "
            "'play favorites,' and 'table scraps of attention' for students "
            "outside an inner circle. Reviewer dynamics suggest school is a "
            "strong fit for engaged-family households who want close staff "
            "interaction, with the trade-off that less-connected families "
            "may feel sidelined. Indoor classroom + campus setting."
        ),
    },
    "c514b766": {  # Stormy Wade Courts — 10r, 4.3★, tennis_court (Slice B FLIP-in)
        "short": (
            "Public tennis courts open to all, in good condition with "
            "working lights that stay on past 10pm. Quiet — often empty. "
            "Occasional graffiti reported but courts themselves are "
            "well-kept."
        ),
        "long": (
            "10 reviews at 4.3★ — public tennis courts (located at 2675 "
            "Palo Verde Blvd S, on the Little Knights Preschool campus). "
            "Reviewers describe courts in great condition, clean and "
            "nicely kept; lights work well and stay on past 10pm. Open "
            "to the public at no cost. Negative signal: one reviewer "
            "noted 'too much graffiti, zero tennis players' — usage is "
            "light, so you'll often have a court to yourself. Best fit "
            "for pickup play and casual practice; not a tennis-club "
            "atmosphere. Outdoor courts — bring water + sun protection "
            "in summer."
        ),
    },
    "b26b36e3": {  # Little People's Day Care Inc — 8r, 3.5★, child_care_agency
        "short": (
            "Polarized reviews — some parents report kindergarten-prep "
            "success and engaged teachers; others describe friction with "
            "management. Visit in person before committing."
        ),
        "long": (
            "8 reviews at 3.5★ — long-running LHC daycare with sharply "
            "polarized reviewer experience. Positive signals: 5-star "
            "reviews credit specific staff (notably Karen) with flexible "
            "scheduling for part-time families, successful potty training "
            "in a month, and helping children grow emotionally for "
            "kindergarten. Critical reviews describe the director as "
            "'rude' and 'quick to unenroll' when concerns are raised, "
            "and one parent flagged unhelpful potty-training support "
            "despite the daycare's marketing claims. The polarization "
            "suggests fit-dependence — best to visit in person, meet the "
            "director directly, and discuss your specific needs before "
            "committing. Indoor facility."
        ),
    },
    "7bb2ff20": {  # Family Tree Daycare — 6r, 4.3★, child_care_agency
        "short": (
            "Family-feel daycare with hand-painted classrooms. Consistent "
            "positive feedback on welcoming staff and 'family vibe'; "
            "long-time parents report kids excited to attend."
        ),
        "long": (
            "6 reviews at 4.3★ — small LHC daycare with a deliberate "
            "family-feel atmosphere (hand-painted murals on the walls). "
            "Multi-year families consistently report 5-star experiences: "
            "warm welcome for both child and parent, kids excited to "
            "return each day, staff described as 'so much heart.' One "
            "negative review (also long-tenured parent) flags 'no real "
            "structure,' high teacher turnover, and operational issues "
            "like children left in wet clothes — likely indicates the "
            "curriculum is light on structured early-ed and heavy on "
            "warmth, so best fit for families prioritizing community over "
            "structured Pre-K prep. Indoor facility."
        ),
    },
    "dcd053e5": {  # New Day School (3438 Oro Grande Blvd) — 6r, 4.0★, preschool
        "short": (
            "Well-regarded preschool with professional teachers and a fun "
            "learning environment. Staffing ratio occasionally flagged. "
            "One of two New Day School campuses in LHC (Oro Grande Blvd)."
        ),
        "long": (
            "6 reviews at 4.0★ — preschool at 3438 Oro Grande Blvd, one "
            "of two New Day School locations in LHC (the other is on "
            "Havasupai Blvd). Reviewers describe the school as 'very "
            "well run by caring and excellent professional teachers' and "
            "'a fun place for the kids.' Multi-year families report "
            "their children loving it and growing significantly. One "
            "critical review flags 'too many kids, not enough teachers' "
            "— consistent with the small-school trade-off where staffing "
            "ratios can feel tight at peak. Indoor facility."
        ),
    },
    "1757c6da": {  # New Day School (2915 Havasupai Blvd) — 5r, 4.2★, preschool
        "short": (
            "Long-tenured preschool with named-staff praise (Mrs Kim Mia) "
            "and consistent 5-star reviews from multi-year families. "
            "One of two New Day School campuses (Havasupai Blvd)."
        ),
        "long": (
            "5 reviews at 4.2★ — preschool at 2915 Havasupai Blvd, one "
            "of two New Day School locations in LHC (the other is on "
            "Oro Grande Blvd). Strong recurring praise from multi-year "
            "families: 'amazing with my Emma,' 'really care about kids,' "
            "'son loves it there.' Mrs Kim Mia gets specific named-staff "
            "callouts as 'the absolute GREATEST.' Note: a 2017 1-star "
            "review claims 'this school is closed' — clearly stale; the "
            "school is operating with active multi-year reviews through "
            "2025. Indoor facility."
        ),
    },
    "8448145b": {  # Nelly's Nursery & Day Care — 5r, 1.8★, child_care_agency
        "short": (
            "Reviews are sharply polarized: one consistent 5-star account "
            "praises cleanliness + toys, but multiple critical reviews "
            "describe management friction. Visit + verify AZDHS license "
            "before committing."
        ),
        "long": (
            "5 reviews at 1.8★ — small LHC daycare with starkly divided "
            "reviewer experience. One 5-star account from a multi-month "
            "family praises Nelly's care, cleanliness, and toy selection. "
            "Multiple critical reviews flag concerns: parents describe "
            "owner as 'kicks them out when concerns are raised' and at "
            "least one explicit 'don't bring your kids here' from a "
            "parent. The volume + tone of critical reviews suggests "
            "operational issues worth taking seriously — operator note: "
            "consider visiting in person, verifying AZDHS childcare "
            "license status, and asking for current-parent references "
            "before committing. Indoor facility."
        ),
    },
    "63b5e7f9": {  # Hilltop Learning Center — 3r, 3.7★, primary=None
        "short": (
            "Preschool / early-learning facility at the Hilltop Community "
            "Church campus. Low review volume; positive signals highlight "
            "named staff (Ms Shelly, Ms Shanna, Janessa)."
        ),
        "long": (
            "3 reviews at 3.7★ — preschool / early-learning facility "
            "at 3180 McCulloch Blvd N, on the Hilltop Community Church "
            "campus (the Church itself is a separate cat-13 entity). "
            "5-star reviews highlight named staff: Ms Shelly, Ms Shanna, "
            "and Janessa — multi-child families report both kids loving "
            "specific teachers. One critical review flags concerns about "
            "a staff member's family background and recommends more "
            "extensive employment screening. Low review volume means "
            "smaller sample; visit in person and form your own view. "
            "Indoor facility."
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

        # Self-verify: count cat-12 entities with long-form crowd_notes.
        cat12 = session.scalars(
            select(Category).where(Category.slug == "classes-sports-recreation")
        ).one()
        all_cat12 = session.scalars(
            select(Entity)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .where(
                and_(
                    EntityCategory.category_id == cat12.id,
                    Entity.is_active == 1,
                )
            )
        ).all()
        with_long = sum(
            1
            for e in all_cat12
            if isinstance(e.crowd_notes, dict) and e.crowd_notes.get("long")
        )
        print(
            f"  cat-12 entities with long-form crowd_notes: "
            f"{with_long} (gate-4 target: >= 10)"
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
