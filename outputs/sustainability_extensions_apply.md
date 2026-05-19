# Sustainability Layer Extensions — Pre-Positioned Apply Artifact

> **What this is:** the ready-to-apply patch closing triage §8 #1 — bundling the 4 sustainability-layer extension carries (5.7 `wildlife_refuge` + 5.9 cat-12 types + 5.10 cat-10 types + 5.11 cat-11 types) into a single pre-Phase-7 chore commit. **NOT a direct file edit** — staged as an outputs/ artifact so the operator applies it when both Cursor sessions are NOT in flight (avoids any FUSE-staleness risk on `app/contrib/google_types_mapping.py`).
>
> **Author:** Cowork primary, 2026-05-20 post-`848524b`. Authored against the verified-unmapped state of `app/contrib/google_types_mapping.py` (315 lines, head SHA `848524b`).
>
> **Scope:** 14 new direct mappings added to `_PRIMARY_TYPE_MAP`. One carry (`church`) intentionally omitted — operator-decide between cat-12 (5.9 The Ark Center context) vs cat-13 (religious / nonprofit framing); documented in §5 below.

---

## §1 Context

Across Phase 5.7 + 5.9 + 5.10 + 5.11, each sub-phase's `§1 sustainability` work surfaced Google primary_types that landed via `_DISCOVERY_DOMAIN_FALLBACK` catch-all rather than direct `_PRIMARY_TYPE_MAP` entries. The catch-all works correctly (no mis-routes observed), but direct mappings are more deterministic + document intent explicitly + harden against Google's `types[]` array changes. Each close-out flagged these as V1.5 carry. Triage §8 #1 recommends bundling all 4 sets into a single pre-Phase-7 chore commit (~20–30 min eng).

**Carry sources:**
- 5.7 carry: `wildlife_refuge` direct mapping (caught by `(None, "entertainment_attractions")` catch-all today; surfaced by Bill Williams River NWR)
- 5.9 carry: `athletic_field` / `educational_institution` / `primary_school` / `sports_complex` / `sports_club` / `country_club` (+ `church` — operator-decide; omitted from this artifact)
- 5.10 carry: `camping_cabin` / `cottage` / `mobile_home_park` / `guest_house` (currently caught via secondary-types[] match against existing `lodging` direct mapping)
- 5.11 carry: `pet_supply_store` / `animal_shelter` / `aquarium_store`

**Verified unmapped 2026-05-20:** all 14 types confirmed absent from current `_PRIMARY_TYPE_MAP` via `grep -E "^\s*\"<type>\":" app/contrib/google_types_mapping.py` against `848524b`. The 15th (`church`) is also unmapped but intentionally skipped pending operator decision.

**File-scope safety:** `app/contrib/google_types_mapping.py` is NOT in the file scope of either Phase 6.4 (Lane D) or Phase 7 (Lane E) wrapper. Gotcha #18 disjoint. However, applying this artifact while Cursor sessions are mid-flight introduces FUSE-staleness risk on the working tree; recommend applying after Cursor returns (or pause Cursor sessions briefly while applying).

---

## §2 Patch — `app/contrib/google_types_mapping.py`

The patch appends 4 new mapping blocks. Insertion points are after the existing per-category section's last entry (file is sectioned per Tier 1 category for readability — preserve this convention).

### Block 1 — `wildlife_refuge` (cat-7 carry from 5.7)

**Insert after line 146** (`"golf_course": ("outdoors-parks-trails", "commercial"),`):

```python
    # Phase 5.7 V1.5 carry — wildlife_refuge direct mapping. Caught by
    # the (None, "entertainment_attractions") -> "outdoors-parks-trails"
    # catch-all (5.7 1dfd28e) today via Bill Williams River NWR; this
    # direct mapping is defensive vs Google ever changing the types[]
    # routing AND documents intent explicitly. Same 1-line shape as the
    # golf_course widening above. `place` (federal land, not commercial)
    # contrasts with golf_course's `commercial` (entry fees / staffed).
    "wildlife_refuge": ("outdoors-parks-trails", "place"),
```

### Block 2 — cat-10 lodging extensions (carry from 5.10)

**Insert after line 286** (`"bed_and_breakfast": ("lodging-vacation-rentals", "commercial"),`):

