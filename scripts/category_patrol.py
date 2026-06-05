"""Category patrol — flag providers whose primary_category looks wrong.

Categorization in this repo is deterministic substring matching with no semantic
check (``app/categories/subcategories.derive_primary_category`` walks Google type
tokens through a ~90-entry map to one of 13 canonical primaries; unmatched rows
get ``None``). Multi-source ingest merges through ``ingest_reconciler`` with no
sanity check that the resulting category makes sense. This patrol is the missing
semantic pass: a scheduled, low-cost gpt-4o-mini sweep that reads
Claude-authored per-category rulesets and flags rows whose stored
``primary_category`` disagrees with what the signals say it should be.

It is deliberately *advisory*: it writes only two additive, nullable columns
(``category_confidence`` 0-1, ``category_flagged_at``) that NO serving path reads
(see the c1d2e3f4a5b6 migration). A flagged row keeps serving exactly as before;
the flag just routes it into an admin "miscategorized?" review list. Worst-case
blast radius is a wrong flag, never a wrong listing.

Cost: rules + one item is ~500 tokens in / ~30 out, so a full-catalog pass with
gpt-4o-mini is on the order of $0.10-0.30 per thousand providers -- cheap enough
to run weekly from GitHub Actions (the local-LLM mechanism was cut on exactly
this economics in the discovery plan).

Prod-write discipline (CLAUDE.md): writes are gated. Default is a DRY RUN that
prints counts + a sample and touches nothing. ``--apply`` performs the write and
must follow the dry-run -> counts -> Casey-approval sequence; never run --apply
against prod without that.

Usage
-----
    python scripts/category_patrol.py                 # dry run, whole catalog
    python scripts/category_patrol.py --limit 50      # dry run, first 50
    python scripts/category_patrol.py --json
    python scripts/category_patrol.py --apply         # WRITE flags (gated!)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.categories.subcategories import PRIMARY_CATEGORY_SLUGS  # noqa: E402
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

logger = logging.getLogger("category_patrol")

RULESETS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "category_rules"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_THRESHOLD = 0.75
_VALID_PRIMARIES = frozenset(PRIMARY_CATEGORY_SLUGS)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSignals:
    """The categorization-relevant fields the classifier reasons over."""

    id: str
    name: str
    current_primary: str | None
    google_primary_category: str | None = None
    google_categories: list[str] | None = None
    subcategory: str | None = None
    legacy_category: str | None = None

    @classmethod
    def from_provider(cls, p: Provider) -> "ProviderSignals":
        cats = p.google_categories if isinstance(p.google_categories, list) else None
        return cls(
            id=p.id,
            name=p.provider_name,
            current_primary=p.primary_category,
            google_primary_category=p.google_primary_category,
            google_categories=cats,
            subcategory=p.subcategory,
            legacy_category=p.category,
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current_primary_category": self.current_primary,
            "google_primary_category": self.google_primary_category,
            "google_categories": self.google_categories or [],
            "subcategory": self.subcategory,
            "legacy_category": self.legacy_category,
        }


@dataclass(frozen=True)
class Verdict:
    """The classifier's read: the primary it believes is correct + confidence."""

    primary: str | None  # one of the 13 canonical slugs, or None when unsure
    confidence: float  # 0-1 confidence in ``primary``
    reason: str = ""


@dataclass
class FlagDecision:
    signals: ProviderSignals
    verdict: Verdict
    flag: bool


# ---------------------------------------------------------------------------
# Rulesets
# ---------------------------------------------------------------------------


def load_rulesets(directory: Path = RULESETS_DIR) -> dict[str, str]:
    """Load ``prompts/category_rules/<primary>.md`` into ``{slug: markdown}``.

    Only files whose stem is one of the 13 canonical slugs are loaded; a
    README or any stray file is ignored. Missing directory -> empty dict (the
    classifier still runs on signals alone, just with weaker guidance).
    """
    out: dict[str, str] = {}
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        slug = path.stem
        if slug in _VALID_PRIMARIES:
            out[slug] = path.read_text(encoding="utf-8").strip()
    return out


