"""The acceptance gate is the guarantee that she never buys and then finds out she cannot cook."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from menu_costing.domain.models import (
    IngredientInput,
    KitchenProfile,
    PantryItem,
    Recipe,
    RecipeInput,
)
from menu_costing.domain.recipes import check_ingredients, evaluate_gate
from menu_costing.domain.units import ConversionTable


def test_ingredient_status_is_have_short_or_missing(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    checks = {c.name: c for c in check_ingredients(stroganoff, pantry, table)}
    assert checks["cebola"].status == "have"
    assert (checks["alcatra"].status, checks["alcatra"].shortfall) == ("short", 200)
    assert (checks["creme de leite"].status, checks["creme de leite"].stock) == ("missing", None)


def test_gate_is_ready_only_when_everything_is_confirmed(
    pantry: list[PantryItem],
    table: ConversionTable,
    stroganoff: Recipe,
    complete_kitchen: KitchenProfile,
) -> None:
    checks = check_ingredients(stroganoff, pantry, table)
    assert evaluate_gate(stroganoff, complete_kitchen, checks, table).ready


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        (lambda r, k: setattr(r, "liked", None), "liked_unknown"),
        (lambda r, k: setattr(r, "liked", False), "not_liked"),
        (lambda r, k: setattr(k, "oven", None), "kitchen_unknown:oven"),
        (lambda r, k: setattr(r, "equipment_required", ["forno"]), "equipment_missing:forno"),
        (lambda r, k: setattr(r, "burners_needed", 5), "burners_insufficient"),
        (
            lambda r, k: setattr(r, "techniques_required", ["massa fresca"]),
            "technique_missing:massa fresca",
        ),
        (
            lambda r, k: setattr(r, "techniques_required", ["confeitar"]),
            "technique_unknown:confeitar",
        ),
        (lambda r, k: setattr(r, "purchases", r.purchases[1:]), "purchase_needed:alcatra"),
        (lambda r, k: setattr(r.purchases[0], "quantity", 100), "purchase_insufficient:alcatra"),
    ],
)
def test_each_unmet_condition_names_its_blocker(
    pantry: list[PantryItem],
    table: ConversionTable,
    stroganoff: Recipe,
    complete_kitchen: KitchenProfile,
    change: Callable[[Recipe, KitchenProfile], None],
    blocker: str,
) -> None:
    recipe, kitchen = stroganoff, complete_kitchen
    change(recipe, kitchen)
    checks = check_ingredients(recipe, pantry, table)
    report = evaluate_gate(recipe, kitchen, checks, table)
    assert not report.ready
    assert blocker in {b.code for b in report.blockers}


def test_per_portion_items_scale_with_the_yield(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    stroganoff.per_portion_items = [
        IngredientInput(name="arroz", quantity=150, unit="g", pantry_item="Arroz branco tipo 1"),
        IngredientInput(name="embalagem", quantity=1, unit="un", pantry_item=None),
    ]
    checks = {c.name: c for c in check_ingredients(stroganoff, pantry, table)}
    assert (checks["arroz"].scope, checks["arroz"].needed) == ("porcao", 600)
    assert checks["arroz"].conversion == "150 g por porção x 4 porções: 600 g"
    assert (checks["embalagem"].status, checks["embalagem"].shortfall) == ("missing", 4)


def test_a_pantry_name_the_model_invented_is_rejected(
    pantry: list[PantryItem], table: ConversionTable
) -> None:
    recipe = RecipeInput(
        title="x",
        url="https://example.org/x",
        yield_portions=1,
        ingredients=[
            IngredientInput(name="creme", quantity=1, unit="un", pantry_item="Creme de leite")
        ],
    )
    with pytest.raises(Exception, match="nome exato"):
        check_ingredients(recipe, pantry, table)