```python

    # Phase 5.10 V1.5 carry — 4 lodging direct mappings. The 5.10 §1
    # load empirically catches these via the secondary-types[] match
    # against the existing `lodging` direct mapping (above), but direct
    # mappings document intent explicitly + harden against Google
    # types[] array changes. Same defensive pattern 5.8 followed for
    # events. mobile_home_park is `place` (the park itself is a public/
    # community surface; individual rentals are commercial — secondary-
    # types[] match handles individual rentals via the same path).
    # camping_cabin + cottage + guest_house are `commercial` (fee-based
    # rentals).
    "camping_cabin": ("lodging-vacation-rentals", "commercial"),
    "cottage": ("lodging-vacation-rentals", "commercial"),
    "mobile_home_park": ("lodging-vacation-rentals", "place"),
    "guest_house": ("lodging-vacation-rentals", "commercial"),
```

### Block 3 — cat-11 pets extensions (carry from 5.11)

**Insert after line 208** (`"dog_trainer": ("pets", "commercial"),`):

```python

    # Phase 5.11 V1.5 carry — 3 pets direct mappings. Pre-Phase-5.11
    # `veterinary_care` + `pet_store` covered vet clinics + retail pet
    # stores. The 5.11 §1 load surfaced no `pet_supply_store` /
    # `animal_shelter` / `aquarium_store` entries explicitly because
    # Google emitted the more generic `pet_store` for retail surfaces,
    # but adding these is defensive vs Google ever splitting the
    # consolidated `pet_store` back out + documents intent for cat-11
    # routing. `pet_supply_store` + `aquarium_store` are `commercial`
    # (retail); `animal_shelter` is `place` (typically nonprofit / civic
    # facility — same shape as `dog_park`).
    "pet_supply_store": ("pets", "commercial"),
    "animal_shelter": ("pets", "place"),
    "aquarium_store": ("pets", "commercial"),
```

### Block 4 — cat-12 classes-sports-recreation extensions (carry from 5.9)

**Insert after line 254** (`"pickleball_court": ("classes-sports-recreation", "place"),`):

```python

    # Phase 5.9 V1.5 carry — 6 classes-sports-recreation direct
    # mappings. The 5.9 §1 sustainability matrix flagged athletic_field
    # / educational_institution / primary_school / sports_complex /
    # sports_club / country_club as deferred-to-V1.5 widening targets.
    # Surfaces relevant to existing 5.9 entries: Sand Volleyball at
    # Rotary Park (athletic_field primary; currently in cat-5 HWC per
    # 5.9 Slice F decision) + Mohave Traffic School + Psalms Learning
    # Center (educational_institution-ish surfaces, currently routed
    # via the `school` direct mapping at line 288).
    #
    # `commercial` vs `place` split: educational_institution +
    # primary_school + sports_club + country_club are `commercial` (fee-
    # based / membership / staffed); athletic_field + sports_complex
    # are `place` (typically municipal/public-park amenities — same
    # shape as swimming_pool / tennis_court / pickleball_court above).
    #
    # NOTE: `church` was a sibling 5.9 carry candidate but is omitted
    # here per operator-decide (cat-12 vs cat-13 framing depends on
    # the 5.9 The Ark Center recategorization decision). See
    # outputs/v1_5_carry_inventory_triage.md §4 carry #29.
    "athletic_field": ("classes-sports-recreation", "place"),
    "educational_institution": ("classes-sports-recreation", "commercial"),
    "primary_school": ("classes-sports-recreation", "commercial"),
    "sports_complex": ("classes-sports-recreation", "place"),
    "sports_club": ("classes-sports-recreation", "commercial"),
    "country_club": ("classes-sports-recreation", "commercial"),
```

**Total net additions:** 14 mapping lines + ~30 comment lines = ~44 lines net to `app/contrib/google_types_mapping.py` (315 → ~359 lines).

---

## §3 Test guard — `tests/test_sustainability_extensions.py` (new file)

Single-file test guard verifying all 14 new mappings round-trip correctly through the public mapping function. Keeps the scope minimal (no full re-test of pre-existing mappings; just the new ones).

