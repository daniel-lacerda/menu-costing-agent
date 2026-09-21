"""Cost of goods sold and delivery prices. Pure arithmetic, no I/O."""

from __future__ import annotations

from .errors import DomainError
from .models import (
    CostBreakdown,
    CostLine,
    IngredientCheck,
    PantryItem,
    PriceScenario,
    Pricing,
    Purchase,
    Recipe,
)
from .pantry import find_item
from .recipes import package_in, purchase_for
from .units import ConversionTable


def cost_breakdown(
    recipe: Recipe,
    checks: list[IngredientCheck],
    pantry: list[PantryItem],
    table: ConversionTable,
) -> CostBreakdown:
    lines: list[CostLine] = []
    for check in checks:
        purchase = purchase_for(check.name, recipe.purchases)
        if check.status == "missing":
            if purchase is None:
                raise DomainError(f"Sem compra registrada para {check.name}.")
            lines.append(_purchase_line(check, purchase, check.needed, check.unit, table))
            continue
        item = find_item(check.pantry_item or "", pantry)
        if item is None:
            raise DomainError(f"{check.pantry_item!r} não está na despensa.")
        from_stock = min(check.needed, item.stock_base)
        lines.append(
            CostLine(
                ingredient=check.name,
                source="despensa",
                quantity=from_stock,
                unit=item.base_unit,
                unit_cost_brl=item.unit_cost_brl,
                cost_brl=from_stock * item.unit_cost_brl,
                reference=f"planilha linha {item.row}: {item.name}",
            )
        )
        if check.shortfall > 0:
            if purchase is None:
                raise DomainError(f"Sem compra registrada para completar {check.name}.")
            lines.append(_purchase_line(check, purchase, check.shortfall, item.base_unit, table))
    cmv_batch = sum(line.cost_brl for line in lines)
    return CostBreakdown(
        yield_portions=recipe.yield_portions,
        lines=lines,
        cmv_batch_brl=cmv_batch,
        cmv_portion_brl=cmv_batch / recipe.yield_portions,
        purchases_brl=sum(p.total_brl for p in recipe.purchases),
    )


def price_floor(cmv_brl: float, platform_fee: float) -> float:
    return cmv_brl / (1 - platform_fee)


def price_for_margin(cmv_brl: float, platform_fee: float, margin: float) -> PriceScenario:
    """Price such that profit is `margin` of what the cook receives after the platform fee."""
    if not 0 <= margin < 1:
        raise DomainError("A margem deve estar entre 0 e 1.")
    price = cmv_brl / ((1 - platform_fee) * (1 - margin))
    fee = price * platform_fee
    net = price - fee
    return PriceScenario(
        margin=margin, price_brl=price, fee_brl=fee, net_brl=net, profit_brl=net - cmv_brl
    )


def pricing(cmv_portion_brl: float, platform_fee: float, margins: list[float]) -> Pricing:
    return Pricing(
        platform_fee=platform_fee,
        cmv_portion_brl=cmv_portion_brl,
        floor_price_brl=price_floor(cmv_portion_brl, platform_fee),
        scenarios=[price_for_margin(cmv_portion_brl, platform_fee, m) for m in margins],
    )


def _purchase_line(
    check: IngredientCheck, purchase: Purchase, used: float, unit: str, table: ConversionTable
) -> CostLine:
    unit_cost = purchase.price_brl / package_in(purchase, check, table)
    return CostLine(
        ingredient=check.name,
        source="compra",
        quantity=used,
        unit=unit,
        unit_cost_brl=unit_cost,
        cost_brl=used * unit_cost,
        reference=(
            f"compra: {purchase.packages} x {purchase.quantity:g} {purchase.unit} "
            f"a R$ {purchase.price_brl:.2f}"
        ),
    )
