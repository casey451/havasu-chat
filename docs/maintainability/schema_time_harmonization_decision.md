# Schema time-type harmonization — decision

**Date:** 2026-05-05 (Slice 52).
**Author:** Claude design pass + Casey approval.
**Status:** Draft → Decided after Casey's call.
**Companion:** `docs/maintainability/schema_time_harmonization_campaign.md` (Slice 53–55 plan, written after this decision lands).

## §1 The inconsistency

`app/db/models.py` (lines 105, 106, 200, 201 as of `d188517`):

```python
class Event(Base):
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

class Program(Base):
    schedule_start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    schedule_end_time: Mapped[str] = mapped_column(String(5), nullable=False)
```

Same logical type. Two SQL types. `Event.start_time` arrived in the initial events table (alembic `54d37d2c4d32_initial_events_table.py`); `Program.schedule_start_time` arrived later (`c3a9e2f5b801_add_programs_table.py`) as `String(5)` because the ingestion lane was already producing `HH:MM` strings and a string column was the path of least resistance at the time.

## §2 Why it matters

- **Cross-table comparisons require parsing.** Code that wants to ask "is this program's window overlapping with this event's start?" must `time.fromisoformat()` the program string. Easy to forget, easy to mis-handle invalid strings.
- **Sort behavior is fragile.** `String(5)` sorts lexically. `"09:00" < "10:00"` works because of the zero-pad. `"9:00" < "10:00"` would lie (`"9" > "1"`). The Pydantic validator at `app/schemas/program.py` enforces zero-padding, but a direct INSERT without going through the validator would corrupt sort order.
- **Type-checker can't help.** `str` accepts any string; mypy/Pyright can't catch a `"25:00"` typo. `datetime.time` would.
- **The cost compounds across the codebase.** A grep at `d188517` finds **134 occurrences across 29 files** spanning `app/admin/`, `app/chat/`, `app/contrib/`, `app/core/`, `app/db/`, `app/programs/`, `app/schemas/`, `alembic/`, `scripts/`, and 15 test files. Each reader has to know whether the field is a string or a `time` object. Two shapes means twice the cognitive load on any future maintainer.

## §3 Options

### Option A — Big-bang migration

One Alembic migration converts `schedule_start_time` and `schedule_end_time` from `String(5)` to `Time`, with USING-clause CASTs. All ~134 call sites updated in the same slice. Tests updated.

**Pros.** One commit. No transient dual-shape state. Schema arrives at the desired end state immediately.

**Cons.** Large diff (estimate +200/-200 across 30+ files). High blast radius if anything regresses. Requires production DB downtime (the ALTER TABLE locks the table during the type conversion; on Railway with ~hundreds of program rows this is sub-second, but the deploy itself is the gating risk). Difficult to roll back partially.

### Option B — Phased migration

Add new `schedule_start_time_typed` and `schedule_end_time_typed` columns alongside the existing strings. Dual-write from every writer. Migrate readers tier by tier (admin → chat → core helpers → tests). Once all readers consume the typed columns, drop the strings in a final cleanup slice.

**Pros.** Each slice ships independently. No moment where readers and writers are out of sync. Production risk is small per slice. Rollback is a single revert.

**Cons.** Multiple slices (estimate 4: add columns + dual-write, migrate chat/core readers, migrate admin readers, drop old columns). Transient schema state where a Program row carries both the string and the typed value — disk-and-mental-overhead. The dual-write code adds ephemeral surface that needs to be deleted at the end of the campaign.

### Option C — Application-layer compatibility

Keep DB as `String(5)`. Add a `Program.schedule_start_time_t` Python `@property` that parses on read, returns `datetime.time`. Keep the string for storage; readers that want a `time` object call the property.

**Pros.** Zero schema migrations. Lowest immediate risk.

**Cons.** Doesn't fix the inconsistency at the schema layer — anyone reading the DB outside the ORM still sees a string. Every property access re-parses (small cost but adds up across hot paths in `tier1_handler` and `context_builder`). Doesn't catch invalid data at write time. Adds two parallel attribute names to remember.

