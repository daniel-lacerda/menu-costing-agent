"""Prices follow the statement: she receives 0.90 P, so P must be at least CMV / 0.90."""

from __future__ import annotations

import pytest
from menu_costing.domain.models import PantryItem, Recipe
from menu_costing.domain.pricing import cost_breakdown, price_floor, price_for_margin
from menu_costing.domain.recipes import check_ingredients
from menu_costing.domain.units import ConversionTable


def test_floor_price_leaves_zero_profit_after_the_fee() -> None:
    floor = price_floor(9.0, 0.10)
    assert floor == pytest.approx(10.0)
    assert 0.90 * floor - 9.0 == pytest.approx(0.0)


@pytest.mark.parametrize("margin", [0.20, 0.35, 0.50])
def test_margin_is_profit_over_what_she_receives(margin: float) -> None:
    scenario = price_for_margin(9.0, 0.10, margin)
    assert scenario.net_brl == pytest.approx(0.90 * scenario.price_brl)
    assert scenario.profit_brl == pytest.approx(scenario.net_brl - 9.0)
    assert scenario.profit_brl / scenario.net_brl == pytest.approx(margin)


def test_cost_splits_stock_at_pantry_cost_and_shortfall_at_purchase_cost(
    pantry: list[PantryItem], table: ConversionTable, stroganoff: Recipe
) -> None:
    recipe = stroganoff
    breakdown = cost_breakdown(recipe, check_ingredients(recipe, pantry, table), pantry, table)
    alcatra = [line for line in breakdown.lines if line.ingredient == "alcatra"]
    assert [line.source for line in alcatra] == ["despensa", "compra"]
    assert alcatra[0].cost_brl == pytest.approx(34.00)
    assert alcatra[1].cost_brl == pytest.approx(200 * 8.50 / 200)
    assert breakdown.cmv_portion_brl == pytest.approx(breakdown.cmv_batch_brl / 4)