```python
"""Phase 5.7+5.9+5.10+5.11 V1.5 carry — sustainability layer extensions test guard.

Verifies the 14 new direct mappings added in the
sustainability_extensions_apply commit resolve to the expected
(category_slug, place_type) tuples.

The mappings close 4 deferred carries:
- 5.7 carry: wildlife_refuge → outdoors-parks-trails
- 5.9 carry: athletic_field + 5 cat-12 types → classes-sports-recreation
- 5.10 carry: camping_cabin + 3 cat-10 types → lodging-vacation-rentals
- 5.11 carry: pet_supply_store + 2 cat-11 types → pets

`church` is intentionally NOT covered (operator-decide between cat-12 vs
cat-13; see outputs/v1_5_carry_inventory_triage.md §4 carry #29 + the
sustainability_extensions_apply artifact §5 narrative).
"""
from __future__ import annotations

import pytest

from app.contrib.google_types_mapping import _PRIMARY_TYPE_MAP


# Each tuple: (primary_type, expected_slug, expected_place_type)
SUSTAINABILITY_EXTENSIONS: list[tuple[str, str, str]] = [
    # 5.7 carry — wildlife_refuge → cat-7
    ("wildlife_refuge", "outdoors-parks-trails", "place"),
    # 5.9 carry — 6 cat-12 types
    ("athletic_field", "classes-sports-recreation", "place"),
    ("educational_institution", "classes-sports-recreation", "commercial"),
    ("primary_school", "classes-sports-recreation", "commercial"),
    ("sports_complex", "classes-sports-recreation", "place"),
    ("sports_club", "classes-sports-recreation", "commercial"),
    ("country_club", "classes-sports-recreation", "commercial"),
    # 5.10 carry — 4 cat-10 types
    ("camping_cabin", "lodging-vacation-rentals", "commercial"),
    ("cottage", "lodging-vacation-rentals", "commercial"),
    ("mobile_home_park", "lodging-vacation-rentals", "place"),
    ("guest_house", "lodging-vacation-rentals", "commercial"),
    # 5.11 carry — 3 cat-11 types
    ("pet_supply_store", "pets", "commercial"),
    ("animal_shelter", "pets", "place"),
    ("aquarium_store", "pets", "commercial"),
]


@pytest.mark.parametrize("primary_type,expected_slug,expected_place_type", SUSTAINABILITY_EXTENSIONS)
def test_sustainability_extension_direct_mapping(
    primary_type: str,
    expected_slug: str,
    expected_place_type: str,
) -> None:
    """Each new mapping resolves to the expected (slug, place_type) tuple."""
    assert primary_type in _PRIMARY_TYPE_MAP, (
        f"{primary_type!r} should be in _PRIMARY_TYPE_MAP after the "
        f"sustainability_extensions_apply commit lands"
    )
    actual_slug, actual_place_type = _PRIMARY_TYPE_MAP[primary_type]
    assert actual_slug == expected_slug, (
        f"{primary_type!r}: expected slug {expected_slug!r}, got {actual_slug!r}"
    )
    assert actual_place_type == expected_place_type, (
        f"{primary_type!r}: expected place_type {expected_place_type!r}, "
        f"got {actual_place_type!r}"
    )


def test_church_intentionally_unmapped() -> None:
    """`church` is a 5.9 carry candidate but operator-decide pending —
    asserts the artifact's §5 narrative ("church omitted") stays honest.

    If a future commit DOES map `church`, delete this test in the same
    commit + update outputs/v1_5_carry_inventory_triage.md §4 carry #29.
    """
    assert "church" not in _PRIMARY_TYPE_MAP, (
        "`church` was omitted from the sustainability_extensions_apply "
        "commit per operator-decide between cat-12 (5.9 The Ark Center "
        "context) vs cat-13 (religious / nonprofit). If this test fails, "
        "the mapping was added — update outputs/v1_5_carry_inventory_triage.md "
        "§4 carry #29 to reflect the disposition."
    )
```

**Tests added:** 15 (14 parametrized for the new mappings + 1 for the `church` omission guard).

---

## §4 Apply recipe — PowerShell-safe

Run these in order from `C:\Users\casey\projects\havasu-chat`:

