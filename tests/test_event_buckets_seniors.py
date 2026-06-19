"""The Seniors bucket is registered in the shared bucket vocabulary."""

from app.home.event_buckets import GROUP_DEFS, GROUP_NOUNS


def test_seniors_bucket_present_and_ordered():
    keys = [k for k, _label, _icon in GROUP_DEFS]
    assert "seniors" in keys
    # Seniors sits right after the Kids & Family overlay.
    assert keys.index("seniors") == keys.index("family") + 1


def test_seniors_has_rollup_nouns():
    assert "seniors" in GROUP_NOUNS
    singular, plural = GROUP_NOUNS["seniors"]
    assert singular and plural
