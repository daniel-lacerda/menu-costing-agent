"""The unit cost is the statement's definition: total paid divided by quantity bought."""

from __future__ import annotations

from pathlib import Path

import pytest
from menu_costing.domain.models import PantryAmendment, PantryItem
from menu_costing.domain.pantry import find_item, load_pantry


def test_both_sheets_join_completely(pantry: list[PantryItem]) -> None:
    assert len(pantry) == 37
    assert [item.row for item in pantry] == list(range(2, 39))


@pytest.mark.parametrize(
    ("name", "unit_cost", "stock_base"),
    [
        ("Arroz branco tipo 1", 24.90 / 5000, 5000),
        ("Ovos", 24.00 / 30, 30),
        ("Alcaparras", 82.00 / 2000, 2000),
        ("Azeite de oliva extra virgem", 30.99 / 500, 500),
    ],
)
def test_unit_cost_and_stock_are_expressed_in_base_units(
    pantry: list[PantryItem], name: str, unit_cost: float, stock_base: float
) -> None:
    item = find_item(name, pantry)
    assert item is not None
    assert item.unit_cost_brl == pytest.approx(unit_cost)
    assert item.stock_base == stock_base


def test_only_counted_items_have_unknown_package_size(pantry: list[PantryItem]) -> None:
    unknown = {item.name for item in pantry if item.package_size_unknown}
    assert unknown == {"Ovos", "Cobertura de chocolate"}


def test_an_amendment_from_the_cook_turns_a_counted_item_into_grams(pantry_path: Path) -> None:
    amendment = PantryAmendment(
        name="cobertura de chocolate", package_size=1000, package_unit="g", stated_by_cook=True
    )
    item = find_item("Cobertura de chocolate", load_pantry(pantry_path, [amendment]))
    assert item is not None
    assert (item.base_unit, item.stock_base) == ("g", 1000)
    assert item.unit_cost_brl == pytest.approx(79.90 / 1000)
