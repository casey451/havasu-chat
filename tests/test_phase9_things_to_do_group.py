"""Phase 9b — things-to-do-group registry + bundle."""

from __future__ import annotations

from app.groups import themed_groups as tg


def test_things_to_do_group_registered() -> None:
    assert "things-to-do-group" in tg.THEMED_GROUPS
    assert tg.THEMED_GROUPS["things-to-do-group"] == [
        "events",
        "outdoors-parks-trails",
        "classes-sports-recreation",
    ]


def test_things_to_do_labels() -> None:
    assert tg.group_label("things-to-do-group") == "Things to Do"
    assert "Events" in tg.group_one_liner("things-to-do-group")
    assert tg.group_accent("things-to-do-group") == "warm"


def test_resolve_map_categories() -> None:
    cats = tg.resolve_map_categories("things-to-do-group")
    assert cats is not None
    assert "events" in cats
