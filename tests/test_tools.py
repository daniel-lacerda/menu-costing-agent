"""The tool boundary: provider-safe schemas and the refusals the statement requires."""

from __future__ import annotations

import json
from typing import Any

import pytest
from menu_costing.tools import Tool


def call(
    tools: dict[str, Tool], name: str, args: dict[str, Any], session: str = "s1"
) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(tools[name].handler(args, session_id=session))
    return result


KITCHEN = {
    "burners": 4,
    "oven": False,
    "pressure_cooker": True,
    "air_fryer": False,
    "blender": True,
    "fuel": "gas",
    "fridge_space": "medio",
    "time_per_batch": "mais_de_2h",
}

RECIPE = {
    "title": "Frango com batata",
    "url": "https://example.org/frango",
    "yield_portions": 4,
    "ingredients": [
        {"name": "peito de frango", "quantity": 600, "unit": "g", "pantry_item": "Peito de frango"},
        {"name": "creme de leite", "quantity": 200, "unit": "g", "pantry_item": None},
    ],
    "equipment_required": ["fogao"],
}

PURCHASE = {"ingredient": "creme de leite", "quantity": 200, "unit": "g", "price_brl": 4.5}


def test_schemas_carry_no_references(tools: dict[str, Tool]) -> None:
    for tool in tools.values():
        text = json.dumps(tool.schema)
        assert "$ref" not in text and "$defs" not in text, tool.name
        assert tool.schema["parameters"]["additionalProperties"] is False


def test_invalid_arguments_come_back_as_a_result_not_an_exception(tools: dict[str, Tool]) -> None:
    result = call(tools, "recipe_register", {"title": "sem url"})
    assert result["error"] == "Argumentos inválidos."


def test_pricing_is_refused_until_the_cook_accepts(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    assert "não foi aceito" in call(tools, "dish_price", {"recipe_id": "r1"})["error"]


def test_acceptance_is_refused_while_the_gate_is_open(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    result = call(tools, "recipe_update", {"recipe_id": "r1", "liked": True, "accepted": True})
    assert "creme de leite" in result["error"]


def test_unconfirmed_purchase_prices_are_refused(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    result = call(
        tools,
        "recipe_update",
        {"recipe_id": "r1", "purchases": [{**PURCHASE, "confirmed_by_cook": False}]},
    )
    assert "confirmado" in result["error"]


def test_purchases_beyond_the_budget_block_acceptance(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    expensive = {**PURCHASE, "price_brl": 95.0, "confirmed_by_cook": True}
    result = call(
        tools,
        "recipe_update",
        {"recipe_id": "r1", "liked": True, "purchases": [expensive], "accepted": True},
    )
    assert "orçamento" in result["error"]


def test_accepted_dish_is_priced_and_the_budget_is_committed(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    confirmed = {**PURCHASE, "confirmed_by_cook": True}
    accepted = call(
        tools,
        "recipe_update",
        {"recipe_id": "r1", "liked": True, "purchases": [confirmed], "accepted": True},
    )
    assert accepted["accepted"] is True
    assert accepted["budget"]["remaining_brl"] == pytest.approx(80.0 - 4.5)
    priced = call(tools, "dish_price", {"recipe_id": "r1", "chosen_price_brl": 9.9})
    cmv = (600 * 28.00 / 2000 + 4.5) / 4
    assert priced["cost"]["cmv_portion_brl"] == pytest.approx(cmv, abs=1e-4)
    assert priced["pricing"]["floor_price_brl"] == pytest.approx(cmv / 0.9, abs=1e-4)
    assert priced["chosen_price_brl"] == 9.9


def test_the_menu_and_the_kitchen_outlive_the_session(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN, session="monday")
    call(tools, "recipe_register", RECIPE, session="monday")
    assert call(tools, "kitchen_profile", {}, session="tuesday")["missing"] == []
    later = call(tools, "recipe_update", {"recipe_id": "r1", "liked": True}, session="tuesday")
    assert later["recipe_id"] == "r1"
    assert later["budget"]["total_brl"] == 80.0
