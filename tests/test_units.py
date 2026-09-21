"""Every unit string in the spreadsheet must parse, and recipe measures must convert or refuse."""

from __future__ import annotations

import pytest
from menu_costing.domain.errors import DomainError
from menu_costing.domain.units import ConversionTable, convert_measure, parse_pantry_unit


@pytest.mark.parametrize(
    ("text", "base", "per_unit"),
    [
        ("kg", "g", 1000),
        ("L", "ml", 1000),
        ("un", "un", 1),
        ("un 500g", "g", 500),
        ("un 400g", "g", 400),
        ("un 500ml", "ml", 500),
        ("un 100ml", "ml", 100),
        ("balde 2kg", "g", 2000),
    ],
)
def test_parse_every_pantry_unit_in_the_spreadsheet(text: str, base: str, per_unit: float) -> None:
    unit = parse_pantry_unit(text)
    assert (unit.base, unit.per_unit) == (base, per_unit)


def test_unknown_pantry_unit_is_a_data_error() -> None:
    with pytest.raises(ValueError):
        parse_pantry_unit("saco")


@pytest.mark.parametrize(
    ("quantity", "unit", "base", "item", "expected", "expected_unit"),
    [
        (3, "dentes", "g", "Alho", 15, "g"),
        (2, "colheres de sopa", "ml", "Azeite de oliva extra virgem", 30, "ml"),
        (1, "xícara", "g", "Arroz branco tipo 1", 204, "g"),
        (200, "g", "ml", "Leite integral", 200 / 1.03, "ml"),
        (0.5, "kg", "g", "Batata", 500, "g"),
        (2, "un", "un", "Ovos", 2, "un"),
    ],
)
def test_recipe_measures_convert_to_the_pantry_base_unit(
    table: ConversionTable,
    quantity: float,
    unit: str,
    base: str,
    item: str,
    expected: float,
    expected_unit: str,
) -> None:
    result = convert_measure(quantity, unit, base, item, table)  # type: ignore[arg-type]
    assert result.unit == expected_unit
    assert result.quantity == pytest.approx(expected)


def test_conversion_note_shows_the_cook_what_was_assumed(table: ConversionTable) -> None:
    assert convert_measure(3, "dentes", "g", "Alho", table).note == "3 dentes = 15 g"
    assert convert_measure(600, "g", "g", "Peito de frango", table).note == "600 g"


def test_mass_for_a_counted_item_without_package_size_is_refused(table: ConversionTable) -> None:
    with pytest.raises(DomainError, match="pantry_amend"):
        convert_measure(50, "g", "un", "Cobertura de chocolate", table)


def test_unknown_recipe_unit_lists_the_accepted_ones(table: ConversionTable) -> None:
    with pytest.raises(DomainError, match="colher de sopa"):
        convert_measure(1, "lata", "g", "Tomate", table)
