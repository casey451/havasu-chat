"""
Backfill event.provider_id by matching contact_name, optional non-allowlist source,
or title+description+location blob (entity_matcher-style scoring).

Prerequisites: providers table populated (Phase 1.3). Only updates rows where
provider_id IS NULL; only writes provider_id and updated_at.

Usage:
  python -m app.db.backfill_event_providers
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Sequence

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from app.db.models import Provider as ProviderModel
from sqlalchemy.orm import Session

from app.chat.entity_matcher import CANONICAL_EXTRAS, match_entity_with_rows
from app.chat.normalizer import normalize
from app.db.seed_providers import _norm_provider_name

# Step 1 / 2: structured fields (contact_name, source when not allowlisted)
CONTACT_SOURCE_THRESHOLD = 90.0
# Step 3: title + description + location_name (noisier)
BLOB_THRESHOLD = 95.0

SOURCE_ALLOWLIST = frozenset({"admin", "user", "scraped", ""})


def _needles_for_canonical(canonical: str) -> frozenset[str]:
    """Mirror app.chat.entity_matcher._needles_for_canonical (not exported there)."""
    out: set[str] = set()
    c = canonical.strip()
    if not c:
        return frozenset()
    out.add(normalize(c))
    out.add(c.lower())
    for extra in CANONICAL_EXTRAS.get(c, []):
        n = normalize(extra)
        if n:
            out.add(n)
    return frozenset(x for x in out if x)


def _best_blob_score(norm_query: str, needles: frozenset[str]) -> float:
    best = 0.0
    for needle in needles:
        best = max(best, float(fuzz.token_set_ratio(norm_query, needle)))
    return best


def _blob_scores_against_canonicals(blob: str, canonical_names: Sequence[str]) -> list[tuple[str, float]]:
    """Per-provider best score using same needle logic as match_entity_with_rows."""
    norm = normalize(blob)
    if not norm:
        return []
    out: list[tuple[str, float]] = []
    for c in canonical_names:
        c = c.strip()
        if not c:
            continue
        needles = _needles_for_canonical(c)
        out.append((c, _best_blob_score(norm, needles)))
    return out


def _simple_fuzzy_scores(query: str, providers: list[ProviderModel]) -> list[tuple[ProviderModel, float]]:
    """token_set_ratio(query, provider.provider_name) for each provider."""
    q = (query or "").strip()
    if not q:
        return []
    scored: list[tuple[ProviderModel, float]] = []
    for p in providers:
        score = float(fuzz.token_set_ratio(q, p.provider_name))
        scored.append((p, score))
    return scored


def _pick_provider(
    scored: list[tuple[ProviderModel, float]],
    threshold: float,
) -> tuple[ProviderModel | None, bool, list[tuple[str, float]]]:
    """
    Ambiguity rule: accept iff best >= threshold and
    (second < threshold OR second <= best - 5).
    Otherwise if best >= threshold and second >= threshold and second > best - 5 → ambiguous.

    Returns (provider_or_none, is_ambiguous, detail_rows as (provider_name, score)).
    """
    if not scored:
        return None, False, []
    sorted_pairs = sorted(scored, key=lambda x: (-x[1], x[0].provider_name))
    best_p, best_s = sorted_pairs[0]
    second_s = sorted_pairs[1][1] if len(sorted_pairs) > 1 else -1.0
    if best_s < threshold:
        return None, False, []
    if second_s < threshold or second_s <= best_s - 5.0:
        return best_p, False, [(best_p.provider_name, best_s)]
    amb: list[tuple[str, float]] = [
        (p.provider_name, s) for p, s in sorted_pairs if s >= threshold and s > best_s - 5.0
    ]
    return None, True, amb[:15]


def _norm_source_allowlisted(source: str | None) -> bool:
    s = (source or "").strip().lower()
    return s in SOURCE_ALLOWLIST


@dataclass
class AmbiguousEventRecord:
    event_id: str
    event_title: str
    step: str
    candidates: list[tuple[str, float]]


@dataclass
class FuzzyLinkDetail:
    step: str
    event_id: str
    event_title: str
    provider_name: str
    score: float


@dataclass
class BackfillEventProvidersResult:
    events_scanned: int = 0
    skipped_already_linked: int = 0
    linked_contact_exact: int = 0
    linked_contact_fuzzy: int = 0
    linked_source_exact: int = 0
    linked_source_fuzzy: int = 0
    linked_blob: int = 0
    contact_fuzzy_details: list[FuzzyLinkDetail] = field(default_factory=list)
    source_fuzzy_details: list[FuzzyLinkDetail] = field(default_factory=list)
    blob_details: list[FuzzyLinkDetail] = field(default_factory=list)
    ambiguous: list[AmbiguousEventRecord] = field(default_factory=list)
    events_updated: int = 0


def _print_report(
    result: BackfillEventProvidersResult,
    *,
    linked_count: int,
    null_count: int,
) -> None:
    print("=== Backfill event.provider_id ===")
    print(f"events scanned: {result.events_scanned}")
    print(f"already linked (skipped): {result.skipped_already_linked}")
    print(f"linked via contact_name exact: {result.linked_contact_exact}")
    print(f"linked via contact_name fuzzy: {result.linked_contact_fuzzy}")
    for d in result.contact_fuzzy_details:
        print(
            f"  contact fuzzy  score={d.score:.1f}  event_title={d.event_title!r}  "
            f"-> provider={d.provider_name!r}  (event.id={d.event_id})"
        )
    print(f"linked via source exact: {result.linked_source_exact}")
    print(f"linked via source fuzzy: {result.linked_source_fuzzy}")
    for d in result.source_fuzzy_details:
        print(
            f"  source fuzzy  score={d.score:.1f}  event_title={d.event_title!r}  "
            f"-> provider={d.provider_name!r}  (event.id={d.event_id})"
        )
    print(f"linked via title/description/location blob: {result.linked_blob}")
    for d in result.blob_details:
        print(
            f"  blob match  score={d.score:.1f}  event_title={d.event_title!r}  "
            f"-> provider={d.provider_name!r}  (event.id={d.event_id})"
        )
    print(f"ambiguous (skipped): {len(result.ambiguous)}")
    for amb in result.ambiguous:
        print(f"  event id={amb.event_id}  title={amb.event_title!r}  step={amb.step}")
        for cname, sc in amb.candidates:
            print(f"    candidate: {cname!r}  score={sc:.1f}")
    print(f"events updated this run: {result.events_updated}")
    print(f"events with provider_id set (after run): {linked_count}")
    print(f"events with provider_id null (after run): {null_count}")


def backfill_event_providers(db: Session) -> BackfillEventProvidersResult:
    from app.db.models import Event, Provider

    result = BackfillEventProvidersResult()
    providers: list[Provider] = db.query(Provider).order_by(Provider.provider_name).all()
    if not providers:
        raise RuntimeError(
            "providers table is empty — run Phase 1.3 provider seed (app.db.seed_providers) "
            "before backfill_event_providers."
        )

    prov_by_norm: dict[str, list[Provider]] = {}
    for p in providers:
        n = _norm_provider_name(p.provider_name)
        prov_by_norm.setdefault(n, []).append(p)

    canonical_names = [p.provider_name for p in providers]
    events: list[Event] = db.query(Event).order_by(Event.id).all()
    result.events_scanned = len(events)
    now = datetime.now(UTC).replace(tzinfo=None)

    for ev in events:
        if ev.provider_id is not None:
            result.skipped_already_linked += 1
            continue

        chosen: Provider | None = None
        step_kind: str | None = None

        # --- Step 1: contact_name ---
        cn = (ev.contact_name or "").strip()
        if cn:
            norm_cn = _norm_provider_name(cn)
            exact_cands = prov_by_norm.get(norm_cn, [])
            if len(exact_cands) == 1:
                chosen = exact_cands[0]
                step_kind = "contact_exact"
            elif len(exact_cands) > 1:
                result.ambiguous.append(
                    AmbiguousEventRecord(
                        event_id=ev.id,
                        event_title=ev.title,
                        step="contact_name_exact_duplicate",
                        candidates=[(p.provider_name, 100.0) for p in exact_cands],
                    )
                )
            else:
                scored = _simple_fuzzy_scores(cn, providers)
                pick, amb, details = _pick_provider(scored, CONTACT_SOURCE_THRESHOLD)
                if amb:
                    result.ambiguous.append(
                        AmbiguousEventRecord(
                            event_id=ev.id,
                            event_title=ev.title,
                            step="contact_name_fuzzy",
                            candidates=details,
                        )
                    )
                elif pick is not None:
                    chosen = pick
                    step_kind = "contact_fuzzy"
                    result.contact_fuzzy_details.append(
                        FuzzyLinkDetail(
                            step="contact_fuzzy",
                            event_id=ev.id,
                            event_title=ev.title,
                            provider_name=pick.provider_name,
                            score=details[0][1],
                        )
                    )

        # --- Step 2: source (non-allowlist only) ---
        if chosen is None and not _norm_source_allowlisted(ev.source):
            src = (ev.source or "").strip()
            if src:
                norm_src = _norm_provider_name(src)
                exact_cands = prov_by_norm.get(norm_src, [])
                if len(exact_cands) == 1:
                    chosen = exact_cands[0]
                    step_kind = "source_exact"
                elif len(exact_cands) > 1:
                    result.ambiguous.append(
                        AmbiguousEventRecord(
                            event_id=ev.id,
                            event_title=ev.title,
                            step="source_exact_duplicate",
                            candidates=[(p.provider_name, 100.0) for p in exact_cands],
                        )
                    )
                else:
                    scored = _simple_fuzzy_scores(src, providers)
                    pick, amb, details = _pick_provider(scored, CONTACT_SOURCE_THRESHOLD)
                    if amb:
                        result.ambiguous.append(
                            AmbiguousEventRecord(
                                event_id=ev.id,
                                event_title=ev.title,
                                step="source_fuzzy",
                                candidates=details,
                            )
                        )
                    elif pick is not None:
                        chosen = pick
                        step_kind = "source_fuzzy"
                        result.source_fuzzy_details.append(
                            FuzzyLinkDetail(
                                step="source_fuzzy",
                                event_id=ev.id,
                                event_title=ev.title,
                                provider_name=pick.provider_name,
                                score=details[0][1],
                            )
                        )

        # --- Step 3: title + description + location (no contact_name) ---
        if chosen is None:
            blob = "\n".join(
                [
                    (ev.title or "").strip(),
                    (ev.description or "").strip(),
                    (ev.location_name or "").strip(),
                ]
            )
            # Per-name scores use the same needle set as match_entity_with_rows (CANONICAL_EXTRAS).
            name_scores = _blob_scores_against_canonicals(blob, canonical_names)
            scored_providers: list[tuple[Provider, float]] = []
            name_to_prov = {p.provider_name: p for p in providers}
            for pname, sc in name_scores:
                p = name_to_prov.get(pname)
                if p is not None:
                    scored_providers.append((p, sc))
            pick, amb, details = _pick_provider(scored_providers, BLOB_THRESHOLD)
            # Public matcher (single best, >75 internal); must agree on winner when we link at ≥95.
            me_hint = match_entity_with_rows(blob, canonical_names)
            if amb:
                result.ambiguous.append(
                    AmbiguousEventRecord(
                        event_id=ev.id,
                        event_title=ev.title,
                        step="title_description_location_blob",
                        candidates=details,
                    )
                )
            elif pick is not None:
                if me_hint is not None and me_hint[0] != pick.provider_name:
                    raise RuntimeError(
                        "Internal error: blob best provider disagrees with match_entity_with_rows "
                        f"({pick.provider_name!r} vs {me_hint[0]!r}); event id={ev.id}"
                    )
                chosen = pick
                step_kind = "blob"
                result.blob_details.append(
                    FuzzyLinkDetail(
                        step="blob",
                        event_id=ev.id,
                        event_title=ev.title,
                        provider_name=pick.provider_name,
                        score=details[0][1],
                    )
                )

        if chosen is not None:
            ev.provider_id = chosen.id
            ev.updated_at = now
            result.events_updated += 1
            if step_kind == "contact_exact":
                result.linked_contact_exact += 1
            elif step_kind == "contact_fuzzy":
                result.linked_contact_fuzzy += 1
            elif step_kind == "source_exact":
                result.linked_source_exact += 1
            elif step_kind == "source_fuzzy":
                result.linked_source_fuzzy += 1
            elif step_kind == "blob":
                result.linked_blob += 1

    db.commit()

    linked = db.query(Event).filter(Event.provider_id.isnot(None)).count()
    null_n = db.query(Event).filter(Event.provider_id.is_(None)).count()
    _print_report(result, linked_count=linked, null_count=null_n)
    return result


def main(argv: list[str] | None = None) -> int:
    from app.bootstrap_env import ensure_dotenv_loaded
    from app.db.database import SessionLocal, init_db

    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Backfill event.provider_id from providers")
    parser.parse_args(argv)
    init_db()
    with SessionLocal() as db:
        backfill_event_providers(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
