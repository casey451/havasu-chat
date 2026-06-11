"""Name + Google-type signal rules for the health/beauty *leaf* taxonomy.

Why this exists (2026-06-11 categorization workstream): the fine leaf a
provider lands on is its PRIMARY ``entity_categories`` link, assigned in bulk by
the A.3 taxonomy migration (``scripts/apply_taxonomy_remap.py`` reading
``A-migration-PROD-final.csv``). That migration mis-shelved the skin/spa cluster
because Google's ``types`` array cannot separate the cases:

  * ``skin_care_clinic`` covers BOTH medical dermatology AND cosmetic skincare;
  * ``spa`` covers BOTH a day spa / massage studio AND a medical med-spa.

The audit (scripts/audit_subcategory_assignments.py, 2026-06-11) found the result
inverted: the *Med Spas & Aesthetics* leaf held 3 dermatologists + 2 esthetics
studios and ZERO real med spas, while ~15 actual med spas sat in *Day Spas &
Massage*, and a dermatology clinic sat in *Primary Care*. The coarse
``subcategory`` columns were fine — this is purely a leaf-assignment problem.

Casey's routing decisions (2026-06-11), encoded here:
  * dermatologists (medical skin)            -> ``dermatology-and-skin`` (Health)
  * medical med-spas (Botox/laser/IV/...)    -> ``med-spas-and-aesthetics`` (Beauty)
  * cosmetic esthetics / facials / waxing    -> ``day-spas-and-massage`` (Beauty)
  * genuine massage / day spas               -> ``day-spas-and-massage`` (no change)

These are PURE functions (no DB/ORM) so they backfill offline, run on ingest,
and unit-test against Casey's named examples. ``classify_skin_spa_leaf`` returns
``None`` for anything that is NOT a skin/spa-cluster row, so callers leave hair,
nail, and every non-beauty provider untouched — minimal blast radius.
"""

from __future__ import annotations

import re

DERMATOLOGY = "dermatology-and-skin"
MED_SPAS = "med-spas-and-aesthetics"
DAY_SPAS = "day-spas-and-massage"

# The leaves this corrector is allowed to MOVE BETWEEN. A provider currently on
# any of these (or signalled as dermatology from elsewhere, e.g. Primary Care)
# is in scope; everything else is left alone.
SKIN_SPA_CLUSTER_LEAVES = frozenset(
    {DERMATOLOGY, MED_SPAS, DAY_SPAS, "primary-care"}
)

# --- signals ---------------------------------------------------------------
# Dermatology = medical skin. Highest priority: a dermatologist is never a med
# spa or a day spa, even when Google tags it skin_care_clinic / doctor / spa.
_DERM_SIGNALS = ("dermatolog",)  # dermatology, dermatologist, dermatologic
_DERM_TYPES = ("dermatologist",)

# Medical med-spa signals — procedural / medical-grade aesthetic markers only.
# Deliberately NOT bare "aesthetic(s)" — Casey routes cosmetic esthetics to Day
# Spas, and several pure-cosmetic studios use "Aesthetics" in their name
# (Evie Aesthetics, Sunrise Aesthetics).
_MED_SPA_PHRASES = (
    "med spa", "medspa", "medical spa", "medical esthetic", "medical aesthetic",
    "botox", "injectable", "filler", "dysport", "juvederm",
    "laser", "coolsculpt", "microneedl", "micro-needl", "micro needl",
    "rejuvenation", "hormone therapy", "hormone replacement", "wellness and medspa",
)
# Short tokens that need word boundaries so they don't match inside other words
# ("iv" inside "river", "prp" inside ...): matched with \b...\b.
_MED_SPA_WORD_TOKENS = ("iv", "prp")
_MED_SPA_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _MED_SPA_WORD_TOKENS) + r")\b"
)
# "iv therapy/drip/hydration/lounge/bar" phrases (covered by the \biv\b token too,
# but listed for documentation of intent).

