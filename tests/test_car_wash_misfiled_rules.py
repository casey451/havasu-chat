"""T3.2 — detailing shops mis-shelved under car-wash route to auto-detailing."""

from __future__ import annotations

from app.categories.car_wash_misfiled_rules import classify_car_wash_misfiled_leaf


def test_detailers_route_to_auto_detailing() -> None:
    for name in (
        "Accelerated Detail",
        "Tapped Out Mobile Detailing",
        "Detail Specialties & Ceramic Coating",
        "Perfection 2 Detail & Ceramic Coating",
    ):
        assert classify_car_wash_misfiled_leaf(name) == "auto-detailing", name


def test_real_car_wash_is_left_untouched() -> None:
    for name in ("Quick Quack Car Wash", "Blue Wave Express Wash", "", None):
        assert classify_car_wash_misfiled_leaf(name) is None, name
