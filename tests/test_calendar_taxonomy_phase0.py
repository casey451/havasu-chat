"""Calendar taxonomy rebuild — Phase 0 (2026-06-25): bucket labels + the new
``learn`` (Classes & Workshops) top-level bucket.

Phase 0 is a pure display change: relabel the existing buckets and add one new
top-level bucket. ``funzone`` (Bowling, Billiards & Family Fun) stays a
render-time SECTION under Things to Do per Casey's call, so it is NOT a
top-level bucket. Routing of rows into ``learn`` is wired in a later phase
(ingest stamps the non-fitness activity tags), so this file only covers the
display surface and the GROUP_DEFS/GROUP_NOUNS invariant.
"""

from __future__ import annotations

from app.home.event_buckets import GROUP_DEFS, GROUP_NOUNS


def test_relabeled_bucket_labels() -> None:
    labels = {key: label for key, label, _icon in GROUP_DEFS}
    assert labels["events"] == "Things to Do"
    assert labels["music"] == "Music & Nightlife"
    assert labels["classes"] == "Fitness & Sports"


def test_learn_bucket_present() -> None:
    keys = [k for k, _label, _icon in GROUP_DEFS]
    assert "learn" in keys
    labels = {key: label for key, label, _icon in GROUP_DEFS}
    assert labels["learn"] == "Classes & Workshops"


def test_funzone_is_not_a_toplevel_bucket() -> None:
    # Casey 2026-06-25: the bowling/billiards/family-fun cluster is a section
    # under Things to Do, not its own top-level bucket.
    keys = {k for k, _label, _icon in GROUP_DEFS}
    assert "funzone" not in keys


def test_learn_has_rollup_nouns() -> None:
    assert "learn" in GROUP_NOUNS
    singular, plural = GROUP_NOUNS["learn"]
    assert singular and plural


def test_every_bucket_has_rollup_nouns() -> None:
    # rollup_summary() / day_groups() index GROUP_NOUNS by every GROUP_DEFS key;
    # a missing entry would KeyError at render time.
    keys = {k for k, _label, _icon in GROUP_DEFS}
    assert keys <= set(GROUP_NOUNS)
