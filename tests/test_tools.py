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
    "equipment": {"forno": False, "panela de pressão": True, "liquidificador": True},
    "time_per_batch": "mais de 2 horas",
    "notes": "fogão a gás",
}

RECIPE = {
    "title": "Frango com batata",
    "url": "https://example.org/frango",
    "yield_portions": 4,
    "ingredients": [
        {"name": "peito de frango", "quantity": 600, "unit": "g", "pantry_item": "Peito de frango"},
        {"name": "creme de leite", "quantity": 200, "unit": "g", "pantry_item": None},
    ],
    "techniques_required": ["refogar"],
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
    assert "refogar" in result["error"]


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
        {
            "recipe_id": "r1",
            "liked": True,
            "techniques": {"refogar": True},
            "purchases": [expensive],
            "accepted": True,
        },
    )
    assert "orçamento" in result["error"]


def test_accepted_dish_is_priced_and_the_budget_is_committed(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    confirmed = {**PURCHASE, "confirmed_by_cook": True}
    accepted = call(
        tools,
        "recipe_update",
        {
            "recipe_id": "r1",
            "liked": True,
            "techniques": {"refogar": True},
            "purchases": [confirmed],
            "accepted": True,
        },
    )
    assert accepted["accepted"] is True
    assert accepted["budget"]["remaining_brl"] == pytest.approx(80.0 - 4.5)
    priced = call(tools, "dish_price", {"recipe_id": "r1", "chosen_price_brl": 9.9})
    cmv = (600 * 28.00 / 2000 + 4.5) / 4
    assert priced["cost"]["cmv_portion_brl"] == pytest.approx(cmv, abs=0.01)
    assert priced["pricing"]["floor_price_brl"] == pytest.approx(cmv / 0.9, abs=0.01)
    assert priced["chosen_price_brl"] == 9.9


def test_a_price_below_the_floor_is_refused_and_nothing_is_recorded(
    tools: dict[str, Tool],
) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    call(
        tools,
        "recipe_update",
        {
            "recipe_id": "r1",
            "liked": True,
            "techniques": {"refogar": True},
            "purchases": [{**PURCHASE, "confirmed_by_cook": True}],
            "accepted": True,
        },
    )
    refused = call(tools, "dish_price", {"recipe_id": "r1", "chosen_price_brl": 1.0})
    assert "abaixo do preço mínimo" in refused["error"]
    assert call(tools, "dish_price", {"recipe_id": "r1"})["chosen_price_brl"] is None


def test_re_registering_an_accepted_dish_keeps_the_acceptance_and_the_price(
    tools: dict[str, Tool],
) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    call(tools, "recipe_register", RECIPE)
    call(
        tools,
        "recipe_update",
        {
            "recipe_id": "r1",
            "liked": True,
            "techniques": {"refogar": True},
            "purchases": [{**PURCHASE, "confirmed_by_cook": True}],
            "accepted": True,
        },
    )
    call(tools, "dish_price", {"recipe_id": "r1", "chosen_price_brl": 9.9})
    again = call(tools, "recipe_register", RECIPE)
    assert again["gate"]["ready"] is True
    assert call(tools, "dish_price", {"recipe_id": "r1"})["chosen_price_brl"] == 9.9
    changed = {**RECIPE, "yield_portions": 8}
    assert "já foi aceito" in call(tools, "recipe_register", changed)["error"]


def test_the_budget_is_shared_by_every_accepted_dish(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN)
    first = {**PURCHASE, "price_brl": 50.0, "confirmed_by_cook": True}
    call(tools, "recipe_register", RECIPE)
    call(
        tools,
        "recipe_update",
        {
            "recipe_id": "r1",
            "liked": True,
            "techniques": {"refogar": True},
            "purchases": [first],
            "accepted": True,
        },
    )
    call(tools, "recipe_register", {**RECIPE, "url": "https://example.org/outro"})
    second = {**PURCHASE, "price_brl": 35.0, "confirmed_by_cook": True}
    result = call(
        tools,
        "recipe_update",
        {"recipe_id": "r2", "liked": True, "purchases": [second], "accepted": True},
    )
    assert "orçamento restante é R$ 30.00" in result["error"]


def test_the_kitchen_carries_the_time_it_was_last_updated(tools: dict[str, Tool]) -> None:
    assert "updated_at" not in call(tools, "kitchen_profile", {})["profile"]
    written = call(tools, "kitchen_profile", {"burners": 4})["profile"]["updated_at"]
    assert call(tools, "kitchen_profile", {})["profile"]["updated_at"] == written


def test_kitchen_facts_accumulate_across_calls(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", {"equipment": {"forno": False}})
    profile = call(tools, "kitchen_profile", {"equipment": {"air fryer": True}})["profile"]
    assert profile["equipment"] == {"forno": False, "air fryer": True}


def test_the_menu_and_the_kitchen_outlive_the_session(tools: dict[str, Tool]) -> None:
    call(tools, "kitchen_profile", KITCHEN, session="monday")
    call(tools, "recipe_register", RECIPE, session="monday")
    assert call(tools, "kitchen_profile", {}, session="tuesday")["missing"] == []
    later = call(tools, "recipe_update", {"recipe_id": "r1", "liked": True}, session="tuesday")
    assert later["recipe_id"] == "r1"
    assert later["budget"]["total_brl"] == 80.0