```powershell
# 1. Pre-flight — confirm Cursor is NOT in flight on this lane
git status --short
# Expected: clean working tree OR only Cursor's Phase 6.4 / 7 files
# If Cursor is touching app/contrib/google_types_mapping.py: STOP — gotcha #18 violation
#   (verify by reading the wrapper's expected file list)

# 2. Open the target file in your editor
# Apply the 4 patch blocks from §2 above at the specified line anchors

# 3. Create the new test file with content from §3 above
# Path: tests/test_sustainability_extensions.py

# 4. Verify
python -m pytest tests/test_sustainability_extensions.py -v
# Expected: 15 passed (14 parametrized + 1 omission guard)

python -m pytest -q
# Expected: 2060 + 15 = 2075 collected; all green (assuming Cursor's
#           parallel work hasn't landed; if it has, baseline shifts)

ruff check app/contrib/google_types_mapping.py tests/test_sustainability_extensions.py
# Expected: 0 issues

# 5. Stage + commit (PowerShell-safe; multiple -m flags; no bash heredocs)
git add app/contrib/google_types_mapping.py tests/test_sustainability_extensions.py
git commit `
  -m "chore(data): sustainability layer direct mappings -- 5.7+5.9+5.10+5.11 V1.5 carries" `
  -m "Closes triage sec8 #1 -- bundles 4 deferred sustainability-layer extension carries into a single pre-Phase-7 chore commit. 14 new direct mappings in _PRIMARY_TYPE_MAP across cat-7 (wildlife_refuge), cat-10 (camping_cabin + cottage + mobile_home_park + guest_house), cat-11 (pet_supply_store + animal_shelter + aquarium_store), cat-12 (athletic_field + educational_institution + primary_school + sports_complex + sports_club + country_club)." `
  -m "All 14 types were previously caught via _DISCOVERY_DOMAIN_FALLBACK catch-alls + secondary-types[] matches; direct mappings are defensive vs Google types[] array changes + document intent explicitly. Same shape as Phase 5.7 golf_course / 5.8 events / 5.10 hotel widening commits. church omitted per operator-decide (cat-12 vs cat-13 framing depends on 5.9 The Ark Center recategorization decision; see outputs/v1_5_carry_inventory_triage.md sec4 carry #29). Test guard at tests/test_sustainability_extensions.py (+15 tests; 14 parametrized + 1 church-omission guard)."

# 6. Push (when ready)
git push origin main
```

**Expected commit shape:** 1 substantive commit; 2 files changed; net +59 lines (~44 in mapping file + ~75 in new test file - 0 deletions). Alembic head unchanged. Pytest 2060 → 2075 (or whatever Cursor's parallel work baselined to + 15).

---

## §5 What's NOT in this commit

- **`church` direct mapping.** Operator-decide between cat-12 (5.9 The Ark Center building also houses Psalms Learning Center which IS cat-12) vs cat-13 (religious / nonprofit). The 5.9 close-out's "The Ark Center recategorization" carry frames this as a per-entity decision; mapping `church` globally would force one disposition for ALL churches in future scrapes. Recommend: leave `church` unmapped until the operator picks a default; the `_DISCOVERY_DOMAIN_FALLBACK` catch-all continues to route via `(None, "childcare_education") → "classes-sports-recreation"` if the church surfaces under a 5.9-domain scrape, OR via operator queue if it surfaces unmapped.
- **`fitness_sports` 7 HWC-absorbed types** (gyms / yoga / pilates / crossfit / martial_arts / jiu_jitsu / dance). These continue to route to cat-5 HWC via the existing `(None, "fitness_sports") → "health-wellness-care"` catch-all. The 5.9 carry was explicit that V1.5 may want selective dual-cat with cat-12 for entities offering distinct cat-12 services — NOT a global re-mapping. Out of scope for this artifact.
- **`hair_salon` / `beauty_salon` / `nail_salon`.** Explicitly mapped to `(None, None)` per Phase 5 prereq §3.1.a lock ("skip beauty_personal_care in Phase 5; revisit V1.5"). Triage doc treats this as a separate carry from the sustainability extensions; not bundled here.

---

## §6 If Cursor's parallel work changes the baseline

If Phase 6.4 (Lane D) ships before this artifact is applied, the Lane D commit will have added `users.boat_mode_preference` alembic migration + ~30–50 net-new tests. The baseline becomes `2090–2110` + this artifact's +15 = `2105–2125`. Verify by re-running `python -m pytest --collect-only -q | tail -3` immediately before applying.

If Phase 7 (Lane E) ships before this artifact is applied, similarly the baseline shifts (~+50–80 tests, plus possibly a User.last_active_at migration). Re-verify before applying.

If BOTH lanes ship before this artifact is applied, the baseline is whatever post-D-and-E shows; apply normally. The 14 new mappings don't conflict with anything either lane touches (Lane D = templates/static/routes; Lane E = chat/snowbird/halt3).

---

## §7 Rollback path

If the commit causes unexpected behavior, rollback is straightforward:

```powershell
# Soft rollback (keep changes staged for re-attempt)
git reset --soft HEAD~1

# Hard rollback (discard the commit + changes)
git reset --hard HEAD~1

# If already pushed, revert via new commit
git revert <commit_sha>
git push origin main
```

No alembic migration to roll back. No template/static-asset changes to roll back. Only the mapping table + test file. Low-risk; rollback unlikely to be needed.

---

*Authored by Cowork primary at the post-`848524b` dispatch-pre-position session (2026-05-20). Lives at `outputs/sustainability_extensions_apply.md`. Closes triage §8 #1 when applied. The 14 new mappings + test guard are ready to apply at operator discretion — recommend applying after both Cursor sessions return OR during a clean window between them.*