def rulesets_block(rulesets: dict[str, str]) -> str:
    if not rulesets:
        return "(no category rulesets provided)"
    parts = [f"## {slug}\n{text}" for slug, text in sorted(rulesets.items())]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt + classifier
# ---------------------------------------------------------------------------

_SYSTEM_PREAMBLE = """\
You are a careful data-quality auditor for a Lake Havasu City local directory.
Each business is assigned exactly one "primary category" from this fixed set of
13 slugs:

{slugs}

Below are rulesets describing what belongs in each category. Given one business's
signals, decide which single slug is the BEST primary category for it.

Rules:
- Choose exactly one slug from the set above, or "none" if the signals are too
  thin to decide.
- Judge by what the business primarily IS, not incidental attributes.
- When the current assignment is defensible, return it rather than inventing a
  change.

Calibrate ``confidence`` to how clearly the signals point to ONE category. Use
the full 0.0-1.0 range and grade honestly — do NOT default to a single value
like 0.9 for every answer:
- 0.95-1.0  unambiguous: the primary type maps to exactly one slug (e.g.
            "car_dealer" -> auto-rv-fuel, "dentist" -> health-wellness-care),
            no plausible alternative.
- 0.80-0.94 strong, but one defensible alternative exists.
- 0.60-0.79 genuinely fits two categories; you picked the better one.
- below 0.60 thin or conflicting signals — prefer "none" over a weak guess.
Reserve 0.9+ for clear-cut cases only.

Respond with a JSON object only:
{{"correct_primary": "<slug-or-none>", "confidence": <0.0-1.0>, "reason": "<short>"}}
where confidence is how sure you are of correct_primary.

Rulesets:
{rulesets}
"""


