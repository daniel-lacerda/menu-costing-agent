"""The acceptance gate is the guarantee that she never buys and then finds out she cannot cook."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from menu_costing.domain.errors import DomainError
from menu_costing.domain.models import (
    IngredientInput,
    KitchenProfile,
    PantryItem,
    PurchaseInput,
    Recipe,
    RecipeInput,
)
from menu_costing.domain.recipes import (
    carry_purchases,
    check_ingredients,
    evaluate_gate,
    plan_purchases,
)
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
        (lambda r, k: setattr(k, "time_per_batch", None), "kitchen_unknown:time_per_batch"),
        (lambda r, k: setattr(r, "equipment_required", ["forno"]), "equipment_missing:forno"),
        (
            lambda r, k: setattr(r, "equipment_required", ["batedeira"]),
            "equipment_unknown:batedeira",
        ),
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


def test_a_dish_waits_only_for_what_it_uses(
    pantry: list[PantryItem],
    table: ConversionTable,
    stroganoff: Recipe,
    complete_kitchen: KitchenProfile,
) -> None:
    complete_kitchen.equipment = {}
    checks = check_ingredients(stroganoff, pantry, table)
    assert evaluate_gate(stroganoff, complete_kitchen, checks, table).ready
    assert complete_kitchen.missing() == []


def test_equipment_and_techniques_match_however_she_spelled_them(
    pantry: list[PantryItem],
    table: ConversionTable,
    stroganoff: Recipe,
    complete_kitchen: KitchenProfile,
) -> None:
    stroganoff.equipment_required = ["Panela de Pressao"]
    stroganoff.techniques_required = ["REFOGAR"]
    checks = check_ingredients(stroganoff, pantry, table)
    assert evaluate_gate(stroganoff, complete_kitchen, checks, table).ready


def test_the_stove_is_declared_by_burners_not_as_equipment() -> None:
    with pytest.raises(ValueError, match="burners_needed"):
        RecipeInput(
            title="x",
            url="https://example.org/x",
            yield_portions=2,
            ingredients=[IngredientInput(name="arroz", quantity=200, unit="g")],
            equipment_required=["fogão"],
            techniques_required=["cozinhar"],
        )


def test_an_unknown_technique_blocker_names_the_ones_already_confirmed(
    pantry: list[PantryItem],
    table: ConversionTable,
    stroganoff: Recipe,
    complete_kitchen: KitchenProfile,
) -> None:
    stroganoff.techniques_required = ["Refogar", "assar"]
    checks = check_ingredients(stroganoff, pantry, table)
    codes = {
        b.code: b.message
        for b in evaluate_gate(stroganoff, complete_kitchen, checks, table).blockers
    }
    assert "technique_unknown:Refogar" not in codes
    assert "Já confirmado por ela: refogar" in codes["technique_unknown:assar"]


def test_the_same_name_cannot_appear_twice_in_a_recipe() -> None:
    with pytest.raises(ValueError, match="repetido"):
        RecipeInput(
            title="x",
            url="https://example.org/x",
            yield_portions=2,
            ingredients=[IngredientInput(name="arroz", quantity=200, unit="g")],
            techniques_required=["cozinhar"],
            per_portion_items=[IngredientInput(name="Arroz", quantity=100, unit="g")],
        )


def test_purchases_are_whole_packages_covering_the_shortfall(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    checks = check_ingredients(stroganoff, pantry, table)
    small_box = PurchaseInput(
        ingredient="creme de leite", quantity=150, unit="g", price_brl=3.5, confirmed_by_cook=True
    )
    bottle = PurchaseInput(
        ingredient="alcatra", quantity=0.5, unit="kg", price_brl=21.0, confirmed_by_cook=True
    )
    planned = {p.ingredient: p for p in plan_purchases([small_box, bottle], checks, table)}
    assert (planned["creme de leite"].packages, planned["creme de leite"].total_brl) == (2, 7.0)
    assert planned["alcatra"].packages == 1


def test_a_purchase_for_something_she_already_has_is_refused(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    checks = check_ingredients(stroganoff, pantry, table)
    onions = PurchaseInput(
        ingredient="cebola", quantity=1, unit="kg", price_brl=6.0, confirmed_by_cook=True
    )
    with pytest.raises(DomainError, match="Não falta 'cebola'"):
        plan_purchases([onions], checks, table)


def test_re_registration_keeps_only_the_purchases_still_needed(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    smaller = stroganoff.model_copy(deep=True)
    smaller.ingredients[0].quantity = 0.5  # the pantry covers half a kilo of beef
    checks = check_ingredients(smaller, pantry, table)
    carried = carry_purchases(stroganoff.purchases, checks, table)
    assert [p.ingredient for p in carried] == ["creme de leite"]


def test_a_purchase_in_another_measure_of_the_same_kind_is_converted(
    pantry: list[PantryItem], table: ConversionTable
) -> None:
    recipe = RecipeInput(
        title="x",
        url="https://example.org/x",
        yield_portions=1,
        ingredients=[IngredientInput(name="vinho", quantity=0.5, unit="xícara de chá")],
        techniques_required=["refogar"],
    )
    checks = check_ingredients(recipe, pantry, table)
    bottle = PurchaseInput(
        ingredient="vinho", quantity=750, unit="ml", price_brl=25.0, confirmed_by_cook=True
    )
    assert plan_purchases([bottle], checks, table)[0].packages == 1
    with pytest.raises(DomainError, match="tipos diferentes"):
        plan_purchases(
            [
                PurchaseInput(
                    ingredient="vinho", quantity=1, unit="kg", price_brl=1, confirmed_by_cook=True
                )
            ],
            checks,
            table,
        )


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
        techniques_required=["refogar"],
    )
    with pytest.raises(Exception, match="nome exato"):
        check_ingredients(recipe, pantry, table)