# Cosmetic spa / massage TYPES — when none of the above medical signals fire, a
# row of one of these types belongs on Day Spas & Massage. Deliberately EXCLUDES
# ``beauty_salon`` (Google's type for hair salons — those stay on Hair Salons &
# Barbers) and ``nail_salon`` (stays on Nail Salons): this corrector only moves
# the skin/spa/med-spa/dermatology cluster, never hair or nail.
_COSMETIC_SPA_TYPES = (
    "spa", "massage_spa", "massage",
)
# Cosmetic markers that, when present alongside a medical-skin type
# (skin_care_clinic), reveal an esthetics/beauty studio rather than a medical
# dermatology practice. Complexions (makeup_artist|hair_care|massage_spa) and
# Skin Deep Esthetics (beauty_salon|hair_care) carry these; a pure medical skin
# clinic like "928 SKIN" (skin_care_clinic|medical_clinic only) does not.
_COSMETIC_MARKER_TOKENS = (
    "beauty_salon", "hair_care", "hair_salon", "makeup_artist", "nail_salon",
    "massage_spa", "massage", "tanning", "body_art",
)
_COSMETIC_MARKER_NAME_HINTS = (
    "esthet", "aesthet", "facial", "wax", "lash", "brow", "beauty", "salon",
)


def _haystack(name: str | None, gpc: str | None, categories) -> str:
    parts: list[str] = []
    if name:
        parts.append(str(name))
    if gpc:
        parts.append(str(gpc))
    if isinstance(categories, (list, tuple)):
        parts.extend(str(c) for c in categories if c)
    elif categories:
        parts.append(str(categories))
    return " ".join(parts).lower()


def _has_med_spa_signal(hay: str) -> bool:
    if any(p in hay for p in _MED_SPA_PHRASES):
        return True
    return bool(_MED_SPA_WORD_RE.search(hay))


def classify_skin_spa_leaf(
    name: str | None,
    google_primary_category: str | None = None,
    google_categories=None,
) -> str | None:
    """Correct leaf slug for a skin/spa-cluster provider, or ``None``.

    Priority: dermatology (medical) -> medical med-spa -> cosmetic spa/esthetics.
    Returns ``None`` when the row shows no skin/spa-cluster signal at all, so the
    caller leaves it untouched (hair, nail, GPs, and everything else).
    """
    hay = _haystack(name, google_primary_category, google_categories)
    gpc = (google_primary_category or "").lower()

    # 1. Dermatology — medical skin. Beats everything.
    if any(s in hay for s in _DERM_SIGNALS) or gpc in _DERM_TYPES:
        return DERMATOLOGY

    # 2. Medical med-spa — procedural / medical-grade aesthetic markers.
    if _has_med_spa_signal(hay):
        return MED_SPAS

    # 3. Medical-skin clinic (skin_care_clinic) with no med-spa signal: split by
    #    whether cosmetic markers are present. Pure medical skin -> Dermatology;
    #    cosmetic skin/esthetics studio -> Day Spas (Casey's routing).
    if gpc == "skin_care_clinic":
        has_cosmetic_marker = any(t in hay for t in _COSMETIC_MARKER_TOKENS) or any(
            h in hay for h in _COSMETIC_MARKER_NAME_HINTS
        )
        return DAY_SPAS if has_cosmetic_marker else DERMATOLOGY

    # 4. Genuine day spa / massage. Keyed ONLY on the Google PRIMARY type, never
    #    on name/category hints: a salon's types[] array routinely carries stray
    #    "spa"/"massage" tokens, and matching those wrongly pulled hair salons,
    #    chiropractors, yoga studios, dentists, etc. into Day Spas (caught in the
    #    2026-06-11 dry-run). Med spas are already handled at branch 2; cosmetic
    #    skin studios at branch 3. Everything else is left untouched.
    if gpc in _COSMETIC_SPA_TYPES:
        return DAY_SPAS

    return None