def build_messages(signals: ProviderSignals, rulesets: dict[str, str]) -> list[dict[str, str]]:
    system = _SYSTEM_PREAMBLE.format(
        slugs=", ".join(PRIMARY_CATEGORY_SLUGS),
        rulesets=rulesets_block(rulesets),
    )
    user = "Business signals:\n" + json.dumps(signals.as_payload(), ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_verdict(raw: str) -> Verdict:
    """Parse a model JSON response into a Verdict. Tolerant: bad data -> null."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return Verdict(primary=None, confidence=0.0, reason="unparseable")
    primary = data.get("correct_primary")
    primary = str(primary).strip().lower() if primary is not None else None
    if primary not in _VALID_PRIMARIES:
        primary = None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get("reason", ""))[:280]
    return Verdict(primary=primary, confidence=confidence, reason=reason)


# A classifier maps signals -> Verdict. The default hits gpt-4o-mini; tests inject
# a deterministic stand-in so they never touch the network.
Classifier = Callable[[ProviderSignals], Verdict]


def make_openai_classifier(rulesets: dict[str, str], *, model: str | None = None) -> Classifier:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key or OpenAI is None:
        raise RuntimeError(
            "OPENAI_API_KEY not set (or openai not installed); cannot run the live "
            "classifier. Use --limit with a key, or inject a classifier in tests."
        )
    chosen = model or (os.getenv("OPENAI_MODEL") or "").strip() or DEFAULT_MODEL
    client = OpenAI(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)

    def _classify(signals: ProviderSignals) -> Verdict:
        try:
            completion = client.chat.completions.create(
                model=chosen,
                messages=build_messages(signals, rulesets),
                response_format={"type": "json_object"},
                temperature=0.0,
            )
        except Exception:
            logger.exception("category_patrol: OpenAI call failed for %s", signals.id)
            return Verdict(primary=None, confidence=0.0, reason="api-error")
        choice = completion.choices[0] if completion.choices else None
        raw = (choice.message.content or "").strip() if choice and choice.message else ""
        return parse_verdict(raw)

    return _classify


# ---------------------------------------------------------------------------
# Decision logic (pure)
# ---------------------------------------------------------------------------


def evaluate(
    signals: ProviderSignals,
    verdict: Verdict,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> FlagDecision:
    """Flag when the classifier confidently names a DIFFERENT primary.

    No flag when: the verdict is null/uncertain, it agrees with the current
    assignment, or confidence is below threshold. Pure -- no DB, no clock.
    """
    flag = (
        verdict.primary is not None
        and verdict.primary != (signals.current_primary or None)
        and verdict.confidence >= threshold
    )
    return FlagDecision(signals=signals, verdict=verdict, flag=flag)


# ---------------------------------------------------------------------------
# Catalog scan
# ---------------------------------------------------------------------------


@dataclass
class PatrolRun:
    scanned: int = 0
    flagged: list[FlagDecision] = field(default_factory=list)


def load_signals(db: Session, *, limit: int | None = None) -> list[ProviderSignals]:
    """Providers that already carry a primary_category (we audit assignments;
    NULL categories are the uncategorized-export script's job)."""
    stmt = select(Provider).where(Provider.primary_category.is_not(None))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [ProviderSignals.from_provider(p) for p in db.scalars(stmt).all()]


def patrol(
    signals_list: list[ProviderSignals],
    classifier: Classifier,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> PatrolRun:
    run = PatrolRun()
    for sig in signals_list:
        run.scanned += 1
        decision = evaluate(sig, classifier(sig), threshold=threshold)
        if decision.flag:
            run.flagged.append(decision)
    return run


def apply_flags(db: Session, decisions: list[FlagDecision], *, now: datetime) -> int:
    """Write category_confidence + category_flagged_at for flagged rows. Returns
    the number of rows updated. Only SETS flags; clearing/resolution is the
    admin surface's job."""
    written = 0
    for d in decisions:
        prov = db.get(Provider, d.signals.id)
        if prov is None:
            continue
        prov.category_confidence = round(d.verdict.confidence, 4)
        prov.category_flagged_at = now
        written += 1
    db.commit()
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(run: PatrolRun, *, applied: bool, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "scanned": run.scanned,
                    "flagged": len(run.flagged),
                    "applied": applied,
                    "items": [
                        {
                            "id": d.signals.id,
                            "name": d.signals.name,
                            "current_primary": d.signals.current_primary,
                            "suggested_primary": d.verdict.primary,
                            "confidence": round(d.verdict.confidence, 4),
                            "reason": d.verdict.reason,
                        }
                        for d in run.flagged
                    ],
                },
                indent=2,
            )
        )
        return
    mode = "APPLIED" if applied else "DRY RUN (no writes)"
    print(f"Category patrol - {mode}")
    print(f"  scanned: {run.scanned}")
    print(f"  flagged: {len(run.flagged)}")
    for d in run.flagged[:25]:
        print(
            f"    [{d.verdict.confidence:.2f}] {d.signals.name}: "
            f"{d.signals.current_primary} -> {d.verdict.primary}  ({d.verdict.reason})"
        )
    if len(run.flagged) > 25:
        print(f"    ... and {len(run.flagged) - 25} more")
    if not applied and run.flagged:
        print("  (dry run) re-run with --apply to write flags, after approval.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Flag likely-miscategorized providers")
    ap.add_argument("--apply", action="store_true", help="WRITE flags (default: dry run)")
    ap.add_argument("--limit", type=int, default=None, help="Cap providers scanned")
    ap.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Min confidence to flag (default {DEFAULT_THRESHOLD})",
    )
    ap.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    rulesets = load_rulesets()
    if not rulesets:
        logger.warning("category_patrol: no rulesets found in %s", RULESETS_DIR)

    try:
        classifier = make_openai_classifier(rulesets)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        signals_list = load_signals(db, limit=args.limit)
        run = patrol(signals_list, classifier, threshold=args.threshold)
        applied = False
        if args.apply:
            now = datetime.now(UTC)
            written = apply_flags(db, run.flagged, now=now)
            applied = True
            logger.info("category_patrol: wrote %d flags", written)

    _print_report(run, applied=applied, as_json=args.as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