### Option D — Do nothing

Acknowledge the inconsistency, leave it. Document the convention ("Program times are HH:MM strings; Event times are `time` objects") and move on.

**Pros.** Zero engineering cost.

**Cons.** The cost compounds — every new reader has to handle both shapes. And the next person who adds a "time-of-day" field to a third table has to make the same arbitrary choice.

## §4 Recommendation

**Option B — phased migration.** Reasons:

1. **Lowest production risk per slice.** Each phase is independently shippable and revertible.
2. **Reviewable diffs.** A single 200-file diff is harder to review than four 50-file diffs.
3. **Rolls naturally with the project's slice rhythm.** The codebase has shipped 21+ slices in a single session; 4-slice campaigns are the established cadence.
4. **The transient cost is bounded.** The dual-write window is one slice (Slice 53); cleanup happens at Slice 55 / 56.

The phased plan is sketched in §5. Slice 53 starts the implementation only after this decision lands and Casey signs off.

## §5 Campaign sketch (executes after decision)

| Slice | Subject                                                  | Footprint                                                                  |
| ----- | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| 53 (SHIPPED `83d41f7`)    | Add `schedule_start_time_typed` / `schedule_end_time_typed`; dual-write | Alembic migration (additive, nullable); update all writers (~10 files)     |
| 54 (SHIPPED `13883da`)    | Migrate `app/chat/` + `app/core/` readers to typed cols  | ~12 files; lots of test updates                                            |
| 55    | Migrate `app/admin/` readers + form handling             | ~6 files; admin-template updates                                           |
| 56    | Drop `schedule_start_time` / `schedule_end_time`; rename | Alembic migration; remove dual-write; rename typed cols to canonical names |

Each slice has its own bootstrap doc when it's drafted (i.e., we don't pre-write Slice 56's bootstrap until 53 has shipped — the campaign refines as it executes).

## §6 Alternatives considered and rejected

- **String(5) but enforced at write time only.** Add a check constraint in SQL, no other change. Doesn't help readers; doesn't compose with arithmetic. Rejected.
- **TIMESTAMP instead of TIME.** Storing program windows as full timestamps anchored to a sentinel date. Wastes bytes; introduces TZ confusion. Rejected.
- **JSONB with structured fields.** Replacing the two columns with one JSONB column carrying structured time data. Over-engineered for two scalars. Rejected.

## §7 Decision

**Decision (Casey, 2026-05-05): Option B — phased migration.**

Confirms the §4 recommendation. The §5 campaign sketch (Slices 53–56: add typed cols + dual-write → migrate chat/core readers → migrate admin readers → drop strings + rename) stands as the implementation path. Per-slice bootstraps are drafted just before each slice executes (i.e., Slice 53's bootstrap is written before Slice 53 starts; Slice 56's bootstrap is not pre-written until 53 has shipped).

Slice 53 starts the implementation. Its Step 0 must re-survey the call-site count (the §2 figure of 134 occurrences will shift slightly between this decision landing and Slice 53's start) and verify no new `schedule_*_time` writers were added in the meantime.

## §8 Verification posture for the eventual campaign

Per `docs/WORKING_AGREEMENT.md`'s deterministic-behavior verification rule:

- Every Slice in the campaign must hash-equality verify reads from the affected tier (Slice 54: hash a known set of Tier-1 / Tier-2 / Tier-3 outputs before and after; expect equality).
- Every slice must run the full test suite (`python -m pytest -q -m "not integration"`).
- Slice 56 (the cleanup) must additionally show a production catalog fingerprint before and after to rule out drift.

The 134-occurrence count in §2 is from `grep -rn "schedule_start_time\|schedule_end_time" --include="*.py"` (or equivalent) on the working tree as of `d188517`. The number may shift slightly by the time Slice 53 starts; re-survey at Slice 53's Step 0.
